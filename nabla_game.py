"""NABLA ARENA - stage 2 deterministic rules/turn game prototype.

No GUI, server, CPU or external database. The source-of-truth action function
never commits an invalid/unsupported move. Use only with trusted test data;
production must enforce CPU/time/memory limits and server-side authentication.
"""
from __future__ import annotations

from copy import deepcopy
from random import Random
from typing import Any

from cards import CARD_COUNTS, build_deck
from nabla_math import (
    apply_card, apply_mixed_chain, apply_whole_board,
    proportional_on_shared_domain,
)

FUNCTIONS = {
    'zero': '0', 'one': '1', 'x': 'x', 'x2': 'x**2',
    'exp': 'exp(x)', 'sin': 'sin(x)', 'cos': 'cos(x)',
}
ALL_OPERATIONS = {'all_diff': 1, 'all_diff2': 2}
REPEATABLE_OPERATIONS = {'diff', 'integrate'}
SINGLE_OPERATIONS = {
    'diff', 'integrate', 'limit_plus_inf', 'limit_minus_inf',
    'limit_zero', 'limsup_plus_inf', 'liminf_plus_inf',
    'sqrt', 'inverse', 'log',
}
MIXED_OPERATIONS = {'mul', 'div'}


def _base(number: int, formula: str):
    return {'id': number, 'expression': formula}


def new_game(seed: int | None = None) -> dict[str, Any]:
    """Construct a full game with 78 physical cards and randomized first seat.

    `seed` is solely for reproducible local testing; use entropy in production.
    """
    deck = build_deck(seed=seed)
    current = Random(seed).randrange(2)
    return {
        'version': 2,
        'players': [
            {'name': 'プレイヤー1', 'hand': deck[:7], 'bases': [_base(1,'1'),_base(2,'x'),_base(3,'x**2')], 'next_basis_id': 4},
            {'name': 'プレイヤー2', 'hand': deck[7:14], 'bases': [_base(1,'1'),_base(2,'x'),_base(3,'x**2')], 'next_basis_id': 4},
        ],
        'deck': deck[14:],  # pop(0): same shuffled ordering as stage 1
        'discard': [],
        'current': current,
        'turn_number': 1,
        'consecutive_passes': 0,
        'revision': 0,
        'finished': False,
        'winner': None,  # None represents draw if finished=True
        'end_reason': None,
        'history': [],
    }


def _response(status, state, reason='', *, event=None, branch_options=None):
    return {'status':status, 'reason':reason, 'state':state,
            'event':event, 'branch_options':branch_options or []}


def _valid_player(value):
    return type(value) is int and value in (0,1)


def _result_end(state, reason):
    """Finalize from *live* basis counts; winner is a seat or None (draw)."""
    counts = [len(p['bases']) for p in state['players']]
    if counts[0] == counts[1]: winner = None
    else: winner = 0 if counts[0] > counts[1] else 1
    state.update(finished=True, winner=winner, end_reason=reason)


def _zero_victory(state):
    sizes = [len(p['bases']) for p in state['players']]
    if sizes[0] and sizes[1]: return False
    if sizes[0] == sizes[1]:
        state.update(finished=True, winner=None, end_reason='双方0次元')
    else:
        state.update(finished=True, winner=0 if sizes[0] else 1, end_reason='0次元到達')
    return True


def _complete(state, actor, event, used_indexes):
    """Committed action: consume selected physical cards and replenish atomically."""
    hand = state['players'][actor]['hand']
    used = [hand[i] for i in used_indexes]
    for i in sorted(used_indexes, reverse=True):
        del hand[i]
    state['discard'].extend(used)
    draw_count = min(len(used), len(state['deck']))
    hand.extend(state['deck'][:draw_count])
    del state['deck'][:draw_count]
    event['used_cards'] = used
    event['draw_count'] = draw_count
    event['deck_remaining'] = len(state['deck'])
    state['history'].append(event)
    state['consecutive_passes'] = 0
    state['revision'] += 1
    if not _zero_victory(state) and not state['deck']:
        _result_end(state, '山札切れ')
    if not state['finished']:
        state['current'] = 1-actor
        state['turn_number'] += 1
    return _response('ok', state, event=event)


def _noncommitted(status, original, reason, opts=None):
    # Always return an isolated unchanged state: no accidental mutation on errors.
    return _response(status, deepcopy(original), reason, branch_options=opts)


def _find_basis(board, number):
    return next((basis for basis in board if basis['id'] == number), None)


def _proportional_to_older(formula, board, except_id=None):
    for existing in board:
        if existing['id'] == except_id: continue
        same = proportional_on_shared_domain(formula, existing['expression'])
        if same == 'unsupported': return ('unsupported', None)
        if same == 'yes': return ('yes', existing['id'])
    return ('no', None)


