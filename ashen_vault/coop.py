"""Bounded shared-state co-op preview for 1-3 independent identities."""
from copy import deepcopy
from hashlib import sha256
import json

from agent_world import FunctionSpec, FunctionOutcome, StateRule
from agent_world.errors import RuleViolation

from .characters import hero_for, build_for, spell_slot_capacity
from .content import combatant
from .engine import apply as battle_apply, active, RulesError
from .rules import incapacitated

def schema(props=None, required=()):
    return {'type':'object','properties':props or {},'required':list(required),'additionalProperties':False}


PARTY_ID={'type':'string','minLength':8,'maxLength':24,'pattern':'^[a-f0-9]+$'}
INVITE={'type':'string','minLength':16,'maxLength':64}
CLASS={'type':'string','enum':['fighter','rogue','wizard']}
TURN={'type':'integer','minimum':1}
BOOL={'type':'boolean'}

PARTY_STATE=schema({
    'version':{'type':'integer','minimum':1},
    'revision':{'type':'integer','minimum':0},
    'party_id':PARTY_ID,
    'owner_role_id':{'type':'string'},
    'invite_hash':{'type':'string'},
    'phase':{'enum':['forming','active','complete','retired']},
    'members':{'type':'object','additionalProperties':{'type':'object'}},
    'battle':{'type':['object','null']},
    'rewards':{'type':'object'},
    'seconds':{'type':'integer','minimum':0},
    'rest_requests':{'type':'object','additionalProperties':{'type':'string'}},
},('version','revision','party_id','owner_role_id','invite_hash','phase','members','battle','rewards','seconds','rest_requests'))


def scope_for(party_id):return 'party:'+party_id


def _raw_party(ctx, scope):
    row=ctx.conn.execute(
        "SELECT value_json,deleted FROM world_state WHERE universe=? AND scope=? AND state_key='state'",
        (ctx.universe,scope),
    ).fetchone()
    if row is None or row['deleted']:return None
    return json.loads(row['value_json'])


def authorize_party_state(ctx,scope,key,access):
    if key!='state' or not scope.startswith('party:'):return False
    if ctx.function_id in ('party.create','party.join'):return True
    state=_raw_party(ctx,scope)
    return state is not None and any(member.get('role_id')==ctx.actor_role_id for member in state['members'].values())


def load_party(ctx,party_id):
    state=ctx.get_state(scope_for(party_id),'state')
    if state is None:raise RuleViolation('PartyNotFound')
    return state


def seat_for(state,role_id):
    return next((seat for seat,member in state['members'].items() if member['role_id']==role_id),None)


def _member(role_id,class_key,seat):
    hero=hero_for(class_key);hero.update(id=seat,team='heroes')
    return {'role_id':role_id,'class_key':class_key,'build':build_for(class_key),'hero':hero,
            'level':1,'xp':0,'gold':0,'potions':0,'ready':False,
            'second_wind':2 if class_key=='fighter' else 0,
            'spell_slots':spell_slot_capacity(1) if class_key=='wizard' else {'1':0,'2':0}}


def _random_hex(ctx,parts):
    return ''.join(f'{ctx.random_int(0,0x7fffffff):08x}' for _ in range(parts))


def create(ctx,args):
    class_key=args['class_key']
    for _ in range(4):
        party_id=_random_hex(ctx,1)
        if ctx.get_state(scope_for(party_id),'state') is None:break
    else:raise RuleViolation('PartyIdCollision')
    invite=_random_hex(ctx,2)
    state={'version':1,'revision':0,'party_id':party_id,'owner_role_id':ctx.actor_role_id,
           'invite_hash':sha256(invite.encode()).hexdigest(),'phase':'forming',
           'members':{'p1':_member(ctx.actor_role_id,class_key,'p1')},'battle':None,
           'rewards':{},'seconds':0,'rest_requests':{}}
    ctx.set_state(scope_for(party_id),'state',state,expected_version=0)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'invite_code':invite})


