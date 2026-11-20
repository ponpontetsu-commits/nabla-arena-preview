"""NABLA ARENA CPU opponents (local demonstration only).

Legal actions are validated with the very same `play()` function as a human.
This agent deliberately never commits a mathematics foul. It does not inspect the
human player's hand, even though the game engine holds it on the server.

Difficulty levels:
  easy: random sampled legal move;
  medium: choose a high-value legal one-card/pair move;
  hard: evaluate more candidates, repeated operations and multi-card chains,
        with a conservative risk/hand-cost heuristic.
This is bounded heuristic search, not a solver of the full game tree.
"""
from __future__ import annotations

from collections import Counter
import random
from time import monotonic

from nabla_game import FUNCTIONS, ALL_OPERATIONS, REPEATABLE_OPERATIONS, MIXED_OPERATIONS, play

DIFFICULTIES = {'easy': '初級', 'medium': '中級', 'hard': '上級'}
CPU_SEAT = 1


def _actions(state, difficulty):
    hand = state['players'][CPU_SEAT]['hand']
    first = {}
    for i, code in enumerate(hand):
        first.setdefault(code, i)
    own = state['players'][CPU_SEAT]['bases']
    other = state['players'][1-CPU_SEAT]['bases']
    sides = [(1-CPU_SEAT, other), (CPU_SEAT, own)]
    # Candidate generation is deterministic; equal card types are interchangeable.
    for code, idx in first.items():
        if code in FUNCTIONS:
            for seat, _board in sides:
                if difficulty != 'easy' and seat != CPU_SEAT:
                    continue
                yield {'kind': 'add', 'card_indices': [idx], 'target_player': seat}
        elif code in ALL_OPERATIONS:
            for seat, _board in sides:
                yield {'kind': 'operate', 'card_indices': [idx], 'target_player': seat}
        elif code not in MIXED_OPERATIONS:
            for seat, board in sides:
                for basis in board[:12]:
                    yield {'kind': 'operate', 'card_indices': [idx],
                           'target_player': seat, 'basis_id': basis['id']}
    if difficulty in ('medium', 'hard'):
        # n-th derivatives/integrals are allowed, but mixing both is prohibited.
        for op in REPEATABLE_OPERATIONS:
            indexes = [i for i, code in enumerate(hand) if code == op]
            maximum = min(len(indexes), 2 if difficulty == 'medium' else 3)
            for count in range(2, maximum+1):
                for seat, board in sides:
                    for basis in board[:12]:
                        yield {'kind': 'operate', 'card_indices': indexes[:count],
                               'target_player': seat, 'basis_id': basis['id']}
    # Mixed mul/div chains must alternate operator, function and are evaluated left-to-right.
    operators = [(code, idx) for code, idx in first.items() if code in MIXED_OPERATIONS]
    functions = [(code, idx) for code, idx in first.items() if code in FUNCTIONS]
    for _op, op_index in operators:
        for _func, fn_index in functions:
            for seat, board in sides:
                for basis in board[:12]:
                    yield {'kind': 'operate', 'card_indices': [op_index, fn_index],
                           'target_player': seat, 'basis_id': basis['id']}
    if difficulty == 'hard' and len(operators) >= 2 and len(functions) >= 2:
        # Evaluate a small number of two-pair combinations; used cards are distinct.
        for op1 in operators[:2]:
            for op2 in operators[:2]:
                if op1[1] == op2[1]:
                    continue
                for fn1 in functions[:3]:
                    for fn2 in functions[:3]:
                        if fn1[1] == fn2[1]:
                            continue
                        indexes = [op1[1], fn1[1], op2[1], fn2[1]]
                        for seat, board in sides:
                            for basis in board[:8]:
                                yield {'kind':'operate', 'card_indices': indexes,
                                       'target_player': seat, 'basis_id': basis['id']}


def _score(before, after, action, difficulty):
    """Public-board heuristic. NEVER inspect the human's private cards."""
    if after['finished']:
        if after['winner'] == CPU_SEAT:
            return 1_000_000
        if after['winner'] is None:
            return 0
        return -1_000_000
    own0 = len(before['players'][CPU_SEAT]['bases'])
    opp0 = len(before['players'][0]['bases'])
    own1 = len(after['players'][CPU_SEAT]['bases'])
    opp1 = len(after['players'][0]['bases'])
    # A lost enemy basis is more important than adding one new friendly basis.
    enemy_reduction = opp0-opp1
    own_gain = own1-own0
    if difficulty == 'medium':
        return 160*enemy_reduction + 85*own_gain - 3*len(action['card_indices'])
    score = 225*enemy_reduction + 105*own_gain
    score += 4*(own1-opp1)  # retain a lead when the deck is almost empty
    score -= 6*max(0, len(action['card_indices'])-1)
    if after['deck']:
        # Prefer not to expose the CPU to an immediate zero-dimensional loss.
        if own1 == 1: score -= 25
        # Using a zero card is legal but usually a wasted tempo.
        if all(before['players'][CPU_SEAT]['hand'][i] == 'zero' for i in action['card_indices']):
            score -= 12
    return score


def choose_cpu_action(state, difficulty='medium', *, seed=None, max_seconds=5.0):
    """Return a legal move, or pass if no safely computable move was found.

    `play()` simulates without mutating input. Unsupported math and fouls are
    discarded, never intentionally chosen. Limits are best-effort: a single
    expensive symbolic calculation cannot be interrupted inside the same thread.
    """
    if difficulty not in DIFFICULTIES:
        raise ValueError('CPUの難易度が不正です。')
    if state['finished'] or state['current'] != CPU_SEAT:
        raise ValueError('CPUの手番ではありません。')
    rng = random.Random(seed)
    limit = {'easy': 35, 'medium': 85, 'hard': 170}[difficulty]
    candidates = list(_actions(state, difficulty))
    # Scatter candidate types and target choices. This also prevents bias when
    # the number of bases exceeds the candidate budget.
    rng.shuffle(candidates)
    end_time = monotonic() + max_seconds
    legal = []
    for action in candidates[:limit]:
        if monotonic() > end_time:
            break
        outcome = play(state, CPU_SEAT, action, expected_revision=state['revision'])
        if outcome['status'] == 'unsupported' and outcome.get('branch_options'):
            for branch in outcome['branch_options'][:4]:
                branched = dict(action, branch=branch)
                test = play(state, CPU_SEAT, branched, expected_revision=state['revision'])
                if test['status'] == 'ok':
                    legal.append((branched, test['state']))
            continue
        if outcome['status'] == 'ok':
            legal.append((action, outcome['state']))
        if difficulty == 'easy' and len(legal) >= 6:
            break
    if not legal:
        return {'kind': 'pass'}
    if difficulty == 'easy':
        return rng.choice(legal)[0]
    scores = [_score(state, result, act, difficulty) for act, result in legal]
    top = max(scores)
    choices = [a for (a, _), score in zip(legal, scores) if score == top]
    return rng.choice(choices)


def take_cpu_turn(state, difficulty='medium', *, seed=None, max_seconds=5.0):
    action = choose_cpu_action(state, difficulty, seed=seed, max_seconds=max_seconds)
    outcome = play(state, CPU_SEAT, action, expected_revision=state['revision'])
    if outcome['status'] != 'ok':
        # Never force a speculative or illegal move; pass if the computation
        # became unavailable or invalid between evaluation and commit.
        outcome = play(state, CPU_SEAT, {'kind': 'pass'}, expected_revision=state['revision'])
        action = {'kind': 'pass'}
    return action, outcome
