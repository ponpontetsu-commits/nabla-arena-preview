"""NABLA ARENA online room authority.

Room codes identify invitations, never authentication. A 256-bit seat token
is returned to the joining browser, stored only as a SHA-256 digest at rest.
All game moves, timeouts, presence, and persistence are server-authoritative.

Production deployment: a SINGLE worker (process) and a durable database.
SQLite on an ephemeral hosting filesystem does NOT survive instance replacement;
use a mounted durable volume or set DATABASE_URL to an external PostgreSQL DB.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from nabla_game import new_game, play, public_view
from sandbox_math import safe_play

TURN_SECONDS = 120
ABSENCE_GRACE = 15
DISCONNECT_SECONDS = 300
MAX_ROOMS = 10000


class Storage:
    """Portable JSON room store for SQLite or external PostgreSQL (optional)."""
    def __init__(self, db_path=None, database_url=None):
        database_url = database_url or os.environ.get('DATABASE_URL')
        self.postgres = bool(database_url)
        if self.postgres:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError('DATABASE_URLを使うには psycopg[binary] が必要です。') from exc
            # A single-worker deployment intentionally uses a single connection.
            self.conn = psycopg.connect(database_url, autocommit=True)
            self.conn.execute('CREATE TABLE IF NOT EXISTS nabla_rooms (code TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        else:
            db_path = db_path or os.environ.get('NABLA_DB_PATH', 'nabla_rooms.sqlite3')
            if db_path != ':memory:':
                Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.execute('CREATE TABLE IF NOT EXISTS nabla_rooms (code TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            self.conn.commit()

    def _run(self, sql, parameters=()):
        if self.postgres:
            sql = sql.replace('?', '%s')
        return self.conn.execute(sql, parameters)

    def load(self, code):
        row = self._run('SELECT payload FROM nabla_rooms WHERE code=?', (code,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, room):
        payload = json.dumps(room, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        self._run('INSERT INTO nabla_rooms(code,payload) VALUES (?,?) '
                  'ON CONFLICT(code) DO UPDATE SET payload=excluded.payload', (room['code'], payload))
        if not self.postgres:
            self.conn.commit()

    def count(self):
        return self._run('SELECT COUNT(*) FROM nabla_rooms').fetchone()[0]

    def close(self):
        self.conn.close()


def _digest(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def _valid_token(token):
    return isinstance(token, str) and 40 <= len(token) <= 128 and token.isascii()


def _clean_name(name):
    return (name.strip()[:24] if isinstance(name, str) else '') or 'プレイヤー'


class OnlineRooms:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or time.time
        self.lock = threading.RLock()

    @staticmethod
    def fail(message, status='error'):
        return {'ok': False, 'status': status, 'message': message}

    def _seat(self, room, token):
        if not _valid_token(token):
            return None
        hashed = _digest(token)
        for seat, member in enumerate(room['members']):
            if member and hmac.compare_digest(member['token_hash'], hashed):
                return seat
        return None

    def _view(self, room, seat, now):
        game = room.get('game')
        members = room['members']
        phase = room['phase']
        live = [bool(m and now - m['last_seen'] <= ABSENCE_GRACE) for m in members]
        return {
            'code': room['code'], 'seat': seat, 'phase': phase,
            'connected': live,
            'players_joined': sum(m is not None for m in members),
            'online': True, 'mode': 'online', 'ready': phase == 'playing',
            'timer_seconds': TURN_SECONDS,
            'deadline': room.get('deadline'),
            'paused': room.get('pause_since') is not None,
            'pause_remaining': round(max(0,DISCONNECT_SECONDS-(now-room['pause_since']))) if room.get('pause_since') is not None else None,
            'server_now': now,
            'remaining_seconds': max(0, room['remaining']) if room.get('pause_since') is not None else (max(0, room['deadline']-now) if room.get('deadline') is not None else None),
            'rematch_votes': room.get('rematch_votes', [False, False]),
            'match_number': room.get('match_number', 1),
            'match_void': room.get('match_void', False),
            **(public_view(game, seat) if game else {
                'revision': 0, 'turn_number': 0, 'current': None,
                'players': [{'name':m['name'] if m else '参加待ち', 'hand_count': 0, 'bases':[], 'dimension':0} for m in members],
                'deck_remaining': 78, 'finished': False, 'history':[], 'winner':None, 'end_reason':None,
            }),
        }

    def create(self, name):
        with self.lock:
            if self.store.count() >= MAX_ROOMS:
                return self.fail('ルームが上限に達しました。')
            for _ in range(50):
                code = f'{secrets.randbelow(1000000):06d}'
                if self.store.load(code) is None:
                    break
            else:
                return self.fail('ルーム番号の発行に失敗しました。')
            token = secrets.token_urlsafe(32)
            now = self.clock()
            room = {
                'code': code, 'phase': 'waiting', 'members': [
                    {'name': _clean_name(name), 'token_hash': _digest(token), 'last_seen': now}, None],
                'created': now, 'game': None, 'deadline': None, 'remaining': TURN_SECONDS,
                'pause_since': None, 'rematch_votes': [False, False], 'match_number': 1,
                'match_void': False,
            }
            self.store.save(room)
            return {'ok': True, 'code': code, 'token': token, 'seat': 0,
                    'state': self._view(room, 0, now)}

    def join(self, code, name):
        with self.lock:
            if not isinstance(code, str) or len(code) != 6 or not code.isdecimal():
                return self.fail('6桁のルーム番号を指定してください。')
            room = self.store.load(code)
            if not room:
                return self.fail('ルームが見つかりません。')
            if room['phase'] != 'waiting' or room['members'][1] is not None:
                return self.fail('このルームは満員、または対戦開始済みです。')
            token = secrets.token_urlsafe(32)
            now = self.clock()
            room['members'][1] = {'name': _clean_name(name), 'token_hash': _digest(token), 'last_seen': now}
            game = new_game()
            for i, member in enumerate(room['members']):
                game['players'][i]['name'] = member['name']
            room.update(phase='playing', game=game, deadline=now+TURN_SECONDS,
                        remaining=TURN_SECONDS, pause_since=None)
            self._tick(room, now)  # creator may have already gone offline
            self.store.save(room)
            return {'ok': True, 'code': code, 'token': token, 'seat': 1,
                    'state': self._view(room, 1, now)}

    def _tick(self, room, now):
        if room['phase'] != 'playing' or room['game']['finished']:
            return
        online = [m is not None and now-m['last_seen'] <= ABSENCE_GRACE for m in room['members']]
        if not all(online):
            if room['pause_since'] is None:
                # timer stops when the first member is judged absent
                pause_at = min(now, min(m['last_seen'] + ABSENCE_GRACE for m in room['members'] if m and now-m['last_seen'] > ABSENCE_GRACE))
                room['remaining'] = max(0, room['deadline'] - pause_at)
                room['pause_since'] = pause_at
                room['deadline'] = None
            if now - room['pause_since'] >= DISCONNECT_SECONDS:
                game = room['game']
                game['finished'] = True
                game['winner'] = None
                game['end_reason'] = '通信切断（5分経過）による無効試合'
                game['revision'] += 1
                room['match_void'] = True
                room['phase'] = 'finished'
            return
        if room['pause_since'] is not None:
            # Both seats restored: unused time is carried forward.
            room['deadline'] = now + room['remaining']
            room['pause_since'] = None
        if room['deadline'] is not None and now >= room['deadline']:
            # One authoritative automatic pass, then a fresh 120-second turn.
            result = play(room['game'], room['game']['current'], {'kind':'pass', 'reason':'timeout'},
                          expected_revision=room['game']['revision'])
            if result['status'] == 'ok':
                room['game'] = result['state']
                if room['game']['finished']:
                    room['phase'] = 'finished'
                    room['deadline'] = None
                else:
                    room['deadline'] = now + TURN_SECONDS
                    room['remaining'] = TURN_SECONDS

    def _authenticated(self, code, token, now):
        room = self.store.load(code) if isinstance(code, str) else None
        if not room:
            return None, None
        seat = self._seat(room, token)
        return (room, seat) if seat is not None else (None, None)

    def state(self, code, token):
        with self.lock:
            now = self.clock()
            room, seat = self._authenticated(code, token, now)
            if room is None:
                return self.fail('ルームまたは認証情報を確認できません。', 'unauthorized')
            # Timeouts and disconnection detection must precede a reconnect.
            self._tick(room, now)
            room['members'][seat]['last_seen'] = now
            self._tick(room, now)
            self.store.save(room)
            return {'ok': True, 'state': self._view(room, seat, now)}

    def action(self, code, token, action, revision):
        with self.lock:
            now = self.clock()
            room, seat = self._authenticated(code, token, now)
            if room is None:
                return self.fail('認証に失敗しました。', 'unauthorized')
            self._tick(room, now)
            room['members'][seat]['last_seen'] = now
            self._tick(room, now)
            if room['phase'] != 'playing' or room['pause_since'] is not None:
                self.store.save(room)
                return self.fail('現在は操作できません。再接続待ち、または対戦終了です。', 'paused')
            if type(revision) is not int or not isinstance(action, dict):
                return self.fail('操作形式が不正です。', 'input_error')
            if room['game']['current'] != seat:
                return self.fail('相手の手番です。', 'not_your_turn')
            if room['game']['revision'] != revision:
                self.store.save(room)
                return {'ok':False,'status':'stale','message':'古い盤面です。','state':self._view(room,seat,now)}
            remaining = max(0, room['deadline'] - now)
            # Server accepted the action within time. Stop the clock for math.
            result = safe_play(room['game'], seat, action, revision)
            done = self.clock()
            if result['status'] in ('ok', 'foul'):
                room['game'] = result['state']
                if room['game']['finished']:
                    room['phase'] = 'finished'; room['deadline'] = None
                else:
                    room['deadline'] = done + TURN_SECONDS
                    room['remaining'] = TURN_SECONDS
            else:
                # Unsupported and invalid input do not consume player thinking time.
                room['deadline'] = done + remaining
            self.store.save(room)
            return {'ok': result['status'] in ('ok','foul'), 'status':result['status'],
                    'message':result['reason'],'branch_options':result.get('branch_options',[]),
                    'event':result.get('event'), 'state':self._view(room,seat,done)}

    def leave(self, code, token):
        with self.lock:
            now = self.clock()
            room, seat = self._authenticated(code, token, now)
            if room is None:
                return self.fail('認証に失敗しました。', 'unauthorized')
            if room['phase'] == 'waiting':
                room['phase'] = 'closed'
            elif room['phase'] == 'playing':
                room['game']['finished'] = True
                room['game']['winner'] = 1-seat
                room['game']['end_reason'] = '途中退出による不戦敗'
                room['game']['revision'] += 1
                room['phase'] = 'finished'
                room['deadline'] = None
            self.store.save(room)
            return {'ok': True, 'state':self._view(room, seat, now)}

    def rematch(self, code, token):
        with self.lock:
            now = self.clock()
            room, seat = self._authenticated(code, token, now)
            if room is None:
                return self.fail('認証に失敗しました。', 'unauthorized')
            if room['phase'] != 'finished':
                return self.fail('対戦終了後に再戦を選んでください。')
            if room['rematch_votes'][seat]:
                return {'ok':True, 'state':self._view(room,seat,now)}
            room['rematch_votes'][seat] = True
            if all(room['rematch_votes']):
                game = new_game()
                for i,m in enumerate(room['members']):
                    game['players'][i]['name'] = m['name']
                    m['last_seen'] = now
                room['game'] = game
                room['phase'] = 'playing'
                room['match_void'] = False
                room['deadline'] = now + TURN_SECONDS
                room['remaining'] = TURN_SECONDS
                room['pause_since'] = None
                room['match_number'] += 1
                room['rematch_votes'] = [False,False]
            self.store.save(room)
            return {'ok':True, 'state':self._view(room,seat,now)}