def join(ctx,args):
    state=load_party(ctx,args['party_id'])
    if seat_for(state,ctx.actor_role_id):
        return FunctionOutcome({'party':project(state,ctx.actor_role_id),'already_joined':True})
    if state['phase']!='forming':raise RuleViolation('PartyAlreadyStarted')
    if len(state['members'])>=3:raise RuleViolation('PartyFull')
    if sha256(args['invite_code'].encode()).hexdigest()!=state['invite_hash']:raise RuleViolation('InvalidPartyInvite')
    seat=next(seat for seat in ('p1','p2','p3') if seat not in state['members'])
    state['members'][seat]=_member(ctx.actor_role_id,args['class_key'],seat);state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'seat':seat})


def _require_member(state,ctx):
    seat=seat_for(state,ctx.actor_role_id)
    if seat is None:raise RuleViolation('NotPartyMember')
    return seat


def ready(ctx,args):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    if state['phase']!='forming':raise RuleViolation('PartyAlreadyStarted')
    state['members'][seat]['ready']=args['ready'];state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def _party_battle(state,draw):
    actors={}
    owners={}
    positions={'p1':[3,2],'p2':[3,3],'p3':[3,4]}
    for seat,member in state['members'].items():
        hero=deepcopy(member['hero']);hero.update(id=seat,team='heroes',position=positions[seat],
            action=True,reaction=True,bonus_action=True,extra_actions=0)
        actors[seat]=hero;owners[seat]=member['role_id']
    enemy=combatant('warden');enemy.update(id='enemy',name='结队守卫',team='enemy',position=[4,3],
        hp=12+8*(len(actors)-1),max_hp=12+8*(len(actors)-1),nonlethal=True)
    actors['enemy']=enemy;owners['enemy']='world:npc'
    battle={'phase':'lobby','owners':owners,'actors':actors,'order':[],'initiative':{},'index':0,
            'round':0,'turn_id':0,'pending':None,'window_serial':0,'winner':None}
    first=sorted(state['members'])[0]
    return battle_apply(battle,first,'begin',{},draw)[0]


def _sync_members(state):
    if not state['battle']:return
    for seat,member in state['members'].items():
        if seat in state['battle']['actors']:member['hero']=deepcopy(state['battle']['actors'][seat])


def _settle(state):
    battle=state['battle']
    if not battle or battle['phase']!='complete':return
    _sync_members(state)
    if battle['winner']=='heroes' and 'coop_guard' not in state['rewards']:
        beneficiaries=sorted(state['members'])
        state['rewards']['coop_guard']={'xp_each':50,'gold_each':5,'beneficiaries':beneficiaries}
        for seat in beneficiaries:
            state['members'][seat]['xp']+=50;state['members'][seat]['gold']+=5
    state['phase']='complete'


def _advance_npc(state,draw):
    for _ in range(8):
        battle=state['battle']
        if not battle or battle['phase']!='active':return
        if battle['pending']:
            if battle['pending']['reactor']!='enemy':return
            battle,_=battle_apply(battle,'enemy','react',
                {'window_id':battle['pending']['window_id'],'choice':'attack','knockout':True},draw)
            state['battle']=battle;_settle(state);continue
        if active(battle)!='enemy':return
        enemy=battle['actors']['enemy'];tid=battle['turn_id']
        living=[(seat,a) for seat,a in battle['actors'].items()
                if seat!='enemy' and a['team']=='heroes' and not incapacitated(a)]
        if not living:return
        adjacent_targets=[(seat,a) for seat,a in living
                          if max(abs(a['position'][i]-enemy['position'][i]) for i in (0,1))<=1]
        if enemy['action'] and adjacent_targets:
            target=min(adjacent_targets,key=lambda pair:(pair[1]['hp'],pair[0]))[0]
            battle,_=battle_apply(battle,'enemy','attack',{'turn_id':tid,'target':target,'knockout':True},draw)
        else:
            battle,_=battle_apply(battle,'enemy','end_turn',{'turn_id':tid},draw)
        state['battle']=battle;_settle(state)
    raise RuleViolation('PartyNpcStepBudgetExceeded')


