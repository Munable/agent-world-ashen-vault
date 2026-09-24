"""Solo campaign logic. All authoritative changes use the caller's world transaction."""
from copy import deepcopy
from .campaign_content import ROOMS, WEAPONS, REWARDS, make_battle
from .content import ARENA
from .engine import apply as battle_apply, active, adjacent, clear_step, RulesError, require
from .rules import d20, heal, incapacitated


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


def view(state):
    if state is None:return {'entities':{},'meta':{'joined':False,'actions':[{'label':'开始冒险','tool':'adventure.join','arguments':{}}]}}
    s=state;b=s['battle']
    hero=deepcopy(b['actors']['hero'] if b else s['hero'])
    if not b:hero['position']=list(ROOMS[s['room']]['position'])
    entities={'hero':hero}
    if b:entities['enemy']=deepcopy(b['actors']['enemy'])
    known={key:{'name':value['name'],'position':list(value['position']),'visited':key in s['visited']} for key,value in ROOMS.items() if key in s['visited']}
    meta={'joined':True,'revision':s['revision'],'room':s['room'],'room_name':ROOMS[s['room']]['name'],
          'text':ROOMS[s['room']]['text'],'known_rooms':known,'status':s['status'],'ending':s['ending'],
          'level':s['level'],'xp':s['xp'],'next_xp':300 if s['level']==1 else None,'gold':s['gold'],'potions':s['potions'],
          'second_wind':s['second_wind'],'action_surge':s['action_surge'],'hit_dice':s['hit_dice'],'minutes':s['seconds']/60,'long_rest_wait_seconds':max(0,57600-(s['seconds']-s['last_long_rest_end'])),
          'style':s['build']['style'],'weapon':hero['weapon'],'build':deepcopy(s['build']),
          'quest':s['ending'] if s['ending'] else ('火种已经归营。回祭坛使用新能力接受守印考验。' if s['level']==2 else '火种已经归营。请选择 2 级成长。') if s['flags'].get('delivered') else '带回失落火种；通行可交涉或战斗。',
          'arena':deepcopy(ARENA) if b else {'width':14,'height':8,'walls':[],'difficult':[]},'battle':None,'pending_check':None}
    if b:meta['battle']={key:deepcopy(b[key]) for key in ('phase','round','turn_id','pending','order')};meta['battle']['active']=active(b)
    if s['pending_check']:meta['pending_check']={key:deepcopy(s['pending_check'][key]) for key in ('kind','test','dc')}
    meta['actions']=available(s)
    meta['presentation']={'schema':'ashen-campaign/1','asset_manifest':'asset://ashen-vault-ember/campaign-assets.json'}
    return {'entities':entities,'meta':meta,'resources':{'presentation_assets':{'uri':'asset://ashen-vault-ember/campaign-assets.json','media_type':'application/json','version':'1'}}}


