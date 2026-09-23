"""Real browser + independent authenticated HTTP clients; no LLM autonomy claim."""
from pathlib import Path
import json
import os
import sys
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.live import LiveServer
from playwright.sync_api import sync_playwright,expect


def main():
    report={};errors=[];requests=[]
    with LiveServer() as server,sync_playwright() as p:
        try:browser=p.chromium.launch(headless=True)
        except Exception:
            if os.name!='nt':raise
            browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1160,'height':900})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append((r.url,r.headers,r.post_data or '')))
        page.goto(server.url+'/watch')
        expect(page.locator('#status')).to_have_attribute('data-phase','lobby')
        with httpx.Client(base_url=server.url,trust_env=False,timeout=10) as http:
            counter=0
            def invoke(seat,fn,args,operation=None):
                nonlocal counter
                counter+=1
                r=http.post('/v1/functions/vault.'+fn+'/invoke',headers={'Authorization':'Bearer '+server.tokens[seat]},
                    json={'operation_id':operation or f'browser-{counter}','arguments':args})
                assert r.status_code==200,(fn,r.status_code,r.text)
                return r.json()
            for seat in ('warden','sentinel'):invoke(seat,'join',{'seat':seat})
            started=invoke('warden','begin',{})['result']
            mover=started['active'];reactor='sentinel' if mover=='warden' else 'warden'
            expect(page.locator('#status')).to_have_attribute('data-phase','active')
            path=[[4,2],[5,2],[6,1],[7,1]] if mover=='warden' else [[7,2],[6,1],[5,1],[4,1]]
            arrived=invoke(mover,'move',{'turn_id':1,'path':path})
            expected=','.join(map(str,path[-1]))
            expect(page.locator(f'[data-actor={mover}]')).to_have_attribute('data-position',expected)
            retreat=[6,1] if mover=='warden' else [5,1]
            waiting=invoke(mover,'move',{'turn_id':1,'path':[retreat]},'pending-move')
            assert waiting['result']['result']['status']=='awaiting_reaction'
            expect(page.locator('#window')).to_be_visible()
            expect(page.locator(f'[data-actor={mover}]')).to_have_attribute('data-position',expected)
            window=waiting['result']['result']['window_id']
            server.stop();server.start()
            snapshot=http.post('/v1/public/views/battle/snapshot',json={}).json()['snapshot']
            assert snapshot['meta']['pending']['window_id']==window
            reaction=invoke(reactor,'react',{'window_id':window,'choice':'decline'},'reaction-once')
            repeated=invoke(reactor,'react',{'window_id':window,'choice':'decline'},'reaction-once')
            assert repeated['replayed'] and repeated['result']==reaction['result']
            expect(page.locator('#window')).to_be_hidden()
            expect(page.locator(f'[data-actor={mover}]')).to_have_attribute('data-position',','.join(map(str,retreat)))
            final=http.post('/v1/public/views/battle/snapshot',json={}).json()['snapshot']
            assert final['entities'][reactor]['reaction'] is True
            report.update(public_observer=True,server_movement=True,pause_before_departure=True,
                          reaction_persists_after_process_restart=True,off_turn_reaction=True,
                          declined_reaction_not_spent=True,replayed_reaction_not_reapplied=True)
        assert not context.cookies()
        for url,headers,body in requests:
            assert 'authorization' not in headers and 'cookie' not in headers
            assert all(token not in url+body for token in server.tokens.values())
        assert page.evaluate('JSON.stringify([localStorage,sessionStorage])')=='[{},{}]'
        output=ROOT/'test-results';output.mkdir(exist_ok=True)
        page.screenshot(path=str(output/'observer-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(output/'observer-mobile.png'),full_page=True)
        assert not errors,errors
        report.update(no_browser_credentials=True,no_persistent_browser_storage=True,mobile_no_overflow=True,page_errors=errors)
        context.close();browser.close()
    (output/'browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
