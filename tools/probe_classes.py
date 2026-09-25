"""Deterministic cross-class route probes; not human/model win rates."""
import argparse,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ashen_vault.campaign import apply,available
from ashen_vault.campaign_content import new_campaign,REWARDS

def apply_one(state,rng,name,args):
    before=state;state,_=apply(state,name,{'revision':state['revision'],**args},rng.randint)
    assert state['role_id']==before['role_id']
    assert state['build'].get('class_key','fighter')==before['build'].get('class_key','fighter')
    assert state['revision']==before['revision']+1 and state['seconds']>=before['seconds']
    assert 0<=state['hero']['hp']<=state['hero']['max_hp']
    assert state['xp']==sum(REWARDS[key]['xp'] for key in state['rewards'])
    if state['build'].get('class_key')=='wizard':assert all(value>=0 for value in state['spell_slots'].values())
    return state

def offered(state,name,**wanted):
    for item in available(state):
        if item['tool'].split('.')[-1]!=name:continue
        if all(item['arguments'].get(k)==v for k,v in wanted.items()):
            args=dict(item['arguments']);args.pop('revision',None);return args
    return None

def do(state,rng,name,**wanted):
    args=offered(state,name,**wanted)
    if args is None:raise AssertionError(f'missing offered action {name} {wanted}')
    return apply_one(state,rng,name,args)

def fight(state,rng,class_key):
    for _ in range(180):
        if not state['battle'] or state['status']!='exploring':return state
        actions=available(state);assert actions
        hero=state['battle']['actors']['hero'];picked=None
        if hero['hp']<=max(2,hero['max_hp']//2):
            for recovery in ('second_wind','potion'):
                picked=next((a for a in actions if a['tool'].split('.')[-1]==recovery),None)
                if picked:break
        if picked is None and class_key=='wizard':
            casts=[a for a in actions if a['tool'].endswith('.cast') and a['arguments'].get('spell') in ('magic_missile','ray_of_frost')]
            casts.sort(key=lambda a:(a['arguments'].get('spell')!='magic_missile',-a['arguments'].get('slot_level',0)))
            if casts:picked=casts[0]
        order=('react','steady_aim','attack','cunning_action','approach','end_turn') if class_key=='rogue' else (
              'react','action_surge','attack','stand','approach','dodge','end_turn')
        if picked is None:
            for name in order:
                picked=next((a for a in actions if a['tool'].split('.')[-1]==name),None)
                if picked:break
        if picked is None:raise AssertionError('cross-class policy deadlock')
        args=dict(picked['arguments']);args.pop('revision',None)
        state=apply_one(state,rng,picked['tool'].split('.')[-1],args)
    raise AssertionError('combat did not terminate')

def play(seed,class_key,route):
    rng=random.Random(seed);state=new_campaign('probe-'+class_key,class_key)
    armor=offered(state,'cast',spell='mage_armor') if class_key=='wizard' else None
    if armor is not None:state=apply_one(state,rng,'cast',armor)
    state=do(state,rng,'travel',destination='gate');state=do(state,rng,'interact',target='inscription')
    state=do(state,rng,'travel',destination='fork');state=do(state,rng,'travel',destination='guard')
    state=do(state,rng,'interact',target='pay_guard' if route=='paid' else 'parley' if route=='parley' else 'challenge')
    state=fight(state,rng,class_key)
    if state['status']!='exploring':return state
    state=do(state,rng,'travel',destination='shrine')
    for _ in range(10):
        if offered(state,'interact',target='take_ember') is not None:break
        state=do(state,rng,'interact',target='dread_recover' if 'frightened' in state['hero']['conditions'] else 'dread')
    state=do(state,rng,'interact',target='take_ember')
    for room in ('guard','fork','gate','camp'):state=do(state,rng,'travel',destination=room)
    state=do(state,rng,'interact',target='deliver')
    level=offered(state,'level_up')
    if level is None:raise AssertionError('level 2 not offered')
    state=apply_one(state,rng,'level_up',level);state=do(state,rng,'rest',kind='long')
    armor=offered(state,'cast',spell='mage_armor') if class_key=='wizard' else None
    if armor is not None:state=apply_one(state,rng,'cast',armor)
    for room in ('gate','fork','guard','shrine'):state=do(state,rng,'travel',destination=room)
    state=do(state,rng,'interact',target='trial');state=fight(state,rng,class_key)
    if state['status']=='completed' and state['level']==2 and state['xp']>=900:
        level=offered(state,'level_up')
        if level is not None:state=apply_one(state,rng,'level_up',level)
    return state

def run(count):
    groups={}
    for class_key in ('fighter','rogue','wizard'):
        for route in ('paid','fight','parley'):
            rows=[play(seed,class_key,route) for seed in range(count)]
            groups[class_key+':'+route]={'runs':count,'completed':sum(s['status']=='completed' for s in rows),
                'captured':sum(s['status']=='captured' for s in rows),'reached_level_3':sum(s['level']==3 for s in rows)}
    report={'scope':'Deterministic cross-class scripted policies; NOT human or model win rates.',
            'runs':count*9,'groups':groups,'invariants':'passed'}
    (ROOT/'test-results').mkdir(exist_ok=True)
    (ROOT/'test-results/g2-class-simulation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--count',type=int,default=25);args=p.parse_args()
    if not 1<=args.count<=200:p.error('--count must be 1..200')
    run(args.count)
