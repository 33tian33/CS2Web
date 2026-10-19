const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context=vm.createContext({document:{},bpMapKeys:{},setInterval(){},window:{addEventListener(){}},fetch:()=>new Promise(()=>{}),teamIdentity:t=>t?.name||'待定'});
vm.runInContext(fs.readFileSync('public/app.js','utf8'),context);
vm.runInContext(`
state={teams:[{id:1,name:'Alpha'},{id:2,name:'Beta'}],matches:[
{id:1,team_a:1,team_b:2,round_name:'已完成场次',bo:3,status:'finished',time:'2026-10-19T12:00'},
{id:2,team_a:1,team_b:2,round_name:'正在比赛',bo:3,status:'live',time:'2026-10-19T13:00'},
{id:3,team_a:1,team_b:2,round_name:'未来场次',bo:3,status:'scheduled',time:''}
]};`,context);
const run=code=>vm.runInContext(code,context);
const before=run('JSON.stringify(state.matches)');
assert.match(run('adminMatches()'),/已完成场次/);
run('hideFinishedMatches=true');
const filtered=run('adminMatches()');
assert.doesNotMatch(filtered,/已完成场次/);
assert.match(filtered,/正在比赛/);
assert.match(filtered,/未来场次/);
assert.match(filtered,/type="checkbox" checked/);
assert.equal(run('JSON.stringify(state.matches)'),before);
run('hideFinishedMatches=false');
assert.match(run('adminMatches()'),/已完成场次/);
console.log('Schedule filter: finished hidden, live/scheduled retained, restore and non-mutation passed');
