"""Isolate untrusted symbolic work in one short-lived, killable process.

This is a bounded preview-level safeguard, not a complete hardened sandbox.
Individual processes are spawned so that parent server/room storage stay intact.
"""
from __future__ import annotations
import multiprocessing as mp
import os
from nabla_game import play
from cpu import take_cpu_turn


def _worker(send, name, args):
    try:
        result = play(*args) if name == 'play' else take_cpu_turn(*args)
        send.send(('ok', result))
    except BaseException as exc:
        try:
            send.send(('error', type(exc).__name__))
        except Exception:
            pass
    finally:
        send.close()


def _invoke(name, args):
    seconds = max(1, min(60, int(os.environ.get('NABLA_MAX_CALC_SECONDS', '12'))))
    ctx = mp.get_context('spawn')
    receive, send = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_worker, args=(send, name, args), daemon=True)
    try:
        process.start()
        send.close()
        if receive.poll(seconds):
            try:
                result_type, result = receive.recv()
            except (EOFError, OSError):
                result_type, result = 'error', '計算プロセスが終了しました。'
            if result_type == 'ok':
                return result
            raise RuntimeError('計算プロセスの実行に失敗しました: ' + str(result))
        raise TimeoutError('数学演算が制限時間を超えました。カードは消費されません。')
    finally:
        receive.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        if process.is_alive():
            process.kill()
        process.join(timeout=1)


def safe_play(state, actor, action, revision):
    if os.environ.get('NABLA_ISOLATE_MATH') != '1':
        return play(state, actor, action, expected_revision=revision)
    try:
        # expected_revision is the 4th positional argument in play().
        return _invoke('play', (state, actor, action, revision))
    except (TimeoutError, RuntimeError) as exc:
        return {'status':'unsupported', 'reason':str(exc), 'state':state}


def safe_cpu_turn(state, difficulty):
    if os.environ.get('NABLA_ISOLATE_MATH') != '1':
        return take_cpu_turn(state, difficulty)
    try:
        return _invoke('cpu', (state, difficulty))
    except (TimeoutError, RuntimeError):
        # CPU has a mathematically legal fallback if search times out.
        result = play(state, 1, {'kind':'pass'}, expected_revision=state['revision'])
        return {'kind':'pass'}, result
