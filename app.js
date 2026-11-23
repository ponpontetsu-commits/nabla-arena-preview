'use strict';
const $=id=>document.getElementById(id);
const enc=t=>String(t??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const symbols={
 zero:'0',one:'1',x:'x',x2:'x<sup>2</sup>',exp:'e<sup>x</sup>',sin:'sin x',cos:'cos x',
 all_diff:'<span class="mini-stack">全体 <span>d/dx</span></span>',
 all_diff2:'<span class="mini-stack">全体 <span>d²/dx²</span></span>',
 diff:'d/dx',integrate:'∫',mul:'×',div:'÷',
 limit_plus_inf:'<span class="limit"><span class="op">lim</span><span class="sub">x → +∞</span></span>',
 limit_minus_inf:'<span class="limit"><span class="op">lim</span><span class="sub">x → −∞</span></span>',
 limit_zero:'<span class="limit"><span class="op">lim</span><span class="sub">x → 0</span></span>',
 limsup_plus_inf:'<span class="limit"><span class="op">limsup</span><span class="sub">x → +∞</span></span>',
 liminf_plus_inf:'<span class="limit"><span class="op">liminf</span><span class="sub">x → +∞</span></span>',
 sqrt:'√',inverse:'f⁻¹',log:'log',
};
const names={zero:'0',one:'1',x:'x',x2:'x²',exp:'eˣ',sin:'sin x',cos:'cos x',all_diff:'全体微分',all_diff2:'全体2階微分',diff:'微分',integrate:'積分',mul:'乗算',div:'除算',limit_plus_inf:'＋∞への極限',limit_minus_inf:'−∞への極限',limit_zero:'0への極限',limsup_plus_inf:'上極限',liminf_plus_inf:'下極限',sqrt:'平方根',inverse:'逆関数',log:'自然対数'};
const functions = new Set(['zero','one','x','x2','exp','sin','cos']);
const globalOps = new Set(['all_diff','all_diff2']);
const mixOps = new Set(['mul','div']);
let model=null, selected=[], target=null, order=[], historyMode=false, dragFrom=null, pendingAction=null, busy=false;
let currentMode='local', currentDifficulty='medium';
const isCpu=()=>model?.mode==='cpu';
const viewerSeat=()=>isOnline()?model?.seat:(isCpu()?0:model?.current);
const canAct=()=>model?.ready&&!model.finished&&!busy&&(isOnline()?(!model.paused&&model.current===model.seat):(!isCpu()||model.current===0));
let animations=localStorage.getItem('nabla_anim')!=='off';
const supers='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳';
const math=(code, m)=> m || `<span class="formula-as-text">${enc(code).replaceAll('**','^')}</span>`;
function getCurrent(){return model?.players[viewerSeat()]}
function hand(){return getCurrent()?.hand||[]}
function seatName(seat){return model?.players[seat]?.name||`プレイヤー${seat+1}`}
const localSidKey='nabla_local_session_id';
let localSid=localStorage.getItem(localSidKey);
if(!localSid){
 let b=new Uint8Array(32);
 if(globalThis.crypto&&crypto.getRandomValues)crypto.getRandomValues(b);
 else b=Uint8Array.from({length:32},(_,i)=>((Date.now()+i*73+Math.random()*256)&255));
 localSid=Array.from(b,n=>n.toString(16).padStart(2,'0')).join('');
 localStorage.setItem(localSidKey,localSid);
}
async function api(path,data){
  const headers={'X-NABLA-Local':localSid};
  if(path.startsWith('online/')){
   if(online.token)headers['X-NABLA-Seat']=online.token;
  }
  const init=data===undefined?{cache:'no-store',headers}:{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify(data),cache:'no-store'};
  const response=await fetch('/api/'+path,init);
  const body=await response.json();
  if(!response.ok) throw Error(body.message||'通信に失敗しました。');
  return body;
}
function setMessage(msg,kind='info'){$('msg').textContent=msg;$('msg').dataset.kind=kind}
function openModal(title,html){$('modalTitle').textContent=title;$('modalText').innerHTML=html;$('modalShade').classList.add('open')}
function closeModal(){$('modalShade').classList.remove('open')}
function showHandoff(){
  if(!model||model.finished)return;
  $('handoffTitle').textContent=`${seatName(model.current)} の番です`;
  $('handoffDetail').textContent=`${model.current===0?'先攻・後攻はランダムに決定しています。':'盤面と手札は、準備完了まで非公開です。'}\n周囲の人に画面を見られない状態で「準備完了」を押してください。`;
  $('handoff').classList.remove('hidden');
  $('game').classList.remove('hidden');
}
async function startGame(mode='local', difficulty='medium'){
 try{
  $('startLocal').disabled=true;$('startCPU').disabled=true;
  const names=[$('name1').value.trim(),$('name2').value.trim()];
  localStorage.setItem('nabla_name1',names[0]);localStorage.setItem('nabla_name2',names[1]);
  const data=await api('new',{names,mode,difficulty});
  currentMode=mode;currentDifficulty=difficulty;
  model=data.state;selected=[];target=null;order=[];historyMode=false;
  $('home').classList.add('hidden');$('game').classList.remove('hidden');
  if(isCpu()){
   $('handoff').classList.add('hidden');render();
   if(model.current===1)await runCpuTurn();
   else setMessage('あなたの番です。カードと対象を選んでください。');
  }else{
   showHandoff();setMessage('ゲームを開始しました。','info');
  }
 }catch(e){alert('対戦を開始できません: '+e.message)}
 finally{$('startLocal').disabled=false;$('startCPU').disabled=false}
}
async function runCpuTurn(){
 if(!isCpu()||!model||model.finished||model.current!==1)return;
 busy=true;
 $('cpuThinking').classList.remove('hidden');
 render();setMessage('CPUが合法手を評価しています。');
 try{
  
  const data=await api('cpu',{revision:model.revision,game_id:model.game_id});
  model=data.state;selected=[];target=null;order=[];
  if(model.finished){renderFinished();showResult()}
  else {render();setMessage('CPUの操作を計算ログに表示しました。あなたの番です。')}
 }catch(e){setMessage('CPUの操作に失敗しました：'+e.message,'error')}
 finally{busy=false;$('cpuThinking').classList.add('hidden');if(model&&!model.finished)render()}
}
async function ready(){
 try{
  const data=await api('ready',{});model=data.state;
  selected=[];target=null;order=hand().map((_,i)=>i);historyMode=false;
  $('handoff').classList.add('hidden');render();setMessage('カードを選び、対象の基底または場をクリックしてください。');
 }catch(e){alert(e.message)}
}
function basisRows(arr){
 const first=arr.slice(0,10), second=arr.slice(10,20);
 if(arr.length>20){arr.slice(20).forEach((item,i)=>(i%2?second:first).push(item))}
 return [first,second];
}
function drawField(side, seat){
 const board=model.players[seat], isSelf=side==='self';
 $(side+'Field').classList.toggle('current',seat===model.current);
 $(side+'Name').textContent=board.name;
 $(side+'Count').textContent=`${board.dimension}次元`;
 if(!isSelf)$('oppHandCount').textContent=`手札 ${board.hand_count}枚`;
 const rows=basisRows(board.bases);
 $(side+'Rows').innerHTML=rows.map(row=>`<div class="basis-row">${row.map(b=>`<button type="button" class="basis ${target?.seat===seat&&target?.basisId===b.id?'selected':''}" data-side="${side}" data-basis="${b.id}" title="No.${b.id}: ${enc(b.expression)}"><span class="no">No.${b.id}</span><span class="formula">${math(b.expression,b.mathml)}</span></button>`).join('')}</div>`).join('');
 const area=$(side+'Field').querySelector('.field-main');
 area.classList.toggle('picked',target?.seat===seat&&target?.basisId===undefined);
}
function drawHand(){
 const items=hand();$('handCount').textContent=items.length;
 if(order.length!==items.length || new Set(order).size!==items.length)order=items.map((_,i)=>i);
 $('handList').innerHTML=order.map(i=>{
  const code=items[i],seq=selected.indexOf(i)+1;
  return `<button draggable="true" class="hand-card ${seq?'chosen':''}" data-index="${i}" title="${enc(names[code])}" type="button" aria-label="${enc(names[code])}">${seq?`<span class="num">${seq<=20?supers[seq-1]:seq}</span>`:''}<span class="card-symbol">${symbols[code]||enc(code)}</span></button>`;
 }).join('');
}
function eventView(ev){
 if(!ev)return '<div class="empty">まだ行動履歴がありません。</div>';
 const actor=seatName(ev.actor), title=ev.kind==='pass'?'パス':ev.kind==='add'?'基底の追加':'演算';
 let html=`<div class="event-title">${enc(actor)}：${title}${Number.isInteger(ev.basis_id)?` → No.${ev.basis_id}`:''}</div>`;
 if(ev.kind==='pass')return html+`<p>${ev.reason==='timeout'?'時間切れ':'任意'}パス。カードの補充はありません。</p>`;
 const cards=(ev.used_cards||[]).map(x=>names[x]||x).join(' → ');
 html+=`<div class="log-label">使用カード</div><p>${enc(cards)}</p>`;
 if(ev.target_player===0||ev.target_player===1)html+=`<p>対象：${enc(seatName(ev.target_player))}${ev.basis_id?` の No.${ev.basis_id}`:' の場全体'}</p>`;
 for(const calc of ev.calculations||[]){
  if(calc.id)html+=`<div class="event-text">No.${calc.id} の計算</div>`;
  // The server formats the committed operation as one concise equation.
  // Do not recompute the action or repeat verbose narration in the main log.
  if(calc.answer_mathml)html+=`<div class="math-line nabla-answer-line">${calc.answer_mathml}</div>`;
  else if(calc.after!==undefined&&calc.after!==null)html+=`<div class="math-line">${math(calc.after,calc.after_mathml)}</div>`;
  else if(calc.before!==undefined&&calc.before!==null)html+=`<div class="math-line">${math(calc.before,calc.before_mathml)}</div>`;
  if(calc.reason)html+=`<div class="log-explain">${enc(calc.reason)}</div>`;
  if(calc.domain_changed_note)html+=`<div class="log-explain">${enc(calc.domain_changed_note)}</div>`;
 }
 if(!ev.calculations?.length && ev.after!==undefined&&ev.after!==null)html+=`<div class="log-label">追加・更新する基底</div><div class="math-line">${math(ev.after,ev.after_mathml)}</div>`;
 for(const item of ev.removed||[])html+=`<p><strong>No.${item.id} 消滅</strong>：${enc(item.reason)}</p>`;
 if(ev.status==='foul')html+=`<p>反則：${enc(ev.reason)}</p>`;
 if(ev.draw_count!==undefined)html+=`<div class="log-explain">補充 ${ev.draw_count}枚 ／ 山札残り ${ev.deck_remaining??model?.deck_remaining??'?'}枚</div>`;
 return html;
}
function selectionPreview(){
 const list=selected.map((i,j)=>`${j+1}. ${names[hand()[i]]||hand()[i]}`).join(' → ');
 const where=target?`${seatName(target.seat)} の ${target.basisId?`No.${target.basisId}`:'場全体'}`:'未選択';
 return `<div class="log-label">実行前の選択内容</div><div class="event-title">${enc(list)}</div><p>対象：${enc(where)}</p><div class="log-explain">計算結果は実行後に表示されます。</div>`;
}
function renderLog(){
 $('historyBtn').textContent=historyMode?'直前の操作に戻す':'全履歴を表示';
 const past=model.history||[];
 if(historyMode){
  $('logBody').innerHTML=`<div class="log-label">全計算履歴（最新順）</div>${past.length?[...past].reverse().map((ev,i)=>`<section class="history-entry"><div class="log-label">${past.length-i}手目</div>${eventView(ev)}</section>`).join(''):'まだ履歴がありません。'}`;
 }else $('logBody').innerHTML=selected.length?selectionPreview():`<div class="log-label">直前の操作</div>${eventView(past[past.length-1])}`;
}
function render(){
 if(!model||!model.ready||model.finished && model.players[viewerSeat()].hand===undefined)return;
 $('deckNum').textContent=model.deck_remaining;
 $('turnNo').textContent=`${model.turn_number}手目${isCpu()&&model.current===1?'・CPU思考中':''}`;
 drawField('self',viewerSeat());
 drawField('opp',1-viewerSeat());
 drawHand();renderLog();if(isOnline())updateOnlineClock();
 const enabled=canAct();$('executeBtn').disabled=!enabled;$('passBtn').disabled=!enabled;$('cancelBtn').disabled=!enabled;
}
function getKind(){let first=hand()[selected[0]];return functions.has(first)?'add':'operate'}
function setTarget(seat,id){
 const code=hand()[selected[0]];
 target={seat};
 if(!functions.has(code)&&!globalOps.has(code)&&Number.isInteger(id))target.basisId=id;
 render();
}
function resetSelection(){selected=[];target=null;render()}
function makeAction(){
 if(!selected.length)throw Error('手札からカードを選択してください。');
 if(!target)throw Error('対象となる基底、または場を選択してください。');
 const kind=getKind();
 if(kind==='operate'&&!globalOps.has(hand()[selected[0]])&&!target.basisId)throw Error('この演算は対象となる基底カードをクリックしてください。');
 const act={kind,card_indices:selected.slice(),target_player:target.seat};
 if(target.basisId)act.basis_id=target.basisId;
 return act;
}
async function submit(action){
 if(busy)return;busy=true;$('executeBtn').disabled=true;
 try{
  const data=isOnline()?await api('online/action',{room:online.room,action,revision:model.revision,game_id:model.game_id}):await api('action',{action,revision:model.revision,game_id:model.game_id});
  if(data.branch_options?.length){
   pendingAction=action;
   openModal('逆関数の枝を選択',`<p>使用する枝を選択してください。計算結果は確定後に表示します。</p><div class="branch-buttons">${data.branch_options.map(x=>`<button type="button" class="branch-option" data-branch="${enc(x)}">${enc(x)}</button>`).join('')}</div>`);
   return;
  }
  if(!data.ok){
   if(data.status==='stale'&&data.state){model=data.state;resetSelection()}
   setMessage(data.message||'操作を確定できません。', 'error');return;
  }
  model=data.state;selected=[];target=null;
  if(model.finished){
   $('handoff').classList.add('hidden');
   // The last final board is still public, but hand information stays concealed.
   renderFinished(); showResult();
  }else if(isCpu()){render();await runCpuTurn()}
  else if(isOnline()){render();updateOnlineClock()}
  else{showHandoff()}
 }catch(e){setMessage('通信エラー：'+e.message,'error')}
 finally{busy=false;$('executeBtn').disabled=false}
}
async function execute(){if(!canAct())return;try{await submit(makeAction())}catch(e){setMessage(e.message,'error')}}
async function passTurn(){if(!canAct())return;await submit({kind:'pass'})}
function renderFinished(){
 $('deckNum').textContent=model.deck_remaining; $('turnNo').textContent='対戦終了';
 drawField('self',viewerSeat());drawField('opp',1-viewerSeat());
 $('handList').innerHTML='';$('handCount').textContent='—';$('historyBtn').textContent='全履歴を表示';
 historyMode=false; renderLog();
 $('executeBtn').disabled=true;$('passBtn').disabled=true;
}
function showResult(){
 const winner=model.match_void?'無効試合':model.winner===null?'引き分け':`${seatName(model.winner)} の勝利`;
 openModal('対戦終了',`<p class="result-text"><strong>${enc(winner)}</strong></p><p>理由：${enc(model.end_reason)}</p><p>ウィンドウを閉じると最終盤面と全履歴を確認できます。</p><div class="modal-row"><button id="toHome">ホームに戻る</button><button id="restart">再対戦</button></div>`);
}
function showRules(){openModal('ルール・カード一覧',`<p>各プレイヤーは最初に <strong>1、x、x²</strong> の基底3つと手札7枚を持ちます。カードを使って相手の基底を消し、相手の場を0次元にすると勝利です。</p><p>基底が0、発散、または同じ場の別の基底と比例した場合は消滅します。山札切れでは残る次元数で勝敗を判定します。</p><p>原典に基づく全21種類・78枚。対数は底eで「log」と表記します。</p><h3>カード一覧</h3><div class="card-list">${Object.keys(names).map(c=>`<div class="card-list-item"><span>${symbols[c]}</span><span>${enc(names[c])}</span></div>`).join('')}</div><p>数学エンジンが未対応の場合、カードを消費せず選び直します。現在は検証用のブラウザ対戦版です。</p>`)}
function menu(){openModal('メニュー',`<div class="menu-options"><button id="rules">ルール・カード一覧</button><button id="fullscreen">全画面表示切り替え</button><button id="animation">演出：${animations?'ON':'OFF'}</button><button id="quitGame">対戦を終了</button></div>`)}
$('startLocal').addEventListener('click',()=>startGame('local'));
$('startCPU').addEventListener('click',()=>openModal('CPU対戦：難易度を選択','<p>難易度を選んで開始します。CPUは数学的に不正な演算を意図的には行いません。</p><div class="branch-buttons"><button data-cpu="easy">初級</button><button data-cpu="medium">中級</button><button data-cpu="hard">上級</button></div>'));
$('readyBtn').addEventListener('click',ready);
$('historyBtn').addEventListener('click',()=>{historyMode=!historyMode;renderLog()});
$('cancelBtn').addEventListener('click',resetSelection);
$('executeBtn').addEventListener('click',execute);
$('passBtn').addEventListener('click',passTurn);
$('menuBtn').addEventListener('click',menu);
$('rulesHome').addEventListener('click',showRules);
$('closeModal').addEventListener('click',closeModal);
$('modalShade').addEventListener('click',ev=>{if(ev.target===$('modalShade'))closeModal()});
$('handList').addEventListener('click',ev=>{
 if(!canAct())return;
 const btn=ev.target.closest('[data-index]');if(!btn)return;
 const i=Number(btn.dataset.index),n=selected.indexOf(i);
 if(n<0)selected.push(i);else selected.splice(n,1);
 render();
});
document.querySelector('.arena').addEventListener('click',ev=>{
 if(!canAct()||ev.target.closest('[data-scroll]'))return;
 const area=ev.target.closest('.field-main'),b=ev.target.closest('[data-basis]');
 if(!area)return;
 const seat=area.dataset.field==='self'?viewerSeat():1-viewerSeat();
 setTarget(seat,b?Number(b.dataset.basis):undefined);
});
document.querySelectorAll('[data-scroll]').forEach(btn=>btn.addEventListener('click',ev=>{ev.stopPropagation();$(btn.dataset.scroll+'Scroll').scrollBy({left:Number(btn.dataset.direction)*270,behavior:'smooth'})}));
document.querySelectorAll('[data-hand-move]').forEach(btn=>btn.addEventListener('click',()=>{$('handList').scrollBy({left:Number(btn.dataset.handMove)*360,behavior:'smooth'})}));
$('handList').addEventListener('dragstart',ev=>{const btn=ev.target.closest('[data-index]');if(!btn)return;dragFrom=Number(btn.dataset.index);ev.dataTransfer.effectAllowed='move'});
$('handList').addEventListener('dragover',ev=>{if(ev.target.closest('[data-index]'))ev.preventDefault()});
$('handList').addEventListener('drop',ev=>{
 const btn=ev.target.closest('[data-index]');if(!btn||dragFrom===null)return;ev.preventDefault();
 const from=order.indexOf(dragFrom),to=order.indexOf(Number(btn.dataset.index));
 if(from>=0&&to>=0){order.splice(to,0,order.splice(from,1)[0]);drawHand()}
 dragFrom=null;
});
$('handList').addEventListener('dragend',()=>{dragFrom=null});
$('modalText').addEventListener('click',async ev=>{
 const el=ev.target.closest('button');if(!el)return;
 if(el.dataset.cpu){const difficulty=el.dataset.cpu;closeModal();await startGame('cpu',difficulty)}
 else if(el.classList.contains('branch-option')&&pendingAction){const action={...pendingAction,branch:el.dataset.branch};pendingAction=null;closeModal();await submit(action)}
 else if(el.id==='rules')showRules();
 else if(el.id==='fullscreen'){closeModal();try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen()}catch(e){setMessage('全画面表示に切り替えられませんでした。','error')}}
 else if(el.id==='animation'){animations=!animations;localStorage.setItem('nabla_anim',animations?'on':'off');document.body.classList.toggle('reduce-motion',!animations);menu()}
 else if(el.id==='quitGame'){openModal('対戦終了の確認',isOnline()?'<p>オンライン対戦から退出すると不戦敗になります。</p><div class="modal-row"><button id="confirmQuit">退出する</button></div>':'<p>このローカル対戦を終了してホームへ戻りますか？</p><div class="modal-row"><button id="confirmQuit">終了する</button></div>')}
 else if(el.id==='confirmQuit'||el.id==='toHome'){closeModal();if(isOnline()){if(el.id==='confirmQuit')await leaveOnline();else stopOnline()}else{$('handoff').classList.add('hidden');$('game').classList.add('hidden');$('home').classList.remove('hidden');model=null}}
 else if(el.id==='restart'){if(isOnline())await onlineRematch();else{closeModal();await startGame(currentMode,currentDifficulty)}}
 else if(el.id==='onlineCreate'){await createOnline()}
 else if(el.id==='onlineJoin'){await joinOnline($('joinRoomCode')?.value)}
});
document.addEventListener('keydown',ev=>{
 if(!$('modalShade').classList.contains('open')){
  if(ev.key==='Escape'&&canAct()){resetSelection()}
  if(ev.key==='Enter'&&!['INPUT','TEXTAREA','BUTTON'].includes(document.activeElement?.tagName)&&$('handoff').classList.contains('hidden'))execute();
 }else if(ev.key==='Escape')closeModal();
});
$('name1').value=localStorage.getItem('nabla_name1')||'';
$('name2').value=localStorage.getItem('nabla_name2')||'';
document.body.classList.toggle('reduce-motion',!animations);

