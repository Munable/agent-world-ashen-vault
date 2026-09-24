import unittest
import random
from copy import deepcopy
from ashen_vault.campaign_content import new_campaign, REWARDS
from ashen_vault.campaign import apply, view, path_to, available
from ashen_vault.engine import RulesError, apply as battle_apply
from ashen_vault.rules import d20
from tests.test_engine import battle
from tests.test_rules import dice


def command(state,name,draw=None,**args):
    return apply(state,name,{'revision':state['revision'],**args},draw or random.Random(7).randint)


def at_delivered():
    state=new_campaign('player')
    for name,args in [('travel',{'destination':'gate'}),('interact',{'target':'inscription'}),('travel',{'destination':'fork'}),
                      ('travel',{'destination':'guard'}),('interact',{'target':'pay_guard'}),('travel',{'destination':'shrine'}),
                      ('interact',{'target':'dread'}),('interact',{'target':'take_ember'}),('travel',{'destination':'guard'}),('travel',{'destination':'fork'}),
                      ('travel',{'destination':'gate'}),('travel',{'destination':'camp'}),('interact',{'target':'deliver'})]:
        state,_=command(state,name,**args)
    return state


def leveled():return command(at_delivered(),'level_up',style='defense')[0]


class CampaignTests(unittest.TestCase):
    def test_whole_noncombat_growth_route(self):
        state=at_delivered();self.assertEqual(state['xp'],300);self.assertEqual(state['level'],1)
        self.assertEqual(set(state['rewards']),{'inscription','guard_access','ember_delivery'})
        self.assertTrue(all(a['tool']=='adventure.level_up' for a in view(state)['meta']['actions']))
        old_hp=state['hero']['hp'];new,events=command(state,'level_up',style='defense')
        self.assertEqual((new['level'],new['hero']['max_hp'],new['hero']['hp']),(2,20,old_hp))
        self.assertEqual((new['hit_dice'],new['action_surge']),(2,1))
        self.assertEqual(events[-1]['kind'],'level_up')

    def test_level_choice_blocks_extra_actions_until_applied(self):
        with self.assertRaisesRegex(RulesError,'LevelChoicePending'):command(at_delivered(),'travel',destination='gate')

    def test_repeated_level_request_cannot_repeat_growth(self):
        state=leveled();old=deepcopy(state)
        with self.assertRaises(RulesError):command(state,'level_up',style='dueling')
        self.assertEqual(state,old)

    def test_dueling_tradeoff_is_real(self):
        state,_=command(at_delivered(),'level_up',style='dueling')
        self.assertEqual((state['hero']['ac'],state['hero']['damage_bonus']),(18,5))

    def test_paid_route_spends_gold_once_and_awards_once(self):
        state=at_delivered();self.assertEqual(state['gold'],68)
        state=leveled()
        for room in ('gate','fork','guard'):state,_=command(state,'travel',destination=room)
        with self.assertRaises(RulesError):command(state,'interact',target='pay_guard')
        self.assertEqual(state['xp'],300)

    def test_no_client_state_mutation_on_rejected_intent(self):
        s=new_campaign('player');before=deepcopy(s)
        with self.assertRaises(RulesError):command(s,'travel',destination='shrine')
        self.assertEqual(s,before)

    def test_wrong_place_cannot_claim_goal(self):
        state=new_campaign('player')
        for target in ('deliver','take_ember','pay_guard','cache','trial'):
            with self.assertRaises(RulesError):command(state,'interact',target=target)
        self.assertEqual(state['xp'],0)

    def test_no_guard_passage_without_resolution(self):
        state=new_campaign('player')
        for dest in ('gate','fork','guard'):state,_=command(state,'travel',destination=dest)
        with self.assertRaises(RulesError):command(state,'travel',destination='shrine')

    def test_second_wind_consumes_real_resource(self):
        s=new_campaign('player');s['hero']['hp']=2
        s,events=command(s,'second_wind',dice(4))
        self.assertEqual((s['hero']['hp'],s['second_wind']),(7,1));self.assertEqual(s['seconds'],6)

    def test_potion_is_consumed_even_at_full_hp(self):
        s,events=command(new_campaign('player'),'potion',dice(4,4))
        self.assertEqual((s['hero']['hp'],s['potions']),(12,0))
        with self.assertRaises(RulesError):command(s,'potion')

    def test_short_rest_does_not_automatically_heal(self):
        s=leveled();s['hero']['hp']=1;s['second_wind']=0;s['action_surge']=0
        s,_=command(s,'rest',kind='short');self.assertEqual((s['hero']['hp'],s['second_wind'],s['action_surge']),(1,1,1))
        s,_=command(s,'spend_hit_die',dice(3));self.assertEqual((s['hero']['hp'],s['hit_dice']),(6,1))
        s,_=command(s,'spend_hit_die',dice(10));self.assertEqual((s['hero']['hp'],s['hit_dice']),(18,0))
        with self.assertRaises(RulesError):command(s,'spend_hit_die')

    def test_hit_die_choice_ends_when_rest_activity_ends(self):
        s,_=command(leveled(),'rest',kind='short');s,_=command(s,'travel',destination='gate')
        with self.assertRaises(RulesError):command(s,'spend_hit_die')

    def test_long_rest_cooldown_uses_fictional_seconds(self):
        s,_=command(leveled(),'rest',kind='long');self.assertEqual(s['hit_dice'],2)
        with self.assertRaisesRegex(RulesError,'LongRestTooSoon'):command(s,'rest',kind='long')
        self.assertFalse(any(a['arguments'].get('kind')=='long' for a in view(s)['meta']['actions']))
        for _ in range(16):s,_=command(s,'rest',kind='short')
        s,_=command(s,'rest',kind='long');self.assertEqual(s['hero']['hp'],20)

    def cache_state(self):
        s=leveled()
        for room in ('gate','fork','cache'):s,_=command(s,'travel',destination=room)
        return s

    def test_failed_tactical_mind_does_not_spend_second_wind(self):
        s,events=command(self.cache_state(),'interact',dice(2),target='cache',use_luck=False)
        self.assertIsNotNone(s['pending_check']);old=s['second_wind']
        s,events=command(s,'resolve_check',dice(1),choice='tactical')
        self.assertEqual(s['second_wind'],old);self.assertNotIn('cache',s['rewards'])
        with self.assertRaises(RulesError):command(s,'interact',target='cache')

    def test_successful_tactical_mind_spends_exactly_once(self):
        s,_=command(self.cache_state(),'interact',dice(8),target='cache',use_luck=False)
        s,events=command(s,'resolve_check',dice(2),choice='tactical')
        self.assertEqual(s['second_wind'],1);self.assertEqual(s['potions'],3)
        self.assertEqual([e['kind'] for e in events],['tactical_mind','check_result','reward'])

    def test_pending_check_blocks_other_actions_without_losing_decision(self):
        s,_=command(self.cache_state(),'interact',dice(2),target='cache',use_luck=False);old=deepcopy(s)
        with self.assertRaises(RulesError):command(s,'travel',destination='fork')
        self.assertEqual(s,old)

    def test_lucky_rerolls_only_one_selected_die(self):
        r=d20(dice(1,1,5),0,advantage=True,reroll_one=True)
        self.assertEqual(r['initial_dice'],[1,1]);self.assertEqual(r['dice'],[5,1])
        r=d20(dice(1,7,20),0,disadvantage=True,reroll_one=True);self.assertEqual(r['natural'],7)

    def test_nimble_entry_into_enemy_space_does_not_provoke(self):
        s=battle();s['actors']['warden'].update(size='small',nimble=True);s['actors']['sentinel']['position']=[4,2]
        updated,result=battle_apply(s,'warden','move',{'turn_id':1,'path':[[4,2],[5,2]]},dice())
        self.assertIsNone(updated['pending']);self.assertEqual(updated['actors']['warden']['position'],[5,2])
        self.assertEqual(updated['actors']['warden']['movement'],15)

    def test_revision_conflict_never_rolls(self):
        with self.assertRaises(RulesError):apply(new_campaign('p'),'potion',{'revision':99},dice())

    def test_camp_rest_required_and_no_remote_equipment_change(self):
        s,_=command(leveled(),'travel',destination='gate')
        for cmd,args in [('rest',{'kind':'short'}),('equip',{'weapon':'mace'})]:
            with self.assertRaises(RulesError):command(s,cmd,**args)

    def test_hidden_rooms_not_in_initial_projection(self):
        v=view(new_campaign('p'));self.assertEqual(set(v['meta']['known_rooms']),{'camp'})
        self.assertNotIn('shrine',str(v));self.assertNotIn('owners',str(v))

    def test_retirement_preserves_growth_without_claiming_victory(self):
        s,_=command(leveled(),'retire');self.assertEqual(s['status'],'retired');self.assertEqual(s['level'],2)
        self.assertEqual(view(s)['meta']['actions'],[])

    def test_solo_npc_needs_no_other_user_role(self):
        s=leveled()
        for room in ('gate','fork','guard','shrine'):s,_=command(s,'travel',destination=room)
        s,events=command(s,'interact',target='trial')
        self.assertEqual(s['role_id'],'player');self.assertIn('enemy',s['battle']['actors'])
        self.assertTrue(s['battle']['pending'] or s['battle']['order'][s['battle']['index']]=='hero')


    def battle_state(self,level=2):
        from ashen_vault.campaign_content import make_battle
        s=leveled() if level==2 else new_campaign('player')
        s['room']='shrine' if level==2 else 'guard'
        s['battle']=make_battle(s,dice(2,18))
        s['battle']['actors']['enemy']['position']=[4,2]
        s['battle']['actors']['enemy']['hp']=99
        s['battle']['actors']['enemy']['max_hp']=99
        return s

    def test_action_surge_grants_exactly_one_extra_action(self):
        s=self.battle_state();tid=s['battle']['turn_id']
        s,_=command(s,'action_surge')
        for _ in range(2):s,_=command(s,'attack',dice(2),turn_id=tid,target='enemy',use_luck=False)
        self.assertFalse(s['battle']['actors']['hero']['action'])
        with self.assertRaisesRegex(RulesError,'ActionSpent'):command(s,'attack',turn_id=tid,target='enemy')
        with self.assertRaisesRegex(RulesError,'ActionSurgeUnavailable'):command(s,'action_surge')

    def test_action_surge_after_spent_action_restores_one(self):
        s=self.battle_state();tid=s['battle']['turn_id']
        s,_=command(s,'attack',dice(2),turn_id=tid,target='enemy',use_luck=False)
        s,_=command(s,'action_surge');s,_=command(s,'dodge',turn_id=tid)
        self.assertFalse(s['battle']['actors']['hero']['action']);self.assertEqual(s['action_surge'],0)

    def test_bonus_action_does_not_refresh_between_buttons(self):
        s=self.battle_state();s['battle']['actors']['hero']['hp']=2
        s,_=command(s,'second_wind',dice(3))
        self.assertEqual(s['battle']['actors']['hero']['hp'],7)
        with self.assertRaisesRegex(RulesError,'BonusActionSpent'):command(s,'potion')
        self.assertEqual(s['potions'],1)

    def test_sap_applies_next_attack_then_expires(self):
        from ashen_vault.rules import melee_attack
        from ashen_vault.engine import _turn_start
        s=self.battle_state();b=s['battle'];h=b['actors']['hero'];enemy=b['actors']['enemy']
        melee_attack(h,enemy,dice(15,2));self.assertEqual(enemy['sapped_by'],'hero')
        result=melee_attack(enemy,h,dice(20,2))
        self.assertEqual(result['attack']['mode'],'disadvantage');self.assertNotIn('sapped_by',enemy)
        enemy['sapped_by']='hero';b['index']=b['order'].index('hero');_turn_start(b)
        self.assertNotIn('sapped_by',enemy)

    def test_scripted_low_hp_enemy_stops_for_player_reaction(self):
        s=self.battle_state();b=s['battle'];b['actors']['enemy']['hp']=2
        s,events=command(s,'end_turn',turn_id=b['turn_id'])
        self.assertIsNotNone(s['battle']['pending'])
        self.assertEqual(s['battle']['pending']['reactor'],'hero')
        position=list(s['battle']['actors']['enemy']['position'])
        s,_=command(s,'react',window_id=s['battle']['pending']['window_id'],choice='decline')
        self.assertEqual(s['status'],'completed')
        self.assertEqual(s['hero']['hp'],12)
        self.assertEqual(position,[4,2])
        self.assertEqual(s['rewards']['seal_trial']['gold'],30)

    def test_retreat_preserves_both_health_values_and_no_reward(self):
        s=self.battle_state(level=1);b=s['battle']
        b['actors']['hero'].update(position=[0,2],hp=7)
        b['actors']['enemy']['hp']=6
        s,_=command(s,'escape',turn_id=b['turn_id'])
        self.assertEqual(s['hero']['hp'],7);self.assertEqual(s['flags']['guard_hp'],6)
        self.assertEqual(s['room'],'fork');self.assertFalse(s['rewards'])

    def test_knockout_failure_is_terminal_not_auto_healed(self):
        s=self.battle_state(level=1);b=s['battle'];b['actors']['hero']['hp']=1
        s,events=command(s,'end_turn',dice(20,6,6),turn_id=b['turn_id'])
        self.assertEqual(s['status'],'captured');self.assertEqual(s['hero']['hp'],1)
        self.assertIn('unconscious',s['hero']['conditions']);self.assertIsNone(s['battle'])
        with self.assertRaisesRegex(RulesError,'AdventureEnded'):command(s,'second_wind')

    def test_final_presentation_frame_matches_committed_projection(self):
        s=new_campaign('player');s['hero']['hp']=1
        s,events=command(s,'second_wind',dice(5))
        self.assertEqual(events[-1]['frame'],view(s));self.assertEqual(events[-1]['frame']['meta']['minutes'],.1)

    def test_outside_posture_is_an_explicit_action(self):
        s=new_campaign('p');s['hero']['conditions']=['prone']
        s,_=command(s,'recover_posture')
        self.assertEqual(s['hero']['conditions'],[]);self.assertEqual(s['seconds'],6)


    def test_declining_luck_for_one_attack_does_not_erase_species_trait(self):
        s=self.battle_state();tid=s['battle']['turn_id']
        s,_=command(s,'attack',dice(1),turn_id=tid,target='enemy',use_luck=False)
        self.assertTrue(s['hero']['lucky']);self.assertTrue(s['battle']['actors']['hero']['lucky'])

    def test_dwarvish_language_is_a_real_inscription_gate(self):
        s=new_campaign('player');s,_=command(s,'travel',destination='gate')
        blocked=deepcopy(s);blocked['build']['languages'].remove('dwarvish')
        with self.assertRaisesRegex(RulesError,'DwarvishRequired'):command(blocked,'interact',target='inscription')
        s,events=command(s,'interact',target='inscription')
        self.assertEqual(events[0]['data']['check'],'language:dwarvish')
        self.assertEqual(s['rewards']['inscription']['resolution'],'authored-dwarvish-inscription')

    def test_naturally_stealthy_opens_a_real_hide_route(self):
        s=new_campaign('player')
        for room in ('gate','fork','guard'):
            s,_=command(s,'travel',destination=room)
            if room=='gate':s,_=command(s,'interact',target='inscription')
        stealth=[a for a in available(s) if a['arguments'].get('target')=='stealth_passage']
        self.assertEqual(len(stealth),1)
        s,events=command(s,'interact',dice(12),target='stealth_passage',use_luck=False)
        check=next(e for e in events if e['kind']=='check')
        self.assertEqual((check['data']['skill'],check['data']['trait'],check['data']['test']['total']),('stealth','naturally_stealthy',15))
        self.assertTrue(s['flags']['guard_access'])
        self.assertEqual(s['rewards']['guard_access']['resolution'],'authored-naturally-stealthy-hide')

    def test_carpenters_tools_are_a_real_cache_option(self):
        s=new_campaign('player')
        for room in ('gate','fork','cache'):
            s,_=command(s,'travel',destination=room)
            if room=='gate':s,_=command(s,'interact',target='inscription')
        self.assertTrue(any(a['arguments'].get('target')=='cache_tools' for a in available(s)))
        s,events=command(s,'interact',dice(9),target='cache_tools',use_luck=False)
        check=next(e for e in events if e['kind']=='check')
        self.assertEqual((check['data']['check'],check['data']['test']['total']),('carpenters_tools',12))
        self.assertEqual(s['rewards']['cache']['resolution'],'carpenters_tools_check')
        self.assertFalse(any(a['arguments'].get('target') in ('cache','cache_tools') for a in available(s)))

    def test_brave_fear_save_and_recovery_are_enforced(self):
        s=new_campaign('player');s['room']='shrine';s['visited'].append('shrine');s['flags']['guard_access']=True
        s,events=command(s,'interact',dice(2,3),target='dread',use_luck=False)
        check=next(e for e in events if e['kind']=='check')
        self.assertEqual((check['data']['test']['mode'],check['data']['trait']),('advantage','brave'))
        self.assertIn('frightened',s['hero']['conditions'])
        s['room']='guard'
        self.assertFalse(any(a['arguments'].get('destination')=='shrine' for a in available(s)))
        with self.assertRaisesRegex(RulesError,'FrightenedCannotApproachSource'):command(s,'travel',destination='shrine')
        s,events=command(s,'interact',dice(4,12),target='dread_recover',use_luck=False)
        self.assertNotIn('frightened',s['hero']['conditions']);self.assertTrue(s['flags']['dread_cleared'])
        s,_=command(s,'travel',destination='shrine');self.assertEqual(s['room'],'shrine')

    def test_ember_cannot_bypass_dread_resolution(self):
        s=new_campaign('player');s['room']='shrine';s['visited'].append('shrine');s['flags']['guard_access']=True
        with self.assertRaisesRegex(RulesError,'EmberUnavailable'):command(s,'interact',target='take_ember')

    def test_potion_purchase_changes_a_real_early_route_choice(self):
        s,_=command(new_campaign('player'),'buy_potion')
        self.assertEqual((s['gold'],s['potions']),(18,2))
        for room in ('gate','fork','guard'):
            s,_=command(s,'travel',destination=room)
            if room=='gate':s,_=command(s,'interact',target='inscription')
        self.assertFalse(any(a['arguments'].get('target')=='pay_guard' for a in available(s)))
        with self.assertRaisesRegex(RulesError,'InsufficientGold'):command(s,'interact',target='pay_guard')
        self.assertEqual(s['xp'],75)

    def test_merchant_stock_is_persistent_and_never_negative(self):
        s=new_campaign('p');s['gold']=150
        for _ in range(2):s,_=command(s,'buy_potion')
        self.assertEqual((s['gold'],s['potions'],s['flags']['potions_bought']),(50,3,2))
        with self.assertRaises(RulesError):command(s,'buy_potion')

    def test_outside_time_advance_clears_only_transient_combat_flags(self):
        s=new_campaign('p');s['hero'].update(sapped_by='enemy',dodge=True,hp=4)
        s,_=command(s,'travel',destination='gate')
        self.assertNotIn('sapped_by',s['hero']);self.assertFalse(s['hero']['dodge'])
        self.assertEqual(s['hero']['hp'],4)


    def test_projection_geometry_cannot_mutate_rule_geometry(self):
        from ashen_vault.content import ARENA
        s=self.battle_state();original=deepcopy(ARENA)
        projection=view(s);projection['meta']['arena']['walls']={(5,4),(5,5)}
        self.assertEqual(ARENA,original)
        from ashen_vault.engine import clear_step
        self.assertFalse(clear_step([4,4],[5,3]))


    def test_projected_room_positions_do_not_alias_authored_content(self):
        from ashen_vault.campaign_content import ROOMS
        s=new_campaign('p');before=deepcopy(ROOMS)
        v=view(s);v['entities']['hero']['position'][0]=99
        v['meta']['known_rooms']['camp']['position'][1]=99
        self.assertEqual(ROOMS,before)