def begin(ctx,args):
    state=load_party(ctx,args['party_id']);_require_member(state,ctx)
    if state['phase']!='forming':raise RuleViolation('PartyAlreadyStarted')
    if not state['members'] or not all(member['ready'] for member in state['members'].values()):
        raise RuleViolation('WaitingForPartyReady')
    state['battle']=_party_battle(state,ctx.random_int);state['phase']='active';state['revision']+=1
    _advance_npc(state,ctx.random_int);_sync_members(state)
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def _combat(ctx,args,command):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    if state['phase']!='active' or not state['battle']:raise RuleViolation('PartyEncounterNotActive')
    battle=state['battle']
    if active(battle)!=seat:raise RuleViolation('NotYourPartyTurn')
    params={'turn_id':args['turn_id']}
    if command=='attack':params.update(target='enemy',knockout=False,use_luck=args.get('use_luck',True))
    try:battle,result=battle_apply(battle,seat,command,params,ctx.random_int)
    except RulesError as exc:raise RuleViolation(str(exc)) from None
    state['battle']=battle;_settle(state)
    if state['phase']=='active':_advance_npc(state,ctx.random_int)
    _sync_members(state);state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'result':result})


def attack(ctx,args):return _combat(ctx,args,'attack')
def end_turn(ctx,args):return _combat(ctx,args,'end_turn')


def rest_request(ctx,args):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    if state['phase'] not in ('complete','retired'):raise RuleViolation('FinishEncounterBeforePartyRest')
    kind=args['kind'];state['rest_requests'][seat]=kind
    requested=set(state['rest_requests'])
    all_seats=set(state['members'])
    completed=False
    if requested==all_seats and {state['rest_requests'][member] for member in all_seats}=={kind}:
        state['seconds']+=3600 if kind=='short' else 28800
        for member in state['members'].values():
            hero=member['hero']
            if kind=='long':
                hero['hp']=hero['max_hp']
                if member['class_key']=='fighter':member['second_wind']=2
                if member['class_key']=='wizard':member['spell_slots']=spell_slot_capacity(member['level'])
            elif member['class_key']=='fighter':
                member['second_wind']=min(2,member['second_wind']+1)
        state['rest_requests']={};completed=True
    state['revision']+=1;ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'rest_completed':completed})


def rest_cancel(ctx,args):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    state['rest_requests'].pop(seat,None);state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def look(ctx,args):
    state=load_party(ctx,args['party_id']);_require_member(state,ctx)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def project(state,role_id):
    seat=seat_for(state,role_id)
    members={key:{'seat':key,'class_key':member['class_key'],'level':member['level'],'xp':member['xp'],
                  'gold':member['gold'],'ready':member['ready'],'hero':deepcopy(member['hero'])}
             for key,member in state['members'].items()}
    battle=deepcopy(state['battle'])
    actions=[]
    if state['phase']=='forming':
        actions.append({'tool':'party.ready','arguments':{'party_id':state['party_id'],'ready':True}})
        if all(member['ready'] for member in state['members'].values()):
            actions.append({'tool':'party.begin','arguments':{'party_id':state['party_id']}})
    elif state['phase']=='active' and battle and active(battle)==seat and not battle['pending']:
        hero=battle['actors'][seat]
        if hero['action'] and not incapacitated(battle['actors']['enemy']):
            actions.append({'tool':'party.attack','arguments':{'party_id':state['party_id'],'turn_id':battle['turn_id']}})
        actions.append({'tool':'party.end_turn','arguments':{'party_id':state['party_id'],'turn_id':battle['turn_id']}})
    elif state['phase'] in ('complete','retired'):
        for kind in ('short','long'):
            actions.append({'tool':'party.rest_request','arguments':{'party_id':state['party_id'],'kind':kind}})
    return {'party_id':state['party_id'],'revision':state['revision'],'phase':state['phase'],'your_seat':seat,
            'members':members,'battle':battle,'rewards':deepcopy(state['rewards']),'seconds':state['seconds'],
            'rest_requests':deepcopy(state['rest_requests']),'actions':actions}


