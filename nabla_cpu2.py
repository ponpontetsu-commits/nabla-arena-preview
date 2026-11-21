"""NABLA ARENA CPU strategy replacement.

Different heuristics for easy, medium and hard; every candidate is checked by
exactly the normal play() engine. Hidden opponent hand is NEVER inspected.
"""
from __future__ import annotations
from collections import Counter
from functools import lru_cache
from time import monotonic
import random
import sympy as sp
from nabla_game import FUNCTIONS, ALL_OPERATIONS, REPEATABLE_OPERATIONS, MIXED_OPERATIONS, play

DIFFICULTIES={'easy':'初級','medium':'中級','hard':'上級'}
CPU_SEAT=1


@lru_cache(maxsize=2048)
def _strength(text):
    """Approximate tie-breaking, never used for math legality or winner."""
    try:
        from nabla_math import parse_formula, X
        expr=parse_formula(text)
        def points(node):
            if node.is_Add:
                return max((points(arg) for arg in node.args),default=0)
            if node.is_Mul:
                return sum(points(arg) for arg in node.args)
            if node.func in (sp.sin,sp.cos):
                return 4
            if node.func==sp.exp:
                coef=sp.simplify(sp.diff(node.args[0],X))
                return max(1,8*float(abs(coef))) if coef.is_number else 8
            if node.is_Pow and node.exp.is_number:
                return points(node.base)*float(node.exp) if node.exp>0 else 0
            if node==X:
                return 1
            return 0
        return min(100.0,max(0.,float(points(expr))))
    except (ValueError,TypeError,OverflowError,RecursionError):
        return 0.


def _candidates(state,difficulty):
    hand=state['players'][CPU_SEAT]['hand']
    unique={}
    for i,c in enumerate(hand): unique.setdefault(c,i)
    boards=[(0,state['players'][0]['bases']),(1,state['players'][1]['bases'])]
    # All candidate generation uses CPU hand and PUBLIC basis expressions only.
    for card,index in unique.items():
        if card in FUNCTIONS:
            yield {'kind':'add','card_indices':[index], 'target_player':CPU_SEAT}
            if difficulty=='easy':
                yield {'kind':'add','card_indices':[index], 'target_player':0}
        elif card in ALL_OPERATIONS:
            for seat,_ in boards:
                yield {'kind':'operate','card_indices':[index], 'target_player':seat}
        elif card not in MIXED_OPERATIONS:
            for seat,bases in boards:
                for basis in bases[:16]:
                    yield {'kind':'operate','card_indices':[index], 'target_player':seat,'basis_id':basis['id']}
    if difficulty!='easy':
        for op in REPEATABLE_OPERATIONS:
            indexes=[i for i,c in enumerate(hand) if c==op]
            for count in range(2,min(len(indexes),3 if difficulty=='hard' else 2)+1):
                for seat,bases in boards:
                    for basis in bases[:12]:
                        yield {'kind':'operate','card_indices':indexes[:count],
                               'target_player':seat,'basis_id':basis['id']}
    operators=[(name,idx) for name,idx in unique.items() if name in MIXED_OPERATIONS]
    functions=[(name,idx) for name,idx in unique.items() if name in FUNCTIONS]
    for _,op_idx in operators:
        for _,fn_idx in functions:
            for seat,bases in boards:
                for basis in bases[:16]:
                    yield {'kind':'operate','card_indices':[op_idx,fn_idx],
                           'target_player':seat,'basis_id':basis['id']}
    if difficulty=='hard' and len(operators)>=2 and len(functions)>=2:
        for first in operators:
            for second in operators:
                if second[1]==first[1]:continue
                for f1 in functions:
                    for f2 in functions:
                        if f1[1]==f2[1]:continue
                        for seat,bases in boards:
                            for basis in bases[:8]:
                                yield {'kind':'operate',
                                       'card_indices':[first[1],f1[1],second[1],f2[1]],
                                       'target_player':seat,'basis_id':basis['id']}


def _cheap_priority(state,action):
    cards=[state['players'][CPU_SEAT]['hand'][i] for i in action['card_indices']]
    target=action['target_player']
    value=0
    if target==0:
        value+=15 if action['kind']=='operate' else -50
    elif action['kind']=='add':
        value+=9
    if cards and cards[0]=='all_diff2':value+=4
    if cards and cards[0]=='zero' and action['kind']=='add':value-=35
    value-=max(0,len(cards)-1)*2
    return value


@lru_cache(maxsize=2048)
def _risk_for_formula(formula):
    try:
        from nabla_math import apply_card
        result=apply_card(formula,'diff')
        if result.status=='vanished':return 7
        if result.status=='unsupported':return 1
        return 0
    except (ValueError,TypeError):
        return 1


