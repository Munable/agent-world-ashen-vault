import tempfile
import unittest
from pathlib import Path
from agent_world import WorldRuntime, WorldDefinition, StateRule
from agent_world.world_sdk import install_world
from ashen_vault.campaign_content import new_campaign
from ashen_vault.campaign_world import WORLD

LOOSE={"type":"object"}

class CampaignMigrationTests(unittest.TestCase):
    def test_g1_fighter_state_upgrades_without_resetting_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime=WorldRuntime(Path(temp)/"world.sqlite3")
            old=new_campaign("legacy-role","fighter")
            for key in ("spell_slots","arcane_recovery"):old.pop(key,None)
            old["version"]=1;old["build"].pop("class_key",None);old["build"].pop("supported_weapons",None)
            old["hero"].pop("class_key",None);old["hero"].pop("critical_threshold",None);old["hero"].pop("remarkable_athlete",None)
            old.update(level=2,xp=300,status="completed")
            old["rewards"]={"inscription":{"xp":75,"gold":0,"potions":0},"guard_access":{"xp":75,"gold":0,"potions":0},"ember_delivery":{"xp":150,"gold":20,"potions":0},"seal_trial":{"xp":0,"gold":30,"potions":0,"resolution":"victory"}}
            def init(ctx):ctx.set_state("campaign:legacy-role","state",old)
            legacy=WorldDefinition("ashen-vault-ember","Legacy G1",(),version=1,state_version=1,state_rules=(StateRule("campaign:","state",LOOSE),),initialize=init)
            install_world(runtime,"ashen-vault-ember",legacy);install_world(runtime,"ashen-vault-ember",WORLD)
            state=runtime.get_state("ashen-vault-ember","campaign:legacy-role","state")["value"]
            self.assertEqual((state["version"],state["level"],state["xp"],state["hero"]["hp"]),(2,2,900,12))
            self.assertEqual(state["build"]["class_key"],"fighter")
            self.assertEqual(state["spell_slots"],{"1":0,"2":0})
            self.assertEqual(state["rewards"]["seal_trial"]["xp"],600)

if __name__=="__main__":unittest.main()
