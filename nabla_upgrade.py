"""One-shot, all-or-nothing source updater for the NABLA ARENA v3 branch.

Run from the project root on the *nabla-arena-update* branch. No overwrite of
main or backup branches. Does not change user credentials or deployment config.
"""
from __future__ import annotations
from pathlib import Path
import ast
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
MARK='NABLA-REVISION-2026-11'


def replace_once(text,old,new,description):
    count=text.count(old)
    if count!=1:
        raise RuntimeError(f'{description}: expected exactly one matching source block, found {count}')
    return text.replace(old,new,1)


def upgrade():
    required=['cards.py','cpu.py','nabla_game.py','online_rooms.py','server.py','index.html','app.js','nabla_math.py']
    source={name:(ROOT/name).read_text(encoding='utf-8') for name in required}
    if MARK in source['nabla_game.py']:
        print('Already applied. No changes needed.')
        return
    changes={}

    game=source['nabla_game.py']
    game=replace_once(game,"from cards import CARD_COUNTS, build_deck", "from cards import CARD_COUNTS, build_deck\nfrom nabla_upgraderules import restrict_initial_hands, draw_allowed_cards\n# "+MARK, 'game imports')
    game=replace_once(game,"from random import Random", "from random import Random\nimport secrets", "match ID dependency")
    game=replace_once(game,"deck = build_deck(seed=seed)","deck = restrict_initial_hands(build_deck(seed=seed))",'initial deal')
    game=replace_once(game,"'version': 2,","'version': 3,\n        'game_id': secrets.token_hex(12) if seed is None else 'seed-'+str(seed),",'state version')
    game=replace_once(game,"    draw_count = min(len(used), len(state['deck']))\n    hand.extend(state['deck'][:draw_count])\n    del state['deck'][:draw_count]",
                      "    drawn = draw_allowed_cards(state['deck'],len(used),state['turn_number'])\n    draw_count = len(drawn)\n    hand.extend(drawn)", 'draw protection')
    game=replace_once(game,"    state['history'].append(event)",
                      "    event['id'] = str(state.get('game_id','legacy'))+'-'+str(state['revision']+1)\n    state['history'].append(event)", 'committed move id')
    game=replace_once(game,"        next_state['history'].append(event)",
                      "        event['id'] = str(state.get('game_id','legacy'))+'-'+str(state['revision']+1)\n        next_state['history'].append(event)", 'pass id')
    game=replace_once(game,"        bad_state['history'].append(event)",
                      "        event['id'] = str(state.get('game_id','legacy'))+'-'+str(state['revision']+1)\n        bad_state['history'].append(event)", 'foul id')
    game=replace_once(game,"        'revision': state['revision'], 'turn_number':state['turn_number'],",
                      "        'game_id':state.get('game_id'), 'revision': state['revision'], 'turn_number':state['turn_number'],",'public game identity')
    changes['nabla_game.py']=game

    math=source['nabla_math.py']
    math=replace_once(math,
        "            if not _is_elementary(result):\n                raise UnsupportedMath('積分結果が初等関数で表せると証明できません。')",
        """            if not _is_elementary(result):
                # Fallback only after the existing algorithms did not produce
                # an elementary primitive. The next check is exact.
                try:
                    from sympy.integrals.manualintegrate import manualintegrate
                    alternative=manualintegrate(expr,X)
                    if _is_elementary(alternative) and sp.simplify(sp.diff(alternative,X)-expr)==0:
                        result=alternative
                except (ValueError, TypeError, NotImplementedError, RecursionError):
                    pass
            if not _is_elementary(result):
                raise UnsupportedMath('積分結果が初等関数で表せると証明できません。')""", 'verified integral algorithm fallback')
    math=replace_once(math,"    return []\n\n\ndef apply_card", """    if expr == sp.tan(X):
        return [('principal',sp.atan(X),sp.Interval.open(-sp.pi/2,sp.pi/2),
                 'tan(x) を (-pi/2,pi/2) に制限します。')]
    if expr.func == sp.exp:
        rate=sp.diff(expr.args[0],X)
        if rate.is_real and rate.is_number and rate.is_zero is False and not expr.args[0].subs(X,0):
            return [('standard',sp.log(X)/rate,sp.S.Reals,
                     '単調な指数関数の逆を自然対数として計算します。')]
    return []


def apply_card""", 'additional verified inverse families')
    changes['nabla_math.py']=math

    cards=source['cards.py']
    cards=replace_once(cards,"    deck = build_deck(seed=seed)\n    return {'hands': [deck[:7], deck[7:14]], 'deck': deck[14:]}",
                       "    from nabla_upgraderules import restrict_initial_hands\n    deck = restrict_initial_hands(build_deck(seed=seed))\n    return {'hands': [deck[:7], deck[7:14]], 'deck': deck[14:]}", 'deal helper')
    changes['cards.py']=cards

    cpu=source['cpu.py']
    cpu+='\n# '+MARK+' -- tested strategy modules replace earlier heuristics.\nfrom nabla_cpu2 import choose_cpu_action, take_cpu_turn\n'
    changes['cpu.py']=cpu

    online=source['online_rooms.py']
    online=replace_once(online,'        self.lock = threading.RLock()',
                        '        self.lock = threading.RLock()\n        if os.environ.get(\'NABLA_INVALIDATE_OLD_ROOMS\')==\'1\':\n            from nabla_upgraderules import invalidate_old_rooms\n            invalidate_old_rooms(self.store)\n        # '+MARK, 'online version activation')
    online=replace_once(online,'    def leave(self, code, token):', '''    def explain(self, code, token, event_id):
        from nabla_steps import explain_event
        with self.lock:
            now=self.clock()
            room,seat=self._authenticated(code,token,now)
            if room is None:
                return self.fail('認証に失敗しました。','unauthorized')
            if not isinstance(event_id,str) or len(event_id)>80:
                return self.fail('履歴番号が不正です。')
            game=room.get('game') or {}
            ev=next((e for e in game.get('history',[]) if e.get('id')==event_id),None)
            if ev is None:
                return self.fail('計算履歴が見つかりません。')
            if '_explanation' not in ev:
                ev['_explanation']=explain_event(ev)
                self.store.save(room)
            return {'ok':True,'explanation':ev['_explanation']}

    def leave(self, code, token):''','online explanation')
    online=replace_once(online,"    def action(self, code, token, action, revision):",
                        "    def action(self, code, token, action, revision, game_id=None):", 'online revision identity signature')
    online=replace_once(online,"            if room['game']['revision'] != revision:",
                        "            if room['game'].get('game_id') != game_id or room['game']['revision'] != revision:", 'online stale game protection')
    changes['online_rooms.py']=online

    server=source['server.py']
    server=replace_once(server,'from sandbox_math import safe_play, safe_cpu_turn',
                        'from sandbox_math import safe_play, safe_cpu_turn\nfrom nabla_practice import dispatch as dispatch_practice\nfrom nabla_steps import explain_event\n# '+MARK,'server imports')
    server=replace_once(server, "    if path == '/app.js':\n        return 200, (ROOT/'app.js').read_bytes(), 'application/javascript; charset=utf-8'",
                        "    if path == '/app.js':\n        return 200, (ROOT/'app.js').read_bytes(), 'application/javascript; charset=utf-8'\n    if path == '/nabla_upgrade_ui.js':\n        return 200, (ROOT/'nabla_upgrade_ui.js').read_bytes(), 'application/javascript; charset=utf-8'\n    if path == '/nabla_upgrade.css':\n        return 200, (ROOT/'nabla_upgrade.css').read_bytes(), 'text/css; charset=utf-8'",'static addon')
    server=replace_once(server,"    v['human_seat'] = 0 if mode == 'cpu' else seat",
                        "    v['human_seat'] = 0 if mode == 'cpu' else seat\n    v['deadline'] = _STATE.get('deadline')\n    v['server_now'] = time.time()\n    v['timer_seconds'] = 120", 'local timer payload')
    server=replace_once(server,
                        "_STATE = {'game':state,'ready':mode == 'cpu',\n                      'mode':mode,'difficulty':difficulty}",
                        "_STATE = {'game':state,'ready':mode == 'cpu',\n                      'mode':mode,'difficulty':difficulty,\n                      'deadline':time.time()+120 if mode=='cpu' and state['current']==0 else None}",
                        'new local game clock')
    server=replace_once(server,"            _STATE['ready'] = True\n            return _http_result({'ok':True,'state':_view()})",
                        "            _STATE['ready'] = True\n            _STATE['deadline']=time.time()+120\n            return _http_result({'ok':True,'state':_view()})",'handoff clock')
    server=replace_once(server,"            _STATE['game'] = result['state']\n            return _http_result({'ok':True,'status':'ok','state':_view(),",
                        "            _STATE['game'] = result['state']\n            _STATE['deadline']=time.time()+120 if not _STATE['game']['finished'] and _STATE['game']['current']==0 else None\n            return _http_result({'ok':True,'status':'ok','state':_view(),",'CPU completed clock')
    server=replace_once(server,"            result = safe_play(state,state['current'],action,revision)",
                        """            if _STATE.get('deadline') and time.time() >= _STATE['deadline']:
                expired=play(state,state['current'],{'kind':'pass','reason':'timeout'},state['revision'])
                _STATE['game']=expired['state']
                _STATE['deadline']=None
                if _STATE['mode']=='local':
                    _STATE['ready']=False
                return _http_result({'ok':True,'status':'ok','message':'時間切れによりパスしました。',
                                     'state':_view(),'event':expired.get('event')})
            result = safe_play(state,state['current'],action,revision)""",'deadline on action')
    server=replace_once(server,"                _STATE['game'] = result['state']\n                if _STATE['mode'] == 'local':",
                        "                _STATE['game'] = result['state']\n                _STATE['deadline']=None\n                if _STATE['mode'] == 'local':",'clock stop after play')
    # CPU deadline starts only after the CPU returns control to the human.
    server=replace_once(server,"        if path == '/api/cpu':",
                        """        if path == '/api/timeout':
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
        if path == '/api/cpu':""",'server timeout route')
    server=replace_once(server,"        if _STATE['game'] is None:\n            return _http_result({'ok':False,'message':'対戦が開始されていません。'},409)",
                        """        if path.startswith('/api/practice/'):
            return _http_result(dispatch_practice(_STATE,path,data))
        if path == '/api/explain':
            game=_STATE.get('game') or {}
            ev=next((e for e in game.get('history',[]) if e.get('id')==data.get('event_id')),None)
            if ev is None:
                return _http_result({'ok':False,'message':'計算履歴が見つかりません。'})
            if '_explanation' not in ev:
                ev['_explanation']=explain_event(ev)
            return _http_result({'ok':True,'explanation':ev['_explanation']})
        if _STATE['game'] is None:
            return _http_result({'ok':False,'message':'対戦が開始されていません。'},409)""",'local practice and explanation')
    server=replace_once(server,"                    elif path == '/api/online/leave':\n                        result = _ONLINE.leave(code,token)",
                        "                    elif path == '/api/online/explain':\n                        result = _ONLINE.explain(code,token,data.get('event_id'))\n                    elif path == '/api/online/leave':\n                        result = _ONLINE.leave(code,token)", 'online explanation endpoint')
    server=replace_once(server,"            if type(revision) is not int or revision != state['revision']:",
                        "            if data.get('game_id')!=state.get('game_id') or type(revision) is not int or revision != state['revision']:", 'CPU stale game protection')
    server=replace_once(server,"            if not isinstance(action,dict) or type(revision) is not int:",
                        "            if data.get('game_id')!=state.get('game_id') or not isinstance(action,dict) or type(revision) is not int:",'local stale game protection')
    server=replace_once(server,"result = _ONLINE.action(code,token,data.get('action'),data.get('revision'))",
                        "result = _ONLINE.action(code,token,data.get('action'),data.get('revision'),data.get('game_id'))",'online stale request protection')
    changes['server.py']=server

    html=source['index.html']
    if '</head>' not in html or '</body>' not in html:
        raise RuntimeError('index.html has unexpected document layout.')
    html=replace_once(html,'</head>', '<link rel="stylesheet" href="/nabla_upgrade.css">\n</head>', 'styles')
    html=replace_once(html,'</body>', '<script src="/nabla_upgrade_ui.js"></script>\n</body>', 'UI addon')
    changes['index.html']=html

    script=source.get('app.js') or (ROOT/'app.js').read_text(encoding='utf-8')
    script=replace_once(script,"api('cpu',{revision:model.revision})",
                        "api('cpu',{revision:model.revision,game_id:model.game_id})", 'CPU UI game ID')
    script=replace_once(script,"{room:online.room,action,revision:model.revision}):await api('action',{action,revision:model.revision}",
                        "{room:online.room,action,revision:model.revision,game_id:model.game_id}):await api('action',{action,revision:model.revision,game_id:model.game_id}", 'online and local action game ID')
    script=replace_once(script,"   await new Promise(resolve=>setTimeout(resolve,900));\n","",'remove artificial 900ms CPU delay')
    changes['app.js']=script

    # Syntax check every generated Python file before touching the source tree.
    for name,content in changes.items():
        if name.endswith('.py'):
            ast.parse(content,filename=name)
    for name in ('nabla_cpu2.py','nabla_practice.py','nabla_steps.py','nabla_upgraderules.py'):
        ast.parse((ROOT/name).read_text(encoding='utf-8'),filename=name)
    if not (ROOT/'nabla_upgrade_ui.js').exists() or not (ROOT/'nabla_upgrade.css').exists():
        raise RuntimeError('Upgrade UI files are missing. Upload all package files first.')

    # Atomic-ish source write: all patterns checked and syntax valid beforehand.
    for name,content in changes.items():
        target=ROOT/name
        temporary=ROOT/(name+'.nabla-pending')
        temporary.write_text(content,encoding='utf-8')
    for name in changes:
        (ROOT/(name+'.nabla-pending')).replace(ROOT/name)
    print('NABLA ARENA update applied to current checkout:', ', '.join(sorted(changes)))


if __name__=='__main__':
    try:
        upgrade()
    except Exception as exc:
        print('UPGRADE FAILED WITHOUT COMMIT: '+str(exc),file=sys.stderr)
        sys.exit(1)
