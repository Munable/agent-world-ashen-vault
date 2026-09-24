"""Original six-region solo slice; values are authored, not a generic RPG kernel."""
from copy import deepcopy
from .content import combatant, ARENA
from .characters import build_for, hero_for, spell_slot_capacity

ROOMS = {
 'camp': {'name':'归火营地','position':[1,3],'neighbors':['gate'],'text':'营地提供安全休息和补给。找回火种，再决定是否接受守印者的考验。'},
 'gate': {'name':'旧门厅','position':[4,3],'neighbors':['camp','fork'],'text':'矮人语石碑记载旧墓库的通行誓约。读懂它后才能辨认守卫的职责。'},
 'fork': {'name':'风蚀岔路','position':[7,3],'neighbors':['gate','cache','guard'],'text':'侧道通往一个封闭补给箱，正路由守卫把守。'},
 'cache': {'name':'封闭补给间','position':[7,6],'neighbors':['fork'],'text':'可尝试撬开卡住的箱盖。只有一次有效机会；失败不消失，也不能原地无限重掷。'},
 'guard': {'name':'守卫前厅','position':[10,3],'neighbors':['fork','shrine'],'text':'守卫要求通行费。可以支付、交涉、挑战，也可借一头高大驮兽的遮蔽尝试潜行。守卫以击昏入侵者为目标。'},
 'shrine': {'name':'余烬祭坛','position':[12,3],'neighbors':['guard'],'text':'失落的火种被令人胆寒的余烬低语环绕。先直面恐惧，再决定是否取走火种或接受守印考验。'},
}
WEAPONS = {'flail':{'name':'连枷','die':8,'type':'bludgeoning','mastery':'sap'},
           'morningstar':{'name':'晨星锤','die':8,'type':'piercing','mastery':'sap'},
           'mace':{'name':'硬头锤','die':6,'type':'bludgeoning','mastery':'sap'},
           'shortsword':{'name':'短剑','die':6,'type':'piercing','mastery':'vex','finesse':True},
           'quarterstaff':{'name':'奥术长杖','die':6,'type':'bludgeoning','mastery':None}}
REWARDS = {'inscription':{'xp':75,'gold':0,'potions':0},
           'guard_access':{'xp':75,'gold':0,'potions':0},
           'ember_delivery':{'xp':150,'gold':20,'potions':0},
           'cache':{'xp':0,'gold':10,'potions':2},
           'seal_trial':{'xp':600,'gold':30,'potions':0}}
# Compatibility alias for G1 callers; new campaigns may choose one of three audited builds.
BUILD = build_for('fighter')

def new_campaign(role_id: str, class_key: str = 'fighter') -> dict:
    build = build_for(class_key)
    hero = hero_for(class_key)
    return {'version':2,'revision':0,'role_id':role_id,'room':'camp','visited':['camp'],'status':'exploring',
            'hero':hero,'build':build,'level':1,'xp':0,'gold':68,'potions':1,'hit_dice':1,
            'second_wind':2 if class_key=='fighter' else 0,'action_surge':0,
            'spell_slots':spell_slot_capacity(1) if class_key=='wizard' else {'1':0,'2':0},
            'arcane_recovery':1 if class_key=='wizard' else 0,
            'seconds':0,'last_long_rest_end':-57600,
            'rewards':{},'flags':{},'attempts':[],'pending_check':None,'battle':None,'battle_serial':0,
            'short_rest_open':False,'ending':None}


def make_battle(state: dict, draw) -> dict:
    from .engine import apply
    hero=deepcopy(state['hero']);hero.update(position=[3,2],action=True,reaction=True,bonus_action=True,extra_actions=0)
    hero.pop('sapped_by',None)
    enemy=combatant('warden');enemy.update(id='enemy',name='执誓守卫',team='enemy',size='medium',position=[8,2],nonlethal=True)
    if state['flags'].get('delivered'):
        enemy.update(source='Original trial melee profile',name='守印者',hp=18,max_hp=18,attack_bonus=4,damage_bonus=2)
    battle={'phase':'lobby','owners':{'hero':state['role_id'],'enemy':'world:npc'},'actors':{'hero':hero,'enemy':enemy},
            'order':[],'initiative':{},'index':0,'round':0,'turn_id':0,'pending':None,'window_serial':0,'winner':None}
    return apply(battle,'hero','begin',{},draw)[0]
