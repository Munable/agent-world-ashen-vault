const $=selector=>document.querySelector(selector);
const ns='http://www.w3.org/2000/svg';
function svg(name,attrs,text){const node=document.createElementNS(ns,name);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text!==undefined)node.textContent=text;return node;}
async function post(path,body){const response=await fetch(path,{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error('HTTP '+response.status);return response.json();}
function render(snapshot){
 const meta=snapshot.meta,arena=meta.arena,board=$('#board');board.replaceChildren();
 for(let y=0;y<arena.height;y++)for(let x=0;x<arena.width;x++){
  const wall=arena.walls.some(p=>p[0]===x&&p[1]===y),hard=arena.difficult.some(p=>p[0]===x&&p[1]===y);
  board.append(svg('rect',{x:x*40+1,y:y*40+1,width:38,height:38,rx:2,fill:wall?'#596169':hard?'#45443c':'#23313a'}));
  if(hard)board.append(svg('path',{d:`M${x*40+8} ${y*40+32}l24 -24 M${x*40+8} ${y*40+20}l12 -12`,stroke:'#a79f7a','stroke-width':2}));
 }
 $('#actors').replaceChildren();
 for(const [id,actor] of Object.entries(snapshot.entities)){
  const [x,y]=actor.position,isActive=id===meta.active,color=id==='warden'?'#97bed0':'#cfaa83';
  const group=svg('g',{'data-actor':id,'data-position':actor.position.join(',')});
  group.append(svg('circle',{cx:x*40+20,cy:y*40+20,r:13,fill:actor.dead?'#555d61':color,stroke:isActive?'#fff6cf':'none','stroke-width':3}));
  group.append(svg('text',{x:x*40+20,y:y*40+24,'text-anchor':'middle',fill:'#16212a','font-size':12},id==='warden'?'卫':'骷'));board.append(group);
  const card=document.createElement('div');card.className='actor';card.dataset.seat=id;
  const name=document.createElement('strong');name.textContent=actor.name+(isActive?' · 当前回合':'');
  const info=document.createElement('div');info.className='small';info.textContent=`HP ${actor.hp}/${actor.max_hp} · AC ${actor.ac} · 剩余移动 ${actor.movement} 英尺 · 动作 ${actor.action?'可用':'已用'} · 反应 ${actor.reaction?'可用':'已用'}${actor.dead?' · 死亡':actor.knocked_out?' · 击昏':''}${actor.conditions.length?' · '+actor.conditions.join(', '):''}`;
  card.append(name,info);$('#actors').append(card);
 }
 const names={lobby:'等待两个身份分别加入',active:'战斗中',complete:'本次战斗已结束'};
 $('#status').textContent=`${names[meta.phase]} · 第 ${meta.round} 轮 · 回合 ${meta.turn_id}${meta.winner?' · 胜出 '+meta.winner:''}`;
 $('#status').dataset.phase=meta.phase;
 const pending=meta.pending;$('#window').hidden=!pending;
 if(pending)$('#window').textContent=`等待 ${pending.reactor} 决定机会攻击或放弃。窗口 ${pending.window_id}。${pending.mover} 尚未离开当前位置。`;
}
function renderEvents(events){
 const list=$('#events');list.replaceChildren();
 for(const event of events){const item=document.createElement('li'),p=event.payload;
  if(event.kind==='seat_joined')item.textContent=`${p.seat} 已加入`;
  else {let line=`第 ${p.round} 轮 · ${p.actor} · ${p.command}`;const result=p.result?.attack_result||p.result;
   if(result?.attack){line+=` | d20 [${result.attack.dice.join(', ')}] ${result.attack.mode} +${result.attack.modifier} = ${result.attack.total} | ${result.hit?'命中，伤害 '+result.damage:'未命中'}${result.critical?'，重击':''}`;}
   if(p.result?.status==='awaiting_reaction')line+=' | 等待反应，不是已到达';item.textContent=line;}
  list.append(item);
 }
}
let stopped=false;
async function refresh(){
 try{const view=await post('/v1/public/views/battle/snapshot',{});render(view.snapshot);const stream=await post('/v1/public/streams/combat/read',{limit:50});renderEvents(stream.events);$('#error').textContent='';}
 catch(error){$('#error').textContent='当前无法读取最新状态，画面保留上次事实：'+error.message;}
 finally{if(!stopped)setTimeout(refresh,document.hidden?2500:900);}
}
window.addEventListener('pagehide',()=>{stopped=true;});refresh();
