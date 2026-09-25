import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,access} from 'node:fs/promises';
import {Playback,sample,validateManifest,validateCue} from '../ashen_vault/web/campaign-player.mjs';
const manifest=JSON.parse(await readFile(new URL('../ashen_vault/web/campaign-assets.json',import.meta.url),'utf8'));
const initial={entities:{hero:{hp:12,max_hp:12,position:[1,3]}},meta:{revision:0,actions:[]}};
function event(step=0,kind='travel',action='a'){
 const frame=structuredClone(initial);frame.meta.revision=step+1;frame.entities.hero.position=[4,3];
 return {occurred_at:100,cue:{version:1,cue_id:`${action}:${step}`,subject_id:'hero',channel:'action',phase:'finish',name:'campaign.'+kind,
  data:{schema:manifest.schema,action_id:action,step,caused_by:step?`${action}:${step-1}`:null,frame,event:{start:[1,3],end:[4,3]}}}};
}
function player(){const rendered=[];const p=new Playback(manifest,(scene,fx,skin)=>rendered.push({scene:structuredClone(scene),fx,skin}),{animate:false});p.reset(initial);return {p,rendered};}

test('moving placeholder follows confirmed path rather than teleporting early',()=>{
 const e=event();const value=sample(initial,e.cue.data.frame,e.cue,.5);
 assert.deepEqual(value.frame.entities.hero.position,[2.5,3]);assert.deepEqual(initial.entities.hero.position,[1,3]);
});
test('swapping skins never changes authoritative facts',async()=>{
 const {p}=player();await p.play([event()],{now:100});const state=structuredClone(p.snapshot);
 p.setSkin('moon');assert.deepEqual(p.snapshot,state);p.setSkin('amber');assert.deepEqual(p.snapshot,state);
 assert.throws(()=>p.setSkin('download-arbitrary-code'));
});
test('duplicate cue does not apply a result twice',async()=>{
 const {p}=player();await p.play([event()],{now:100});await p.play([event()],{now:100});assert.equal(p.stats.applied,1);assert.equal(p.stats.duplicates,1);
});
test('missing causal step rejects the batch before modifying state',async()=>{
 const {p}=player();await assert.rejects(p.play([event(1)],{now:100}),/causal gap/);assert.deepEqual(p.snapshot,initial);
});
test('an invalid first causal parent is not silently accepted',async()=>{
 const {p}=player(),e=event();e.cue.data.caused_by='unseen';await assert.rejects(p.play([e],{now:100}),/causal gap/);
});
test('unknown semantic binding is an error, not a fake success',()=>{
 assert.throws(()=>validateCue(event(0,'missing').cue,manifest),/Missing/);
});
test('invalid asset data cannot become executable color or shape code',()=>{
 const bad=structuredClone(manifest);bad.skins.amber.hero='url(javascript:alert(1))';assert.throws(()=>validateManifest(bad),/palette/);
 const badShape=structuredClone(manifest);badShape.skins.amber.shape='remote-script';assert.throws(()=>validateManifest(badShape),/geometric asset/);
});
test('old events restore final facts without animating historical rewards',async()=>{
 const {p}=player();await p.play([event()],{now:200});assert.equal(p.stats.skipped,1);assert.equal(p.stats.animated,0);assert.equal(p.snapshot.meta.revision,1);
});
test('bounded backlog snaps once and does not run an unbounded queue',async()=>{
 const {p,rendered}=player();const events=Array.from({length:40},(_,i)=>event(0,'travel','operation-'+i));await p.play(events,{now:100});
 assert.equal(p.stats.applied,40);assert.equal(p.stats.skipped,40);assert.equal(rendered.length,2);
});
test('a miss has no damage interpolation or hit text',()=>{
 const before={entities:{hero:{hp:12,position:[3,2]},enemy:{hp:11,position:[4,2]}},meta:{}};
 const e=event(0,'combat');e.cue.data.frame=structuredClone(before);
 e.cue.data.event={command:'attack',actor:'hero',result:{target:'enemy',hit:false,damage:0,critical:false,attack:{natural:2}},
  before:{hero:{position:[3,2],hp:12},enemy:{position:[4,2],hp:11}},after:{hero:{position:[3,2],hp:12},enemy:{position:[4,2],hp:11}}};
 const value=sample(before,e.cue.data.frame,e.cue,.8);assert.equal(value.frame.entities.enemy.hp,11);assert.equal(value.fx.attack.hit,false);assert.equal(value.fx.attack.damage,0);
});
test('reaction attack precedes resumed movement',()=>{
 const before={entities:{hero:{hp:12,position:[3,2]},enemy:{hp:11,position:[4,2]}},meta:{}};
 const e=event(0,'combat');e.cue.data.frame=structuredClone(before);e.cue.data.frame.entities.hero.position=[2,2];
 e.cue.data.event={command:'react',actor:'enemy',result:{mover:'hero',attack_result:{hit:false,damage:0,attack:{natural:2}},movement:{traveled:[[2,2]]}},
   before:{hero:{position:[3,2],hp:12},enemy:{position:[4,2],hp:11}},after:{hero:{position:[2,2],hp:12},enemy:{position:[4,2],hp:11}}};
 assert.deepEqual(sample(before,e.cue.data.frame,e.cue,.3).frame.entities.hero.position,[3,2]);
 assert.ok(sample(before,e.cue.data.frame,e.cue,.9).frame.entities.hero.position[0]<3);
});
test('real browser trace has the same final facts with both resource packs',async t=>{
 const file=new URL('../test-results/campaign-trace.json',import.meta.url);
 try{await access(file);}catch{t.skip('Real browser trace is produced by check_campaign_browser.py; not replaced by a synthetic trace.');return;}
 const trace=JSON.parse(await readFile(file,'utf8'));assert.ok(trace.events.length>10);
 const outputs=[];
 for(const skin of ['amber','moon']){
  const p=new Playback(manifest,()=>{},{animate:false});p.reset(trace.initial);p.setSkin(skin);
  // Small batches preserve actual order; every cue is still validated against its causal predecessor.
  for(const e of trace.events)await p.play([e],{now:e.occurred_at});
  const applied=p.stats.applied;await p.play(trace.events,{now:trace.events.at(-1).occurred_at});assert.equal(p.stats.applied,applied);
  outputs.push(p.snapshot);
 }
 assert.deepEqual(outputs[0],outputs[1]);assert.equal(outputs[0].meta.level,3);assert.equal(outputs[0].meta.xp,900);
});

test('class-specific ability feedback is not mislabeled as Action Surge',()=>{
 const before=structuredClone(initial);
 for(const [ability,choice,expected] of [
  ['cunning_action','dash','灵巧动作 · 冲刺'],
  ['steady_aim',undefined,'Steady Aim · 下一次攻击取得优势'],
  ['fast_hands',undefined,'Fast Hands · 操作场景物件'],
  ['arcane_recovery',undefined,'奥术恢复 · 恢复法术位'],
 ]){
  const e=event(0,'ability','ability-'+ability);e.cue.data.frame=structuredClone(before);
  e.cue.data.event={ability,...(choice?{choice}:{})};
  assert.equal(sample(before,e.cue.data.frame,e.cue,.8).fx.text,expected);
 }
});
