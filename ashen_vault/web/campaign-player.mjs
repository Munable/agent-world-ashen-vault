const clone=x=>JSON.parse(JSON.stringify(x));
export function validateManifest(manifest){
 if(manifest?.version!==1||manifest.schema!=='ashen-campaign/2')throw Error('Unsupported asset contract');
 for(const binding of Object.values(manifest.bindings||{}))if(!Number.isFinite(binding.duration_ms)||binding.duration_ms<0||binding.duration_ms>1200)throw Error('Invalid binding duration');
 if(!Object.keys(manifest.skins||{}).length)throw Error('No skin binding');
 for(const skin of Object.values(manifest.skins)){
  for(const k of ['floor','wall','hero','enemy','accent'])if(!/^#[0-9a-fA-F]{6}$/.test(skin[k]))throw Error('Invalid palette');
  if(!['circle','diamond'].includes(skin.shape))throw Error('Unsupported geometric asset');
 }
 return manifest;
}
export function validateCue(cue,manifest){
 if(cue?.version!==1||cue.channel!=='action'||cue.phase!=='finish'||cue.subject_id!=='hero'||typeof cue.cue_id!=='string')throw Error('Unsupported presentation cue');
 const data=cue.data;
 if(data?.schema!==manifest.schema||!Number.isInteger(data.step)||data.step<0||!data.frame?.meta||!data.frame?.entities)throw Error('Malformed world payload');
 if(!manifest.bindings[cue.name])throw Error('Missing semantic resource binding: '+cue.name);
 return true;
}
function mix(a,b,t){return a+(b-a)*t;}
function pathPosition(start,path,t){
 const points=[start,...path];if(points.length===1)return start;
 const f=Math.min(.999999,t)*(points.length-1),index=Math.floor(f),part=f-index;
 return [mix(points[index][0],points[index+1][0],part),mix(points[index][1],points[index+1][1],part)];
}
export function sample(before,after,cue,t){
 const frame=clone(t<.5?before:after),d=cue.data.event;const fx={kind:cue.name,progress:t};
 if(cue.name==='campaign.travel'){
  frame.entities=clone(after.entities);frame.entities.hero.position=pathPosition(d.start,[d.end],t);fx.path=[d.start,d.end];
 } else if(cue.name==='campaign.combat'){
  const r=d.result,actor=d.actor;const attack=r?.attack_result||(r?.attack?r:null);
  let moving=actor,path=r?.traveled||[],moveT=t;
  if(d.command==='react'){
   moving=r.mover;path=r.movement?.traveled||[];moveT=attack?Math.max(0,(t-.6)/.4):t;
  }
  frame.entities=clone(before.entities);
  if(path.length&&frame.entities[moving]){
   const start=d.before[moving].position;frame.entities[moving].position=pathPosition(start,path,moveT);fx.path=[start,...path];
  }
  if(attack){
   const target=r.target||r.mover;const attackT=d.command==='react'?Math.min(1,t/.6):t;
   fx.attack={actor,target,start:d.before[actor]?.position,end:d.before[target]?.position,hit:attack.hit,damage:attack.damage,critical:attack.critical,progress:attackT};
   if(attackT>=.55&&frame.entities[target])frame.entities[target].hp=d.after[target].hp;
  }
 } else if(cue.name==='campaign.spell'){
  const r=d.result;frame.entities=clone(before.entities);
  if(r?.target&&frame.entities[r.target]&&after.entities[r.target]){
   fx.attack={actor:'hero',target:r.target,start:before.entities.hero?.position,end:before.entities[r.target]?.position,
              hit:r.hit!==false,damage:r.damage||0,critical:false,progress:t};
   if(t>=.55)frame.entities[r.target].hp=after.entities[r.target].hp;
  }
  fx.text=r?.spell==='mage_armor'?'Mage Armor · AC '+r.ac:r?.spell==='magic_missile'?'Magic Missile · '+r.damage+' 伤害':r?.spell==='ray_of_frost'?(r.hit?'Ray of Frost · '+r.damage+' 伤害':'Ray of Frost · 未命中'):'法术已结算';
 } else if(cue.name==='campaign.reward')fx.text=[d.after.xp>d.before.xp?'+'+(d.after.xp-d.before.xp)+' XP':'',d.after.gold>d.before.gold?'+'+(d.after.gold-d.before.gold)+' GP':'',d.after.potions>d.before.potions?'+'+(d.after.potions-d.before.potions)+' 药水':''].filter(Boolean).join(' · ');
 else if(cue.name==='campaign.level_up'&&t>=.5)fx.text='升至 '+d.after+' 级';
 else if(cue.name==='campaign.healing')fx.text='+'+(d.after-d.before)+' HP';
 else if(cue.name==='campaign.check')fx.text=(d.test?.mode==='advantage'?'优势 · ':d.test?.mode==='disadvantage'?'劣势 · ':'')+d.check+' '+d.test.total;
 else if(cue.name==='campaign.check_result')fx.text=d.success?'检定成功':'检定失败';
 else if(cue.name==='campaign.item')fx.text=d.outcome==='purchased'?'获得药水 · -50 金币':'已取得火种';
 else if(cue.name==='campaign.ability')fx.text='动作如潮 · 额外行动';
 return {frame,fx};
}
export class Playback{
 constructor(manifest,render,{animate=true}={}){
  this.manifest=validateManifest(manifest);this.render=render;this.animate=animate;this.skin=Object.keys(manifest.skins)[0];
  this.seen=new Set();this.steps=new Map();this.epoch=0;this.snapshot={entities:{},meta:{joined:false,actions:[]}};
  this.stats={applied:0,animated:0,duplicates:0,skipped:0,resets:0};
 }
 setSkin(id){if(!this.manifest.skins[id])throw Error('Unknown asset pack');this.skin=id;this.render(this.snapshot,null,this.skin);}
 reset(snapshot){this.epoch++;this.snapshot=clone(snapshot);this.steps.clear();this.stats.resets++;this.render(this.snapshot,null,this.skin);}
 async play(events,{now=Infinity,live=true}={}){
  const fresh=[],localSeen=new Set(this.seen),steps=new Map(this.steps);
  for(const event of events){
   const cue=event.cue;validateCue(cue,this.manifest);
   if(localSeen.has(cue.cue_id)){this.stats.duplicates++;continue;}
   const old=steps.get(cue.data.action_id);
   if((old===undefined&&(cue.data.step!==0||cue.data.caused_by!==null))||(old!==undefined&&cue.data.step!==old.step+1)||
      (old!==undefined&&cue.data.caused_by!==old.id))throw Error('Presentation causal gap');
   localSeen.add(cue.cue_id);steps.set(cue.data.action_id,{step:cue.data.step,id:cue.cue_id});fresh.push(event);
  }
  if(!fresh.length)return;
  const epoch=this.epoch;this.steps=steps;
  for(const event of fresh){this.seen.add(event.cue.cue_id);}
  while(this.seen.size>512)this.seen.delete(this.seen.values().next().value);
  while(this.steps.size>64)this.steps.delete(this.steps.keys().next().value);
  const cost=fresh.reduce((sum,e)=>sum+this.manifest.bindings[e.cue.name].duration_ms,0);
  const stale=fresh.some(e=>!Number.isFinite(e.occurred_at)||now-e.occurred_at>15||e.occurred_at-now>60);
  if(!live||stale||fresh.length>16||cost>4000){
   this.snapshot=clone(fresh.at(-1).cue.data.frame);this.stats.skipped+=fresh.length;this.stats.applied+=fresh.length;this.render(this.snapshot,null,this.skin);return;
  }
  for(const event of fresh){
   if(epoch!==this.epoch)return;
   const cue=event.cue,after=cue.data.frame,before=this.snapshot,duration=this.manifest.bindings[cue.name].duration_ms;
   if(this.animate&&duration){
    const start=performance.now();
    await new Promise(resolve=>{
     const step=()=>{
      if(epoch!==this.epoch){resolve();return;}
      const t=Math.min(1,(performance.now()-start)/duration),draw=sample(before,after,cue,t);
      this.render(draw.frame,draw.fx,this.skin);
      if(t<1)requestAnimationFrame(step);else resolve();
     };requestAnimationFrame(step);
    });this.stats.animated++;
   }
   if(epoch!==this.epoch)return;
   this.snapshot=clone(after);this.stats.applied++;this.render(this.snapshot,null,this.skin);
  }
 }
}
