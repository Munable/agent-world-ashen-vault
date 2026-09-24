"""Actual browser game loop with authoritative server RNG; no autonomous-model claim."""
from pathlib import Path
import json
import os
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import httpx
from playwright.sync_api import sync_playwright,expect
from agent_world import WorldRuntime
from tests.live import LiveServer


def main():
    errors=[];trace=[];requests=[];initial=[];report={}
    output=ROOT/'test-results';output.mkdir(exist_ok=True)
    with LiveServer(campaign=True) as server,sync_playwright() as p:
        try:browser=p.chromium.launch(headless=True)
        except Exception:
            if os.name!='nt':raise
            browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1200,'height':950})
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        def captured(response):
            if response.status!=200:return
            try:
                if response.url.endswith('/v1/views/adventure/snapshot'):
                    value=response.json()
                    if not initial:initial.append(value['snapshot'])
                elif response.url.endswith('/v1/views/timeline'):
                    trace.extend(response.json()['events'])
            except Exception as exc:
                # The intentional lost-response probe can dispose a Chromium response body before
                # this auxiliary evidence listener reads it. Treat only that protocol race as absent
                # evidence; all other capture failures remain page-test errors.
                if 'No resource with given identifier found' not in str(exc):errors.append('evidence capture: '+str(exc))
        page.on('response',captured)
        page.on('request',lambda r:requests.append((r.url,r.post_data or '')))
        def ready(revision=None):
            page.wait_for_function('rev => window.__ashenDebug && !window.__ashenDebug().busy && (rev === null || window.__ashenDebug().revision >= rev)',arg=revision,timeout=20000)
        def connect():
            page.locator('#key').fill(server.tokens['hero']);page.locator('#connect button').click()
            expect(page.locator('#game')).to_be_visible();ready()
            assert page.locator('#key').input_value()==''
        def select(tool,**args):
            ready()
            buttons=page.locator('#actions button')
            for index in range(buttons.count()):
                b=buttons.nth(index)
                if b.get_attribute('data-tool')!='adventure.'+tool:continue
                body=json.loads(b.get_attribute('data-arguments'))
                if all(body.get(k)==v for k,v in args.items()):return b
            raise AssertionError('Missing offered action: '+tool+' '+json.dumps(args))
        def click(tool,wait=True,**args):
            b=select(tool,**args);rev=page.evaluate('window.__ashenDebug().revision');b.click()
            if wait:ready(0 if rev is None else rev+1)
        def observe_effect(effect):
            page.evaluate("""effect=>{
                window.__testFxObserver?.disconnect();window.__testFxSeen=false;
                window.__testFxObserver=new MutationObserver(()=>{
                    if(document.querySelector('[data-effect='+effect+']'))window.__testFxSeen=true;
                });
                window.__testFxObserver.observe(document.querySelector('#board'),{childList:true,subtree:true});
            }""",effect)
        def saw_effect():
            try:page.wait_for_function('window.__testFxSeen === true',timeout=12000)
            except Exception:
                print('PLAYBACK_FAILURE',json.dumps(page.evaluate('window.__ashenDebug()')))
                page.screenshot(path=str(output/'campaign-failed-playback.png'),full_page=True)
                raise
        page.goto(server.url+'/watch',wait_until='networkidle');connect();click('join')
        assert page.evaluate('window.__ashenDebug().revision')==0
        # Drop only the HTTP response after a real committed write.
        def drop_response(route):
            response=route.fetch();assert response.status==200;route.abort('failed')
        page.route('**/v1/functions/adventure.travel/invoke',drop_response,times=1)
        select('travel',destination='gate').click()
        expect(page.locator('#receipt')).to_be_visible(timeout=12000)
        page.locator('#receipt').click();expect(page.locator('#receipt')).to_be_hidden(timeout=12000)
        ready(1);expect(page.locator('#location')).to_have_text('旧门厅')
        report['lost_response_receipt_recovers_without_new_action']=True
        click('interact',target='inscription')
        click('travel',destination='fork');click('travel',destination='guard')
        click('interact',target='pay_guard');click('travel',destination='shrine')
        observe_effect('feedback');click('interact',wait=False,target='dread');saw_effect();ready()
        for _ in range(8):
            can_take=page.evaluate("() => [...document.querySelectorAll('#actions button')].some(b => JSON.parse(b.dataset.arguments).target === 'take_ember')")
            if can_take:break
            click('interact',target='dread_recover')
        else:raise AssertionError('Brave recovery did not clear authored dread within bounded browser probe')
        click('interact',target='take_ember')
        expect(page.locator('#log')).to_contain_text('dread_save')
        report['brave_dread_resolution_has_visible_feedback']=True
        for room in ('guard','fork','gate','camp'):click('travel',destination=room)
        click('interact',target='deliver')
        expect(page.locator('#stats')).to_contain_text('经验 300/300')
        observe_effect('feedback');click('level_up',wait=False,style='defense');saw_effect()
        page.screenshot(path=str(output/'campaign-level-feedback.png'),full_page=True)
        ready();expect(page.locator('#stats')).to_contain_text('战士 2 级')
        expect(page.locator('#stats')).to_contain_text('HP 12/20')
        before=page.evaluate('window.__ashenDebug()');page.select_option('#skin','moon');after=page.evaluate('window.__ashenDebug()')
        assert before['revision']==after['revision'] and before['level']==after['level']
        assert page.locator('#board polygon').count()>0
        page.screenshot(path=str(output/'campaign-moon.png'),full_page=True)
        report.update(actual_browser_growth_1_to_2=True,no_free_upgrade_healing=True,resource_pack_switch_without_world_write=True)
        # Actual process restart and a new browser document use only the saved key.
        server.stop();server.start();page.reload(wait_until='networkidle')
        expect(page.locator('#game')).to_be_hidden();assert page.locator('#details').inner_text()==''
        connect();expect(page.locator('#stats')).to_contain_text('战士 2 级')
        assert page.evaluate('window.__ashenDebug().stats.animated')==0
        report['reload_and_process_restart_restore_without_historical_animation']=True
        click('rest',kind='long')
        for room in ('gate','fork','cache'):click('travel',destination=room)
        # Cache can succeed, fail, or offer Tactical Mind. All are legitimate server outcomes.
        click('interact',target='cache')
        if page.locator('[data-tool="adventure.resolve_check"]').count():click('resolve_check',choice='tactical')
        click('travel',destination='fork');click('travel',destination='guard');click('travel',destination='shrine');click('interact',target='trial')
        attack_feedback=False;used_surge=False
        for _ in range(90):
            ready()
            if page.locator('#ending').is_visible():break
            buttons=page.locator('#actions button');offered=[{'tool':b.get_attribute('data-tool').split('.')[-1],**json.loads(b.get_attribute('data-arguments'))} for b in buttons.all()]
            names={a['tool'] for a in offered}
            # Same explicit bounded policy used by an ordinary manual client, not hidden writes.
            stats=page.locator('#stats').inner_text()
            import re
            match=re.search(r'HP (\d+)/(\d+)',stats);low=match and int(match[1])<=int(match[2])//2
            choices=(['second_wind','potion'] if low else [])+['react','action_surge','attack','stand','approach','end_turn']
            chosen=next(name for name in choices if name in names)
            if chosen=='react':click('react',choice='decline')
            elif chosen=='attack':
                observe_effect('attack');click('attack',wait=False,knockout=True);saw_effect()
                attack_feedback=True;ready()
            else:
                click(chosen)
                if chosen=='action_surge':used_surge=True
        else:raise AssertionError('Browser policy did not reach terminal state')
        assert attack_feedback and used_surge
        expect(page.locator('#ending')).to_be_visible()
        expect(page.locator('#stats')).to_contain_text('经验 300/300')
        report.update(visible_attack_feedback=True,upgraded_action_surge_used_in_later_encounter=True,
                      solo_scripted_enemy=True,terminal_result_observed=True)
        page.screenshot(path=str(output/'campaign-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(output/'campaign-mobile.png'),full_page=True)
        assert page.evaluate('JSON.stringify([localStorage,sessionStorage])')=='[{},{}]'
        assert not context.cookies()
        assert all(server.tokens['hero'] not in url+body for url,body in requests)
        runtime=WorldRuntime(server.db);runtime.revoke_identity_token(runtime.resolve_identity_token(server.tokens['hero'])['token_id'])
        expect(page.locator('#game')).to_be_hidden(timeout=12000)
        assert page.locator('#details').inner_text()=='' and page.locator('#ending').inner_text()==''
        assert page.locator('#log li').count()==0
        assert not errors,errors
        report.update(no_token_in_url_body_or_browser_storage=True,revocation_clears_private_dom=True,mobile_no_overflow=True,page_errors=errors)
        assert trace and initial
        (output/'campaign-trace.json').write_text(json.dumps({'initial':initial[0],'events':trace},ensure_ascii=False,indent=2),encoding='utf-8')
        context.close();browser.close()
    (output/'campaign-browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
