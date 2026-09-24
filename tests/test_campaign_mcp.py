import unittest
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from tests.live import LiveServer


class CampaignMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_mcp_actor_completes_growth_and_resumes_over_http(self):
        with LiveServer(campaign=True) as server:
            token=server.tokens['hero']
            async with httpx.AsyncClient(trust_env=False,timeout=20,headers={'Authorization':'Bearer '+token}) as http:
                async with streamable_http_client(server.url+'/mcp',http_client=http) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize();tools=await session.list_tools()
                        self.assertIn('adventure.level_up',{t.name for t in tools.tools})
                        joined=await session.call_tool('adventure.join',arguments={'operation_id':'mcp-join','arguments':{}})
                        self.assertFalse(joined.is_error,joined.structured_content)
                        revision=0;serial=0;call=None
                        async def act(name,**args):
                            nonlocal revision,serial,call
                            call={'operation_id':'mcp-adventure-'+str(serial),'arguments':{'revision':revision,**args}};serial+=1
                            value=await session.call_tool('adventure.'+name,arguments=call)
                            self.assertFalse(value.is_error,value.structured_content)
                            revision=value.structured_content['result']['scene']['meta']['revision']
                            return value
                        for name,args in [('travel',{'destination':'gate'}),('interact',{'target':'inscription'}),('travel',{'destination':'fork'}),('travel',{'destination':'guard'}),
                                          ('interact',{'target':'pay_guard'}),('travel',{'destination':'shrine'})]:await act(name,**args)
                        result=await act('interact',target='dread')
                        for _ in range(8):
                            actions=result.structured_content['result']['scene']['meta']['actions']
                            if any(a['arguments'].get('target')=='take_ember' for a in actions):break
                            result=await act('interact',target='dread_recover')
                        else:self.fail('Brave recovery did not clear authored dread within bounded MCP test')
                        for name,args in [('interact',{'target':'take_ember'}),('travel',{'destination':'guard'}),('travel',{'destination':'fork'}),
                                          ('travel',{'destination':'gate'}),('travel',{'destination':'camp'}),('interact',{'target':'deliver'}),('level_up',{'style':'defense'})]:result=await act(name,**args)
                        self.assertEqual(result.structured_content['result']['scene']['meta']['level'],2)
                        replay=await session.call_tool('adventure.level_up',arguments=call)
                        self.assertTrue(replay.structured_content['replayed'])
                        self.assertEqual(replay.structured_content['result'],result.structured_content['result'])
            server.stop();server.start()
            async with httpx.AsyncClient(trust_env=False,timeout=10,headers={'Authorization':'Bearer '+token}) as fresh:
                who=await fresh.get(server.url+'/v1/whoami');self.assertEqual(who.status_code,200)
                seen=await fresh.post(server.url+'/v1/functions/adventure.look/invoke',json={'arguments':{}})
                scene=seen.json()['result']['scene'];self.assertEqual(scene['meta']['level'],2);self.assertEqual(scene['meta']['xp'],300)
                self.assertEqual(scene['entities']['hero']['hp'],12)