def available(s):
    actions=[]
    def add(label,tool,**args):actions.append({'label':label,'tool':'adventure.'+tool,'arguments':{'revision':s['revision'],**args}})
    if s['status'] in ('captured','completed','retired'):return actions
    if s['level']==1 and s['xp']>=300:
        add('升到 2 级：保持防御风格','level_up',style='defense')
        add('升到 2 级：改为决斗风格','level_up',style='dueling')
        return actions
    if s['pending_check']:
        if s['second_wind']>0:add('战术头脑：尝试加骰','resolve_check',choice='tactical')
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
        if h['movement']>0:
            if path_to(b,'hero'):add('靠近敌人','approach',turn_id=tid)
            if h['position'][0]>0 and path_to(b,'hero',[0,h['position'][1]]):add('向出口移动','withdraw',turn_id=tid)
        if 'prone' in h['conditions'] and h['movement']>=h['speed']//2:add('起身','stand',turn_id=tid)
        if h.get('bonus_action'):
            if s['second_wind']>0:add('第二风息','second_wind')
            if s['potions']>0:add('喝治疗药水','potion')
        if s['level']==2 and s['action_surge']>0:add('动作如潮：额外动作','action_surge')
        if h['position'][0]==0:add('离开遭遇','escape',turn_id=tid)
        add('结束回合','end_turn',turn_id=tid);return actions
    for room in ROOMS[s['room']]['neighbors']:
        if room=='shrine' and not s['flags'].get('guard_access'):continue
        add('前往'+(ROOMS[room]['name'] if room in s['visited'] else '未探索通道'),'travel',destination=room)
    room=s['room'];flags=s['flags']
    if room=='gate' and not flags.get('inscription'):add('阅读通行誓约','interact',target='inscription')
    if room=='cache' and 'cache' not in s['attempts'] and 'cache' not in s['rewards']:add('撬开补给箱','interact',target='cache')
    if room=='guard' and flags.get('inscription') and not flags.get('guard_access'):
        if s['gold']>=20:add('支付 20 金币','interact',target='pay_guard')
        if 'parley' not in s['attempts']:add('交涉争取通行','interact',target='parley')
        add('挑战守卫','interact',target='challenge')
    if room=='shrine':
        if flags.get('guard_access') and not flags.get('ember') and not flags.get('delivered'):add('取回火种','interact',target='take_ember')
        if flags.get('delivered') and s['level']==2:add('开始守印考验','interact',target='trial')
    if room=='camp':
        if flags.get('ember') and not flags.get('delivered'):add('交还火种','interact',target='deliver')
        for kind,label in (('short','短休（1 小时）'),('long','长休（8 小时）')):
            if kind=='short' or s['seconds']-s['last_long_rest_end']>=57600:add(label,'rest',kind=kind)
        if s['short_rest_open'] and s['hit_dice']>0:add('花一枚生命骰恢复','spend_hit_die')
        for weapon,info in WEAPONS.items():add('装备'+info['name'],'equip',weapon=weapon)
        if s['gold']>=50 and flags.get('potions_bought',0)<2:add('购买治疗药水（50 金币）','buy_potion')
        add('结束本次远征','retire')
    if 'prone' in s['hero']['conditions']:add('在安全位置起身','recover_posture')
    if s['second_wind']>0:add('第二风息','second_wind')
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
        if kind=='cache':reward(s,events,'cache','athletics_check')
        else:s['flags']['guard_access']=True;reward(s,events,'guard_access','authored-parley-reward')
    elif kind=='parley':start_battle(s,events,draw)


