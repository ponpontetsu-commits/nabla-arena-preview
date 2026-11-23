#!/usr/bin/env python3
"""NABLA ARENA CPU/full-board UI stabilization.

Targets exact published main (f2df273, 2026-11-23). Refuses unexpected
source or partial application. Does not touch deck, math adjudication,
CPU candidate scoring, persistent database, online-room state, or rules.
"""
from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
MARK = 'NABLA-CPU-WHOLEBOARD-STABILITY-V1'

SERVER_OLD = '''@lru_cache(maxsize=1024)
def _mathml(expression):
    if not isinstance(expression, str) or not expression:
        return None
    try:
'''
SERVER_NEW = '''def _mathml(expression):
    # NABLA-CPU-WHOLEBOARD-STABILITY-V1
    # A whole-board event's before/after are lists, not formula strings.
    # Check the type before the cached function sees an unhashable value.
    if not isinstance(expression, str) or not expression:
        return None
    return _mathml_cached(expression)


@lru_cache(maxsize=1024)
def _mathml_cached(expression):
    try:
'''

APP_OLD = ''' }catch(e){setMessage('CPUの操作に失敗しました：'+e.message,'error')}
 finally{busy=false;$('cpuThinking').classList.add('hidden');if(model&&!model.finished)render()}
}
async function ready(){'''
APP_NEW = ''' }catch(e){await recoverCpuAfterError(e)}
 finally{busy=false;$('cpuThinking').classList.add('hidden');if(model&&!model.finished)render()}
}
async function ready(){'''

APP_HELPER = '''// NABLA-CPU-WHOLEBOARD-STABILITY-V1
// A 500 response may arrive AFTER the server commits a CPU turn. Always sync
// authoritative state before offering another turn; never mutate game rules.
async function recoverCpuAfterError(error){
 const message='CPUの操作に失敗しました：'+String(error?.message||'通信または計算エラー');
 let latest;
 try{
  const response=await api('state');
  if(!response.ok||!response.state||!model||response.state.game_id!==model.game_id){
   throw new Error('対戦状態を確認できません。');
  }
  latest=response.state;
 }catch(syncError){
  setMessage(message+'／サーバーの状態を取得できません。','error');
  openModal('CPU対戦：状態の再取得',
   '<p>サーバーから現在の盤面を取得できませんでした。もう一度状態を取得できます。</p>'+
   '<button type="button" id="nablaCpuRecoveryAction">状態を再取得</button>');
  const retry=$('nablaCpuRecoveryAction');
  if(retry)retry.addEventListener('click',()=>{closeModal();recoverCpuAfterError(error)});
  return;
 }
 model=latest;selected=[];target=null;order=[];
 if(model.finished){
  renderFinished();showResult();
  setMessage('サーバーの対戦終了状態を同期しました。');
  return;
 }
 render();
 if(model.current===0){
  setMessage('CPUの操作結果をサーバーから再取得して同期しました。');
  return;
 }
 setMessage(message+'／盤面は同期済みです。再試行できます。','error');
 openModal('CPU対戦：操作を再試行',
  '<p>CPUの手番はまだ終了していません。盤面はサーバーと同期済みです。再試行する場合だけボタンを押してください。</p>'+
  '<button type="button" id="nablaCpuRecoveryAction">CPUの手番を再試行</button>');
 const retry=$('nablaCpuRecoveryAction');
 if(retry)retry.addEventListener('click',()=>{closeModal();runCpuTurn()});
}
'''


def _once(source: str, original: str, replacement: str, description: str) -> str:
    count = source.count(original)
    if count != 1:
        raise RuntimeError(f'{description}: expected one exact anchor, found {count}; no files changed')
    return source.replace(original, replacement, 1)


def transform(server: str, app: str) -> tuple[str, str, bool]:
    # Idempotent only if the complete upgrade is already present.
    done_server = MARK in server
    done_app = MARK in app
    if done_server or done_app:
        if done_server and done_app and 'def _mathml_cached(' in server and 'recoverCpuAfterError(e)' in app:
            return server, app, False
        raise RuntimeError('Partial/unknown CPU-stability patch detected; no files changed')
    fixed_server = _once(server, SERVER_OLD, SERVER_NEW, 'server.py MathML cache guard')
    fixed_app = _once(app, APP_OLD, APP_NEW, 'app.js CPU error handling')
    fixed_app = _once(fixed_app, 'async function runCpuTurn(){', APP_HELPER + '\nasync function runCpuTurn(){', 'app.js CPU helper')
    return fixed_server, fixed_app, True


def main():
    server_path, app_path = ROOT / 'server.py', ROOT / 'app.js'
    if not server_path.is_file() or not app_path.is_file():
        raise RuntimeError('Must run at repository root with server.py and app.js present')
    server, app = server_path.read_text(encoding='utf-8'), app_path.read_text(encoding='utf-8')
    new_server, new_app, changed = transform(server, app)
    if not changed:
        print('Both stability fixes already present; no changes necessary.')
        return
    ast.parse(new_server, filename='server.py')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required for JS syntax check; no files changed')
    with tempfile.TemporaryDirectory() as tempdir:
        temp_app = Path(tempdir) / 'app.js'
        temp_app.write_text(new_app, encoding='utf-8')
        result = subprocess.run([node, '--check', str(temp_app)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('JavaScript syntax invalid; no files changed: ' + result.stderr)
    # Both files and syntaxes verified BEFORE committing to disk.
    server_path.write_text(new_server, encoding='utf-8')
    app_path.write_text(new_app, encoding='utf-8')
    print('Patched server.py and app.js; CI will run the full repository regression suite.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('CPU stability patch refused: ' + str(exc), file=sys.stderr)
        sys.exit(1)