def spec(name,handler,props=None,required=(),access='write',description=''):
    return FunctionSpec(name,handler,schema(props or {},required),access=access,description=description)


SPECS=(
    spec('party.create',create,{'class_key':CLASS},('class_key',),description='Create one private shared-state party and receive a replay-safe invite code.'),
    spec('party.join',join,{'party_id':PARTY_ID,'invite_code':INVITE,'class_key':CLASS},('party_id','invite_code','class_key'),description='Join a forming party with its invite code; one identity receives one seat.'),
    spec('party.look',look,{'party_id':PARTY_ID},('party_id',),access='read',description='Read a party only when your identity is a member.'),
    spec('party.ready',ready,{'party_id':PARTY_ID,'ready':BOOL},('party_id','ready'),description='Set only your own ready flag.'),
    spec('party.begin',begin,{'party_id':PARTY_ID},('party_id',),description='Start only after every current member is ready. NPC turns are world-controlled.'),
    spec('party.attack',attack,{'party_id':PARTY_ID,'turn_id':TURN,'use_luck':BOOL},('party_id','turn_id'),description='Attack on your own observed party turn; no client dice or outcome.'),
    spec('party.end_turn',end_turn,{'party_id':PARTY_ID,'turn_id':TURN},('party_id','turn_id'),description='End only your own observed party turn.'),
    spec('party.rest_request',rest_request,{'party_id':PARTY_ID,'kind':{'enum':['short','long']}},('party_id','kind'),description='Request party downtime. Shared time advances only after every current member requests the same rest kind.'),
    spec('party.rest_cancel',rest_cancel,{'party_id':PARTY_ID},('party_id',),description='Cancel only your own pending rest request.'),
)
STATE_RULE=StateRule('party:','state',PARTY_STATE)
}
INVITE={'type':'string','minLength':16,'maxLength':64}
CLASS={'type':'string','enum':['fighter','rogue','wizard']}
TURN={'type':'integer','minimum':1}
BOOL={'type':'boolean'}

PARTY_STATE=schema({
    'version':{'type':'integer','minimum':1},
    'revision':{'type':'integer','minimum':0},
    'party_id':PARTY_ID,
    'owner_role_id':{'type':'string'},
    'invite_hash':{'type':'string'},
    'phase':{'enum':['forming','active','complete','retired']},
    'members':{'type':'object','additionalProperties':{'type':'object'}},
    'battle':{'type':['object','null']},
    'rewards':{'type':'object'},
    'seconds':{'type':'integer','minimum':0},
    'rest_requests':{'type':'object','additionalProperties':{'type':'string'}},
},('version','revision','party_id','owner_role_id','invite_hash','phase','members','battle','rewards','seconds','rest_requests'))


def scope_for(party_id):return 'party:'+party_id


def _raw_party(ctx, scope):
    row=ctx.conn.execute(
        "SELECT value_json,deleted FROM world_state WHERE universe=? AND scope=? AND state_key='state'",
        (ctx.universe,scope),
    ).fetchone()
    if row is None or row['deleted']:return None
    return json.loads(row['value_json'])


def authorize_party_state(ctx,scope,key,access):
    if key!='state' or not scope.startswith('party:'):return False
    if ctx.function_id in ('party.create','party.join'):return True
    state=_raw_party(ctx,scope)
    return state is not None and any(member.get('role_id')==ctx.actor_role_id for member in state['members'].values())


def load_party(ctx,party_id):
    state=ctx.get_state(scope_for(party_id),'state')
    if state is None:raise RuleViolation('PartyNotFound')
    return state


