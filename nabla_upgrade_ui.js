/* NABLA ARENA upgrade UI; load AFTER app.js. No external network libraries. */
(() => {
 'use strict';
 const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const gs = id => document.getElementById(id);
 const flag = 'nabla_answer_extra_details_v2';
 // NABLA-SPEED-2026-11
 let stepsOn = localStorage.getItem(flag)==='on';
 let activePractice = false;
 let pstate = null;
 let chosen = [];
 let explainCache = new Map();
 let explainPending = new Set();
 const FUNC = [['zero','0'],['one','1'],['x','x'],['x2','x²'],['exp','eˣ'],['sin','sin x'],['cos','cos x']];
 const CATS = [
  ['関数カード',FUNC],
  ['全体演算',[['all_diff','全体微分'],['all_diff2','全体2階微分']]],
  ['個別の微積分',[['diff','微分'],['integrate','積分']]],
  ['乗算・除算',[['mul','乗算'],['div','除算']]],
  ['極限',[['limit_zero','0への極限'],['limit_plus_inf','+∞への極限'],['limit_minus_inf','−∞への極限'],['limsup_plus_inf','上極限'],['liminf_plus_inf','下極限']]],
  ['その他',[['sqrt','平方根'],['inverse','逆関数'],['log','自然対数']]],
 ];
 const DICT = Object.fromEntries(CATS.flatMap(c=>c[1]));
 let targetSeat=1, actorSeat=0, targetBasis=null;

 function showSettings(){
   if(typeof openModal!=='function')return;
   openModal('設定',`<p>計算過程の表示設定</p><div class="menu-options"><button id="nablaStepToggle">追加の詳しい解説：${stepsOn?'ON':'OFF'}</button></div><p>変更はこの端末のブラウザに保存します。演算結果や勝敗には影響しません。</p>`);
 }
 document.addEventListener('click',ev=>{
   const b=ev.target.closest('button');
   if(!b)return;
   if(b.id==='nablaSettingsBtn')showSettings();
   if(b.id==='nablaStepToggle'){
     stepsOn=!stepsOn;localStorage.setItem(flag,stepsOn?'on':'off');
     showSettings();explainCache.clear();
     if(typeof renderLog==='function'&&typeof model!=='undefined'&&model)renderLog();
   }
 });
 function addModalOptions(){
   const text=gs('modalText'),title=gs('modalTitle');
   if(!text||!title)return;
   if(title.textContent==='メニュー'&&!gs('nablaSettingsBtn')){
     const button=document.createElement('button');button.id='nablaSettingsBtn';button.textContent='設定';
     (text.querySelector('.menu-options')||text).appendChild(button);
   }
   if(title.textContent.startsWith('ルール')&&!gs('nablaRuleFouls')){
      const box=document.createElement('section');box.id='nablaRuleFouls';
      box.innerHTML=`<h3>反則負け・基底消滅・計算未対応</h3>
       <p><strong>反則負け</strong>：明示的な0除算、定義域が空となる操作、存在しない通常の極限など、確定済みの反則条件に該当すると、その操作者が敗北します。</p>
       <p><strong>基底消滅</strong>：演算結果が0になる、所定の極限が無限大へ発散する、同じ場の別の基底と比例する場合など。反則とは異なります。</p>
       <p><strong>計算未対応</strong>：厳密に判定できないときはカードを消費せず、選び直します。証明できないことだけを理由に反則とはしません。</p>
       <h4>0除算</h4><p><code>(x²+1) ÷ 0</code> は反則です。一方 <code>(x²−1)/(x−1)</code> では、もとの式の制約 <code>x≠1</code> と簡約後の関数を区別して記録します。</p>
       <h4>極限</h4><p><code>sin(x)</code> の <code>x→+∞</code> での通常の極限は振動して存在しません。<code>x→0</code> の極限は定義域内からの片側極限を認めます。</p>
       <h4>平方根・対数</h4><p><code>√(x²)=|x|</code> です。<code>log</code> は自然対数で、実数では真数が正である必要があります。</p>
       <h4>逆関数</h4><p>関数の単調な枝・定義域・値域を確認します。数学的な反則と、現在の計算エンジンで枝を厳密に確定できない場合は区別します。</p>
       <p>カードによって成立条件が異なるため、具体的な判定はその対戦時の演算ログに従います。</p>`;
      text.appendChild(box);
   }
 }
 const modalText=gs('modalText');
 if(modalText)new MutationObserver(addModalOptions).observe(modalText,{childList:true});

 // Append verified steps asynchronously. No impact on authoritative outcomes.
 const originalEventView=typeof eventView==='function'?eventView:null;
 const idForEvent=ev=>ev?.id??(Number.isInteger(ev?.turn)?`rev-${ev.turn}`:null);
 function labelExplanation(e){
   const lines=(e?.calculations||[]).map((c,i)=>{
     const details=(c.steps||[]).map(s=>`<div class="nabla-step"><div>${esc(s.explanation)}</div>${s.mathml?`<div class="nabla-math">${s.mathml}</div>`:''}</div>`).join('');
     return `<section><div class="log-label">${c.id?'No.'+esc(c.id):'計算'+(i+1)} の途中計算</div>${details}</section>`;
   }).join('');
   return lines || '<small>この操作には追加の途中計算がありません。</small>';
 }
 async function loadExplanation(ev){
   const id=idForEvent(ev);
   if(!id||explainPending.has(id))return;
   explainPending.add(id);
   try{
     const isRoom=typeof isOnline==='function'&&isOnline();
     const room=isRoom&&typeof online!=='undefined'?online.room:null;
     const endpoint=isRoom?'online/explain':'explain';
     const result=await api(endpoint,{event_id:id,...(room?{room}:{})});
     if(result.ok&&result.explanation)explainCache.set(id,result.explanation);
     else explainCache.set(id,{calculations:[]});
   }catch(e){explainCache.set(id,{calculations:[]});}
   finally{
     explainPending.delete(id);
     if(stepsOn&&typeof model!=='undefined'&&model&&typeof renderLog==='function')renderLog();
   }
 }
 if(originalEventView){
   // eventView is a function declaration in the existing application.
   eventView=function(ev){
    if(!ev)return originalEventView(ev);
     const visible=stepsOn?ev:{...ev,calculations:(ev.calculations||[]).map(c=>({...c,steps:[]}))};
     let out=originalEventView(visible);
     if(!stepsOn || !ev || ev.kind==='pass')return out;
     const id=idForEvent(ev);
     if(!id)return out;
     if(explainCache.has(id))out+=`<div class="nabla-steps">${labelExplanation(explainCache.get(id))}</div>`;
     else{
       out+='<div class="nabla-calculating">途中計算を生成中…</div>';
       setTimeout(()=>loadExplanation(ev),0);
     }
     return out;
   };
 }

 // Deck-side timer. Online time is based on authoritative server timestamps.
 const deck=document.querySelector('.deck-area');
 if(deck){
   const timer=document.createElement('div');timer.className='nabla-clock';timer.id='nablaClock';deck.appendChild(timer);
   let previousTurn=null,localStart=Date.now(),localOffset=0,timeoutPending=false,lastTimeoutCheck=0;
   function tick(){
     if(!gs('game')||gs('game').classList.contains('hidden')||typeof model==='undefined'||!model){timer.textContent='';return;}
     const turn=model.revision+'-'+model.current+'-'+model.turn_number+'-'+model.ready;
     if(previousTurn!==turn){previousTurn=turn;localStart=Date.now();localOffset=Date.now()/1000-(model.server_now||Date.now()/1000);}
     if(model.finished){timer.textContent='対戦終了';return;}
     const name=model.players?.[model.current]?.name||`プレイヤー${model.current+1}`;
     if(typeof busy!=='undefined'&&busy){timer.textContent='計算中（タイマー停止）';return;}
     if(typeof isCpu==='function'&&isCpu()&&model.current===1){timer.textContent='CPUの手番';return;}
     let remaining=120;
     if(typeof isOnline==='function'&&isOnline()){
       if(model.paused){timer.textContent='同期中／接続待ち';return;}
       if(model.deadline!=null){
         const offset=typeof online!=='undefined'?online.offset:0;
         remaining=Math.max(0,Math.ceil(model.deadline-(Date.now()/1000-offset)));
       }else{timer.textContent='同期中';return;}
     }else {
       if(!model.ready||model.deadline==null){timer.textContent='手番待ち';return;}
       remaining=Math.max(0,Math.ceil(model.deadline-(Date.now()/1000-localOffset)));
       if(remaining===0&&!timeoutPending&&Date.now()-lastTimeoutCheck>800){
         timeoutPending=true;lastTimeoutCheck=Date.now();
         api('timeout',{}).then(data=>{
           if(!activePractice&&data.ok&&data.status==='timeout'){
             model=data.state;
             if(typeof render==='function')render();
             if(model.finished&&typeof renderFinished==='function'){
               renderFinished();showResult();
             }else if(typeof isCpu==='function'&&isCpu()&&model.current===1){runCpuTurn();}
             else if(model.mode==='local'&&typeof showHandoff==='function')showHandoff();
           }
         }).catch(()=>{}).finally(()=>{timeoutPending=false;});
       }
     }
     timer.textContent=`${name}　残り ${String(Math.floor(remaining/60)).padStart(2,'0')}:${String(remaining%60).padStart(2,'0')}`;
   }
   setInterval(tick,250);
 }

 // Free practice screen in an isolated local session, not a normal match.
 const root=document.createElement('section');root.id='nablaPractice';root.className='nabla-practice hidden';
 document.body.appendChild(root);
 const start=document.createElement('button');start.type='button';start.id='startPractice';
 start.textContent='練習モード（自由演算）';
 const anchor=gs('startOnline')||gs('startLocal');
 if(anchor&&anchor.parentElement)anchor.parentElement.appendChild(start);

 async function practiceAPI(operation,data={}){
   const response=await api('practice/'+operation,data);
   if(!response.ok)throw Object.assign(new Error(response.message||'操作できません。'),{data:response});
   return response;
 }
 async function practiceStart(left,right){
   try{
     const response=await practiceAPI('start',{left,right});
     pstate=response.state;activePractice=true;chosen=[];renderPractice();
   }catch(e){alert('練習モードを開始できません：'+e.message);}
 }
 async function practiceClose(){
   try{await practiceAPI('close',{});}catch(e){}
   activePractice=false;pstate=null;chosen=[];root.classList.add('hidden');
 }
 start.addEventListener('click',()=>{
   const groups=[0,1].map(seat=>`<fieldset><legend>盤面${seat===0?'A':'B'} の初期基底</legend>${FUNC.filter(([code])=>code!=='zero').map(([code,label])=>`<label style="display:inline-flex;gap:5px;margin:5px"><input type="checkbox" data-start-seat="${seat}" value="${code}" ${['one','x','x2'].includes(code)?'checked':''}>${esc(label)}</label>`).join('')}</fieldset>`).join('');
   openModal('練習モード：初期基底の選択',`<p>一覧から初期基底を選択してください。練習中にも変更できます。</p>${groups}<button id="nablaPracticeConfirm">練習開始</button>`);
 });
 document.addEventListener('click',async ev=>{
   if(ev.target.id!=='nablaPracticeConfirm')return;
   const choices=[0,1].map(seat=>[...document.querySelectorAll(`#modalText input[data-start-seat="${seat}"]:checked`)].map(input=>input.value));
   closeModal();await practiceStart(choices[0],choices[1]);
 });
 async function handlePracticeOperation(fn){
   try{const r=await fn();if(r.state)pstate=r.state;renderPractice();}
   catch(e){
     if(e.data?.status==='foul'){
       const reason=e.message;
       if(confirm('反則：'+reason+'\n\nOK：再挑戦／キャンセル：練習を終了'))return;
       await practiceClose();
     }else if(e.data?.branch_options?.length){
       const branch=prompt('逆関数の枝を選択：'+e.data.branch_options.join(', '));
       if(branch){await handlePracticeOperation(()=>practiceAPI('operate',{...currentAction(),branch}));}
     }else alert(e.message);
   }
 }
 function currentAction(){return {actor:actorSeat,target_player:targetSeat,cards:chosen.slice(),
                                      ...(targetBasis?{basis_id:Number(targetBasis)}:{})};}
 function options(p){return p.bases.map(b=>`<option value="${b.id}">No.${b.id}：${esc(b.expression)}</option>`).join('')}
 // Keep the visible selection in sync without recreating the whole page.
 function refreshPracticeSelection(){
    const display = root.querySelector('#practiceSelection');
    if(display) display.textContent = chosen.length ? chosen.map(c=>DICT[c]||c).join(' → ') : '未選択';
    root.querySelectorAll('[data-pcard]').forEach(b=>b.classList.toggle('chosen',chosen.includes(b.dataset.pcard)));
 }
 function refreshPracticeTargetBasis(){
    const input = root.querySelector('#practiceBasis');
    if(!input || !pstate) return;
    input.innerHTML = '<option value="">場全体／追加</option>'+
      (pstate.players[targetSeat]?.bases||[]).map(b=>`<option value="${b.id}">No.${b.id}：${esc(practicePretty(b.expression))}</option>`).join('');
    input.value='';
 }
 // NABLA-MATH-PRESENTATION-2026-11
 // Only a fallback for native <option> and rare MathML failures. Never use
 // text formatting to decide mathematical equality or to alter card inputs.
 function practicePretty(text){
   let value=String(text??'');
   const superscript=n=>String(n).replace(/[0-9+-]/g,c=>({'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹','+':'⁺','-':'⁻'}[c]||c));
   value=value.replace(/\b(sin|cos|tan)\(x\)\*\*([0-9]+)/g,(_,fn,n)=>fn+superscript(n)+'(x)');
   value=value.replace(/\bx\*\*([0-9]+)/g,(_,n)=>'x'+superscript(n));
   value=value.replace(/\bexp\(x\)/g,'eˣ');
   value=value.replace(/\bsqrt\(/g,'√(');
   value=value.replace(/\bAbs\(([^()]*)\)/g,'|$1|');
   value=value.replace(/\*\*/g,'^');
   value=value.replace(/\*/g,' × ');
   value=value.replace(/\\mathbb\{R\}/g,'ℝ').replace(/\\infty/g,'∞').replace(/\\left|\\right/g,'');
   return value;
 }
 function practiceMath(code,mathml){
   // MathML is generated by the server's allowlisted SymPy parser.
   return mathml ? `<span class="practice-formula">${mathml}</span>` :
      `<span class="practice-formula">${esc(practicePretty(code))}</span>`;
 }
 function practiceLogEvent(ev,i){
   const who = ev.actor===0?'盤面A':ev.actor===1?'盤面B':'練習';
   const where = ev.target_player===0?'盤面A':ev.target_player===1?'盤面B':'盤面';
   const cards=(ev.used_cards||[]).map(c=>DICT[c]||c).join(' → ');
   const edit = ev.kind==='edit' ? '手動編集' : (ev.kind==='add'?'関数追加':(ev.kind==='pass'?'パス':'演算'));
   const numbers = Number.isInteger(ev.basis_id)?`／No.${ev.basis_id}`:'';
   let content=`<article class="practice-event"><div class="practice-event-heading">第${esc(ev.turn??i+1)}手｜${esc(edit)}：${esc(cards||ev.edit_operation||'')}</div>
     <div class="practice-event-target">操作側：${who} ／ 対象：${where}${numbers}</div>`;
   const calcs=ev.calculations||[];
   if(calcs.length){
     calcs.forEach((calc,j)=>{
       content+=`<section class="practice-calculation"><div class="practice-calc-title">${calc.id?'No.'+esc(calc.id)+'／':''}計算${j+1}</div>`;
       if(calc.answer_mathml)content+=`<div class="practice-math-line nabla-answer-line">${calc.answer_mathml}</div>`;
       else if(calc.after!=null)content+=`<div class="practice-math-line">${practiceMath(calc.after,calc.after_mathml)}</div>`;
       else if(calc.before!=null)content+=`<div class="practice-math-line">${practiceMath(calc.before,calc.before_mathml)}</div>`;
       if(calc.reason)content+=`<div class="practice-note">判定：${esc(calc.reason)}</div>`;
       if(calc.domain_changed_note)content+=`<div class="practice-note">${esc(practicePretty(calc.domain_changed_note))}</div>`;
       content+='</section>';
     });
   }else{
     if(typeof ev.before==='string')content+=`<div class="practice-math-label">演算前</div><div class="practice-math-line">${practiceMath(ev.before,ev.before_mathml)}</div>`;
     if(typeof ev.after==='string')content+=`<div class="practice-math-label">追加・演算後</div><div class="practice-math-line">${practiceMath(ev.after,ev.after_mathml)}</div>`;
   }
   if(ev.removed?.length)content+=`<div class="practice-removed">${ev.removed.map(r=>`<div><strong>No.${esc(r.id)} 消滅</strong>：${esc(r.reason||'線形従属')}</div>`).join('')}</div>`;
   if(ev.reason)content+=`<div class="practice-note">${esc(ev.reason)}</div>`;
   if(calcs.length)content+=`<button type="button" class="practice-explain-button" data-practice-explain="${i}">詳しい途中計算を表示</button><div class="practice-explanation" hidden></div>`;
   return content+'</article>';
 }
 function renderPractice(){
   if(!activePractice||!pstate)return;
   root.classList.remove('hidden');
   const boards=pstate.players.map((p,i)=>`<div class="practice-board"><h3>${esc(p.name)}　${p.dimension}次元</h3><div class="practice-bases">${p.bases.map(b=>`<span>No.${b.id}：${practiceMath(b.expression,b.mathml)}</span>`).join('')||'<small>基底なし</small>'}</div></div>`).join('');
   const operations=CATS.map(([section,cards])=>`<fieldset><legend>${esc(section)}</legend>${cards.map(([id,label])=>`<button type="button" data-pcard="${id}" class="${chosen.includes(id)?'chosen':''}">${esc(label)}</button>`).join('')}</fieldset>`).join('');
   const basisOptions=(pstate.players[targetSeat]?.bases||[]).map(b=>`<option value="${b.id}" ${Number(targetBasis)===b.id?'selected':''}>No.${b.id}：${esc(practicePretty(b.expression))}</option>`).join('');
   const nodes=pstate.nodes.map(n=>`<option value="${n.id}" ${n.id===pstate.current_node?'selected':''}>#${n.id} ${esc(n.label)}（親 #${n.parent??'—'}）</option>`).join('');
   const history=pstate.history||[];
   const recent=history.slice(-10).map((e,j)=>practiceLogEvent(e,history.length-Math.min(10,history.length)+j)).reverse().join('');
   root.innerHTML=`<header><strong>NABLA ARENA — 練習モード</strong><button id="practiceExit">終了</button></header>
    <div class="practice-inner"><p>全カード無制限・制限時間なし。数学的判定は通常対戦と同一です。</p>
    <div class="practice-boards">${boards}</div>
    ${pstate.finished?`<div class="practice-end">通常対戦なら終了：${esc(pstate.end_reason||'終了')}。履歴を復元するか、基底を再設定してください。</div>`:''}
    <h3>カードを選ぶ（使用順）</h3><div class="practice-categories">${operations}</div>
    <p>選択：<strong id="practiceSelection">${chosen.length?chosen.map(c=>esc(DICT[c]||c)).join(' → '):'未選択'}</strong> <button id="practiceClear">選択解除</button></p>
    <div class="practice-controls"><label>操作する側<select id="practiceActor"><option value="0" ${actorSeat===0?'selected':''}>盤面A</option><option value="1" ${actorSeat===1?'selected':''}>盤面B</option></select></label>
    <label>対象の場<select id="practiceTarget"><option value="0" ${targetSeat===0?'selected':''}>盤面A</option><option value="1" ${targetSeat===1?'selected':''}>盤面B</option></select></label>
    <label>対象の基底<select id="practiceBasis"><option value="">場全体／追加</option>${basisOptions}</select></label>
    <button id="practiceExecute" class="primary">演算する</button></div>
    <h3>基底の手動編集</h3><div class="practice-controls">
    <label>操作<select id="practiceEditAction"><option value="add">追加</option><option value="replace">変更</option><option value="remove">削除</option></select></label>
    <label>関数<select id="practiceEditFunc">${FUNC.filter(([id])=>id!=='zero').map(([id,label])=>`<option value="${id}">${esc(label)}</option>`).join('')}</select></label>
    <button id="practiceEdit">選択中の対象盤面／基底を編集</button></div>
    <h3>履歴の復元・分岐</h3><div class="practice-controls"><label>保存済みの盤面<select id="practiceHistory">${nodes}</select></label><button id="practiceRestore">この状態に戻る</button></div>
    <div class="practice-controls"><button data-preset="initial">最初へ戻す</button><button data-preset="empty">すべて空にする</button><button data-preset="set_initial">現在の盤面を初期盤面に設定</button></div>
    <h3>操作履歴</h3><div class="practice-log">${recent||'まだ履歴はありません。'}</div>
    </div>`;
   root.querySelectorAll('[data-practice-explain]').forEach(button=>button.addEventListener('click',async()=>{
     const box=button.nextElementSibling;
     if(!box)return;
     if(!box.hidden){box.hidden=true;button.textContent='詳しい途中計算を表示';return;}
     box.hidden=false;button.textContent='詳しい途中計算を閉じる';
     if(box.dataset.loaded)return;
     box.textContent='確認済みの計算過程を取得中…';
     button.disabled=true;
     try{
       const response=await practiceAPI('explain',{node:pstate.current_node,history_index:Number(button.dataset.practiceExplain)});
       box.innerHTML=labelExplanation(response.explanation);
       box.dataset.loaded='1';
     }catch(err){box.textContent='途中計算を表示できません：'+err.message;}
     finally{button.disabled=false;}
   }));
   root.querySelector('#practiceExit').addEventListener('click',async()=>{
     if(confirm('練習を終了しますか？\n現在の盤面と分岐履歴は消去されます。'))await practiceClose();
   });
   root.querySelectorAll('[data-pcard]').forEach(b=>b.addEventListener('click',()=>{
     chosen.push(b.dataset.pcard);refreshPracticeSelection();
   }));
   root.querySelector('#practiceClear').addEventListener('click',()=>{chosen=[];refreshPracticeSelection()});
   root.querySelector('#practiceActor').addEventListener('change',e=>{actorSeat=Number(e.target.value)});
   root.querySelector('#practiceTarget').addEventListener('change',e=>{targetSeat=Number(e.target.value);targetBasis=null;refreshPracticeTargetBasis()});
   root.querySelector('#practiceBasis').addEventListener('change',e=>{targetBasis=e.target.value?Number(e.target.value):null});
   root.querySelector('#practiceExecute').addEventListener('click',()=>{
     if(!chosen.length){alert('カードを選んでください。');return;}
     const action=currentAction();
     handlePracticeOperation(()=>practiceAPI('operate',action)).then(()=>{chosen=[];refreshPracticeSelection()});
   });
   root.querySelector('#practiceEdit').addEventListener('click',()=>{
     const operation=root.querySelector('#practiceEditAction').value;
     const code=root.querySelector('#practiceEditFunc').value;
     handlePracticeOperation(()=>practiceAPI('edit',{
       seat:targetSeat,operation,code,...(targetBasis?{basis_id:targetBasis}:{})}));
   });
   root.querySelector('#practiceRestore').addEventListener('click',()=>handlePracticeOperation(()=>practiceAPI('restore',{node:root.querySelector('#practiceHistory').value})));
   root.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>{
     if((b.dataset.preset==='empty'||b.dataset.preset==='set_initial')&&!confirm('この初期盤面に変更しますか？'))return;
     handlePracticeOperation(()=>practiceAPI('reset',{mode:b.dataset.preset}));
   }));
 }
 // Leaving the practice screen discards state. This is best-effort for tab close;
 // server memory is not a permanent database and has bounded session lifetime.
 window.addEventListener('pagehide',()=>{
   if(!activePractice)return;
   const id=localStorage.getItem('nabla_local_session_id');
   if(!id)return;
   fetch('/api/practice/close',{method:'POST',headers:{'Content-Type':'application/json','X-NABLA-Local':id},body:'{}',keepalive:true}).catch(()=>{});
 });
})();

// NABLA-ANSWER-LOG-V2-2026-11-23
