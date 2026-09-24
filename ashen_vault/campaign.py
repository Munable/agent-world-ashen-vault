"""Solo campaign logic. All authoritative changes use the caller's world transaction."""
from copy import deepcopy
from math import ceil
from .campaign_content import ROOMS, WEAPONS, REWARDS, make_battle
from .characters import hp_gain, spell_slot_capacity
from .content import ARENA
from .engine import apply as battle_apply, active, adjacent, clear_step, RulesError, require
from .rules import d20, heal, incapacitated, roll, lose_hp, damage_amount


def path_to(battle, actor_id, destination=None):
    # Movement has weighted terrain costs; FIFO BFS can discard a cheaper route.
    from heapq import heappush, heappop
    from itertools import count
    actor=battle['actors'][actor_id];other=battle['actors']['enemy' if actor_id=='hero' else 'hero']
    goal=destination or other['position'];start=tuple(actor['position']);serial=count()
    queue=[(0,next(serial),start,[])];costs={start:0};best=[];best_distance=max(abs(start[i]-goal[i]) for i in (0,1))
    while queue:
        cost,_,point,path=heappop(queue)
        if cost!=costs[point]:continue
        if (destination is not None and list(point)==destination) or (destination is None and adjacent(list(point),other['position']) and clear_step(list(point),other['position'])):return path
        for dx,dy in ((1,0),(0,-1),(0,1),(-1,0),(1,-1),(1,1),(-1,-1),(-1,1)):
            cell=[point[0]+dx,point[1]+dy];key=tuple(cell)
            if not clear_step(list(point),cell) or cell==other['position']:continue
            step=5+(5 if cell in ARENA['difficult'] else 0)+(5 if 'prone' in actor['conditions'] else 0)
            new_cost=cost+step
            if new_cost>actor['movement'] or new_cost>=costs.get(key,10**9):continue
            costs[key]=new_cost;new_path=path+[cell];heappush(queue,(new_cost,next(serial),key,new_path))
            distance=max(abs(cell[i]-goal[i]) for i in (0,1))
            if distance<best_distance:best_distance=distance;best=new_path
    return best


def class_key(s):
    return s['build'].get('class_key', 'fighter')


def level_ready(s):
    return (s['level'] == 1 and s['xp'] >= 300) or (s['level'] == 2 and s['xp'] >= 900)


def _distance_feet(a, b):
    return max(abs(a[0]-b[0]), abs(a[1]-b[1])) * 5


def _clear_spell_path(a, b):
    steps = max(abs(a[0]-b[0]), abs(a[1]-b[1]))
    if steps <= 1:
        return True
    for index in range(1, steps):
        cell = [round(a[0] + (b[0]-a[0]) * index / steps),
                round(a[1] + (b[1]-a[1]) * index / steps)]
        if cell in ARENA['walls']:
            return False
    return True


def _expire_timed_effects(s):
    until = s['flags'].get('mage_armor_until')
    if class_key(s) == 'wizard' and until is not None and s['seconds'] >= until:
        s['flags'].pop('mage_armor_until', None)
        s['hero']['ac'] = s['hero'].get('unarmored_ac', 12)


def view(state):
    if state is None:
        return {'entities':{},'meta':{'joined':False,'actions':[
            {'label':'以 Fighter 开始冒险','tool':'adventure.join','arguments':{'class_key':'fighter'}},
            {'label':'以 Rogue 开始冒险','tool':'adventure.join','arguments':{'class_key':'rogue'}},
            {'label':'以 Wizard 开始冒险','tool':'adventure.join','arguments':{'class_key':'wizard'}},
        ]}}
    s=state;b=s['battle']
    hero=deepcopy(b['actors']['hero'] if b else s['hero'])
    if not b:hero['position']=list(ROOMS[s['room']]['position'])
    entities={'hero':hero}
    if b:entities['enemy']=deepcopy(b['actors']['enemy'])
    known={key:{'name':value['name'],'position':list(value['position']),'visited':key in s['visited']} for key,value in ROOMS.items() if key in s['visited']}
    next_xp=300 if s['level']==1 else 900 if s['level']==2 else None
    if s['status']=='completed' and level_ready(s):
        quest='守印考验完成。完成 3 级职业方向后，本段成长闭环结束。'
    elif s['ending']:
        quest=s['ending']
    elif s['flags'].get('delivered'):
        quest='火种已经归营。回祭坛接受守印考验。' if s['level']>=2 else '火种已经归营。请选择 2 级成长。'
    else:
        quest='带回失落火种；通行可交涉或战斗。'
    meta={'joined':True,'revision':s['revision'],'room':s['room'],'room_name':ROOMS[s['room']]['name'],
          'text':ROOMS[s['room']]['text'],'known_rooms':known,'status':s['status'],'ending':s['ending'],
          'level':s['level'],'xp':s['xp'],'next_xp':next_xp,'gold':s['gold'],'potions':s['potions'],
          'second_wind':s['second_wind'],'action_surge':s['action_surge'],'hit_dice':s['hit_dice'],
          'spell_slots':deepcopy(s.get('spell_slots',{'1':0,'2':0})),'arcane_recovery':s.get('arcane_recovery',0),
          'minutes':s['seconds']/60,'long_rest_wait_seconds':max(0,57600-(s['seconds']-s['last_long_rest_end'])),
          'class_key':class_key(s),'style':s['build'].get('style'),'weapon':hero['weapon'],'build':deepcopy(s['build']),
          'quest':quest,'arena':deepcopy(ARENA) if b else {'width':14,'height':8,'walls':[],'difficult':[]},
          'battle':None,'pending_check':None}
    if b:meta['battle']={key:deepcopy(b[key]) for key in ('phase','round','turn_id','pending','order')};meta['battle']['active']=active(b)
    if s['pending_check']:meta['pending_check']={key:deepcopy(s['pending_check'][key]) for key in ('kind','test','dc')}
    meta['actions']=available(s)
    meta['presentation']={'schema':'ashen-campaign/2','asset_manifest':'asset://ashen-vault-ember/campaign-assets.json'}
    return {'entities':entities,'meta':meta,'resources':{'presentation_assets':{'uri':'asset://ashen-vault-ember/campaign-assets.json','media_type':'application/json','version':'1'}}}


