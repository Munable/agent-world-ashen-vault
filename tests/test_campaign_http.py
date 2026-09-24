import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from starlette.testclient import TestClient
from agent_world import WorldRuntime
from ashen_vault.server import create_app
from ashen_vault.campaign_world import UNIVERSE


class CampaignHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'campaign.sqlite3';self.app=create_app(self.db,campaign=True)
        self.client=TestClient(self.app);self.addCleanup(self.client.close)
        self.role=self.app.state.runtime.create_role('测试旅人')['role_id']
        self.token=self.app.state.runtime.issue_identity_token(UNIVERSE,self.role)['token']
        self.client.headers['Authorization']='Bearer '+self.token;self.counter=0

    def call(self,name,args=None,operation=None,client=None):
        self.counter+=1
        body={'arguments':args or {}}
        if name!='look':body['operation_id']=operation or 'case-'+str(self.counter)
        return (client or self.client).post('/v1/functions/adventure.'+name+'/invoke',json=body)

    def state(self):return self.app.state.runtime.get_state(UNIVERSE,'campaign:'+self.role,'state')['value']
    def join(self):
        r=self.call('join');self.assertEqual(r.status_code,200,r.text);return r
    def act(self,name,**args):
        r=self.call(name,{'revision':self.state()['revision'],**args});self.assertEqual(r.status_code,200,r.text);return r

    def deliver(self):
        self.join()
        for name,args in [('travel',{'destination':'gate'}),('interact',{'target':'inscription'}),('travel',{'destination':'fork'}),('travel',{'destination':'guard'}),
                          ('interact',{'target':'pay_guard'}),('travel',{'destination':'shrine'})]:self.act(name,**args)
        self.act('interact',target='dread')
        for _ in range(8):
            if self.state()['flags'].get('dread_cleared'):break
            self.act('interact',target='dread_recover')
        else:self.fail('Brave recovery did not clear authored dread within bounded HTTP test')
        for name,args in [('interact',{'target':'take_ember'}),('travel',{'destination':'guard'}),('travel',{'destination':'fork'}),
                          ('travel',{'destination':'gate'}),('travel',{'destination':'camp'}),('interact',{'target':'deliver'})]:self.act(name,**args)

    def counts(self):
        with self.app.state.runtime._conn(readonly=True) as c:return tuple(c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('roles','identity_tokens','operations','events'))

    def test_no_extra_role_or_token_on_repeated_adventure_join(self):
        before=self.counts()[:2]
        for _ in range(3):self.join()
        self.assertEqual(self.counts()[:2],before)

    def test_schema_rejects_client_awards_and_dice(self):
        self.join();before=self.counts()
        for field in ('xp','hp','roll','damage','state','role_id'):
            r=self.call('travel',{'revision':0,'destination':'gate',field:999})
            self.assertEqual(r.status_code,422)
        self.assertEqual(self.counts(),before)

    def test_paid_route_then_new_level_is_persistent(self):
        self.deliver();result=self.act('level_up',style='defense')
        self.assertEqual(result.json()['result']['scene']['meta']['level'],2)
        with TestClient(create_app(self.db,campaign=True)) as fresh:
            fresh.headers['Authorization']='Bearer '+self.token
            who=fresh.get('/v1/whoami');self.assertEqual(who.json()['role_id'],self.role)
            r=self.call('look',client=fresh);self.assertEqual(r.json()['result']['scene']['meta']['xp'],300)
            self.assertEqual(r.json()['result']['scene']['entities']['hero']['max_hp'],20)

    def test_different_operation_ids_do_not_repeat_delivery_reward(self):
        self.deliver();self.act('level_up',style='defense');before=self.state();counts=self.counts()
        for operation in ('new-id-a','new-id-b'):
            r=self.call('interact',{'revision':before['revision'],'target':'deliver'},operation)
            self.assertGreaterEqual(r.status_code,400)
        self.assertEqual(self.state(),before);self.assertEqual(self.counts(),counts)

    def test_same_operation_replay_does_not_duplicate_cues(self):
        self.join();args={'revision':0,'destination':'gate'};before=self.counts()
        a=self.call('travel',args,'once');b=self.call('travel',args,'once')
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(b.status_code,200,b.text)
        self.assertFalse(a.json()['replayed']);self.assertTrue(b.json()['replayed'])
        self.assertEqual(a.json()['result'],b.json()['result'])
        self.assertEqual(self.counts()[3]-before[3],len(a.json()['result']['cues']))
        self.assertEqual(self.state()['seconds'],600)

    def test_concurrent_different_ids_one_reward(self):
        self.join();self.act('travel',destination='gate')
        revision=self.state()['revision']
        def grant(i):
            with TestClient(create_app(self.db,campaign=True)) as c:
                c.headers['Authorization']='Bearer '+self.token
                return c.post('/v1/functions/adventure.interact/invoke',json={'operation_id':'race-'+str(i),'arguments':{'revision':revision,'target':'inscription'}})
        with ThreadPoolExecutor(max_workers=2) as e:results=list(e.map(grant,range(2)))
        self.assertEqual(sum(r.status_code==200 for r in results),1)
        self.assertEqual(self.state()['xp'],75)

    def test_private_view_and_timeline_deny_other_identity(self):
        self.join();r=self.client.post('/v1/views/adventure/snapshot',json={});self.assertEqual(r.status_code,200,r.text)
        cursor=r.json()['timeline_cursor']
        self.act('travel',destination='gate')
        other=self.app.state.runtime.create_role('另一个角色')['role_id']
        other_token=self.app.state.runtime.issue_identity_token(UNIVERSE,other)['token']
        with TestClient(create_app(self.db,campaign=True)) as c:
            c.headers['Authorization']='Bearer '+other_token
            result=c.post('/v1/views/timeline',json={'cursor':cursor})
            self.assertGreaterEqual(result.status_code,400)
            own=c.get('/v1/bootstrap').json()['world_entry_state']['view']['scene']
            self.assertFalse(own['meta']['joined']);self.assertNotIn('旧门厅',str(own))
            changes=c.get('/v1/changes?after=0').json();self.assertEqual(changes['events'],[])
        public=self.client.post('/v1/public/views/adventure/snapshot',json={});self.assertEqual(public.status_code,403)

    def test_snapshot_anchor_and_real_cues_do_not_replay_old_rewards(self):
        self.join();self.act('travel',destination='gate');self.act('interact',target='inscription')
        snapshot=self.client.post('/v1/views/adventure/snapshot',json={}).json()
        self.act('travel',destination='fork')
        timeline=self.client.post('/v1/views/timeline',json={'cursor':snapshot['timeline_cursor']}).json()
        self.assertEqual([e['cue']['name'] for e in timeline['events']],['campaign.travel'])
        for event in timeline['events']:
            self.assertNotIn(self.token,json.dumps(event));self.assertEqual(event['cue']['data']['frame']['meta']['revision'],3)

    def test_long_rest_and_healing_are_real_authorized_transactions(self):
        self.deliver();self.act('level_up',style='defense');self.act('rest',kind='short')
        with patch('agent_world.world_context.secrets.randbelow',return_value=3):r=self.act('spend_hit_die')
        self.assertEqual(r.json()['result']['scene']['entities']['hero']['hp'],18)
        self.assertEqual(self.state()['hit_dice'],1)

    def test_rollback_on_too_large_presentation_payload(self):
        self.join();old=self.state();counts=self.counts()
        with patch('ashen_vault.campaign.view',return_value={'entities':{},'meta':{'huge':'x'*20000,'actions':[]}}):
            r=self.call('travel',{'revision':0,'destination':'gate'})
        self.assertGreaterEqual(r.status_code,400)
        self.assertEqual(self.state(),old);self.assertEqual(self.counts(),counts)

    def test_readonly_identity_cannot_advance_or_take_rewards(self):
        self.join();observe=self.app.state.runtime.issue_identity_token(UNIVERSE,self.role,access_mode='observe')['token']
        self.client.headers['Authorization']='Bearer '+observe
        self.assertEqual(self.call('look').status_code,200)
        self.assertEqual(self.call('travel',{'revision':0,'destination':'gate'}).status_code,403)

    def test_wizard_join_and_spell_slot_replay_are_persistent(self):
        joined=self.call('join',{'class_key':'wizard'},'wizard-join')
        self.assertEqual(joined.status_code,200,joined.text)
        self.assertEqual(self.state()['build']['class'],'Wizard')
        args={'revision':0,'spell':'mage_armor','target':'hero','slot_level':1}
        first=self.call('cast',args,'wizard-armor')
        replay=self.call('cast',args,'wizard-armor')
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(replay.status_code,200,replay.text)
        self.assertFalse(first.json()['replayed']);self.assertTrue(replay.json()['replayed'])
        self.assertEqual(self.state()['spell_slots']['1'],1)
        stale=self.call('cast',args,'wizard-armor-new-id')
        self.assertGreaterEqual(stale.status_code,400)
        self.assertEqual(self.state()['spell_slots']['1'],1)

    def test_join_rejects_unknown_class_before_state_creation(self):
        result=self.call('join',{'class_key':'bard'},'bad-class')
        self.assertEqual(result.status_code,422)
        with self.app.state.runtime._conn(readonly=True) as c:
            count=c.execute("SELECT COUNT(*) FROM world_state WHERE universe=? AND scope=?", (UNIVERSE,'campaign:'+self.role)).fetchone()[0]
        self.assertEqual(count,0)

