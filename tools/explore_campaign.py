"""Explore offered actions without claiming that random clients are good players."""
import json
import random
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ashen_vault.campaign import apply,available,view
from ashen_vault.campaign_content import new_campaign
from tools.probe_campaign import invariants
from ashen_vault.engine import RulesError


def run(seeds=60,steps=100):
    accepted=0;ended=0;kinds=set();phases=set()
    for seed in range(seeds):
        rng=random.Random(seed);s=new_campaign('fuzz-player')
        for step in range(steps):
            menu=available(s)
            if not menu:ended+=1;break
            if step<70:menu=[a for a in menu if a['tool']!='adventure.retire'] or menu
            action=rng.choice(menu);args=dict(action['arguments']);name=action['tool'].split('.')[-1]
            original=json.dumps(s,sort_keys=True)
            # Read-only projection must neither mutate nor roll.
            view(s);assert original==json.dumps(s,sort_keys=True)
            wrong={**args,'revision':s['revision']+1000}
            try:apply(s,name,wrong,lambda lo,hi:(_ for _ in ()).throw(AssertionError('Rejected intent rolled dice')))
            except RulesError:pass
            else:raise AssertionError('Stale revision was accepted')
            assert original==json.dumps(s,sort_keys=True)
            old=s;s,events=apply(s,name,args,rng.randint)
            invariants(old,s);assert events[-1]['frame']==view(s)
            accepted+=1;kinds.add(name);phases.add('battle' if s['battle'] else s['room'])
    report={'scope':'Seeded exploration of offered actions and stale-intent rejection, not a player success-rate test.',
            'seeds':seeds,'maximum_steps_per_seed':steps,'accepted_actions':accepted,'stale_intents_rejected':accepted,
            'terminal_paths':ended,'action_kinds':sorted(kinds),'phases':sorted(phases),'result':'passed'}
    (ROOT/'test-results').mkdir(exist_ok=True);(ROOT/'test-results/exploration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return report

if __name__=='__main__':run()