def _public_risk(after):
    """Heuristic one-step vulnerability with representative *possible* attacks.
    Never reads opponent's actual or future cards.
    """
    own=after['players'][CPU_SEAT]['bases']
    if not own:return 5000
    # Estimate susceptibility to common differentiation attacks only.
    return sum(_risk_for_formula(b['expression']) for b in own[:9])/len(own)


def _score(before,after,action,difficulty):
    if after['finished']:
        if after['winner']==CPU_SEAT:return 1000000
        if after['winner'] is None:return 0
        return -1000000
    b0=before['players'];b1=after['players']
    o0,o1=len(b0[CPU_SEAT]['bases']),len(b1[CPU_SEAT]['bases'])
    e0,e1=len(b0[0]['bases']),len(b1[0]['bases'])
    difference=e0-e1
    change=o1-o0
    cost=len(action['card_indices'])
    if difficulty=='easy':
        return 70*difference+29*change-2*cost
    score=115*difference+75*change-4*cost
    score+=10*(o1-e1)
    own_strength=sum(_strength(b['expression']) for b in b1[1]['bases'][:12])
    opp_strength=sum(_strength(b['expression']) for b in b1[0]['bases'][:12])
    score+=1.3*own_strength-1.5*opp_strength
    if o1==1:score-=30
    if difficulty=='hard':
        score-=8*_public_risk(after)
        if e1==1:score+=18
        if o1>e1:score+=12
    return score


def choose_cpu_action(state,difficulty='medium',*,seed=None,max_seconds=None):
    if difficulty not in DIFFICULTIES:
        raise ValueError('CPUの難易度が不正です。')
    if state['finished'] or state['current']!=CPU_SEAT:
        raise ValueError('CPUの手番ではありません。')
    rng=random.Random(seed)
    budgets={'easy':1.0,'medium':2.0,'hard':4.0}
    caps={'easy':22,'medium':70,'hard':140}
    end=monotonic()+(min(float(max_seconds),budgets[difficulty]) if max_seconds is not None else budgets[difficulty])
    candidates=list(_candidates(state,difficulty))
    rng.shuffle(candidates)
    candidates.sort(key=lambda a:_cheap_priority(state,a),reverse=True)
    checked=set()
    legal=[]
    for action in candidates:
        if len(checked)>=caps[difficulty] or monotonic()>=end:break
        key=(action['kind'],tuple(state['players'][1]['hand'][i] for i in action['card_indices']),
             action['target_player'],action.get('basis_id'))
        if key in checked:continue
        checked.add(key)
        response=play(state,CPU_SEAT,action,expected_revision=state['revision'])
        if response['status']=='unsupported' and response.get('branch_options'):
            for branch in response['branch_options'][:2]:
                if monotonic()>=end:break
                candidate=dict(action,branch=branch)
                result=play(state,CPU_SEAT,candidate,expected_revision=state['revision'])
                if result['status']=='ok':
                    legal.append((candidate,result['state']))
            continue
        if response['status']!='ok':continue  # never select fouls or unsupported
        legal.append((action,response['state']))
        if response['state']['finished'] and response['state']['winner']==CPU_SEAT and difficulty!='easy':
            return action
        if difficulty=='easy' and len(legal)>=6:break
    if not legal:return {'kind':'pass'}
    if difficulty=='easy':
        attacks=[item for item in legal if item[0].get('target_player')==0]
        pool=attacks if attacks and rng.random()<0.65 else legal
        return rng.choice(pool)[0]
    scores=[_score(state,result,action,difficulty) for action,result in legal]
    ranking=sorted(range(len(legal)),key=lambda i:scores[i],reverse=True)
    if difficulty=='medium':
        top=ranking[:min(3,len(ranking))]
        return legal[rng.choice(top if rng.random()<0.2 else top[:1])][0]
    # hard: primarily best evaluated move, occasional tie variation only
    best=scores[ranking[0]]
    tied=[i for i in ranking if abs(scores[i]-best)<0.01]
    return legal[rng.choice(tied)][0]


def take_cpu_turn(state,difficulty='medium',*,seed=None,max_seconds=None):
    action=choose_cpu_action(state,difficulty,seed=seed,max_seconds=max_seconds)
    result=play(state,CPU_SEAT,action,expected_revision=state['revision'])
    if result['status']!='ok':
        action={'kind':'pass'}
        result=play(state,CPU_SEAT,action,expected_revision=state['revision'])
    return action,result
