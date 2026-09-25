import unittest
from copy import deepcopy
from ashen_vault.content import initial_state
from ashen_vault.engine import apply, active, RulesError
from tests.test_rules import dice


def battle():
    state = initial_state()
    state.update(owners={'warden': 'role-a', 'sentinel': 'role-b'}, phase='active', order=['warden', 'sentinel'], round=1, turn_id=1)
    state['actors']['warden']['movement'] = 30
    return state


def act(state, command, values=(), seat='warden', **args):
    return apply(state, seat, command, {'turn_id': state['turn_id'], **args}, dice(*values))


class EngineTests(unittest.TestCase):
    def test_initiative_and_npc_tie_policy(self):
        state = initial_state(); state['owners'] = {'warden': 'a', 'sentinel': 'b'}
        new, result = apply(state, 'warden', 'begin', {}, dice(10, 12))
        self.assertEqual(result['order'], ['sentinel', 'warden'])
        self.assertEqual(new['turn_id'], 1); self.assertEqual(state['phase'], 'lobby')

    def test_begin_needs_both_opted_in(self):
        with self.assertRaisesRegex(RulesError, 'WaitingForParticipants'):
            apply(initial_state(), 'warden', 'begin', {}, dice())

    def test_wrong_turn_never_rolls(self):
        with self.assertRaisesRegex(RulesError, 'NotYourTurn'):
            act(battle(), 'attack', seat='sentinel', target='warden')

    def test_stale_turn_rejected(self):
        with self.assertRaisesRegex(RulesError, 'StaleTurn'):
            apply(battle(), 'warden', 'dash', {'turn_id': 0}, dice())

    def test_attack_miss_still_spends_action(self):
        state = battle(); state['actors']['sentinel']['position'] = [4, 2]
        new, _ = act(state, 'attack', (1,), target='sentinel')
        self.assertFalse(new['actors']['warden']['action']); self.assertTrue(state['actors']['warden']['action'])
        with self.assertRaisesRegex(RulesError, 'ActionSpent'):
            act(new, 'attack', target='sentinel')

    def test_attack_does_not_implicitly_end_turn(self):
        state = battle(); state['actors']['sentinel']['position'] = [4, 2]
        new, _ = act(state, 'attack', (1,), target='sentinel')
        self.assertEqual(active(new), 'warden'); self.assertEqual(new['turn_id'], 1)

    def test_move_can_be_split_around_action(self):
        state, _ = act(battle(), 'move', path=[[4, 2]])
        state, _ = act(state, 'dash')
        state, _ = act(state, 'move', path=[[4, 3]])
        self.assertEqual(state['actors']['warden']['movement'], 50)

    def test_difficult_terrain(self):
        state, _ = act(battle(), 'move', path=[[4, 2], [5, 2], [6, 2]])
        self.assertEqual(state['actors']['warden']['movement'], 10)

    def test_prone_plus_difficult_costs_fifteen(self):
        state = battle(); state['actors']['warden'].update(position=[5, 2], conditions=['prone'])
        state, _ = act(state, 'move', path=[[6, 2]])
        self.assertEqual(state['actors']['warden']['movement'], 15)

    def test_standing_spends_half_speed(self):
        state, _ = act(battle(), 'drop_prone'); state, _ = act(state, 'stand')
        self.assertEqual(state['actors']['warden']['movement'], 15)
        self.assertTrue(state['actors']['warden']['action'])

    def test_standing_requires_enough_movement(self):
        state = battle(); state['actors']['warden'].update(conditions=['prone'], movement=10)
        with self.assertRaisesRegex(RulesError, 'InsufficientMovement'): act(state, 'stand')

    def test_no_teleport_via_path(self):
        with self.assertRaisesRegex(RulesError, 'InvalidPath'): act(battle(), 'move', path=[[10, 2]])

    def test_no_wall_corner_cutting(self):
        state = battle(); state['actors']['warden']['position'] = [4, 4]
        with self.assertRaisesRegex(RulesError, 'InvalidPath'): act(state, 'move', path=[[5, 3]])

    def test_invalid_late_step_rolls_back_entire_intent(self):
        state = battle(); old = deepcopy(state)
        with self.assertRaises(RulesError): act(state, 'move', path=[[4, 2], [5, 4]])
        self.assertEqual(state, old)

    def test_movement_budget(self):
        state = battle(); state['actors']['warden']['movement'] = 0
        with self.assertRaisesRegex(RulesError, 'InsufficientMovement'): act(state, 'move', path=[[4, 2]])

    def test_enemy_space_blocks_move(self):
        state = battle(); state['actors']['sentinel']['position'] = [4, 2]
        with self.assertRaisesRegex(RulesError, 'OccupiedByEnemy'): act(state, 'move', path=[[4, 2]])

    def test_no_voluntary_end_in_ally_space(self):
        state = battle(); state['actors']['sentinel'].update(position=[4, 2], team='warden')
        with self.assertRaisesRegex(RulesError, 'OccupiedDestination'): act(state, 'move', path=[[4, 2]])

    def pending(self):
        state = battle(); state['actors']['sentinel']['position'] = [4, 2]
        return act(state, 'move', path=[[2, 2], [1, 2]])[0]

    def test_opportunity_window_pauses_before_movement(self):
        state = self.pending()
        self.assertEqual(state['actors']['warden']['position'], [3, 2])
        self.assertEqual(state['actors']['warden']['movement'], 30)
        self.assertEqual(state['pending']['reactor'], 'sentinel')

    def test_pending_blocks_normal_actions(self):
        with self.assertRaisesRegex(RulesError, 'ReactionPending'): act(self.pending(), 'end_turn')

    def test_wrong_reactor_rejected(self):
        state = self.pending()
        with self.assertRaisesRegex(RulesError, 'NotYourReaction'):
            act(state, 'react', window_id=state['pending']['window_id'], choice='decline')

    def test_offturn_reaction_then_resume_path(self):
        state = self.pending()
        state, result = act(state, 'react', (1,), seat='sentinel', window_id=state['pending']['window_id'], choice='attack')
        self.assertEqual(state['actors']['warden']['position'], [1, 2])
        self.assertEqual(state['actors']['warden']['movement'], 20)
        self.assertFalse(state['actors']['sentinel']['reaction']); self.assertEqual(active(state), 'warden')

    def test_decline_does_not_spend_reaction(self):
        state = self.pending()
        state, _ = act(state, 'react', seat='sentinel', window_id=state['pending']['window_id'], choice='decline')
        self.assertTrue(state['actors']['sentinel']['reaction']); self.assertIsNone(state['pending'])

    def test_old_window_cannot_be_reused(self):
        state = self.pending(); window = state['pending']['window_id']
        state, _ = act(state, 'react', seat='sentinel', window_id=window, choice='decline')
        with self.assertRaisesRegex(RulesError, 'StaleReactionWindow'):
            act(state, 'react', seat='sentinel', window_id=window, choice='attack')

    def test_lethal_opportunity_stops_before_departure(self):
        state = self.pending()
        state, result = act(state, 'react', (20, 6, 6), seat='sentinel', window_id=state['pending']['window_id'], choice='attack')
        self.assertEqual(state['actors']['warden']['position'], [3, 2])
        self.assertEqual(state['phase'], 'complete'); self.assertEqual(result['movement']['status'], 'interrupted')

    def test_disengage_prevents_opportunity(self):
        state = battle(); state['actors']['sentinel']['position'] = [4, 2]
        state, _ = act(state, 'disengage'); state, _ = act(state, 'move', path=[[2, 2]])
        self.assertIsNone(state['pending']); self.assertEqual(state['actors']['warden']['position'], [2, 2])

    def test_dodge_expires_at_own_next_start(self):
        state, _ = act(battle(), 'dodge'); state, _ = act(state, 'end_turn')
        self.assertTrue(state['actors']['warden']['dodge'])
        state, _ = act(state, 'end_turn', seat='sentinel')
        self.assertFalse(state['actors']['warden']['dodge']); self.assertEqual(state['round'], 2)

    def test_reaction_resets_at_own_start_not_round_end(self):
        state = battle(); state['actors']['sentinel']['reaction'] = False
        state, _ = act(state, 'end_turn')
        self.assertTrue(state['actors']['sentinel']['reaction']); self.assertEqual(state['round'], 1)

    def test_actions_not_available_after_combat(self):
        state = battle(); state['phase'] = 'complete'
        with self.assertRaisesRegex(RulesError, 'EncounterNotActive'): act(state, 'dash')

    def test_unimplemented_rule_never_fabricates_outcome(self):
        with self.assertRaisesRegex(RulesError, 'UnsupportedRule'): act(battle(), 'cast_spell', spell='fireball')

    def test_json_round_trip_does_not_change_initiative_assignment(self):
        import json
        state=initial_state();state['owners']={'warden':'a','sentinel':'b'}
        persisted=json.loads(json.dumps(state,sort_keys=True))
        a,_=apply(state,'warden','begin',{},dice(5,18))
        b,_=apply(persisted,'warden','begin',{},dice(5,18))
        self.assertEqual(a['initiative'],b['initiative']);self.assertEqual(a['order'],b['order'])

    def test_team_victory_does_not_end_when_one_ally_remains(self):
        state=battle()
        ally=deepcopy(state['actors']['warden']);ally.update(id='ally',team='warden',position=[2,3],hp=5)
        state['actors']['ally']=ally
        state['actors']['sentinel']['position']=[4,2]
        new,_=act(state,'attack',(20,6,6),target='sentinel')
        self.assertEqual(new['phase'],'complete')
        self.assertEqual(new['winner'],'warden')
        self.assertEqual(new['actors']['ally']['hp'],5)

    def shield_state(self):
        state=battle();state['order']=['sentinel','warden'];state['index']=0;state['turn_id']=1
        state['actors']['sentinel'].update(position=[4,2],action=True,movement=30)
        state['actors']['warden'].update(position=[3,2],shield_reaction_available=True,shield_slots=1,reaction=True)
        return state

    def test_shield_reaction_pauses_after_hit_and_can_turn_it_into_miss(self):
        state=self.shield_state();hp=state['actors']['warden']['hp']
        state,result=apply(state,'sentinel','attack',{'turn_id':1,'target':'warden','knockout':False},dice(14))
        self.assertEqual(result['status'],'awaiting_reaction');self.assertEqual(state['actors']['warden']['hp'],hp)
        window=state['pending']['window_id']
        state,result=apply(state,'warden','react',{'window_id':window,'choice':'shield'},dice())
        self.assertFalse(result['attack_result']['hit']);self.assertEqual(state['actors']['warden']['hp'],hp)
        self.assertEqual((state['actors']['warden']['ac'],state['actors']['warden']['shield_slots'],state['actors']['warden']['reaction']),(21,0,False))
        state,_=apply(state,'sentinel','end_turn',{'turn_id':state['turn_id']},dice())
        self.assertEqual(state['actors']['warden']['ac'],16)

    def test_declining_shield_preserves_reaction_and_takes_stored_attack(self):
        state=self.shield_state();hp=state['actors']['warden']['hp']
        state,_=apply(state,'sentinel','attack',{'turn_id':1,'target':'warden','knockout':False},dice(14))
        window=state['pending']['window_id']
        state,result=apply(state,'warden','react',{'window_id':window,'choice':'decline'},dice(3))
        self.assertTrue(result['attack_result']['hit']);self.assertLess(state['actors']['warden']['hp'],hp)
        self.assertEqual((state['actors']['warden']['shield_slots'],state['actors']['warden']['reaction']),(1,True))