// --- 第5段階：オンラインルーム UI ---
const online = {room:null, token:null, poller:null, lastFinished:null, lastMatch:null, offset:0};
const onlineStartBtn = $('startOnline');
function inviteUrl(room){return location.origin + location.pathname + '?room=' + encodeURIComponent(room)}
function saveSeat(info){
 online.room=info.code;online.token=info.token;
 localStorage.setItem('nabla_online_seat_'+info.code,info.token);
 localStorage.setItem('nabla_online_last_room',info.code);
}
function isOnline(){return currentMode==='online' && !!online.room}
async function createOnline(){
 try{
  const data=await api('online/create',{name:$('name1').value.trim()||'プレイヤー'});
  saveSeat(data);currentMode='online';model=data.state;
  closeModal();showOnlineState(data.state);beginOnlinePoll();
 }catch(err){setMessage(err.message,'error');openModal('作成できませんでした',`<p>${enc(err.message)}</p>`)}
}
async function joinOnline(code){
 code=String(code||'').trim();
 if(!/^\d{6}$/.test(code)){setMessage('6桁の数字を入力してください。','error');return}
 try{
  const saved=localStorage.getItem('nabla_online_seat_'+code);
  let data;
  if(saved){
   online.room=code;online.token=saved;
   data=await api('online/state?room='+code);
   data={...data,code,token:saved};
  }else{
   data=await api('online/join',{room:code,name:$('name1').value.trim()||'プレイヤー'});
  }
  saveSeat(data);currentMode='online';model=data.state;
  closeModal();showOnlineState(data.state);beginOnlinePoll();
 }catch(err){openModal('参加できませんでした',`<p>${enc(err.message)}</p><p>参加済みの場合は同じブラウザから再接続してください。</p>`)}
}
function onlineDialog(code=''){
 const value=/^\d{6}$/.test(code)?code:'';
 openModal('オンライン対戦',`<p>2人の端末が同じサーバーにアクセスできる必要があります。</p>
 <div class="menu-options"><button id="onlineCreate">新しいルームを作る</button><button id="onlineJoin">ルームに参加する</button></div>
 <p>招待された場合は6桁の番号を入力してください。</p><input id="joinRoomCode" inputmode="numeric" maxlength="6" value="${value}" placeholder="000000" style="padding:10px;width:100%;letter-spacing:3px;font-size:20px" />`);
}
function showOnlineState(s){
 if(!isOnline())return;
 online.offset=Date.now()/1000-s.server_now;
 $('home').classList.add('hidden');
 $('handoff').classList.add('hidden');
 if(s.phase==='waiting'){
  $('game').classList.add('hidden');$('onlineLobby').classList.remove('hidden');
  $('roomCode').textContent=online.room;
  $('inviteLink').value=inviteUrl(online.room);
  $('lobbyStatus').textContent='相手の参加を待っています。';
  return;
 }
 $('onlineLobby').classList.add('hidden');$('game').classList.remove('hidden');
 if(s.phase==='finished'){
  renderFinished();
  if(online.lastFinished!==`${s.match_number}_${s.revision}`){
   online.lastFinished=`${s.match_number}_${s.revision}`;showResult();
  }
 }else{
  online.lastFinished=null;
  render();
  updateOnlineClock();
  setMessage(s.paused?'接続が途切れたため対戦を一時停止しています。':
   s.current===s.seat?'あなたの番です。':'相手の操作を待っています。');
 }
}
function updateOnlineClock(){
 if(!isOnline()||!model||!['playing','finished'].includes(model.phase))return;
 if(model.phase==='finished'){ $('turnNo').textContent='対戦終了';return }
 if(model.paused){
  const left=Math.max(0,Math.ceil(model.pause_remaining-(Date.now()/1000-online.offset-model.server_now)));
  $('turnNo').textContent=`通信切断・残り ${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}`;
 }else{
  const left=Math.max(0,Math.ceil(model.deadline-(Date.now()/1000-online.offset)));
  $('turnNo').textContent=`${model.turn_number}手目　残り ${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}`;
 }
}
async function pollOnline(){
 if(!isOnline())return;
 try{
  const response=await api('online/state?room='+encodeURIComponent(online.room));
  const s=response.state;
  if(!model||model.revision!==s.revision||model.phase!==s.phase||model.match_number!==s.match_number){
   selected=[];target=null;order=[];historyMode=false;
   model=s;showOnlineState(s);
  }else{
   const pauseChanged=model.paused!==s.paused;
   model=s;online.offset=Date.now()/1000-s.server_now;updateOnlineClock();
   if(s.phase==='waiting')$('lobbyStatus').textContent='相手の参加を待っています。';
   if(s.phase==='playing'){
    if(s.paused)setMessage('通信切断による一時停止中。5分で無効試合になります。','error');
    else if(pauseChanged)setMessage(s.current===s.seat?'あなたの番です。':'相手の操作を待っています。');
    if(pauseChanged&&!busy)render();
   }
  }
 }catch(err){setMessage('再接続中：'+err.message,'error')}
}
function beginOnlinePoll(){if(online.poller)clearInterval(online.poller);online.poller=setInterval(pollOnline,2500)}
function stopOnline(){
 localStorage.setItem('nabla_online_last_room','');
 if(online.poller)clearInterval(online.poller);
 online.poller=null;online.room=null;online.token=null;
 currentMode='local';model=null;selected=[];target=null;
 $('onlineLobby').classList.add('hidden');$('handoff').classList.add('hidden');
 $('game').classList.add('hidden');$('home').classList.remove('hidden');
}
async function leaveOnline(){
 if(!isOnline())return;
 try{await api('online/leave',{room:online.room})}catch(err){setMessage(err.message,'error')}
 stopOnline();
}
async function onlineRematch(){
 try{
  const r=await api('online/rematch',{room:online.room});
  model=r.state;
  if(model.phase==='playing'){closeModal();showOnlineState(model)}
  else openModal('再戦申請済み','<p>相手が「再戦」を選ぶと、同じルームで新しい対戦が始まります。</p>');
 }catch(err){setMessage(err.message,'error')}
}
onlineStartBtn.addEventListener('click',()=>onlineDialog());
$('copyInvite').addEventListener('click',async()=>{
 try{await navigator.clipboard.writeText($('inviteLink').value);$('lobbyStatus').textContent='招待URLをコピーしました。'}
 catch{ $('inviteLink').select();$('lobbyStatus').textContent='選択されたURLをコピーしてください。'}
});
$('leaveLobby').addEventListener('click',leaveOnline);
setInterval(updateOnlineClock,250);
const invitedRoom=new URLSearchParams(location.search).get('room');
const recoverRoom=/^\d{6}$/.test(invitedRoom||'')?invitedRoom:localStorage.getItem('nabla_online_last_room');
if(/^\d{6}$/.test(recoverRoom||'')){
 const existing=localStorage.getItem('nabla_online_seat_'+recoverRoom);
 if(existing){
  online.room=recoverRoom;online.token=existing;currentMode='online';
  pollOnline().then(beginOnlinePoll);
 }else if(invitedRoom){
  onlineDialog(invitedRoom);
 }
}

// NABLA-ANSWER-LOG-V2-2026-11-23
