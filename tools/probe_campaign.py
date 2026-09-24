"""Deterministic policy probes, not LLM/player completion-rate estimates."""
import json
import random
from copy import deepcopy
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ashen_vault.campaign import apply,available
from ashen_vault.campaign_content import new_campaign,REWARDS


def invariants(before,state):
    assert state['role_id']==before['role_id']
    assert state['revision']==before['revision']+1
    assert state['seconds']>=before['seconds']
    assert 0<=state['hero']['hp']<=state['hero']['max_hp']
    assert 0<=state['second_wind']<=2 and 0<=state['action_surge']<=1
    assert 0<=state['hit_dice']<=state['level']
    assert state['potions']>=0 and state['gold']>=0
    assert state['xp']==sum(REWARDS[k]['xp'] for k in state['rewards'])
    assert set(before['rewards'])<=set(state['rewards'])
    if state['battle']:
        for actor in state['battle']['actors'].values():assert 0<=actor['hp']<=actor['max_hp'] and actor['movement']>=0


def play(seed,route='fight',style='defense',max_steps=250):
    rng=random.Random(seed);state=new_campaign('simulated-player');steps=0;events_seen=[];abilities=set()
    def act(name,**args):
        nonlocal state,steps
        old=state;state,events=apply(state,name,{'revision':state['revision'],**args},rng.randint)
        invariants(old,state);steps+=1;events_seen.extend(e['kind'] for e in events)
        if name in ('action_surge','second_wind'):abilities.add(name)
        assert steps<=max_steps
    def fight():
        nonlocal state
        for _ in range(180):
            if not state['battle'] or state['status']!='exploring':return
            actions=available(state);assert actions,'Unexpected player deadlock'
            by_name={a['tool'].split('.')[-1]:a for a in actions}
            hero=state['battle']['actors']['hero']
            order=[]
            if hero['hp']<=hero['max_hp']//2:order+=['second_wind','potion']
            order+=['react','action_surge','attack','stand','approach','end_turn']
            chosen=next((by_name[k] for k in order if k in by_name),None);assert chosen
            # A reaction entry may be decline; this policy explicitly accepts it.
            args=dict(chosen['arguments']);args.pop('revision');act(chosen['tool'].split('.')[-1],**args)
        raise AssertionError('Combat failed to reach a player/terminal boundary')
    act('travel',destination='gate');act('interact',target='inscription');act('travel',destination='fork');act('travel',destination='guard')
    act('interact',target='pay_guard' if route=='paid' else 'parley' if route=='parley' else 'challenge');fight()
    if state['status']=='exploring':
        act('travel',destination='shrine')
        while not state['flags'].get('dread_cleared'):
            act('interact',target='dread_recover' if 'frightened' in state['hero']['conditions'] else 'dread')
        act('interact',target='take_ember')
        for room in ('guard','fork','gate','camp'):act('travel',destination=room)
        act('interact',target='deliver');act('level_up',style=style);act('rest',kind='long')
        for room in ('gate','fork','guard','shrine'):act('travel',destination=room)
        act('interact',target='trial');fight()
        if state['status']=='completed' and state['level']==2 and state['xp']>=900:act('level_up')
    return {'ending':state['status'],'level':state['level'],'steps':steps,'hp':state['hero']['hp'],
            'reward_sources':sorted(state['rewards']),'abilities':sorted(abilities),'event_count':len(events_seen)}


def run(count=300):
    groups={};total=0
    for route in ('paid','fight','parley'):
        rows=[play(seed,route) for seed in range(count)]
        assert all(row['ending'] in ('captured','completed') for row in rows)
        groups[route]={'runs':count,'completed':sum(r['ending']=='completed' for r in rows),
                      'captured':sum(r['ending']=='captured' for r in rows),
                      'mean_steps':round(sum(r['steps'] for r in rows)/count,2),'max_steps':max(r['steps'] for r in rows),
                      'reached_level_2_or_more':sum(r['level']>=2 for r in rows),'reached_level_3':sum(r['level']==3 for r in rows),
                      'used_action_surge':sum('action_surge' in r['abilities'] for r in rows)}
        total+=len(rows)
    report={'scope':'Seeded deterministic scripted policy, NOT human or model win rates; no production RNG seed endpoint.',
            'runs':total,'invariants':'passed','routes':groups}
    (ROOT/'test-results').mkdir(exist_ok=True);(ROOT/'test-results/simulation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return report

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,default=300)
    args=parser.parse_args()
    if not 1<=args.count<=2000:parser.error('--count must be 1..2000')
    run(args.count)