def apply(state,command,args,draw):
    s=deepcopy(state);events=[]
    require(args.get('revision')==s['revision'],'StaleAdventureRevision')
    require(s['status']=='exploring','AdventureEnded')
    require(s['level']!=1 or s['xp']<300 or command=='level_up','LevelChoicePending')
    require(not s['pending_check'] or command=='resolve_check','AbilityDecisionPending')
    if command not in ('spend_hit_die','rest'):s['short_rest_open']=False
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
    elif command in ('second_wind','potion','action_surge'):
        b=s['battle'];h=b['actors']['hero'] if b else s['hero']
        require(not incapacitated(h),'Incapacitated')
        if b:require(active(b)=='hero' and not b['pending'],'NotYourTurnOrReactionPending')
        if command=='action_surge':
            require(b is not None and s['level']==2 and s['action_surge']>0,'ActionSurgeUnavailable')
            s['action_surge']-=1
            if h['action']:h['extra_actions']+=1
            else:h['action']=True
            emit(events,s,'ability',ability='action_surge',remaining=s['action_surge'])
        else:
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
            s['room']=dest;s['seconds']+=600
            if dest not in s['visited']:s['visited'].append(dest)
            emit(events,s,'travel',origin='player',start=ROOMS[room]['position'],end=ROOMS[dest]['position'],room=dest)
        elif command=='interact':
            target=args['target']
            if target=='inscription':
                require(room=='gate' and not flags.get('inscription'),'AlreadyReadOrWrongPlace');flags['inscription']=True
                reward(s,events,'inscription','authored-investigation-reward')
            elif target in ('pay_guard','parley','challenge'):
                require(room=='guard' and not flags.get('guard_access'),'GuardAlreadyResolvedOrWrongPlace')
                require(flags.get('inscription'),'ReadTheInscriptionFirst')
                if target=='pay_guard':
                    require(s['gold']>=20,'InsufficientGold');s['gold']-=20;flags['guard_access']=True
                    reward(s,events,'guard_access','authored-paid-passage-reward')
                elif target=='challenge':start_battle(s,events,draw)
                else:
                    require('parley' not in s['attempts'],'NoUnchangedCheckRetry');s['attempts'].append('parley')
                    test=d20(draw,1,dc=13,reroll_one=args.get('use_luck',True));s['seconds']+=60
                    if not test['success'] and s['level']==2 and s['second_wind']>0:s['pending_check']={'kind':'parley','test':test,'dc':13}
                    emit(events,s,'check',check='parley',test=test)
                    if not s['pending_check']:checked_outcome(s,events,'parley',test['success'],draw)
            elif target=='cache':
                require(room=='cache' and 'cache' not in s['attempts'],'NoUnchangedCheckRetryOrWrongPlace');s['attempts'].append('cache')
                test=d20(draw,5,dc=15,reroll_one=args.get('use_luck',True));s['seconds']+=600
                if not test['success'] and s['level']==2 and s['second_wind']>0:s['pending_check']={'kind':'cache','test':test,'dc':15}
                emit(events,s,'check',check='cache',test=test)
                if not s['pending_check']:checked_outcome(s,events,'cache',test['success'],draw)
            elif target=='take_ember':
                require(room=='shrine' and flags.get('guard_access') and not flags.get('ember') and not flags.get('delivered'),'EmberUnavailable')
                flags['ember']=True;emit(events,s,'item',item='ember',outcome='picked_up')
            elif target=='deliver':
                require(room=='camp' and flags.get('ember') and not flags.get('delivered'),'DeliveryUnavailable')
                flags['ember']=False;flags['delivered']=True;reward(s,events,'ember_delivery','authored-return-objective')
            elif target=='trial':
                require(room=='shrine' and flags.get('delivered') and s['level']==2,'CompleteGrowthBeforeTrial');start_battle(s,events,draw)
            else:raise RulesError('UnknownInteraction')
        elif command=='resolve_check':
            pending=s['pending_check'];require(pending is not None,'NoPendingCheck');require(args['choice'] in ('tactical','accept'),'UnknownChoice')
            success=False;bonus=0
            if args['choice']=='tactical':
                require(s['level']==2 and s['second_wind']>0,'TacticalMindUnavailable');bonus=draw(1,10)
                success=pending['test']['total']+bonus>=pending['dc']
                if success:s['second_wind']-=1
            s['pending_check']=None
            emit(events,s,'tactical_mind',bonus=bonus,spent=success,success=success)
            checked_outcome(s,events,pending['kind'],success,draw)
        elif command=='level_up':
            require(s['level']==1 and s['xp']>=300,'LevelNotAvailable');style=args['style'];require(style in ('defense','dueling'),'UnsupportedBuildChoice')
            s['level']=2;s['hero']['max_hp']+=8;s['hit_dice']+=1;s['action_surge']=1;s['build']['style']=style
            s['hero']['ac']=19 if style=='defense' else 18;s['hero']['damage_bonus']=3 if style=='defense' else 5
            emit(events,s,'level_up',before=1,after=2,features=['action_surge','tactical_mind'],style=style)
        elif command=='equip':
            require(room=='camp' and args['weapon'] in WEAPONS,'PrepareSupportedGearAtCamp');weapon=args['weapon'];info=WEAPONS[weapon]
            s['hero'].update(weapon=weapon,damage_die=info['die'],damage_type=info['type']);s['seconds']+=60
            emit(events,s,'equipment',weapon=weapon)
        elif command=='rest':
            require(room=='camp' and s['hero']['hp']>0,'RestRequiresSafeCampAndHP');kind=args['kind'];require(kind in ('short','long'),'UnknownRest')
            if kind=='long':
                require(s['seconds']-s['last_long_rest_end']>=57600,'LongRestTooSoon')
                s['seconds']+=28800;s['last_long_rest_end']=s['seconds'];s['hero']['hp']=s['hero']['max_hp'];s['hit_dice']=s['level'];s['second_wind']=2;s['short_rest_open']=False
                s['hero']['temp_hp']=0
            else:s['seconds']+=3600;s['second_wind']=min(2,s['second_wind']+1);s['short_rest_open']=True
            if s['level']==2:s['action_surge']=1
            emit(events,s,'rest',kind=kind,minutes=s['seconds']/60)
        elif command=='spend_hit_die':
            require(room=='camp' and s['short_rest_open'] and s['hit_dice']>0,'NoCompletedShortRestOrDice')
            die=draw(1,10);before=s['hero']['hp'];heal(s['hero'],max(1,die+2));s['hit_dice']-=1
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
    if s['battle'] is None and s['seconds']-state['seconds']>=6:
        s['hero'].pop('sapped_by',None)
        s['hero'].update(action=True,reaction=True,bonus_action=True,extra_actions=0,movement=s['hero']['speed'],dodge=False,disengage=False)
    s['revision']+=1
    for event in events:
        event['frame']['meta']['revision']=s['revision']
        for action in event['frame']['meta']['actions']:action['arguments']['revision']=s['revision']
    if not events:emit(events,s,'state_changed',command=command)
    events[-1]['frame']=view(s)
    return s,events