def seat_for(state,role_id):
    return next((seat for seat,member in state['members'].items() if member['role_id']==role_id),None)


def _member(role_id,class_key,seat):
    hero=hero_for(class_key);hero.update(id=seat,team='heroes')
    return {'role_id':role_id,'class_key':class_key,'build':build_for(class_key),'hero':hero,
            'level':1,'xp':0,'gold':0,'potions':0,'ready':False,
            'second_wind':2 if class_key=='fighter' else 0,
            'spell_slots':spell_slot_capacity(1) if class_key=='wizard' else {'1':0,'2':0}}


def _random_hex(ctx,parts):
    return ''.join(f'{ctx.random_int(0,0x7fffffff):08x}' for _ in range(parts))


def create(ctx,args):
    class_key=args['class_key']
    for _ in range(4):
        party_id=_random_hex(ctx,1)
        if ctx.get_state(scope_for(party_id),'state') is None:break
    else:raise RuleViolation('PartyIdCollision')
    invite=_random_hex(ctx,2)
    state={'version':1,'revision':0,'party_id':party_id,'owner_role_id':ctx.actor_role_id,
           'invite_hash':sha256(invite.encode()).hexdigest(),'phase':'forming',
           'members':{'p1':_member(ctx.actor_role_id,class_key,'p1')},'battle':None,
           'rewards':{},'seconds':0,'rest_requests':{}}
    ctx.set_state(scope_for(party_id),'state',state,expected_version=0)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'invite_code':invite})


def join(ctx,args):
    state=load_party(ctx,args['party_id'])
    if seat_for(state,ctx.actor_role_id):
        return FunctionOutcome({'party':project(state,ctx.actor_role_id),'already_joined':True})
    if state['phase']!='forming':raise RuleViolation('PartyAlreadyStarted')
    if len(state['members'])>=3:raise RuleViolation('PartyFull')
    if sha256(args['invite_code'].encode()).hexdigest()!=state['invite_hash']:raise RuleViolation('InvalidPartyInvite')
    seat=next(seat for seat in ('p1','p2','p3') if seat not in state['members'])
    state['members'][seat]=_member(ctx.actor_role_id,args['class_key'],seat);state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'seat':seat})


def _require_member(state,ctx):
    seat=seat_for(state,ctx.actor_role_id)
    if seat is None:raise RuleViolation('NotPartyMember')
    return seat


def ready(ctx,args):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    if state['phase']!='forming':raise RuleViolation('PartyAlreadyStarted')
    state['members'][seat]['ready']=args['ready'];state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def _party_battle(state,draw):
    actors={}
    owners={}
    positions={'p1':[3,2],'p2':[3,3],'p3':[3,4]}
    for seat,member in state['members'].items():
        hero=deepcopy(member['hero']);hero.update(id=seat,team='heroes',position=positions[seat],
            action=True,reaction=True,bonus_action=True,extra_actions=0)
        actors[seat]=hero;owners[seat]=member['role_id']
    enemy=combatant('warden');enemy.update(id='enemy',name='结队守卫',team='enemy',position=[4,3],
        hp=12+8*(len(actors)-1),max_hp=12+8*(len(actors)-1),nonlethal=True)
    actors['enemy']=enemy;owners['enemy']='world:npc'
    battle={'phase':'lobby','owners':owners,'actors':actors,'order':[],'initiative':{},'index':0,
            'round':0,'turn_id':0,'pending':None,'window_serial':0,'winner':None}
    first=sorted(state['members'])[0]
    return battle_apply(battle,first,'begin',{},draw)[0]


def _sync_members(state):
    if not state['battle']:return
    for seat,member in state['members'].items():
        if seat in state['battle']['actors']:member['hero']=deepcopy(state['battle']['actors'][seat])


