"""Private campaign adapter: no new login protocol, public RPG state, or client RNG."""
from hashlib import sha256
from agent_world import WorldDefinition, FunctionSpec, StateRule, FunctionOutcome, ViewSpec, PresentationCue
from agent_world.errors import RuleViolation
from .campaign_content import new_campaign
from .campaign import apply, view
from .engine import RulesError
from .coop import SPECS as PARTY_SPECS, STATE_RULE as PARTY_STATE_RULE, authorize_party_state

UNIVERSE='ashen-vault-ember'


def schema(props=None, required=()):
    return {'type':'object','properties':props or {},'required':list(required),'additionalProperties':False}


def load(ctx):return ctx.get_state('campaign:'+ctx.actor_role_id,'state')
def owned(ctx,scope,key,access):
    if scope=='campaign:'+ctx.actor_role_id and key=='state':return True
    if scope.startswith('party:'):return authorize_party_state(ctx,scope,key,access)
    return False


def cues_for(ctx,events):
    action=sha256((ctx.universe+'|'+ctx.actor_role_id+'|'+ctx.operation_id).encode()).hexdigest()[:24]
    cues=[]
    for index,event in enumerate(events):
        cue=PresentationCue(cue_id=f'{action}:{index}',subject_id='hero',channel='action',phase='finish',name='campaign.'+event['kind'],
             data={'schema':'ashen-campaign/2','action_id':action,'step':index,'caused_by':f'{action}:{index-1}' if index else None,
                   'scene_id':'adventure:'+ctx.actor_role_id,'event':event['data'],'frame':event['frame']})
        cues.append(cue)
    return cues


def join(ctx,args):
    state=load(ctx)
    if state is not None:return FunctionOutcome({'scene':view(state),'already_joined':True,'cues':[]})
    state=new_campaign(ctx.actor_role_id,args.get('class_key','fighter'));ctx.set_state('campaign:'+ctx.actor_role_id,'state',state,expected_version=0)
    cues=cues_for(ctx,[{'kind':'joined','data':{'origin':'world_rules'},'frame':view(state)}])
    return FunctionOutcome({'scene':view(state),'cues':[c.event(ctx.actor_role_id).payload for c in cues]},tuple(c.event(ctx.actor_role_id) for c in cues))


def handler(command):
    def run(ctx,args):
        state=load(ctx)
        if state is None:raise RuleViolation('JoinAdventureFirst')
        try:updated,events=apply(state,command,args,ctx.random_int)
        except RulesError as exc:raise RuleViolation(str(exc)) from None
        ctx.set_state('campaign:'+ctx.actor_role_id,'state',updated)
        cues=cues_for(ctx,events)
        return FunctionOutcome({'scene':view(updated),'cues':[c.event(ctx.actor_role_id).payload for c in cues]},tuple(c.event(ctx.actor_role_id) for c in cues))
    return run


def look(ctx,args):return FunctionOutcome({'scene':view(load(ctx))})
def scene(ctx,args):return view(load(ctx))
def bootstrap(ctx):return {'scene':view(load(ctx)),'rules_scope':'G2A constrained Fighter/Rogue/Wizard 1-3 solo growth; finite implemented spell/action list, not full SRD or co-op yet.'}

REV={'type':'integer','minimum':0};TURN={'type':'integer','minimum':1};TEXT={'type':'string','minLength':1,'maxLength':32};BOOL={'type':'boolean'}
CELL={'type':'array','items':{'type':'integer','minimum':0,'maximum':13},'minItems':2,'maxItems':2}
CLASS={'type':'string','enum':['fighter','rogue','wizard']}
SPECS=[FunctionSpec('adventure.join',join,schema({'class_key':CLASS}),description='Initialize your own campaign once with an audited Fighter, Rogue, or Wizard build. The identity already belongs to you; does not create a role or token.'),
       FunctionSpec('adventure.look',look,schema(),access='read',description='Read your private current scene, available actions, revision and any turn/reaction/check decision.')]


def register(name,props=None,required=(),description=''):
    props={'revision':REV,**(props or {})}
    SPECS.append(FunctionSpec('adventure.'+name,handler(name),schema(props,('revision',*required)),description=description or 'Submit one intent with current adventure revision. Never supply outcomes; server validates and resolves.'))