def available(s):
    actions=[]
    def add(label,tool,**args):actions.append({'label':label,'tool':'adventure.'+tool,'arguments':{'revision':s['revision'],**args}})
    cls=class_key(s)
    if level_ready(s):
        if s['level']==1 and cls=='fighter':
            add('升到 2 级：保持防御风格','level_up',style='defense')
            add('升到 2 级：改为决斗风格','level_up',style='dueling')
        elif s['level']==1:
            add('升到 2 级','level_up')
        else:
            label={'fighter':'升到 3 级：Champion','rogue':'升到 3 级：Thief','wizard':'升到 3 级：Evoker'}[cls]
            add(label,'level_up')
        return actions
    if s['status'] in ('captured','completed','retired'):return actions
    if s['pending_check']:
        if cls=='fighter' and s['level']>=2 and s['second_wind']>0:add('战术头脑：尝试加骰','resolve_check',choice='tactical')
        add('接受原检定结果','resolve_check',choice='accept');return actions
    b=s['battle']
    if b:
        if b['pending']:
            if b['pending']['reactor']=='hero':
                add('机会攻击','react',window_id=b['pending']['window_id'],choice='attack',knockout=False)
                add('放弃反应','react',window_id=b['pending']['window_id'],choice='decline')
            return actions
        if active(b)!='hero':return actions
        h=b['actors']['hero'];tid=b['turn_id']
        if h['action'] and adjacent(h['position'],b['actors']['enemy']['position']) and clear_step(h['position'],b['actors']['enemy']['position']):
            add('攻击','attack',turn_id=tid,target='enemy',knockout=False)
            add('击昏攻击','attack',turn_id=tid,target='enemy',knockout=True)
        if h['action']:
            for name,label in (('dodge','闪避'),('disengage','撤离'),('dash','冲刺')):add(label,name,turn_id=tid)
            if cls=='wizard':
                add('施放 Ray of Frost','cast',spell='ray_of_frost',target='enemy',turn_id=tid)
                if s['spell_slots']['1']>0:add('施放 Magic Missile（1环）','cast',spell='magic_missile',target='enemy',slot_level=1,turn_id=tid)
                if s['spell_slots']['2']>0:add('施放 Magic Missile（2环）','cast',spell='magic_missile',target='enemy',slot_level=2,turn_id=tid)
                if s['spell_slots']['1']>0 and not s['flags'].get('mage_armor_until'):
                    add('施放 Mage Armor','cast',spell='mage_armor',target='hero',slot_level=1,turn_id=tid)
        if h['movement']>0:
            if path_to(b,'hero'):add('靠近敌人','approach',turn_id=tid)
            if h['position'][0]>0 and path_to(b,'hero',[0,h['position'][1]]):add('向出口移动','withdraw',turn_id=tid)
        if 'prone' in h['conditions'] and h['movement']>=h['speed']//2:add('起身','stand',turn_id=tid)
        if h.get('bonus_action'):
            if cls=='fighter' and s['second_wind']>0:add('第二风息','second_wind')
            if s['potions']>0:add('喝治疗药水','potion')
            if cls=='rogue' and s['level']>=2:
                add('灵巧动作：冲刺','cunning_action',choice='dash',turn_id=tid)
                add('灵巧动作：撤离','cunning_action',choice='disengage',turn_id=tid)
            if cls=='rogue' and s['level']>=3 and not h.get('moved_this_turn'):
                add('Steady Aim','steady_aim',turn_id=tid)
        if cls=='fighter' and s['level']>=2 and s['action_surge']>0:add('动作如潮：额外动作','action_surge')
        if h['position'][0]==0:add('离开遭遇','escape',turn_id=tid)
        add('结束回合','end_turn',turn_id=tid);return actions
    for room in ROOMS[s['room']]['neighbors']:
        if room=='shrine' and (not s['flags'].get('guard_access') or 'frightened' in s['hero']['conditions']):continue
        add('前往'+(ROOMS[room]['name'] if room in s['visited'] else '未探索通道'),'travel',destination=room)
    room=s['room'];flags=s['flags']
    if room=='gate' and not flags.get('inscription'):add('阅读通行誓约','interact',target='inscription')
    if room=='cache' and 'cache' not in s['attempts'] and 'cache' not in s['rewards']:
        add('强行撬开补给箱（Athletics）','interact',target='cache')
        if s['build'].get('tool')=='carpenters_tools' and 'carpenters_tools' in s['build'].get('equipment',[]):add('用木匠工具调整箱盖','interact',target='cache_tools')
        if s['build'].get('tool')=='thieves_tools' and 'thieves_tools' in s['build'].get('equipment',[]):add('用盗贼工具拆解锁舌','interact',target='cache_thieves')
    if room=='guard' and flags.get('inscription') and not flags.get('guard_access'):
        if s['gold']>=20:add('支付 20 金币','interact',target='pay_guard')
        if 'parley' not in s['attempts']:add('交涉争取通行（Intimidation）','interact',target='parley')
        if s['hero'].get('naturally_stealthy') and 'stealth_passage' not in s['attempts']:add('借高大驮兽遮蔽潜行（Naturally Stealthy）','interact',target='stealth_passage')
        add('挑战守卫','interact',target='challenge')
    if room=='shrine':
        if flags.get('guard_access') and not flags.get('dread_cleared') and 'frightened' not in s['hero']['conditions']:add('直面余烬低语（Brave 优势豁免）','interact',target='dread')
        if flags.get('dread_cleared') and flags.get('guard_access') and not flags.get('ember') and not flags.get('delivered'):add('取回火种','interact',target='take_ember')
        if flags.get('dread_cleared') and flags.get('delivered') and s['level']==2:add('开始守印考验','interact',target='trial')
    if 'frightened' in s['hero']['conditions']:add('稳定心神（Brave 优势豁免）','interact',target='dread_recover')
    if room=='camp':
        if flags.get('ember') and not flags.get('delivered'):add('交还火种','interact',target='deliver')
        for kind,label in (('short','短休（1 小时）'),('long','长休（8 小时）')):
            if kind=='short' or s['seconds']-s['last_long_rest_end']>=57600:add(label,'rest',kind=kind)
        if s['short_rest_open'] and s['hit_dice']>0:add('花一枚生命骰恢复','spend_hit_die')
        if cls=='wizard' and s['short_rest_open'] and s.get('arcane_recovery',0)>0:
            cap=ceil(s['level']/2)
            if s['spell_slots']['1']<spell_slot_capacity(s['level'])['1']:
                add('Arcane Recovery：恢复 1 个一环位','arcane_recovery',slot_level=1,count=1)
                if cap>=2 and spell_slot_capacity(s['level'])['1']-s['spell_slots']['1']>=2:
                    add('Arcane Recovery：恢复 2 个一环位','arcane_recovery',slot_level=1,count=2)
            if cap>=2 and s['spell_slots']['2']<spell_slot_capacity(s['level'])['2']:
                add('Arcane Recovery：恢复 1 个二环位','arcane_recovery',slot_level=2,count=1)
        for weapon in s['build'].get('supported_weapons',[]):
            info=WEAPONS[weapon];add('装备'+info['name'],'equip',weapon=weapon)
        if cls=='wizard' and s['spell_slots']['1']>0 and not flags.get('mage_armor_until'):
            add('施放 Mage Armor','cast',spell='mage_armor',target='hero',slot_level=1)
        if s['gold']>=50 and flags.get('potions_bought',0)<2:add('购买治疗药水（50 金币）','buy_potion')
        add('结束本次远征','retire')
    if 'prone' in s['hero']['conditions']:add('在安全位置起身','recover_posture')
    if cls=='fighter' and s['second_wind']>0:add('第二风息','second_wind')
    if s['potions']>0:add('喝治疗药水','potion')
    return actions


