"""Original six-region solo slice; values are authored, not a generic RPG kernel."""
from copy import deepcopy
from .content import combatant, ARENA

ROOMS = {
 'camp': {'name':'归火营地','position':[1,3],'neighbors':['gate'],'text':'营地提供安全休息和补给。找回火种，再决定是否接受守印者的考验。'},
 'gate': {'name':'旧门厅','position':[4,3],'neighbors':['camp','fork'],'text':'矮人语石碑记载旧墓库的通行誓约。读懂它后才能辨认守卫的职责。'},
 'fork': {'name':'风蚀岔路','position':[7,3],'neighbors':['gate','cache','guard'],'text':'侧道通往一个封闭补给箱，正路由守卫把守。'},
 'cache': {'name':'封闭补给间','position':[7,6],'neighbors':['fork'],'text':'可尝试撬开卡住的箱盖。只有一次有效机会；失败不消失，也不能原地无限重掷。'},
 'guard': {'name':'守卫前厅','position':[10,3],'neighbors':['fork','shrine'],'text':'守卫要求通行费。可以支付、交涉、挑战，也可借一头高大驮兽的遮蔽尝试潜行。守卫以击昏入侵者为目标。'},
 'shrine': {'name':'余烬祭坛','position':[12,3],'neighbors':['guard'],'text':'失落的火种被令人胆寒的余烬低语环绕。先直面恐惧，再决定是否取走火种或接受守印考验。'},
}
WEAPONS = {'flail':{'name':'连枷','die':8,'type':'bludgeoning'},
           'morningstar':{'name':'晨星锤','die':8,'type':'piercing'},
           'mace':{'name':'硬头锤','die':6,'type':'bludgeoning'}}
REWARDS = {'inscription':{'xp':75,'gold':0,'potions':0},
           'guard_access':{'xp':75,'gold':0,'potions':0},
           'ember_delivery':{'xp':150,'gold':20,'potions':0},
           'cache':{'xp':0,'gold':10,'potions':2},
           'seal_trial':{'xp':0,'gold':30,'potions':0}}
BUILD = {'ruleset':'SRD 5.2.1','class':'Fighter','species':'Halfling','background':'原创守路人（SRD 背景创建规则）',
         'abilities':{'str':17,'dex':13,'con':15,'int':10,'wis':12,'cha':8},
         'ability_source':'标准数组 15/13/14/10/12/8；背景 Str+2、Con+1',
         'background_abilities':['str','dex','con'],'origin_feat':'Skilled','style':'defense','saves':{'str':5,'dex':1,'con':4,'int':0,'wis':1,'cha':-1},
         'skills':{'athletics':5,'perception':3,'medicine':3,'intimidation':1,'stealth':3,'survival':3,'insight':3},
         'skill_sources':{'background':['athletics','perception'],'skilled':['medicine','intimidation','stealth'],'fighter':['survival','insight']},
         'tool':'carpenters_tools','languages':['common','dwarvish','elvish'],
         'masteries':['flail','morningstar','mace'],
         'equipment_budget':{'fighter_gp':155,'fighter_spent_gp':127,'background_gp':50,'background_spent_gp':10,'remaining_gp':68},
         'equipment':['chain_mail','shield','flail','morningstar','mace','dungeoneers_pack','carpenters_tools','travelers_clothes'],
         'starting_potion_source':'营地委托方提供一瓶，不计入 SRD 初始装备预算'}


def new_campaign(role_id: str) -> dict:
    hero = combatant('warden')
    hero.update(source='Audited Fighter 1-2 build',srd_pages=[23,47,48,86,87,90,91,92,95,185,187,192,193],id='hero',name='守路旅人',team='hero',size='small',nimble=True,lucky=True,brave=True,naturally_stealthy=True,ac=19,max_hp=12,hp=12,
                attack_bonus=5,damage_die=8,damage_bonus=3,damage_type='bludgeoning',weapon='flail',mastery='sap',
                death_saves=True,bonus_action=True,extra_actions=0,initiative_bonus=1)
    return {'version':1,'revision':0,'role_id':role_id,'room':'camp','visited':['camp'],'status':'exploring',
            'hero':hero,'build':deepcopy(BUILD),'level':1,'xp':0,'gold':68,'potions':1,'hit_dice':1,
            'second_wind':2,'action_surge':0,'seconds':0,'last_long_rest_end':-57600,
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