def _settle(state):
    battle=state['battle']
    if not battle or battle['phase']!='complete':return
    _sync_members(state)
    if battle['winner']=='heroes' and 'coop_guard' not in state['rewards']:
        beneficiaries=sorted(state['members'])
        state['rewards']['coop_guard']={'xp_each':50,'gold_each':5,'beneficiaries':beneficiaries}
        for seat in beneficiaries:
            state['members'][seat]['xp']+=50;state['members'][seat]['gold']+=5
    state['phase']='complete'


def _advance_npc(state,draw):
    for _ in range(8):
        battle=state['battle']
        if not battle or battle['phase']!='active':return
        if battle['pending']:
            if battle['pending']['reactor']!='enemy':return
            battle,_=battle_apply(battle,'enemy','react',
                {'window_id':battle['pending']['window_id'],'choice':'attack','knockout':True},draw)
            state['battle']=battle;_settle(state);continue
        if active(battle)!='enemy':return
        enemy=battle['actors']['enemy'];tid=battle['turn_id']
        living=[(seat,a) for seat,a in battle['actors'].items()
                if seat!='enemy' and a['team']=='heroes' and not incapacitated(a)]
        if not living:return
        adjacent_targets=[(seat,a) for seat,a in living
                          if max(abs(a['position'][i]-enemy['position'][i]) for i in (0,1))<=1]
        if enemy['action'] and adjacent_targets:
            target=min(adjacent_targets,key=lambda pair:(pair[1]['hp'],pair[0]))[0]
            battle,_=battle_apply(battle,'enemy','attack',{'turn_id':tid,'target':target,'knockout':True},draw)
        else:
            battle,_=battle_apply(battle,'enemy','end_turn',{'turn_id':tid},draw)
        state['battle']=battle;_settle(state)
    raise RuleViolation('PartyNpcStepBudgetExceeded')


def begin(ctx,args):
    state=load_party(ctx,args['party_id']);_require_member(state,ctx)
    if state['phase']!='forming':raise RuleViolation('PartyAlreadyStarted')
    if not state['members'] or not all(member['ready'] for member in state['members'].values()):
        raise RuleViolation('WaitingForPartyReady')
    state['battle']=_party_battle(state,ctx.random_int);state['phase']='active';state['revision']+=1
    _advance_npc(state,ctx.random_int);_sync_members(state)
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def _combat(ctx,args,command):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    if state['phase']!='active' or not state['battle']:raise RuleViolation('PartyEncounterNotActive')
    battle=state['battle']
    if active(battle)!=seat:raise RuleViolation('NotYourPartyTurn')
    params={'turn_id':args['turn_id']}
    if command=='attack':params.update(target='enemy',knockout=False,use_luck=args.get('use_luck',True))
    try:battle,result=battle_apply(battle,seat,command,params,ctx.random_int)
    except RulesError as exc:raise RuleViolation(str(exc)) from None
    state['battle']=battle;_settle(state)
    if state['phase']=='active':_advance_npc(state,ctx.random_int)
    _sync_members(state);state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'result':result})


def attack(ctx,args):return _combat(ctx,args,'attack')
def end_turn(ctx,args):return _combat(ctx,args,'end_turn')


def rest_request(ctx,args):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    if state['phase']=='active':raise RuleViolation('FinishEncounterBeforePartyRest')
    kind=args['kind'];state['rest_requests'][seat]=kind
    requested=set(state['rest_requests'])
    all_seats=set(state['members'])
    completed=False
    if requested==all_seats and {state['rest_requests'][member] for member in all_seats}=={kind}:
        state['seconds']+=3600 if kind=='short' else 28800
        for member in state['members'].values():
            hero=member['hero']
            if kind=='long':
                hero['hp']=hero['max_hp']
                if member['class_key']=='fighter':member['second_wind']=2
                if member['class_key']=='wizard':member['spell_slots']=spell_slot_capacity(member['level'])
            elif member['class_key']=='fighter':
                member['second_wind']=min(2,member['second_wind']+1)
        state['rest_requests']={};completed=True
    state['revision']+=1;ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id),'rest_completed':completed})


