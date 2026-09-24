import unittest
from copy import deepcopy

from ashen_vault.coop import _member, _settle, _party_battle, _advance_npc
from tests.test_rules import dice


class CoopTests(unittest.TestCase):
    def state(self):
        return {'version':1,'revision':0,'party_id':'abcdef12','owner_role_id':'role-a','invite_hash':'x',
                'phase':'forming','members':{'p1':_member('role-a','fighter','p1'),
                                             'p2':_member('role-b','wizard','p2')},
                'battle':None,'rewards':{},'seconds':0,'rest_requests':{}}

    def test_party_battle_binds_independent_roles_to_distinct_hero_seats(self):
        state=self.state()
        battle=_party_battle(state,dice(1,20,18))
        self.assertEqual(battle['owners']['p1'],'role-a')
        self.assertEqual(battle['owners']['p2'],'role-b')
        self.assertEqual((battle['actors']['p1']['team'],battle['actors']['p2']['team']),('heroes','heroes'))
        self.assertEqual(battle['actors']['enemy']['team'],'enemy')

    def test_world_driver_never_plays_a_real_users_turn(self):
        state=self.state();state['phase']='active'
        state['battle']={'phase':'active','owners':{'p1':'role-a','p2':'role-b','enemy':'world:npc'},
                         'actors':{'p1':deepcopy(state['members']['p1']['hero']),
                                   'p2':deepcopy(state['members']['p2']['hero']),
                                   'enemy':deepcopy(state['members']['p1']['hero'])},
                         'order':['p1','enemy','p2'],'initiative':{},'index':0,'round':1,'turn_id':1,
                         'pending':None,'window_serial':0,'winner':None}
        state['battle']['actors']['p1'].update(id='p1',team='heroes',position=[3,2],movement=30)
        state['battle']['actors']['p2'].update(id='p2',team='heroes',position=[3,4],movement=30)
        state['battle']['actors']['enemy'].update(id='enemy',team='enemy',position=[4,3],movement=30)
        before=deepcopy(state['battle'])
        _advance_npc(state,dice())
        self.assertEqual(state['battle'],before)

    def test_shared_reward_ledger_distributes_once_per_beneficiary(self):
        state=self.state();state['phase']='active'
        actors={seat:deepcopy(member['hero']) for seat,member in state['members'].items()}
        for seat,actor in actors.items():actor.update(id=seat,team='heroes')
        actors['enemy']=deepcopy(actors['p1']);actors['enemy'].update(id='enemy',team='enemy')
        state['battle']={'phase':'complete','winner':'heroes','actors':actors}
        _settle(state);first=deepcopy(state)
        _settle(state)
        self.assertEqual(state,first)
        self.assertEqual(state['rewards']['coop_guard']['beneficiaries'],['p1','p2'])
        self.assertEqual((state['members']['p1']['xp'],state['members']['p2']['gold']),(50,5))


if __name__ == '__main__':
    unittest.main()