def emit(events,s,event_kind,**data):
    events.append({'kind':event_kind,'data':deepcopy(data),'frame':view(s)})


def reward(s,events,source,resolution):
    if source in s['rewards']:return False
    spec=REWARDS[source];before={'xp':s['xp'],'gold':s['gold'],'potions':s['potions']}
    s['rewards'][source]={**spec,'resolution':resolution}
    for field in before:s[field]+=spec[field]
    emit(events,s,'reward',source=source,resolution=resolution,before=before,after={f:s[f] for f in before})
    return True


def record_battle(s,events,actor,command,args,draw):
    before=deepcopy(s['battle']);updated,result=battle_apply(before,actor,command,args,draw)
    s['battle']=updated;s['hero']=deepcopy(updated['actors']['hero'])
    if updated['round'] > before['round']:s['seconds']+=6
    emit(events,s,'combat',actor=actor,origin='player' if actor=='hero' else 'scripted_npc',command=command,result=result,
         before={k:{'hp':v['hp'],'position':v['position'],'conditions':v['conditions']} for k,v in before['actors'].items()},
         after={k:{'hp':v['hp'],'position':v['position'],'conditions':v['conditions']} for k,v in updated['actors'].items()})
    settle_battle(s,events)
    return result


def settle_battle(s,events):
    b=s['battle']
    if not b or b['phase']!='complete':return
    s['hero']=deepcopy(b['actors']['hero']);winner=b['winner'];s['battle']=None
    if winner!='hero':
        s['status']='captured';s['ending']='旅人被击昏并拘留。角色仍是原角色；本次远征失败，没有自动复活或重新领奖。'
        emit(events,s,'ending',outcome='captured');return
    if s['flags'].get('delivered'):
        reward(s,events,'seal_trial','victory');s['status']='completed';s['ending']='火种归营，守印考验完成。'
        emit(events,s,'ending',outcome='completed')
    else:
        s['flags']['guard_access']=True
        reward(s,events,'guard_access','combat:25-monster-xp+50-authored-objective-xp')
        emit(events,s,'objective',objective='guard_access',outcome='opened')