register('travel',{'destination':TEXT},('destination',),'Travel only to a currently offered adjacent region; hidden state is not client-authoritative.')
register('interact',{'target':TEXT,'use_luck':BOOL},('target',),'Use an interaction offered by look. Rewards are persistent and cannot be collected with new IDs.')
register('resolve_check',{'choice':{'enum':['tactical','accept']}},('choice',),'Resolve a pending failed ability check. Tactical Mind consumes Second Wind only if the bonus changes it to success.')
register('level_up',{'style':{'enum':['defense','dueling']}},(), 'At 300/900 XP apply the next audited class level. Fighter chooses its level-2 style; level 3 uses the fixed SRD subclass for this preview. No free heal.')
register('equip',{'weapon':TEXT},('weapon',),'Prepare one supported Sap weapon at camp, keeping the shield. Combat equipment swapping is not exposed.')
register('rest',{'kind':{'enum':['short','long']}},('kind',),'Camp-only complete downtime: short 60 minutes, long 480 minutes. Long rests cannot start within 16 fictional hours of the previous finish.')
for name in ('spend_hit_die','second_wind','potion','action_surge','retire','recover_posture','buy_potion'):register(name)
register('cunning_action',{'choice':{'enum':['dash','disengage']},'turn_id':TURN},('choice','turn_id'),'Rogue 2+: spend the current Bonus Action on Dash or Disengage.')
register('steady_aim',{'turn_id':TURN},('turn_id',),'Rogue 3+: if you have not moved this turn, spend the Bonus Action, set Speed to 0, and gain Advantage on the next attack this turn.')
register('arcane_recovery',{'slot_level':{'type':'integer','minimum':1,'maximum':2},'count':{'type':'integer','minimum':1,'maximum':2}},('slot_level','count'),'Wizard only, after a completed short rest; recover slots within the SRD half-level rounded-up budget once per Long Rest.')
register('cast',{'spell':{'enum':['mage_armor','magic_missile','ray_of_frost']},'target':TEXT,'slot_level':{'type':'integer','minimum':1,'maximum':2},'turn_id':TURN,'use_luck':BOOL},('spell',),'Cast only the finite implemented Wizard spell set. In combat use the current turn_id; the server spends slots, rolls attacks/damage, and applies effects.')
for name in ('dash','dodge','disengage','drop_prone','stand','end_turn','approach','withdraw','escape'):register(name,{'turn_id':TURN},('turn_id',))
register('move',{'turn_id':TURN,'path':{'type':'array','items':CELL,'minItems':1,'maxItems':12}},('turn_id','path'))
register('attack',{'turn_id':TURN,'target':TEXT,'knockout':BOOL,'use_luck':BOOL},('turn_id','target'))
register('react',{'window_id':TEXT,'choice':{'enum':['attack','decline']},'knockout':BOOL,'use_luck':BOOL},('window_id','choice'))
SPECS.extend(PARTY_SPECS)
INITIAL=new_campaign('schema-example')
STATE=schema({key: {'type': 'integer' if type(value) is int else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'boolean' if type(value) is bool else ['object','string','null']} for key,value in INITIAL.items()},tuple(INITIAL))
WORLD=WorldDefinition('ashen-vault-ember','Ashen Vault: Lost Ember G2 preview',tuple(SPECS),state_rules=(StateRule('campaign:','state',STATE),PARTY_STATE_RULE),
    state_authorizer=owned,bootstrap=bootstrap,views=(ViewSpec('adventure',scene,timeline=True),),
    entry_instructions='Use the user-held token for this universe. Read adventure.look, choose one audited class on adventure.join, then use current offered tools/revision. '
    'Fighter/Rogue/Wizard 1-3 constrained solo campaign plus a 1-3 identity shared-state co-op preview; finite rules, not complete SRD. Server rolls and resolves all actions. '
    'Only the user decides their reaction/ability windows; NPCs follow rules with a bounded driver. Reuse operation_id for a retry. '
    'World time, combat turns and animation time are different. No FreeAPI or required background model. Never reveal credentials.')