def _validate_indices(hand, indices):
    if not isinstance(indices, list) or not indices:
        return '少なくとも1枚のカードを選択してください。'
    if any(type(i) is not int or i < 0 or i >= len(hand) for i in indices):
        return '存在しない手札番号です。'
    if len(indices) != len(set(indices)):
        return '同じカードを重複して選択できません。'
    return None


def play(state: dict[str, Any], actor: int, action: dict[str, Any],
         expected_revision: int | None = None) -> dict[str, Any]:
    """Apply one action from a given player, returning response with a NEW state.

    action examples:
      {'kind':'pass'}
      {'kind':'add','card_indices':[0], 'target_player':0}
      {'kind':'operate','card_indices':[1], 'target_player':1,'basis_id':3}
      {'kind':'operate','card_indices':[0], 'target_player':1}   # whole-board
      {'kind':'operate','card_indices':[0,1,3,2], 'target_player':1,'basis_id':3}
    Card indices are ZERO-BASED positions in the acting player's *current* hand.
    """
    if not _valid_player(actor) or not isinstance(action, dict):
        return _noncommitted('input_error', state, '操作データが不正です。')
    if expected_revision is not None and expected_revision != state.get('revision'):
        return _noncommitted('stale', state, '古い盤面への操作です。最新状態に同期してください。')
    if state['finished']:
        return _noncommitted('input_error', state, 'すでに対戦が終了しています。')
    if state['current'] != actor:
        return _noncommitted('input_error', state, '現在の手番ではありません。')

    kind = action.get('kind')
    if kind == 'pass':
        why = action.get('reason','manual')
        if why not in ('manual','timeout'):
            return _noncommitted('input_error', state, 'パスの理由が不正です。')
        next_state = deepcopy(state)
        event = {'actor':actor, 'kind':'pass', 'reason':why, 'turn':state['turn_number'],
                 'used_cards':[], 'draw_count':0}
        next_state['consecutive_passes'] += 1
        next_state['history'].append(event)
        next_state['revision'] += 1
        if next_state['consecutive_passes'] >= 2:
            _result_end(next_state, '2回連続パス')
        else:
            next_state['current'] = 1-actor
            next_state['turn_number'] += 1
        return _response('ok', next_state, event=event)

    if kind not in ('add','operate'):
        return _noncommitted('input_error', state, '未知の操作です。')
    target = action.get('target_player')
    if not _valid_player(target):
        return _noncommitted('input_error', state, '対象となるプレイヤーが不正です。')

    selection = action.get('card_indices')
    hand = state['players'][actor]['hand']
    problem = _validate_indices(hand, selection)
    if problem:
        return _noncommitted('input_error', state, problem)
    codes = [hand[i] for i in selection]
    for code in codes:
        if code not in CARD_COUNTS:
            return _noncommitted('input_error', state, '未知のカードが含まれています。')
    board = state['players'][target]['bases']
    event = {'actor':actor, 'kind':kind, 'target_player':target,
             'turn':state['turn_number'], 'basis_id':None,
             'before':None, 'after':None, 'calculations':[], 'removed':[]}
    next_state = deepcopy(state)
    new_board = next_state['players'][target]['bases']

    if kind == 'add':
        if len(codes) != 1 or codes[0] not in FUNCTIONS:
            return _noncommitted('input_error', state, '基底追加には関数カードを1枚選んでください。')
        formula = FUNCTIONS[codes[0]]
        new_number = next_state['players'][target]['next_basis_id']
        next_state['players'][target]['next_basis_id'] += 1
        event['basis_id'] = new_number
        event['after'] = formula
        if codes[0] == 'zero':
            event['removed'].append({'id':new_number, 'reason':'0'})
        else:
            dep, same_id = _proportional_to_older(formula, board)
            if dep == 'unsupported':
                return _noncommitted('unsupported', state, '追加基底の線形従属を証明できません。')
            if dep == 'yes':
                event['removed'].append({'id':new_number, 'reason':f'No.{same_id}に比例'})
            else:
                new_board.append(_base(new_number, formula))
        return _complete(next_state, actor, event, selection)

    # Validate operator group BEFORE math invocation or any state change.
    if codes[0] in ALL_OPERATIONS:
        if len(codes) != 1 or 'basis_id' in action:
            return _noncommitted('input_error', state, '全体演算は1枚のカードと対象の場を指定します。')
        operation_result = apply_whole_board([(b['id'],b['expression']) for b in board], ALL_OPERATIONS[codes[0]])
    else:
        number = action.get('basis_id')
        if type(number) is not int or number <= 0:
            return _noncommitted('input_error', state, '個別演算には基底番号を指定してください。')
        base = _find_basis(board, number)
        if base is None:
            return _noncommitted('input_error', state, '対象の基底が見つかりません。')
        event['basis_id'] = number
        event['before'] = base['expression']
        if codes[0] in MIXED_OPERATIONS:
            if len(codes) % 2 or any(
                codes[i] not in MIXED_OPERATIONS or codes[i+1] not in FUNCTIONS
                for i in range(0,len(codes),2)
            ):
                return _noncommitted('input_error', state, '乗除算は演算カード→関数カードの順に選択してください。')
            operations = [(codes[i],FUNCTIONS[codes[i+1]]) for i in range(0,len(codes),2)]
            r = apply_mixed_chain(base['expression'], operations)
        elif codes[0] in REPEATABLE_OPERATIONS:
            if any(code != codes[0] for code in codes):
                return _noncommitted('input_error', state, '微分または積分は同じ種類だけ複数選択できます。')
            prior = base['expression']
            details = []
            r = None
            for _ in codes:
                r = apply_card(prior, codes[0])
                details.append(r.to_dict())
                if r.status not in ('ok','vanished'):
                    break
                prior = r.after
            if r is not None:
                event['calculations'] = details
        elif codes[0] in SINGLE_OPERATIONS and len(codes) == 1:
            r = apply_card(base['expression'], codes[0], branch=action.get('branch'))
        else:
            return _noncommitted('input_error', state, 'このカードの組み合わせは使用できません。')
        operation_result = {'status':r.status, 'reason':r.reason, 'result':r}

    status = operation_result['status']
    if status in ('input_error','unsupported'):
        extra = operation_result.get('result')
        return _noncommitted(status, state, operation_result.get('reason','計算できません。'),
                             extra.branch_options if extra else None)
    if status == 'foul':
        bad_state = deepcopy(state)
        bad_state.update(finished=True,winner=1-actor,end_reason='反則負け')
        event['status']='foul'
        event['reason']=operation_result.get('reason','反則')
        event['used_cards']=codes
        event['draw_count']=0
        if operation_result.get('result'):
            event['calculations'].append(operation_result['result'].to_dict())
        bad_state['history'].append(event)
        bad_state['revision'] += 1
        return _response('foul', bad_state, event['reason'], event=event)
    if status not in ('ok','vanished'):
        return _noncommitted('unsupported', state, '数学的な結果を判定できません。')

    if codes[0] in ALL_OPERATIONS:
        new_board[:] = operation_result['bases']
        event['calculations'] = operation_result.get('calculations',[])
        event['removed'] = operation_result.get('removed',[])
        event['before'] = [{'id':b['id'],'expression':b['expression']} for b in board]
        event['after'] = [{'id':b['id'],'expression':b['expression']} for b in new_board]
    else:
        event['calculations'] = event['calculations'] or [operation_result['result'].to_dict()]
        r = operation_result['result']
        event['after'] = r.after
        if r.status == 'vanished':
            new_board[:] = [b for b in new_board if b['id'] != event['basis_id']]
            event['removed'].append({'id':event['basis_id'], 'reason':r.reason or '0'})
        else:
            dep, match = _proportional_to_older(r.after, board, except_id=event['basis_id'])
            if dep == 'unsupported':
                return _noncommitted('unsupported', state, '演算後の線形従属を証明できません。')
            if dep == 'yes':
                new_board[:] = [b for b in new_board if b['id'] != event['basis_id']]
                event['removed'].append({'id':event['basis_id'], 'reason':f'No.{match}に比例'})
            else:
                _find_basis(new_board, event['basis_id'])['expression'] = r.after
    return _complete(next_state, actor, event, selection)


def public_view(state: dict[str, Any], viewer: int) -> dict[str, Any]:
    """UI projection: private hand visible only to its player.

    For online use, the SERVER must retain full state and authenticate `viewer`.
    """
    if not _valid_player(viewer):
        raise ValueError('プレイヤー番号が不正です。')
    return {
        'revision': state['revision'], 'turn_number':state['turn_number'],
        'current':state['current'], 'deck_remaining':len(state['deck']),
        'players': [
            {'name':p['name'], 'bases':deepcopy(p['bases']),
             'dimension':len(p['bases']), 'hand_count':len(p['hand']),
             **({'hand':p['hand'][:]} if i==viewer else {})}
            for i,p in enumerate(state['players'])
        ],
        'finished':state['finished'], 'winner':state['winner'],
        'end_reason':state['end_reason'],
        'history':deepcopy(state['history']),
    }
