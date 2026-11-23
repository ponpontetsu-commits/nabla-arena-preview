"""NABLA ARENA stage-5 multiplayer prototype.

Two-seat authenticated online rooms, server-authoritative game logic,
server-side clock and persistent room records. See README before publishing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import time
import threading
from functools import lru_cache
# NABLA-PRECISION-PERFORMANCE-2026-11
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from nabla_game import new_game, play, public_view
from cpu import take_cpu_turn, DIFFICULTIES
from nabla_math import parse_formula
from online_rooms import OnlineRooms, Storage
from sandbox_math import safe_play, safe_cpu_turn
from nabla_practice import dispatch as dispatch_practice
from nabla_steps import explain_event, answer_mathml
# NABLA-REVISION-2026-11

try:
    from sympy.printing.mathml import mathml
except ImportError:
    from sympy import printing
    mathml = printing.mathml

ROOT = Path(__file__).resolve().parent
_LOCK = threading.RLock()
_STATE = {'game': None, 'ready': False, 'mode': 'local', 'difficulty': None}
_SESSIONS = {} # separate local/CPU games per browser, with high-entropy session ids
_ONLINE = None
_SESSION_RE = re.compile(r'^[A-Za-z0-9_-]{32,128}$')
_RATE_EVENTS = {}  # create/join rate limiting; single-worker prototype


@lru_cache(maxsize=1024)
def _mathml(expression):
    if not isinstance(expression, str) or not expression:
        return None
    try:
        # Only engine-produced, whitelisted symbolic expression strings are parsed.
        value = parse_formula(expression)
        return '<math xmlns="http://www.w3.org/1998/Math/MathML">' + mathml(value, printer='presentation') + '</math>'
    except Exception:
        return None


def _view(reveal_hand=True):
    state = _STATE['game']
    if state is None:
        return None
    mode = _STATE['mode']
    seat = 0 if mode == 'cpu' else state['current']
    v = public_view(state, seat)
    if not reveal_hand or (mode == 'local' and not _STATE['ready']) or state['finished']:
        v['players'][seat].pop('hand', None)
    v['ready'] = _STATE['ready']
    v['mode'] = mode
    v['difficulty'] = _STATE['difficulty']
    v['human_seat'] = 0 if mode == 'cpu' else seat
    v['deadline'] = _STATE.get('deadline')
    v['server_now'] = time.time()
    v['timer_seconds'] = 120
    for item in v['history']:
        for field in ('before','after'):
            item[field+'_mathml'] = _mathml(item.get(field))
        for calc in item.get('calculations',[]):
            calc['answer_mathml'] = answer_mathml(calc.get('before'), calc.get('after'), item.get('used_cards'))
            for field in ('before','after'):
                calc[field+'_mathml'] = _mathml(calc.get(field))
    for player in v['players']:
        for base in player['bases']:
            base['mathml'] = _mathml(base['expression'])
    return v


def _decorate_online_view(v):
    if not v:
        return v
    for item in v.get('history', []):
        for field in ('before', 'after'):
            item[field+'_mathml'] = _mathml(item.get(field))
        for calc in item.get('calculations', []):
            calc['answer_mathml'] = answer_mathml(calc.get('before'), calc.get('after'), item.get('used_cards'))
            for field in ('before', 'after'):
                calc[field+'_mathml'] = _mathml(calc.get(field))
    for player in v.get('players', []):
        for base in player.get('bases', []):
            base['mathml'] = _mathml(base.get('expression'))
    return v


def _http_result(data, status=200):
    return status, json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def route_get(path):
    if path == '/':
        return 200, (ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8'
    if path == '/app.js':
        return 200, (ROOT/'app.js').read_bytes(), 'application/javascript; charset=utf-8'
    if path == '/nabla_upgrade_ui.js':
        return 200, (ROOT/'nabla_upgrade_ui.js').read_bytes(), 'application/javascript; charset=utf-8'
    if path == '/nabla_upgrade.css':
        return 200, (ROOT/'nabla_upgrade.css').read_bytes(), 'text/css; charset=utf-8'
    if path == '/api/state':
        with _LOCK:
            return (*_http_result({'ok': True, 'state': _view()}), 'application/json; charset=utf-8')
    if path == '/api/health':
        return (*_http_result({'ok': True, 'app': 'NABLA ARENA Stage 6 preview', 'scope': 'local and online'}), 'application/json; charset=utf-8')
    return (*_http_result({'ok': False, 'message':'ページが見つかりません。'},404), 'application/json; charset=utf-8')


# NABLA-MATH-PRESENTATION-2026-11

def _decorate_practice_response(payload):
    """Only enrich returned copies: never change the authoritative game state."""
    state = payload.get('state') if isinstance(payload, dict) else None
    if not isinstance(state, dict):
        return payload
    for player in state.get('players', []):
        for basis in player.get('bases', []):
            basis['mathml'] = _mathml(basis.get('expression'))
    # The practice screen renders only the last ten events. Do not render
    # hundreds of old event formulas on every card operation.
    for event in state.get('history', [])[-10:]:
        for field in ('before', 'after'):
            if isinstance(event.get(field), str):
                event[field + '_mathml'] = _mathml(event[field])
        for calc in event.get('calculations', []):
            calc['answer_mathml'] = answer_mathml(calc.get('before'), calc.get('after'), event.get('used_cards'))
            for field in ('before', 'after'):
                if isinstance(calc.get(field), str):
                    calc[field + '_mathml'] = _mathml(calc[field])
    return payload


def _explain_practice(data):
    """Compute verified educational detail only after the player requests it."""
    room = _STATE.get('practice')
    if room is None:
        return {'ok': False, 'message': '練習モードが開始されていません。'}
    node = data.get('node')
    index = data.get('history_index')
    if str(node) != room.current:
        return {'ok': False, 'message': '盤面が変更されました。履歴を選び直してください。'}
    history = room.nodes[room.current]['game'].get('history', [])
    if type(index) is not int or not 0 <= index < len(history):
        return {'ok': False, 'message': '計算履歴が見つかりません。'}
    return {'ok': True, 'explanation': explain_event(history[index])}

def route_post(path, data):
    global _STATE
    with _LOCK:
        if path == '/api/new':
            names = data.get('names', [])
            if not isinstance(names, list) or len(names)!=2 or any(not isinstance(n,str) for n in names):
                names = ['プレイヤー1','プレイヤー2']
            names = [(n.strip()[:24] or f'プレイヤー{i+1}') for i,n in enumerate(names)]
            mode = data.get('mode', 'local')
            difficulty = data.get('difficulty', 'medium') if mode == 'cpu' else None
            if mode not in ('local', 'cpu') or (mode == 'cpu' and difficulty not in DIFFICULTIES):
                return _http_result({'ok':False,'message':'対戦モードまたはCPU難易度が不正です。'},400)
            state = new_game()
            if mode == 'cpu':
                names[1] = f'CPU（{DIFFICULTIES[difficulty]}）'
            for i,p in enumerate(state['players']): p['name'] = names[i]
            _STATE = {'game':state,'ready':mode == 'cpu',
                      'mode':mode,'difficulty':difficulty,
                      'deadline':time.time()+120 if mode=='cpu' and state['current']==0 else None}
            return _http_result({'ok':True,'state':_view()})
        if path == '/api/practice/explain':
            return _http_result(_explain_practice(data))
        if path.startswith('/api/practice/'):
            return _http_result(_decorate_practice_response(dispatch_practice(_STATE,path,data)))
        if path == '/api/explain':
            game=_STATE.get('game') or {}
            ev=next((e for e in game.get('history',[]) if e.get('id')==data.get('event_id')),None)
            if ev is None:
                return _http_result({'ok':False,'message':'計算履歴が見つかりません。'})
            if '_explanation' not in ev:
                ev['_explanation']=explain_event(ev)
            return _http_result({'ok':True,'explanation':ev['_explanation']})
        if _STATE['game'] is None:
            return _http_result({'ok':False,'message':'対戦が開始されていません。'},409)
        if path == '/api/ready':
            if _STATE['mode'] != 'local':
                return _http_result({'ok':False,'message':'CPU対戦には手番交代画面がありません。'},409)
            _STATE['ready'] = True
            _STATE['deadline']=time.time()+120
            return _http_result({'ok':True,'state':_view()})
        if path == '/api/timeout':
            state=_STATE.get('game')
            if not state:
                return _http_result({'ok':False,'message':'対戦がありません。'})
            deadline=_STATE.get('deadline')
            if deadline is None or time.time()<deadline or state['finished']:
                return _http_result({'ok':True,'status':'unchanged','state':_view()})
            result=play(state,state['current'],{'kind':'pass','reason':'timeout'},state['revision'])
            if result['status']!='ok':
                return _http_result({'ok':False,'message':'時間切れの処理に失敗しました。'})
            _STATE['game']=result['state'];_STATE['deadline']=None
            if _STATE['mode']=='local':_STATE['ready']=False
            return _http_result({'ok':True,'status':'timeout','state':_view(),'event':result.get('event')})
        if path == '/api/cpu':
            if _STATE['mode'] != 'cpu':
                return _http_result({'ok':False,'message':'CPU対戦ではありません。'},409)
            state = _STATE['game']
            if state['finished'] or state['current'] != 1:
                return _http_result({'ok':False,'message':'CPUの手番ではありません。'},409)
            revision = data.get('revision')
            if data.get('game_id')!=state.get('game_id') or type(revision) is not int or revision != state['revision']:
                return _http_result({'ok':False,'message':'盤面が更新されています。'},409)
            action, result = safe_cpu_turn(state, _STATE['difficulty'])
            if result['status'] != 'ok':
                return _http_result({'ok':False,'message':'CPUの行動を確定できません。'},500)
            _STATE['game'] = result['state']
            _STATE['deadline']=time.time()+120 if not _STATE['game']['finished'] and _STATE['game']['current']==0 else None
            return _http_result({'ok':True,'status':'ok','state':_view(),
                                 'event':result.get('event')})
        if path == '/api/action':
            if not _STATE['ready']:
                return _http_result({'ok':False,'message':'次のプレイヤーの準備が完了していません。'},409)
            state = _STATE['game']
            if _STATE['mode'] == 'cpu' and state['current'] != 0:
                return _http_result({'ok':False,'message':'CPUの手番では操作できません。'},409)
            action = data.get('action')
            revision = data.get('revision')
            if data.get('game_id')!=state.get('game_id') or not isinstance(action,dict) or type(revision) is not int:
                return _http_result({'ok':False,'message':'操作データが不正です。'},400)
            if _STATE.get('deadline') and time.time() >= _STATE['deadline']:
                expired=play(state,state['current'],{'kind':'pass','reason':'timeout'},state['revision'])
                _STATE['game']=expired['state']
                _STATE['deadline']=None
                if _STATE['mode']=='local':
                    _STATE['ready']=False
                return _http_result({'ok':True,'status':'ok','message':'時間切れによりパスしました。',
                                     'state':_view(),'event':expired.get('event')})
            result = safe_play(state,state['current'],action,revision)
            if result['status'] in ('ok','foul'):
                _STATE['game'] = result['state']
                _STATE['deadline']=None
                if _STATE['mode'] == 'local':
                    _STATE['ready'] = False if not _STATE['game']['finished'] else True
            return _http_result({
                'ok':result['status'] in ('ok','foul'), 'status':result['status'],
                'message':result['reason'], 'state':_view(),
                'branch_options':result.get('branch_options',[]),
                'event':result.get('event'),
            })
        return _http_result({'ok':False,'message':'不明なAPIです。'},404)


class Handler(BaseHTTPRequestHandler):
    server_version = 'NABLA-Online/0.5'
    def _reply(self,status,payload,mime):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)
    def _online_response(self, data):
        if 'state' in data and isinstance(data['state'], dict):
            _decorate_online_view(data['state'])
        return (*_http_result(data, 200 if data.get('ok') else (401 if data.get('status')=='unauthorized' else 409)),
                'application/json; charset=utf-8')
    def _local_session(self):
        token = self.headers.get('X-NABLA-Local','')
        return token if _SESSION_RE.fullmatch(token) else None
    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/api/online/state':
            args = parse_qs(parsed.query)
            code = args.get('room', [''])[0]
            token = self.headers.get('X-NABLA-Seat','')
            with _LOCK:
                status,payload,mime = self._online_response(_ONLINE.state(code, token))
        elif parsed.path == '/api/state':
            sid = self._local_session()
            if not sid:
                status,payload,mime=(*_http_result({'ok':False,'message':'セッションIDが必要です。'},401),'application/json; charset=utf-8')
            else:
                global _STATE
                with _LOCK:
                    _STATE = _SESSIONS.get(sid, {'game':None,'ready':False,'mode':'local','difficulty':None})
                    status,payload,mime = route_get(parsed.path)
                    _SESSIONS[sid] = _STATE
        else:
            status,payload,mime = route_get(parsed.path)
        self._reply(status,payload,mime)
    def do_POST(self):
        global _STATE
        path=urlsplit(self.path).path
        if path in ('/api/online/create','/api/online/join'):
            ip = self.client_address[0]
            with _LOCK:
                now=time.monotonic()
                hits=[t for t in _RATE_EVENTS.get(ip,[]) if now-t < 60]
                if len(hits)>=12:
                    status,payload=_http_result({'ok':False,'message':'作成・参加の試行回数が多すぎます。少し時間をおいてください。'},429)
                    self._reply(status,payload,'application/json; charset=utf-8')
                    return
                hits.append(now);_RATE_EVENTS[ip]=hits
        
        size = self.headers.get('Content-Length','')
        try:
            n=int(size)
            if not 0<=n<=16_384:raise ValueError
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict):raise ValueError
        except (ValueError,TypeError,OverflowError,json.JSONDecodeError):
            status,payload=_http_result({'ok':False,'message':'リクエスト形式が不正です。'},400)
            self._reply(status,payload,'application/json; charset=utf-8')
            return
        try:
            if path.startswith('/api/online/'):
                token = self.headers.get('X-NABLA-Seat','')
                code = data.get('room','')
                with _LOCK:
                    if path == '/api/online/create':
                        result = _ONLINE.create(data.get('name','プレイヤー'))
                    elif path == '/api/online/join':
                        result = _ONLINE.join(code,data.get('name','プレイヤー'))
                    elif path == '/api/online/action':
                        result = _ONLINE.action(code,token,data.get('action'),data.get('revision'),data.get('game_id'))
                    elif path == '/api/online/explain':
                        result = _ONLINE.explain(code,token,data.get('event_id'))
                    elif path == '/api/online/leave':
                        result = _ONLINE.leave(code,token)
                    elif path == '/api/online/rematch':
                        result = _ONLINE.rematch(code,token)
                    else:
                        result = {'ok':False,'message':'不明なAPIです。'}
                    status,payload,_ = self._online_response(result)
                    if path == '/api/online/action' and result.get('status') in ('input_error','unsupported','stale','foul','ok'):
                        status = 200
            else:
                sid = self._local_session()
                if not sid:
                    status,payload = _http_result({'ok':False,'message':'セッションIDが必要です。'},401)
                else:
                    with _LOCK:
                        _STATE = _SESSIONS.get(sid, {'game':None,'ready':False,'mode':'local','difficulty':None})
                        status,payload = route_post(path,data)
                        _SESSIONS[sid] = _STATE
        except Exception:
            self.log_error('internal error on %s',path)
            status,payload=_http_result({'ok':False,'message':'内部エラーが発生しました。'},500)
        self._reply(status,payload,'application/json; charset=utf-8')
    def log_message(self,fmt,*args):
        # Avoid printing unnecessary local paths or parameters.
        print(f'[{self.log_date_time_string()}] {fmt%args}')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8765')))
    parser.add_argument('--host',default=os.environ.get('HOST','127.0.0.1'))
    args=parser.parse_args()
    global _ONLINE
    if os.environ.get('NABLA_REQUIRE_PERSISTENT_STORAGE') == '1' and not (os.environ.get('DATABASE_URL') or os.environ.get('NABLA_DB_PATH')):
        parser.error('公開時はDATABASE_URLまたは永続ディスク上のNABLA_DB_PATHが必要です。')
    _ONLINE = OnlineRooms(Storage())
    with ThreadingHTTPServer((args.host,args.port),Handler) as httpd:
        print('NABLA ARENA 第5段階 / ローカル・CPU・オンライン対戦')
        print(f'開くURL: http://{args.host}:{args.port}')
        print('停止: Ctrl+C')
        httpd.serve_forever()

if __name__=='__main__': main()

# NABLA-ANSWER-LOG-V2-2026-11-23
