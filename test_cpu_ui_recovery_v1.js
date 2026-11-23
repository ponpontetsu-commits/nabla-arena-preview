'use strict';
// Execute the production helper in an isolated VM with simulated API outcomes.
// This is a JS behavior test; it does not claim to test actual browsers.
const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('app.js', 'utf8');
const marker = '// NABLA-CPU-WHOLEBOARD-STABILITY-V1';
const start = source.indexOf(marker);
const end = source.indexOf('async function runCpuTurn(){', start);
assert(start >= 0 && end > start, 'recovery helper must be installed');
const helper = source.slice(start, end);
assert(source.includes('}catch(e){await recoverCpuAfterError(e)}'));

function setup(apiResult) {
  const ctx = {
    model: { game_id:'test-g', current:1, mode:'cpu', finished:false, revision:0 },
    selected:[1], target:{seat:0}, order:[0],
    api: async()=> { if (apiResult instanceof Error) throw apiResult; return apiResult; },
    render: ()=>{ctx.renders++;}, renderFinished: ()=>{ctx.finished++;},
    showResult: ()=>{ctx.results++;},
    setMessage: (message)=>{ctx.messages.push(message);},
    openModal: (_title,html)=>{ctx.modal=html;},
    closeModal: ()=>{ctx.closed++;},
    runCpuTurn: ()=>{ctx.retryCalls++;},
    $: ()=>({addEventListener: (_name,handler)=>{ctx.retry=handler;}}),
    renders:0,finished:0,results:0,retryCalls:0,closed:0,messages:[],modal:null,retry:null,
  };
  const fn = vm.runInNewContext(helper+'\nrecoverCpuAfterError;', ctx);
  return {ctx, fn};
}
async function run(){
  {
    const {ctx,fn}=setup({ok:true,state:{game_id:'test-g',current:0,mode:'cpu',finished:false,revision:1}});
    await fn(new Error('500'));
    assert.equal(ctx.model.current,0);
    assert.equal(ctx.model.revision,1);
    assert.equal(ctx.renders,1);
    assert.equal(ctx.modal,null);
    assert.equal(ctx.retryCalls,0);
  }
  {
    const {ctx,fn}=setup({ok:true,state:{game_id:'test-g',current:1,mode:'cpu',finished:false,revision:0}});
    await fn(new Error('500'));
    assert.match(ctx.modal,/CPUの手番を再試行/);
    assert.equal(ctx.retryCalls,0);
    ctx.retry();
    assert.equal(ctx.retryCalls,1);
  }
  {
    const {ctx,fn}=setup({ok:true,state:{game_id:'test-g',current:0,mode:'cpu',finished:true,revision:1}});
    await fn(new Error('500'));
    assert.equal(ctx.finished,1);
    assert.equal(ctx.results,1);
  }
  {
    const {ctx,fn}=setup({ok:true,state:{game_id:'different-game',current:0,mode:'cpu',finished:false,revision:1}});
    await fn(new Error('500'));
    assert.equal(ctx.model.game_id,'test-g','must not accept a different game');
    assert.match(ctx.modal,/状態を再取得/);
  }
  {
    const {ctx,fn}=setup(new Error('network down'));
    await fn(new Error('500'));
    assert.match(ctx.modal,/状態を再取得/);
    assert.equal(ctx.retryCalls,0);
  }
  console.log('PASS 5 CPU state recovery scenarios');
}
run().catch(e=>{console.error(e);process.exitCode=1});
