import tempfile
import unittest
from pathlib import Path
from agent_world import WorldRuntime, WorldDefinition, FunctionSpec, StateRule, FunctionOutcome
from agent_world.errors import RuleViolation
from agent_world.world_sdk import install_world
from ashen_vault.campaign_content import new_campaign
from ashen_vault.campaign_world import WORLD, UNIVERSE

EMPTY={'type':'object','properties':{},'additionalProperties':False}
LOOSE={'type':'object'}

def legacy_state(role,status='exploring'):
    state=new_campaign(role,'fighter');state['version']=1
    state.pop('spell_slots',None);state.pop('arcane_recovery',None)
    state['build'].pop('class_key',None);state['build'].pop('supported_weapons',None)
    for key in ('class_key','critical_threshold','remarkable_athlete'):state['hero'].pop(key,None)
    state['status']=status
    return state

def legacy_world(role,state):
    def initialize(ctx):ctx.set_state('campaign:'+role,'state',state)
    def noop(ctx,args):return FunctionOutcome({})
    old_level={'type':'object','properties':{'revision':{'type':'integer','minimum':0},
               'style':{'enum':['defense','dueling']}},'required':['revision','style'],'additionalProperties':False}
    return WorldDefinition('ashen-vault-ember','Legacy G1',(
        FunctionSpec('adventure.join',noop,EMPTY),
        FunctionSpec('adventure.level_up',noop,old_level),
    ),version=1,state_version=1,state_rules=(StateRule('campaign:','state',LOOSE),),initialize=initialize)

class CampaignMigrationTests(unittest.TestCase):
    def test_existing_g1_contract_installs_g2_and_keeps_same_fighter(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime=WorldRuntime(Path(temp)/'world.sqlite3');role=runtime.create_role('legacy')['role_id']
            install_world(runtime,UNIVERSE,legacy_world(role,legacy_state(role)))
            install_world(runtime,UNIVERSE,WORLD)
            seen=runtime.call_function(UNIVERSE,'adventure.look',role,{})
            self.assertEqual(seen['result']['scene']['meta']['class_key'],'fighter')
            with self.assertRaises(RuleViolation):
                runtime.call_function(UNIVERSE,'adventure.join',role,{'class_key':'wizard'},operation_id='wrong-class')
            moved=runtime.call_function(UNIVERSE,'adventure.travel',role,{'revision':0,'destination':'gate'},operation_id='move')
            self.assertEqual(moved['result']['scene']['meta']['class_key'],'fighter')
            saved=runtime.get_state(UNIVERSE,'campaign:'+role,'state')['value']
            self.assertEqual((saved['version'],saved['room'],saved['build']['class_key']),(2,'gate','fighter'))

    def test_completed_g1_trial_gets_g2_xp_without_free_healing(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime=WorldRuntime(Path(temp)/'world.sqlite3');role=runtime.create_role('legacy-done')['role_id']
            old=legacy_state(role,'completed');old.update(level=2,xp=300);old['hero']['hp']=5
            old['rewards']={'inscription':{'xp':75,'gold':0,'potions':0},'guard_access':{'xp':75,'gold':0,'potions':0},
                'ember_delivery':{'xp':150,'gold':20,'potions':0},
                'seal_trial':{'xp':0,'gold':30,'potions':0,'resolution':'victory'}}
            install_world(runtime,UNIVERSE,legacy_world(role,old));install_world(runtime,UNIVERSE,WORLD)
            seen=runtime.call_function(UNIVERSE,'adventure.look',role,{})['result']['scene']
            self.assertEqual((seen['meta']['xp'],seen['entities']['hero']['hp']),(900,5))
            upgraded=runtime.call_function(UNIVERSE,'adventure.level_up',role,{'revision':0},operation_id='level3')
            self.assertEqual((upgraded['result']['scene']['meta']['level'],upgraded['result']['scene']['entities']['hero']['hp']),(3,5))
            saved=runtime.get_state(UNIVERSE,'campaign:'+role,'state')['value']
            self.assertEqual((saved['version'],saved['xp'],saved['rewards']['seal_trial']['xp']),(2,900,600))
