import unittest
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from tests.live import LiveServer


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mcp_and_http_clients_share_rules_and_receipts(self):
        with LiveServer() as server:
            with httpx.Client(trust_env=False,timeout=10,base_url=server.url) as other:
                r=other.post('/v1/functions/vault.join/invoke',headers={'Authorization':'Bearer '+server.tokens['sentinel']},
                    json={'operation_id':'join-sentinel','arguments':{'seat':'sentinel'}})
                self.assertEqual(r.status_code,200)
                async with httpx.AsyncClient(trust_env=False,timeout=15,headers={'Authorization':'Bearer '+server.tokens['warden']}) as http:
                    async with streamable_http_client(server.url+'/mcp',http_client=http) as (read,write):
                        async with ClientSession(read,write) as session:
                            await session.initialize()
                            listed=await session.list_tools()
                            self.assertIn('vault.join',{tool.name for tool in listed.tools})
                            joined=await session.call_tool('vault.join',arguments={'operation_id':'join-warden','arguments':{'seat':'warden'}})
                            self.assertFalse(joined.is_error,joined.structured_content)
                            start=await session.call_tool('vault.begin',arguments={'operation_id':'begin-once','arguments':{}})
                            self.assertFalse(start.is_error,start.structured_content)
                            replay=await session.call_tool('vault.begin',arguments={'operation_id':'begin-once','arguments':{}})
                            self.assertTrue(replay.structured_content['replayed'])
                            self.assertEqual(start.structured_content['random_draws'],replay.structured_content['random_draws'])
                            seen=await session.call_tool('vault.look',arguments={'arguments':{}})
                            self.assertFalse(seen.is_error)
                            self.assertEqual(seen.structured_content['result']['scene']['phase'],'active')
                            self.assertEqual(seen.structured_content['result']['your_seat'],'warden')
                public=other.post('/v1/public/views/battle/snapshot',json={}).json()['snapshot']
                self.assertEqual(public['meta']['order'],start.structured_content['result']['result']['order'])
                self.assertNotIn('awid_',str(public))
                original=other.get('/v1/whoami',headers={'Authorization':'Bearer '+server.tokens['warden']}).json()['role_id']
                server.stop();server.start()
                who=other.get('/v1/whoami',headers={'Authorization':'Bearer '+server.tokens['warden']})
                self.assertEqual(who.json()['role_id'],original)
                resumed=other.post('/v1/functions/vault.look/invoke',headers={'Authorization':'Bearer '+server.tokens['warden']},json={'arguments':{}})
                self.assertEqual(resumed.json()['result']['scene']['turn_id'],1)