def advance_npc(s,events,draw):
    for _ in range(12):
        b=s['battle']
        if not b:return
        if b['pending']:
            if b['pending']['reactor']=='hero':return
            record_battle(s,events,'enemy','react',{'window_id':b['pending']['window_id'],'choice':'attack','knockout':True},draw)
            continue
        if active(b)=='hero':return
        enemy=b['actors']['enemy'];hero=b['actors']['hero'];tid=b['turn_id']
        if enemy['hp']<=max(1,enemy['max_hp']//3):
            if enemy['position'][0]==ARENA['width']-1:
                b.update(phase='complete',winner='hero',pending=None)
                emit(events,s,'objective',objective='enemy_morale',outcome='withdrew',origin='scripted_npc')
                settle_battle(s,events);return
            if enemy['action']:
                record_battle(s,events,'enemy','dash',{'turn_id':tid},draw);continue
            retreat=path_to(b,'enemy',[ARENA['width']-1,enemy['position'][1]])
            if retreat:
                record_battle(s,events,'enemy','move',{'turn_id':tid,'path':retreat},draw);continue
        if enemy['action'] and adjacent(enemy['position'],hero['position']) and clear_step(enemy['position'],hero['position']):
            record_battle(s,events,'enemy','attack',{'turn_id':tid,'target':'hero','knockout':True},draw)
        elif enemy['movement']>0 and (path:=path_to(b,'enemy')):
            record_battle(s,events,'enemy','move',{'turn_id':tid,'path':path},draw)
        else:record_battle(s,events,'enemy','end_turn',{'turn_id':tid},draw)
    raise RulesError('NPC step budget exceeded; no partial transaction is committed')


def start_battle(s,events,draw):
    s['battle_serial']+=1;s['battle']=make_battle(s,draw)
    wound_key='trial_hp' if s['flags'].get('delivered') else 'guard_hp'
    if s['flags'].get(wound_key):s['battle']['actors']['enemy']['hp']=s['flags'][wound_key]
    emit(events,s,'encounter',origin='world_rules',outcome='started',initiative=s['battle']['initiative'])
    advance_npc(s,events,draw)


def checked_outcome(s,events,kind,success,draw):
    emit(events,s,'check_result',check=kind,success=success)
    if success:
        if kind in ('cache','cache_tools','cache_thieves'):
            resolution = 'carpenters_tools_check' if kind=='cache_tools' else 'thieves_tools_check' if kind=='cache_thieves' else 'athletics_check'
            reward(s,events,'cache',resolution)
        else:
            s['flags']['guard_access']=True
            reward(s,events,'guard_access','authored-naturally-stealthy-hide' if kind=='stealth_passage' else 'authored-parley-reward')
            if kind=='stealth_passage':emit(events,s,'objective',objective='guard_access',outcome='hidden_passage',trait='naturally_stealthy')
    elif kind in ('parley','stealth_passage'):start_battle(s,events,draw)


def _cast_spell(s,events,args,draw):
    require(class_key(s)=='wizard','WizardSpellcastingRequired')
    spell=args.get('spell');require(spell in s['build'].get('implemented_spells',[]),'UnsupportedSpell')
    b=s['battle'];h=b['actors']['hero'] if b else s['hero']
    if b:
        require(active(b)=='hero' and not b['pending'],'NotYourTurnOrReactionPending')
        require(args.get('turn_id')==b['turn_id'],'StaleTurn')
        require(h['action'],'ActionSpent')
    if spell=='ray_of_frost':
        require(b is not None,'CombatTargetRequired')
        target=b['actors'].get(args.get('target'));require(target is not None and target['team']!='hero','InvalidTarget')
        distance=_distance_feet(h['position'],target['position'])
        require(distance<=60 and _clear_spell_path(h['position'],target['position']),'SpellTargetOutOfRangeOrCovered')
        close=distance<=5
        advantage='prone' in target['conditions'] and close
        disadvantage=(('prone' in target['conditions'] and not close) or
                     (close and not incapacitated(target)) or
                     (target.get('dodge',False) and not incapacitated(target) and target['speed']>0))
        test=d20(draw,h['spell_attack_bonus'],advantage=advantage,disadvantage=disadvantage,
                 dc=target['ac'],attack=True,reroll_one=h.get('lucky',False) and args.get('use_luck',True))
        raw_roll=roll(draw,8)[0] if test['success'] or (s['level']>=3 and h.get('potent_cantrip')) else 0
        raw=raw_roll if test['success'] else raw_roll//2
        damage=damage_amount(raw,resistant='cold' in target.get('resistances',[]),
                             vulnerable='cold' in target.get('vulnerabilities',[]),immune='cold' in target.get('immunities',[]))
        effect=lose_hp(target,damage) if damage else {'hp_before':target['hp'],'hp_after':target['hp'],'temporary_absorbed':0}
        if test['success'] and not target.get('dead'):
            target['speed_penalty']=max(int(target.get('speed_penalty',0)),10);target['slowed_by']='hero'
        result={'spell':spell,'attack':test,'hit':test['success'],'damage_roll':raw_roll,'damage':damage,'damage_type':'cold',
                'potent_cantrip':bool(not test['success'] and raw_roll),'effect':effect}
        h['action']=False
    else:
        slot=int(args.get('slot_level',1));require(slot in (1,2),'UnsupportedSpellSlot')
        require(s['spell_slots'].get(str(slot),0)>0,'SpellSlotEmpty')
        if spell=='mage_armor':
            require(slot==1,'MageArmorUsesLevelOneSlot')
            s['spell_slots']['1']-=1
            dex=(s['build']['abilities']['dex']-10)//2
            h['ac']=13+dex;s['flags']['mage_armor_until']=s['seconds']+28800
            result={'spell':spell,'slot_level':1,'target':'hero','ac':h['ac'],'expires_at_seconds':s['flags']['mage_armor_until']}
            if b:h['action']=False
            else:s['seconds']+=6
        else:
            require(spell=='magic_missile' and b is not None,'CombatTargetRequired')
            target=b['actors'].get(args.get('target'));require(target is not None and target['team']!='hero','InvalidTarget')
            require(_distance_feet(h['position'],target['position'])<=120 and _clear_spell_path(h['position'],target['position']),
                    'SpellTargetOutOfRangeOrCovered')
            s['spell_slots'][str(slot)]-=1
            darts=2+slot;dice=roll(draw,4,darts);raw=sum(value+1 for value in dice)
            damage=damage_amount(raw,resistant='force' in target.get('resistances',[]),
                                 vulnerable='force' in target.get('vulnerabilities',[]),immune='force' in target.get('immunities',[]))
            effect=lose_hp(target,damage)
            h['action']=False
            result={'spell':spell,'slot_level':slot,'darts':darts,'dice':dice,'damage':damage,'damage_type':'force','effect':effect}
    if b:
        s['hero']=deepcopy(h)
        target=b['actors'].get('enemy')
        if target is not None and incapacitated(target):
            b.update(phase='complete',winner='hero',pending=None)
        emit(events,s,'spell',actor='hero',origin='player',result=result)
        settle_battle(s,events)
        if s['battle'] is not None:advance_npc(s,events,draw)
    else:
        s['hero']=deepcopy(h);emit(events,s,'spell',actor='hero',origin='player',result=result)


def apply(state,command,args,draw):
    s=deepcopy(state);events=[]
    require(args.get('revision')==s['revision'],'StaleAdventureRevision')
    _expire_timed_effects(s)
    pending_level=level_ready(s)
    require(s['status']=='exploring' or (command=='level_up' and pending_level),'AdventureEnded')
    require(not pending_level or command=='level_up','LevelChoicePending')
    require(not s['pending_check'] or command=='resolve_check','AbilityDecisionPending')
    if command not in ('spend_hit_die','rest','arcane_recovery'):s['short_rest_open']=False
    cls=class_key(s)
    battle_commands={'attack','move','approach','withdraw','escape','dash','dodge','disengage','drop_prone','stand','end_turn','react'}
    if command in battle_commands:
        b=s['battle'];require(b is not None,'NoEncounter')
        if command=='react':params={k:v for k,v in args.items() if k!='revision'}
        else:
            require(active(b)=='hero' and not b['pending'],'NotYourTurnOrReactionPending')
            require(args.get('turn_id')==b['turn_id'],'StaleTurn')
            params={k:v for k,v in args.items() if k!='revision'}
        if command in ('approach','withdraw'):
            destination=[0,b['actors']['hero']['position'][1]] if command=='withdraw' else None
            path=path_to(b,'hero',destination)
            require(bool(path),'NoAvailablePathOrAlreadyThere');command='move';params={'turn_id':b['turn_id'],'path':path}
        if command=='escape':
            require(b['actors']['hero']['position'][0]==0,'ReachExitBeforeEscaping')
            s['hero']=deepcopy(b['actors']['hero']);s['flags']['trial_hp' if s['flags'].get('delivered') else 'guard_hp']=b['actors']['enemy']['hp'];s['battle']=None;s['room']='fork'
            emit(events,s,'retreat',outcome='escaped',position=ROOMS['fork']['position'])
        else:
            record_battle(s,events,'hero',command,params,draw)
            advance_npc(s,events,draw)
    elif command=='cast':
        _cast_spell(s,events,args,draw)
    elif command=='cunning_action':
        b=s['battle'];require(b is not None and cls=='rogue' and s['level']>=2,'CunningActionUnavailable')
        require(active(b)=='hero' and not b['pending'] and args.get('turn_id')==b['turn_id'],'NotYourTurnOrReactionPending')
        h=b['actors']['hero'];require(h.get('bonus_action'),'BonusActionSpent')
        choice=args.get('choice');require(choice in ('dash','disengage'),'UnsupportedCunningAction')
        if choice=='dash':h['movement']+=max(0,h['speed']-int(h.get('speed_penalty',0)))
        else:h['disengage']=True
        h['bonus_action']=False;s['hero']=deepcopy(h)
        emit(events,s,'ability',ability='cunning_action',choice=choice)
    elif command=='steady_aim':
        b=s['battle'];require(b is not None and cls=='rogue' and s['level']>=3,'SteadyAimUnavailable')
        require(active(b)=='hero' and not b['pending'] and args.get('turn_id')==b['turn_id'],'NotYourTurnOrReactionPending')
        h=b['actors']['hero'];require(h.get('bonus_action'),'BonusActionSpent');require(not h.get('moved_this_turn'),'AlreadyMovedThisTurn')
        h['bonus_action']=False;h['movement']=0;h['steady_aim']=True;s['hero']=deepcopy(h)
        emit(events,s,'ability',ability='steady_aim',speed=0)
    elif command in ('second_wind','potion','action_surge'):
        b=s['battle'];h=b['actors']['hero'] if b else s['hero']
        require(not incapacitated(h),'Incapacitated')
        if b:require(active(b)=='hero' and not b['pending'],'NotYourTurnOrReactionPending')
        if command=='action_surge':
            require(cls=='fighter' and b is not None and s['level']>=2 and s['action_surge']>0,'ActionSurgeUnavailable')
            s['action_surge']-=1
            if h['action']:h['extra_actions']+=1
            else:h['action']=True
            emit(events,s,'ability',ability='action_surge',remaining=s['action_surge'])
        else:
            if command=='second_wind':require(cls=='fighter','SecondWindUnavailable')
            if b:require(h['bonus_action'],'BonusActionSpent')
            resource='second_wind' if command=='second_wind' else 'potions';require(s[resource]>0,'ResourceEmpty')
            dice=[draw(1,10)] if command=='second_wind' else [draw(1,4),draw(1,4)]
            amount=sum(dice)+(s['level'] if command=='second_wind' else 2);before=h['hp'];restored=heal(h,amount);s[resource]-=1
            if b:h['bonus_action']=False
            emit(events,s,'healing',source=command,dice=dice,before=before,after=h['hp'],restored=restored)
        s['hero']=deepcopy(h)
        if not b:s['seconds']+=6
    else:
        require(s['battle'] is None,'FinishOrExitEncounterFirst')
        room=s['room'];flags=s['flags']
        if command=='travel':
            dest=args['destination'];require(dest in ROOMS[room]['neighbors'],'NotAdjacentRegion')
            require(dest!='shrine' or flags.get('guard_access'),'GuardBlocksPassage')
            require(dest!='shrine' or 'frightened' not in s['hero']['conditions'],'FrightenedCannotApproachSource')
            s['room']=dest;s['seconds']+=600
            if dest not in s['visited']:s['visited'].append(dest)
            emit(events,s,'travel',origin='player',start=ROOMS[room]['position'],end=ROOMS[dest]['position'],room=dest)
        elif command=='interact':
            target=args['target']
            if target=='inscription':
                require(room=='gate' and not flags.get('inscription'),'AlreadyReadOrWrongPlace')
                require('dwarvish' in s['build'].get('languages',[]),'DwarvishRequiredToReadInscription')
                flags['inscription']=True
                emit(events,s,'check_result',check='language:dwarvish',success=True,source='build_language')
                reward(s,events,'inscription','authored-dwarvish-inscription')
            elif target in ('pay_guard','parley','stealth_passage','challenge'):
                require(room=='guard' and not flags.get('guard_access'),'GuardAlreadyResolvedOrWrongPlace')
                require(flags.get('inscription'),'ReadTheInscriptionFirst')
                if target=='pay_guard':
                    require(s['gold']>=20,'InsufficientGold');s['gold']-=20;flags['guard_access']=True
                    reward(s,events,'guard_access','authored-paid-passage-reward')
                elif target=='challenge':
                    start_battle(s,events,draw)
                elif target=='stealth_passage':
                    require(s['hero'].get('naturally_stealthy'),'NaturallyStealthyRequired')
                    require('stealth_passage' not in s['attempts'],'NoUnchangedCheckRetry')
                    s['attempts'].append('stealth_passage')
                    modifier=s['build'].get('skills',{}).get('stealth',0)
                    test=d20(draw,modifier,dc=15,reroll_one=args.get('use_luck',True));s['seconds']+=60
                    emit(events,s,'check',check='stealth_passage',skill='stealth',trait='naturally_stealthy',
                         obscured_by='larger_pack_beast',test=test)
                    checked_outcome(s,events,'stealth_passage',test['success'],draw)
                else:
                    require('parley' not in s['attempts'],'NoUnchangedCheckRetry');s['attempts'].append('parley')
                    modifier=s['build'].get('skills',{}).get('intimidation',0)
                    test=d20(draw,modifier,dc=13,reroll_one=args.get('use_luck',True));s['seconds']+=60
                    if not test['success'] and cls=='fighter' and s['level']>=2 and s['second_wind']>0:s['pending_check']={'kind':'parley','test':test,'dc':13}
                    emit(events,s,'check',check='parley',skill='intimidation',test=test)
                    if not s['pending_check']:checked_outcome(s,events,'parley',test['success'],draw)
            elif target in ('cache','cache_tools','cache_thieves'):
                require(room=='cache' and 'cache' not in s['attempts'],'NoUnchangedCheckRetryOrWrongPlace')
                advantage=False
                if target=='cache_tools':
                    require(s['build'].get('tool')=='carpenters_tools' and 'carpenters_tools' in s['build'].get('equipment',[]),'CarpentersToolsRequired')
                    modifier,dc,check_name,ability=3,12,'carpenters_tools','dex'
                elif target=='cache_thieves':
                    require(s['build'].get('tool')=='thieves_tools' and 'thieves_tools' in s['build'].get('equipment',[]),'ThievesToolsRequired')
                    modifier,dc,check_name,ability=s['build']['skills'].get('sleight_of_hand',5),12,'thieves_tools','dex';advantage=True
                else:
                    modifier=s['build'].get('skills',{}).get('athletics',0);dc,check_name,ability=15,'athletics','str'
                    advantage=bool(cls=='fighter' and s['level']>=3 and s['hero'].get('remarkable_athlete'))
                s['attempts'].append('cache')
                test=d20(draw,modifier,dc=dc,advantage=advantage,reroll_one=args.get('use_luck',True));s['seconds']+=600
                if not test['success'] and cls=='fighter' and s['level']>=2 and s['second_wind']>0:s['pending_check']={'kind':target,'test':test,'dc':dc}
                emit(events,s,'check',check=check_name,ability=ability,proficiency='tool' if target!='cache' else 'skill',test=test)
                if not s['pending_check']:checked_outcome(s,events,target,test['success'],draw)
            elif target in ('dread','dread_recover'):
                recovering=target=='dread_recover'
                if recovering:
                    require('frightened' in s['hero']['conditions'],'NoFrightenedCondition')
                else:
                    require(room=='shrine' and flags.get('guard_access') and not flags.get('dread_cleared') and 'frightened' not in s['hero']['conditions'],'DreadUnavailable')
                brave=bool(s['hero'].get('brave'));modifier=s['build'].get('saves',{}).get('wis',0)
                test=d20(draw,modifier,dc=11,advantage=brave,reroll_one=args.get('use_luck',True));s['seconds']+=60
                emit(events,s,'check',check='dread_save',save='wisdom',trait='brave' if brave else None,test=test)
                if test['success']:
                    s['hero']['conditions']=[condition for condition in s['hero']['conditions'] if condition!='frightened']
                    flags['dread_cleared']=True
                else:
                    s['hero']['conditions']=sorted(set(s['hero']['conditions'])|{'frightened'})
                emit(events,s,'check_result',check='dread_save',success=test['success'],condition='frightened',
                     outcome='ended' if recovering and test['success'] else 'avoided' if test['success'] else 'applied')
            elif target=='take_ember':
                require(room=='shrine' and flags.get('guard_access') and flags.get('dread_cleared') and not flags.get('ember') and not flags.get('delivered'),'EmberUnavailable')
                flags['ember']=True;emit(events,s,'item',item='ember',outcome='picked_up')
            elif target=='deliver':
                require(room=='camp' and flags.get('ember') and not flags.get('delivered'),'DeliveryUnavailable')
                flags['ember']=False;flags['delivered']=True;reward(s,events,'ember_delivery','authored-return-objective')
            elif target=='trial':
                require(room=='shrine' and flags.get('delivered') and flags.get('dread_cleared') and s['level']==2,'CompleteGrowthBeforeTrial');start_battle(s,events,draw)
            else:raise RulesError('UnknownInteraction')
        elif command=='resolve_check':
            pending=s['pending_check'];require(pending is not None,'NoPendingCheck');require(args['choice'] in ('tactical','accept'),'UnknownChoice')
            success=False;bonus=0
            if args['choice']=='tactical':
                require(cls=='fighter' and s['level']>=2 and s['second_wind']>0,'TacticalMindUnavailable');bonus=draw(1,10)
                success=pending['test']['total']+bonus>=pending['dc']
                if success:s['second_wind']-=1
            s['pending_check']=None
            emit(events,s,'tactical_mind',bonus=bonus,spent=success,success=success)
            checked_outcome(s,events,pending['kind'],success,draw)
        elif command=='level_up':
            before_level=s['level'];required=300 if before_level==1 else 900
            require(before_level in (1,2) and s['xp']>=required,'LevelNotAvailable')
            gain=hp_gain(cls);s['level']+=1;s['hero']['max_hp']+=gain;s['hit_dice']+=1
            features=[]
            if s['level']==2:
                if cls=='fighter':
                    style=args.get('style');require(style in ('defense','dueling'),'UnsupportedBuildChoice')
                    s['action_surge']=1;s['build']['style']=style
                    s['hero']['ac']=19 if style=='defense' else 18;s['hero']['damage_bonus']=3 if style=='defense' else 5
                    features=['action_surge','tactical_mind']
                elif cls=='rogue':
                    features=['cunning_action']
                else:
                    s['spell_slots']=spell_slot_capacity(2);s['build']['skills']['arcana']=7
                    s['build']['skill_sources']['scholar_expertise']=['arcana']
                    for name in ('shield','grease'):
                        if name not in s['build']['spellbook']:s['build']['spellbook'].append(name)
                    features=['scholar:arcana_expertise','spell_slots:3x1']
            else:
                if cls=='fighter':
                    s['hero']['critical_threshold']=19;s['hero']['initiative_advantage']=True;s['hero']['remarkable_athlete']=True
                    s['build']['subclass']='Champion';features=['improved_critical','remarkable_athlete']
                elif cls=='rogue':
                    s['hero']['sneak_attack_dice']=2;s['hero']['fast_hands']=True;s['build']['subclass']='Thief'
                    features=['sneak_attack:2d6','steady_aim','thief:fast_hands','thief:second_story_work']
                else:
                    s['spell_slots']=spell_slot_capacity(3);s['hero']['potent_cantrip']=True;s['build']['subclass']='Evoker'
                    for name in ('misty_step','web','scorching_ray','shatter'):
                        if name not in s['build']['spellbook']:s['build']['spellbook'].append(name)
                    features=['spell_slots:4x1+2x2','evoker:evocation_savant','evoker:potent_cantrip']
            emit(events,s,'level_up',before=before_level,after=s['level'],features=features,style=s['build'].get('style'),subclass=s['build'].get('subclass'))
        elif command=='equip':
            weapon=args['weapon'];require(room=='camp' and weapon in s['build'].get('supported_weapons',[]) and weapon in WEAPONS,'PrepareSupportedGearAtCamp')
            info=WEAPONS[weapon]
            s['hero'].update(weapon=weapon,damage_die=info['die'],damage_type=info['type'],mastery=info.get('mastery'),
                             weapon_finesse=bool(info.get('finesse',False)));s['seconds']+=60
            emit(events,s,'equipment',weapon=weapon)
        elif command=='rest':
            require(room=='camp' and s['hero']['hp']>0,'RestRequiresSafeCampAndHP');kind=args['kind'];require(kind in ('short','long'),'UnknownRest')
            if kind=='long':
                require(s['seconds']-s['last_long_rest_end']>=57600,'LongRestTooSoon')
                s['seconds']+=28800;s['last_long_rest_end']=s['seconds'];s['hero']['hp']=s['hero']['max_hp'];s['hit_dice']=s['level'];s['short_rest_open']=False
                s['hero']['temp_hp']=0
                if cls=='fighter':s['second_wind']=2
                if cls=='wizard':s['spell_slots']=spell_slot_capacity(s['level']);s['arcane_recovery']=1
                if s['flags'].pop('mage_armor_until',None) is not None:s['hero']['ac']=s['hero'].get('unarmored_ac',12)
            else:
                s['seconds']+=3600;s['short_rest_open']=True
                if cls=='fighter':s['second_wind']=min(2,s['second_wind']+1)
            if cls=='fighter' and s['level']>=2:s['action_surge']=1
            emit(events,s,'rest',kind=kind,minutes=s['seconds']/60)
        elif command=='arcane_recovery':
            require(room=='camp' and cls=='wizard' and s['short_rest_open'] and s.get('arcane_recovery',0)>0,'ArcaneRecoveryUnavailable')
            slot=int(args.get('slot_level',1));count=int(args.get('count',1));cap=ceil(s['level']/2)
            require(slot in (1,2) and 1<=count<=2 and slot*count<=cap,'ArcaneRecoveryBudgetExceeded')
            maximum=spell_slot_capacity(s['level'])[str(slot)]
            require(maximum>0 and s['spell_slots'][str(slot)]+count<=maximum,'NoExpendedSlotsToRecover')
            s['spell_slots'][str(slot)]+=count;s['arcane_recovery']=0
            emit(events,s,'ability',ability='arcane_recovery',slot_level=slot,count=count)
        elif command=='spend_hit_die':
            require(room=='camp' and s['short_rest_open'] and s['hit_dice']>0,'NoCompletedShortRestOrDice')
            sides={'fighter':10,'rogue':8,'wizard':6}[cls];die=draw(1,sides);before=s['hero']['hp']
            heal(s['hero'],max(1,die+2));s['hit_dice']-=1
            emit(events,s,'healing',source='hit_die',dice=[die],before=before,after=s['hero']['hp'])
        elif command=='buy_potion':
            require(room=='camp' and s['gold']>=50 and flags.get('potions_bought',0)<2,'InsufficientGoldStockOrWrongPlace')
            before={'gold':s['gold'],'potions':s['potions']}
            s['gold']-=50;s['potions']+=1;flags['potions_bought']=flags.get('potions_bought',0)+1;s['seconds']+=60
            emit(events,s,'item',item='healing_potion',outcome='purchased',before=before,after={'gold':s['gold'],'potions':s['potions']})
        elif command=='recover_posture':
            require('prone' in s['hero']['conditions'] and not incapacitated(s['hero']),'NoRecoverablePosture')
            s['hero']['conditions'].remove('prone');s['seconds']+=6
            emit(events,s,'state_changed',command='stand_outside_encounter')
        elif command=='retire':
            require(room=='camp','ReturnToCampBeforeRetiring');s['status']='retired';s['ending']='主动结束远征。已获得的成长与装备保留，没有伪造最终胜利。'
            emit(events,s,'ending',outcome='retired')
        else:raise RulesError('UnsupportedCampaignAction')
    _expire_timed_effects(s)
    if s['battle'] is None and s['seconds']-state['seconds']>=6:
        for key in ('sapped_by','vexed_by','vex_origin_turn','steady_aim','speed_penalty','slowed_by'):
            s['hero'].pop(key,None)
        s['hero'].update(action=True,reaction=True,bonus_action=True,extra_actions=0,movement=s['hero']['speed'],
                         moved_this_turn=False,dodge=False,disengage=False)
    s['revision']+=1
    for event in events:
        event['frame']['meta']['revision']=s['revision']
        for action in event['frame']['meta']['actions']:action['arguments']['revision']=s['revision']
    if not events:emit(events,s,'state_changed',command=command)
    events[-1]['frame']=view(s)
    return s,events
