import {Playback} from '/campaign-player.js';
const $=q=>document.querySelector(q),ns='http://www.w3.org/2000/svg';
const manifest=await fetch('/campaign-assets.json',{credentials:'omit'}).then(r=>r.json());
let token='',control=true,cursor=null,busy=false,syncing=null,pending=null,clockServer=0,clockLocal=0,generation=0,observation=0;
const labels={'campaign.joined':'远征开始','campaign.travel':'正在前往下一片区域','campaign.combat':'战斗裁决','campaign.reward':'奖励已结算','campaign.encounter':'遭遇开始','campaign.ending':'远征结果','campaign.objective':'目标变化','campaign.check_result':'检定结果','campaign.check':'检定','campaign.tactical_mind':'战术头脑','campaign.healing':'恢复','campaign.ability':'职业能力','campaign.level_up':'升级','campaign.equipment':'装备准备','campaign.rest':'休息完成','campaign.retreat':'撤退','campaign.item':'拾取火种','campaign.state_changed':'状态更新'};
function svg(name,attrs={},text){const el=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;return el;}
function actorGlyph(id,actor,skin){
 const [x,y]=actor.position.map(n=>n*40+20),g=svg('g',{'data-actor':id,'data-position':actor.position.join(',')});
 const attrs={fill:actor.dead?'#687779':skin[id==='hero'?'hero':'enemy'],stroke:skin.accent,'stroke-width':2};
 g.append(skin.shape==='circle'?svg('circle',{cx:x,cy:y,r:12,...attrs}):svg('polygon',{points:`${x},${y-15} ${x+13},${y} ${x},${y+15} ${x-13},${y}`,...attrs}));
 g.append(svg('text',{x,y:y+4,'text-anchor':'middle','font-size':11,fill:'#15232b'},id==='hero'?'旅':'守'));
 g.append(svg('rect',{x:x-16,y:y-23,width:32,height:4,fill:'#243b3f'}),svg('rect',{x:x-16,y:y-23,width:32*Math.max(0,actor.hp/actor.max_hp),height:4,fill:skin.hero}));
 if(actor.sapped_by)g.append(svg('text',{x,y:y+28,'text-anchor':'middle',fill:skin.accent,'font-size':11},'削弱'));
 if(actor.conditions?.length)g.append(svg('text',{x,y:y+39,'text-anchor':'middle',fill:skin.accent,'font-size':10},actor.conditions.includes('unconscious')?'昏迷':actor.conditions.join(',')));
 return g;
}
function render(scene,fx,skinId){
 const m=scene.meta,skin=manifest.skins[skinId],board=$('#board');board.replaceChildren();
 $('#game').hidden=!token;$('#disconnect').hidden=!token;
 if(!token)return;
 $('#location').textContent=m.joined?m.room_name:'准备远征';
 if(m.joined){
  const arena=m.arena;
  for(let y=0;y<8;y++)for(let x=0;x<14;x++)board.append(svg('rect',{x:x*40+1,y:y*40+1,width:38,height:38,rx:3,fill:arena.walls.some(p=>p[0]===x&&p[1]===y)?skin.wall:skin.floor}));
  for(const point of arena.difficult)board.append(svg('path',{d:`M${point[0]*40+8} ${point[1]*40+30}l24 -20`,stroke:skin.accent,'stroke-width':3}));
  if(!m.battle){for(const [id,room] of Object.entries(m.known_rooms)){
   board.append(svg('rect',{x:room.position[0]*40+2,y:room.position[1]*40+2,width:36,height:36,rx:7,fill:skin.wall,'data-room':id}));
   board.append(svg('text',{x:room.position[0]*40+20,y:room.position[1]*40-6,'text-anchor':'middle',fill:'#dce8e8','font-size':11},room.name));
  }}
  if(fx?.path)board.append(svg('polyline',{points:fx.path.map(p=>`${p[0]*40+20},${p[1]*40+20}`).join(' '),fill:'none',stroke:skin.accent,'stroke-width':2,'stroke-dasharray':'4 4'}));
  for(const [id,actor] of Object.entries(scene.entities))board.append(actorGlyph(id,actor,skin));
  if(fx?.attack?.start&&fx.attack.end){
   const a=fx.attack,t=a.progress,from=a.start.map(v=>v*40+20),to=a.end.map(v=>v*40+20);
   if(t>.2&&t<.8)board.append(svg('line',{x1:from[0],y1:from[1],x2:to[0],y2:to[1],stroke:skin.accent,'stroke-width':3,'data-effect':'attack'}));
   if(t>.5)board.append(svg('text',{x:to[0],y:to[1]-20-20*t,'text-anchor':'middle',fill:skin.accent,'font-size':18,'data-effect':'damage'},a.hit?`${a.critical?'重击 ':''}-${a.damage}`:'未命中'));
  }
  if(fx?.text){board.append(svg('rect',{x:110,y:36,width:340,height:50,rx:9,fill:'#112126',opacity:.96}));board.append(svg('text',{x:280,y:69,'text-anchor':'middle',fill:skin.accent,'font-size':23,'data-effect':'feedback'},fx.text));}
  const h=scene.entities.hero;
  $('#stats').textContent=`战士 ${m.level} 级 · HP ${h.hp}/${h.max_hp} · AC ${h.ac}\n经验 ${m.xp}/300 · 金币 ${m.gold} · 药水 ${m.potions}\n第二风息 ${m.second_wind}/2 · 动作如潮 ${m.action_surge} · 生命骰 ${m.hit_dice}\n${m.battle?'第 '+m.battle.round+' 轮，当前 '+m.battle.active+'，移动 '+h.movement+' 英尺':'世界内已过 '+Math.floor(m.minutes)+' 分钟'}`;
  $('#stats').style.whiteSpace='pre-line';$('#xp').value=Math.min(300,m.xp);$('#quest').textContent=m.quest;$('#room-text').textContent=m.text;
  $('#details').textContent=`${m.build.species} / ${m.build.background}\n${m.build.ability_source}\n专长 ${m.build.origin_feat} · 风格 ${m.style}\n当前武器 ${m.weapon} · 1d${h.damage_die}+${h.damage_bonus} · Sap\n本切片仅提供三种已掌握的 Sap 近战武器；营地准备、持盾使用。未实现的远程、施法、隐藏及其它动作不会伪造结果。\n`+JSON.stringify(m.build.skills);
  $('#ending').hidden=!m.ending;$('#ending').textContent=m.ending||'';
 } else {$('#stats').textContent='原身份已验证；开始冒险不会创建第二个身份。';$('#quest').textContent='准备角色与委托';$('#room-text').textContent='';}
 $('#caption').textContent=fx?labels[fx.kind]||fx.kind:m.battle?.pending?'等待玩家反应，不会自动放弃。':m.pending_check?'等待检定决定，结果尚未最终结算。':m.joined?'服务器事实已同步。':'首次初始化角色挂接数据。';
 $('#actions').replaceChildren();
 if(control)for(const action of m.actions||[]){const b=document.createElement('button');b.textContent=action.label;b.dataset.tool=action.tool;b.dataset.arguments=JSON.stringify(action.arguments);b.disabled=busy||!!pending;b.onclick=()=>send(action);$('#actions').append(b);}
}
const player=new Playback(manifest,render);
window.__ashenDebug=()=>({stats:{...player.stats},skin:player.skin,revision:player.snapshot.meta.revision,level:player.snapshot.meta.level,joined:player.snapshot.meta.joined,busy});
function notice(text){$('#notice').textContent=text;}
async function api(path,body){
 const headers={'Authorization':'Bearer '+token};if(body!==undefined)headers['Content-Type']='application/json';
 let response;
 try{response=await fetch(path,{method:body===undefined?'GET':'POST',headers,credentials:'omit',body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(8000)});}
 catch{const e=Error('连接未确认，不能据此判断操作没有发生');e.status=0;throw e;}
 const value=await response.json();if(!response.ok){const e=Error(value.message||`HTTP ${response.status}`);e.status=response.status;e.code=value.error;throw e;}return value;
}
function clear(){generation++;token='';cursor=null;pending=null;busy=false;syncing=null;$('#key').value='';$('#log').replaceChildren();$('#game').hidden=true;$('#connect-panel').hidden=false;$('#receipt').hidden=true;$('#retry').hidden=true;for(const id of ['stats','quest','details','room-text','ending','caption'])$('#'+id).textContent='';$('#ending').hidden=true;$('#xp').value=0;player.reset({entities:{},meta:{joined:false,actions:[]}});}
function addLogs(events){
 const list=$('#log'),follow=list.scrollTop+list.clientHeight>=list.scrollHeight-20;
 for(const e of events){const d=e.cue.data.event;const li=document.createElement('li');let label=labels[e.cue.name]||e.cue.name;
  if(e.cue.name==='campaign.combat'){
   const r=d.result,a=r?.attack_result||(r?.attack?r:null);label=(d.origin==='scripted_npc'?'脚本 NPC':'玩家行动')+' · '+d.command;
   if(a)label+=` · d20 ${a.attack.dice.join('/')} +${a.attack.modifier} = ${a.attack.total} · ${a.hit?'命中，伤害 '+a.damage:'未命中'}`;
  }
  if(e.cue.name==='campaign.item')label=d.outcome==='purchased'?'购买药水 · -50 金币':'取回火种';
  if(e.cue.name==='campaign.reward')label+=' · '+[['xp','XP'],['gold','金币'],['potions','药水']].filter(([k])=>d.after[k]>d.before[k]).map(([k,unit])=>'+'+(d.after[k]-d.before[k])+' '+unit).join(' / ');
  li.textContent=label;$('#log').append(li);
 }
 while($('#log').children.length>40)$('#log').firstChild.remove();
 if(follow)list.scrollTop=list.scrollHeight;
}
async function reset(){const mine=generation,obs=++observation;const result=await api('/v1/views/adventure/snapshot',{});if(mine!==generation||obs!==observation)return;
 if(!Number.isFinite(result.observed_at)||!result.timeline_cursor)throw Error('不支持的观察协议');
 clockServer=result.observed_at;clockLocal=performance.now();cursor=result.timeline_cursor;player.reset(result.snapshot);
}
async function sync(){
 if(syncing)return syncing;
 const mine=generation,obs=observation;
 syncing=(async()=>{
  if(!token||!cursor)return;
  const events=[];let more=true;
  while(more){const response=await api('/v1/views/timeline',{cursor,limit:40});if(mine!==generation||obs!==observation)return;
   cursor=response.cursor;events.push(...response.events);more=response.has_more;
   if(events.length>120){await reset();notice('积压记录已恢复为当前状态，没有补播旧动作。');return;}
  }
  if(events.length){busy=true;render(player.snapshot,null,player.skin);addLogs(events);await player.play(events,{now:clockServer+(performance.now()-clockLocal)/1000,live:!document.hidden});}
 })().finally(()=>{if(mine===generation){syncing=null;busy=false;render(player.snapshot,null,player.skin);}});
 return syncing;
}
async function send(action,reuse=false){
 if(!token||busy||(!reuse&&pending))return;
 const mine=generation;busy=true;
 if(!reuse)pending={tool:action.tool,arguments:action.arguments,id:crypto.randomUUID()};
 render(player.snapshot,null,player.skin);
 try{const result=await api('/v1/functions/'+pending.tool+'/invoke',{operation_id:pending.id,arguments:pending.arguments});if(mine!==generation)return;
  pending=null;$('#receipt').hidden=true;$('#retry').hidden=true;await sync();
  if(result.result?.scene?.meta?.revision>player.snapshot.meta.revision)await sync();notice('操作已由服务器确认。');
 }catch(e){if(mine!==generation)return;
  if(e.status===401||e.status===403){clear();notice('身份认证失效或无控制权限，页面数据已清除。');}
  else if(e.status>=400&&e.status<500){pending=null;await reset();notice('操作被拒绝，已同步当前状态：'+e.message);}
  else {$('#receipt').hidden=false;$('#retry').hidden=false;notice('结果待确认。只确认回执或重试原操作，不创建新操作。');}
 }finally{if(mine===generation){busy=false;render(player.snapshot,null,player.skin);}}
}
$('#connect').onsubmit=async e=>{
 e.preventDefault();const supplied=$('#key').value.trim();clear();
 if(!/^awid_[A-Za-z0-9_-]+$/.test(supplied)){notice('身份令牌格式不正确。');return;}
 token=supplied;const mine=generation;busy=true;
 try{const who=await api('/v1/whoami');if(mine!==generation)return;control=who.access_mode!=='observe';await reset();
  $('#connect-panel').hidden=true;notice(control?'原身份已验证；继续已有远征或开始一次新远征。':'只读身份：可以查看，不能控制。');
 }catch(e){if(mine===generation){clear();notice('连接未完成：'+e.message);}}finally{if(mine===generation){busy=false;render(player.snapshot,null,player.skin);}}
};
$('#disconnect').onclick=()=>{clear();notice('已断开，身份令牌与当前页面数据已清除。');};
$('#skin').onchange=e=>player.setSkin(e.target.value);
$('#retry').onclick=()=>send(null,true);
$('#receipt').onclick=async()=>{
 if(!pending)return;try{await api('/v1/receipts/'+encodeURIComponent(pending.id));pending=null;$('#receipt').hidden=true;$('#retry').hidden=true;await sync();notice('已找到已提交回执，未重复执行。');}
 catch(e){notice(e.status===404?'尚无回执；只能重试同一操作，不能据此新建操作。':e.message);}
};
async function loop(){if(token&&!busy&&!document.hidden){try{await sync();}catch(e){if(e.status===401||e.status===403){clear();notice('权限已失效，旧数据已清除。');}else{try{await reset();notice('已恢复当前状态，没有重播历史动作。');}catch{notice('暂时无法读取最新状态，显示的是上次确认状态。');}}}}setTimeout(loop,1000);}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&token)reset().catch(()=>{});});
window.addEventListener('pagehide',()=>clear());loop();