def rest_cancel(ctx,args):
    state=load_party(ctx,args['party_id']);seat=_require_member(state,ctx)
    state['rest_requests'].pop(seat,None);state['revision']+=1
    ctx.set_state(scope_for(state['party_id']),'state',state)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def look(ctx,args):
    state=load_party(ctx,args['party_id']);_require_member(state,ctx)
    return FunctionOutcome({'party':project(state,ctx.actor_role_id)})


def project(state,role_id):
    seat=seat_for(state,role_id)
    members={key:{'seat':key,'class_key':member['class_key'],'level':member['level'],'xp':member['xp'],
                  'gold':member['gold'],'ready':member['ready'],'hero':deepcopy(member['hero'])}
             for key,member in state['members'].items()}
    battle=deepcopy(state['battle'])
    actions=[]
    if state['phase']=='forming':
        actions.append({'tool':'party.ready','arguments':{'party_id':state['party_id'],'ready':True}})
        if all(member['ready'] for member in state['members'].values()):
            actions.append({'tool':'party.begin','arguments':{'party_id':state['party_id']}})
    elif state['phase']=='active' and battle and active(battle)==seat and not battle['pending']:
        hero=battle['actors'][seat]
        if hero['action'] and not incapacitated(battle['actors']['enemy']):
            actions.append({'tool':'party.attack','arguments':{'party_id':state['party_id'],'turn_id':battle['turn_id']}})
        actions.append({'tool':'party.end_turn','arguments':{'party_id':state['party_id'],'turn_id':battle['turn_id']}})
    elif state['phase'] in ('complete','retired'):
        for kind in ('short','long'):
            actions.append({'tool':'party.rest_request','arguments':{'party_id':state['party_id'],'kind':kind}})
    return {'party_id':state['party_id'],'revision':state['revision'],'phase':state['phase'],'your_seat':seat,
            'members':members,'battle':battle,'rewards':deepcopy(state['rewards']),'seconds':state['seconds'],
            'rest_requests':deepcopy(state['rest_requests']),'actions':actions}


def spec(name,handler,props=None,required=(),access='write',description=''):
    return FunctionSpec(name,handler,schema(props or {},required),access=access,description=description)


SPECS=(
    spec('party.create',create,{'class_key':CLASS},('class_key',),description='Create one private shared-state party and receive a replay-safe invite code.'),
    spec('party.join',join,{'party_id':PARTY_ID,'invite_code':INVITE,'class_key':CLASS},('party_id','invite_code','class_key'),description='Join a forming party with its invite code; one identity receives one seat.'),
    spec('party.look',look,{'party_id':PARTY_ID},('party_id',),access='read',description='Read a party only when your identity is a member.'),
    spec('party.ready',ready,{'party_id':PARTY_ID,'ready':BOOL},('party_id','ready'),description='Set only your own ready flag.'),
    spec('party.begin',begin,{'party_id':PARTY_ID},('party_id',),description='Start only after every current member is ready. NPC turns are world-controlled.'),
    spec('party.attack',attack,{'party_id':PARTY_ID,'turn_id':TURN,'use_luck':BOOL},('party_id','turn_id'),description='Attack on your own observed party turn; no client dice or outcome.'),
    spec('party.end_turn',end_turn,{'party_id':PARTY_ID,'turn_id':TURN},('party_id','turn_id'),description='End only your own observed party turn.'),
    spec('party.rest_request',rest_request,{'party_id':PARTY_ID,'kind':{'enum':['short','long']}},('party_id','kind'),description='Request party downtime. Shared time advances only after every current member requests the same rest kind.'),
    spec('party.rest_cancel',rest_cancel,{'party_id':PARTY_ID},('party_id',),description='Cancel only your own pending rest request.'),
)
STATE_RULE=StateRule('party:','state',PARTY_STATE)
