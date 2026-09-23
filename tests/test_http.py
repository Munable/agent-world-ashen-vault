import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from starlette.testclient import TestClient
from agent_world import WorldRuntime
from ashen_vault.server import create_app


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name)/'world.sqlite3'
        self.app = create_app(self.db); self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.roles, self.tokens = {}, {}
        for seat in ('warden', 'sentinel'):
            role = self.app.state.runtime.create_role(seat)['role_id']
            self.roles[seat] = role
            self.tokens[seat] = self.app.state.runtime.issue_identity_token('ashen-vault', role)['token']
        self.counter = 0

    def call(self, seat, function, arguments=None, operation=None, client=None):
        self.counter += 1
        payload = {'arguments': arguments or {}}
        if function != 'look': payload['operation_id'] = operation or f'op-{self.counter}'
        return (client or self.client).post('/v1/functions/vault.'+function+'/invoke',
            headers={'Authorization': 'Bearer '+self.tokens[seat]}, json=payload)

    def state(self):
        return self.app.state.runtime.get_state('ashen-vault', 'encounter', 'state')['value']

    def setup_battle(self):
        for seat in self.roles:
            self.assertEqual(self.call(seat, 'join', {'seat': seat}).status_code, 200)
        with patch('agent_world.world_context.secrets.randbelow', side_effect=[0, 19]):
            result = self.call('warden', 'begin')
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.state()['order'][0], 'warden')
        moved = self.call('warden', 'move', {'turn_id': 1, 'path': [[4,2],[5,2],[6,1],[7,1]]})
        self.assertEqual(moved.status_code, 200, moved.text)

    def counts(self):
        with self.app.state.runtime._conn(readonly=True) as c:
            return tuple(c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                for table in ('roles', 'identity_tokens', 'operations', 'stream_events'))

    def test_no_auth_cannot_join(self):
        result = self.client.post('/v1/functions/vault.join/invoke',json={'operation_id':'no-auth','arguments':{'seat':'warden'}})
        self.assertEqual(result.status_code, 401)

    def test_seat_binds_only_callers_identity(self):
        self.assertEqual(self.call('warden','join',{'seat':'warden'}).status_code,200)
        self.assertEqual(self.state()['owners']['warden'], self.roles['warden'])
        self.assertGreaterEqual(self.call('sentinel','join',{'seat':'warden'}).status_code,400)
        self.assertGreaterEqual(self.call('warden','join',{'seat':'sentinel'}).status_code,400)

    def test_user_cannot_supply_roll_damage_or_actor(self):
        self.setup_battle(); before=self.counts()
        for field in ('damage','roll','advantage','actor_role_id'):
            r=self.call('warden','attack',{'turn_id':1,'target':'sentinel',field:20})
            self.assertEqual(r.status_code,422)
        self.assertEqual(self.counts(),before)

    def test_duplicate_attack_receipt_never_rerolls(self):
        self.setup_battle(); before=self.counts()
        with patch('agent_world.world_context.secrets.randbelow', side_effect=[14, 2]) as rng:
            a=self.call('warden','attack',{'turn_id':1,'target':'sentinel'},'exactly-once')
            b=self.call('warden','attack',{'turn_id':1,'target':'sentinel'},'exactly-once')
        self.assertEqual(a.status_code,200,a.text); self.assertEqual(b.status_code,200,b.text)
        self.assertEqual(rng.call_count,2)
        self.assertFalse(a.json()['replayed']);self.assertTrue(b.json()['replayed'])
        self.assertEqual(a.json()['result'],b.json()['result'])
        self.assertEqual(self.state()['actors']['sentinel']['hp'],9)
        after=self.counts();self.assertEqual(after[2]-before[2],1);self.assertEqual(after[3]-before[3],1)
        receipt=self.client.get('/v1/receipts/exactly-once',headers={'Authorization':'Bearer '+self.tokens['warden']})
        self.assertEqual(receipt.status_code,200)
        self.assertIn('random_draws',str(receipt.json()))

    def test_changed_arguments_cannot_reuse_operation_id(self):
        self.setup_battle()
        self.assertEqual(self.call('warden','dodge',{'turn_id':1},'same').status_code,200)
        self.assertGreaterEqual(self.call('warden','dash',{'turn_id':1},'same').status_code,400)
        self.assertTrue(self.state()['actors']['warden']['dodge'])

    def test_concurrent_same_attack_only_applies_once(self):
        self.setup_battle()
        def hit(_):
            with TestClient(create_app(self.db)) as client:
                return self.call('warden','attack',{'turn_id':1,'target':'sentinel'},'concurrent',client).json()
        with patch('agent_world.world_context.secrets.randbelow',side_effect=[14,2]) as rng:
            with ThreadPoolExecutor(max_workers=2) as executor: results=list(executor.map(hit,range(2)))
        self.assertEqual(rng.call_count,2)
        self.assertEqual(sorted(r['replayed'] for r in results),[False,True])
        self.assertEqual(self.state()['actors']['sentinel']['hp'],9)

    def test_reaction_survives_new_runtime_and_preserves_identity(self):
        self.setup_battle()
        r=self.call('warden','move',{'turn_id':1,'path':[[6,2]]},'leave-reach')
        self.assertEqual(r.status_code,200,r.text)
        pending=self.state()['pending'];self.assertIsNotNone(pending)
        before=self.counts()
        with TestClient(create_app(self.db)) as fresh:
            who=fresh.get('/v1/whoami',headers={'Authorization':'Bearer '+self.tokens['sentinel']})
            self.assertEqual(who.json()['role_id'],self.roles['sentinel'])
            r=self.call('sentinel','react',{'window_id':pending['window_id'],'choice':'decline'},'offturn-reaction',fresh)
            self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.state()['actors']['warden']['position'],[6,2])
        self.assertIsNone(self.state()['pending']);self.assertEqual(self.counts()[:2],before[:2])

    def test_illegal_turn_changes_no_state_or_dice(self):
        self.setup_battle(); state=self.state();before=self.counts()
        with patch('agent_world.world_context.secrets.randbelow') as rng:
            result=self.call('sentinel','attack',{'turn_id':1,'target':'warden'})
        self.assertGreaterEqual(result.status_code,400);rng.assert_not_called()
        self.assertEqual(self.state(),state);self.assertEqual(self.counts(),before)

    def test_public_snapshot_contains_no_identity_credentials(self):
        self.setup_battle()
        r=self.client.post('/v1/public/views/battle/snapshot',json={})
        self.assertEqual(r.status_code,200)
        for token in self.tokens.values():self.assertNotIn(token,r.text)
        self.assertNotIn('owners',r.text)
        self.assertEqual(r.json()['snapshot']['meta']['active'],'warden')

    def test_read_does_not_roll_or_write(self):
        self.setup_battle(); before=self.counts(); state=self.state()
        with patch('agent_world.world_context.secrets.randbelow') as rng:
            result=self.call('warden','look')
        self.assertEqual(result.status_code,200); rng.assert_not_called()
        self.assertEqual(self.counts(),before); self.assertEqual(self.state(),state)

    def test_revoked_identity_cannot_act(self):
        self.setup_battle();runtime=self.app.state.runtime
        token_id=runtime.resolve_identity_token(self.tokens['warden'])['token_id']
        runtime.revoke_identity_token(token_id)
        self.assertEqual(self.call('warden','dodge',{'turn_id':1}).status_code,401)

    def test_wrong_world_identity_cannot_act(self):
        self.tokens['warden']=self.app.state.runtime.issue_identity_token('other-world',self.roles['warden'])['token']
        self.assertIn(self.call('warden','join',{'seat':'warden'}).status_code,(401,403))

    def test_unsupported_spells_are_not_discoverable(self):
        r=self.client.get('/v1/discover?prefix=vault.&include_schemas=true',headers={'Authorization':'Bearer '+self.tokens['warden']})
        self.assertEqual(r.status_code,200)
        self.assertNotIn('vault.cast_spell',r.text)
        self.assertGreaterEqual(self.call('warden','cast_spell',{'spell':'fireball'}).status_code,400)

    def test_key_cannot_impersonate_other_role_in_envelope(self):
        payload={'operation_id':'impersonate','role_id':self.roles['sentinel'],'arguments':{'seat':'warden'}}
        r=self.client.post('/v1/functions/vault.join/invoke',headers={'Authorization':'Bearer '+self.tokens['warden']},json=payload)
        self.assertGreaterEqual(r.status_code,400)
        self.assertFalse(self.state()['owners'])

    def test_observe_token_can_read_but_cannot_control(self):
        role=self.roles['warden']
        observe=self.app.state.runtime.issue_identity_token('ashen-vault',role,access_mode='observe')['token']
        before=self.counts()
        r=self.client.post('/v1/functions/vault.look/invoke',headers={'Authorization':'Bearer '+observe},json={'arguments':{}})
        self.assertEqual(r.status_code,200)
        denied=self.client.post('/v1/functions/vault.join/invoke',headers={'Authorization':'Bearer '+observe},json={'operation_id':'read-only','arguments':{'seat':'warden'}})
        self.assertEqual(denied.status_code,403)
        self.assertEqual(self.counts(),before)

