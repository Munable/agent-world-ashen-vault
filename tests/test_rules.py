import unittest
from ashen_vault.content import combatant
from ashen_vault import rules


def dice(*values):
    iterator = iter(values)
    return lambda low, high: next(iterator)


class RulesTests(unittest.TestCase):
    def test_attack_one_always_misses(self):
        self.assertFalse(rules.d20(dice(1), 100, dc=1, attack=True)['success'])

    def test_attack_twenty_always_hits_and_crits(self):
        result = rules.d20(dice(20), 0, dc=100, attack=True)
        self.assertTrue(result['success']); self.assertTrue(result['critical'])

    def test_check_twenty_is_not_automatic_success(self):
        self.assertFalse(rules.d20(dice(20), 0, dc=30)['success'])

    def test_save_one_is_not_automatic_failure(self):
        self.assertTrue(rules.d20(dice(1), 12, dc=10)['success'])

    def test_advantage_takes_higher(self):
        self.assertEqual(rules.d20(dice(1, 18), 0, advantage=True)['natural'], 18)

    def test_disadvantage_takes_lower(self):
        self.assertEqual(rules.d20(dice(20, 3), 0, disadvantage=True)['natural'], 3)

    def test_opposing_sources_cancel(self):
        result = rules.d20(dice(11), 0, advantage=True, disadvantage=True)
        self.assertEqual(result['dice'], [11]); self.assertEqual(result['mode'], 'normal')

    def test_invalid_rng_output_is_rejected(self):
        for value in (0, 21, True):
            with self.assertRaises(ValueError): rules.roll(dice(value), 20)

    def test_resistance_rounds_down(self):
        self.assertEqual(rules.damage_amount(5, resistant=True), 2)

    def test_resistance_precedes_vulnerability(self):
        self.assertEqual(rules.damage_amount(5, resistant=True, vulnerable=True), 4)

    def test_reduction_precedes_resistance(self):
        self.assertEqual(rules.damage_amount(28, reduction=5, resistant=True, vulnerable=True), 22)

    def test_immunity_cancels_damage(self):
        self.assertEqual(rules.damage_amount(99, immune=True, vulnerable=True), 0)

    def test_no_negative_damage(self):
        self.assertEqual(rules.damage_amount(2, reduction=5), 0)
        with self.assertRaises(ValueError): rules.damage_amount(-1)

    def test_temporary_hp_absorbs_before_hp(self):
        actor = combatant('warden'); actor['temp_hp'] = 5
        rules.lose_hp(actor, 7)
        self.assertEqual((actor['temp_hp'], actor['hp']), (0, 9))

    def test_monster_zero_hp_dies(self):
        actor = combatant('warden'); rules.lose_hp(actor, 11)
        self.assertTrue(actor['dead'])

    def test_pc_zero_hp_unconscious_but_not_dead(self):
        actor = combatant('warden'); actor['death_saves'] = True
        rules.lose_hp(actor, 11)
        self.assertFalse(actor['dead']); self.assertIn('unconscious', actor['conditions'])

    def test_massive_damage_threshold_is_remaining_damage(self):
        actor = combatant('warden'); actor.update(hp=2, death_saves=True)
        rules.lose_hp(actor, 13)
        self.assertTrue(actor['dead'])

    def test_knockout_uses_one_hp_not_legacy_zero(self):
        actor = combatant('warden'); rules.lose_hp(actor, 20, knockout=True)
        self.assertEqual(actor['hp'], 1); self.assertFalse(actor['dead'])
        self.assertIn('unconscious', actor['conditions']); self.assertIn('prone', actor['conditions'])

    def test_critical_rolls_dice_twice_not_modifier(self):
        attacker, target = combatant('warden'), combatant('sentinel')
        attacker['position'] = [3, 2]; target['position'] = [4, 2]
        result = rules.melee_attack(attacker, target, dice(20, 2, 3))
        self.assertEqual(result['damage'], 6); self.assertEqual(result['damage_dice'], [2, 3])

    def test_miss_does_not_roll_damage(self):
        a, b = combatant('warden'), combatant('sentinel'); b['position'] = [4, 2]
        result = rules.melee_attack(a, b, dice(1))
        self.assertFalse(result['hit']); self.assertEqual(result['damage_dice'], [])

    def test_prone_attacker_has_disadvantage(self):
        a, b = combatant('warden'), combatant('sentinel'); b['position'] = [4, 2]; a['conditions'] = ['prone']
        self.assertEqual(rules.melee_attack(a, b, dice(20, 1))['attack']['mode'], 'disadvantage')

    def test_prone_target_grants_nearby_advantage(self):
        a, b = combatant('warden'), combatant('sentinel'); b['position'] = [4, 2]; b['conditions'] = ['prone']
        self.assertEqual(rules.melee_attack(a, b, dice(1, 15, 2))['attack']['mode'], 'advantage')

    def test_prone_and_dodge_cancel(self):
        a, b = combatant('warden'), combatant('sentinel'); b['position'] = [4, 2]
        b.update(conditions=['prone'], dodge=True)
        self.assertEqual(rules.melee_attack(a, b, dice(15, 2))['attack']['mode'], 'normal')

    def test_zero_speed_loses_dodge(self):
        a, b = combatant('warden'), combatant('sentinel'); b['position'] = [4, 2]; b.update(speed=0, dodge=True)
        self.assertEqual(rules.melee_attack(a, b, dice(1))['attack']['mode'], 'normal')

    def test_unconscious_melee_hit_is_critical(self):
        a, b = combatant('warden'), combatant('sentinel'); b['position'] = [4, 2]; b['conditions'] = ['unconscious', 'prone']
        result = rules.melee_attack(a, b, dice(15, 16, 2, 3))
        self.assertTrue(result['critical']); self.assertEqual(len(result['damage_dice']), 2)

    def test_healing_caps_and_does_not_stand_up(self):
        actor = combatant('warden'); rules.lose_hp(actor, 99, knockout=True)
        rules.heal(actor, 99)
        self.assertEqual(actor['hp'], 11); self.assertEqual(actor['conditions'], ['prone'])

    def test_healing_does_not_revive_dead(self):
        actor = combatant('warden'); rules.lose_hp(actor, 99)
        self.assertEqual(rules.heal(actor, 10), 0)

    def down(self):
        actor = combatant('warden'); actor['death_saves'] = True; rules.lose_hp(actor, 11)
        return actor

    def test_death_save_twenty_restores_one(self):
        actor = self.down(); rules.death_save(actor, dice(20))
        self.assertEqual(actor['hp'], 1); self.assertNotIn('unconscious', actor['conditions'])

    def test_death_save_one_counts_twice(self):
        actor = self.down(); rules.death_save(actor, dice(1))
        self.assertEqual(actor['death_failures'], 2)

    def test_three_successes_stabilize(self):
        actor = self.down()
        for _ in range(3): rules.death_save(actor, dice(10))
        self.assertTrue(actor['stable']); self.assertEqual(actor['hp'], 0)
        self.assertEqual((actor['death_successes'], actor['death_failures']), (0, 0))

    def test_three_failures_die(self):
        actor = self.down()
        for _ in range(3): rules.death_save(actor, dice(9))
        self.assertTrue(actor['dead'])

    def test_damage_at_zero_resumes_saves_and_crit_counts_twice(self):
        actor = self.down(); actor['stable'] = True
        rules.lose_hp(actor, 1, critical=True)
        self.assertFalse(actor['stable']); self.assertEqual(actor['death_failures'], 2)

    def test_zero_damage_does_not_fail_a_death_save(self):
        actor = self.down(); rules.lose_hp(actor, 0, critical=True)
        self.assertEqual(actor['death_failures'], 0)

    def test_healing_resets_save_counts(self):
        actor = self.down(); actor.update(death_successes=2, death_failures=2)
        rules.heal(actor, 1)
        self.assertEqual((actor['death_successes'], actor['death_failures']), (0, 0))

    def test_stable_creature_does_not_roll(self):
        actor = self.down(); actor['stable'] = True
        with self.assertRaises(ValueError): rules.death_save(actor, dice())
