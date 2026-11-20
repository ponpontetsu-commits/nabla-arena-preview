"""NABLA ARENA: symbolic math prototype (stage 1, not a deployed game).

Pure Python/SymPy implementation deliberately returns 'unsupported' rather than
inventing results. It does not mutate deck, hands, turns, timers or server state.

Design inputs are restricted AST-style formula strings (NOT eval/sympify on text).
Rules from 2026-11-21 NABLA ARENA spec, especially 75, 78-89, 92, 95,
97, 107-109, 113, 115, 117, 118, 121-122.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

import sympy as sp
from sympy.calculus.util import continuous_domain

X = sp.Symbol('x', real=True)
Y = sp.Symbol('y', real=True)

_ALLOWED_FUNCTIONS = {
    'sin': sp.sin, 'cos': sp.cos, 'tan': sp.tan,
    'exp': sp.exp, 'log': sp.log, 'sqrt': sp.sqrt,
    'asin': sp.asin, 'acos': sp.acos, 'atan': sp.atan,
    'sinh': sp.sinh, 'cosh': sp.cosh, 'tanh': sp.tanh,
    'asinh': sp.asinh, 'acosh': sp.acosh, 'atanh': sp.atanh,
    'Abs': sp.Abs,
}
_ALLOWED_NAMES = {'x': X, 'pi': sp.pi, 'e': sp.E, 'E': sp.E}
_ALLOWED_RESULT_FUNCS = set(_ALLOWED_FUNCTIONS.values())
_MAX_NODES = 180
_MAX_CHARS = 700

class InputError(ValueError):
    """Unusable card or formula input, not an in-game mathematics foul."""

class UnsupportedMath(Exception):
    """Proof cannot be completed reliably by this prototype."""


@dataclass
class Result:
    status: str                       # ok / vanished / foul / unsupported / input_error
    before: str
    after: str | None = None
    latex_before: str | None = None
    latex_after: str | None = None
    domain_before: str | None = None
    domain_after: str | None = None
    domain_changed_note: str | None = None
    reason: str = ''
    steps: list[dict[str, str]] = field(default_factory=list)
    branch_options: list[str] = field(default_factory=list)

    def to_dict(self):
        return vars(self).copy()


def parse_formula(text: str) -> sp.Expr:
    """Safe parser for program-generated expressions, e.g. `x**2*exp(x)`.

    Explicit whitelist; no Python function calls except known mathematics, no
    attributes, indexing, assignments, floats, lists, or arbitrary identifiers.
    A production server must also apply request size and computation time limits.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > _MAX_CHARS:
        raise InputError('数式の長さ・形式が不正です。')
    try:
        tree = ast.parse(text.replace('^', '**'), mode='eval')
    except SyntaxError as exc:
        raise InputError('数式を読み取れません。') from exc
    if len(list(ast.walk(tree))) > _MAX_NODES:
        raise InputError('数式が複雑すぎます。')

    def read(node):
        if isinstance(node, ast.Expression): return read(node.body)
        if isinstance(node, ast.Constant):
            if type(node.value) is int and abs(node.value) <= 100000:
                return sp.Integer(node.value)
            raise InputError('整数以外の数値や未対応の定数は使えません。')
        if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            val = read(node.operand)
            return val if isinstance(node.op, ast.UAdd) else -val
        if isinstance(node, ast.BinOp):
            a, b = read(node.left), read(node.right)
            if isinstance(node.op, ast.Add): return a+b
            if isinstance(node.op, ast.Sub): return a-b
            if isinstance(node.op, ast.Mult): return a*b
            if isinstance(node.op, ast.Div):
                if b == 0: raise InputError('数式そのものに0除算があります。')
                return a/b
            if isinstance(node.op, ast.Pow):
                if b.is_number is not True or b.is_real is not True:
                    raise InputError('指数には実数の定数式だけを使用できます。')
                if b.is_Rational and (abs(b.p)>64 or b.q>32):
                    raise InputError('指数の上限を超えました。')
                return a**b
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            f = _ALLOWED_FUNCTIONS.get(node.func.id)
            if f is not None and len(node.args)==1 and not node.keywords:
                return f(read(node.args[0]))
        raise InputError('この形式の数式には対応していません。')
    expr = read(tree)
    if not isinstance(expr, sp.Expr) or expr.has(sp.zoo, sp.nan):
        raise InputError('実数関数として解釈できません。')
    return expr


def _format(expr):
    return sp.sstr(expr).replace('log(', 'log(')


def _domain(expr):
    try:
        d = continuous_domain(expr, X, sp.S.Reals)
        if d is sp.S.EmptySet or d.is_empty is True:
            return sp.S.EmptySet
        # Exclude symbolic uncertain complicated sets; never guess.
        if isinstance(d, sp.ConditionSet): raise UnsupportedMath('定義域を厳密に決定できません。')
        return d
    except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
        raise UnsupportedMath('定義域を厳密に決定できません。') from exc


def _is_zero(expr):
    v = sp.simplify(expr)
    if v == 0: return True
    eq = v.equals(0)
    if eq is None: raise UnsupportedMath('式が恒等的に0か証明できません。')
    return eq is True


def _finite_real_expr(expr):
    if expr in (sp.nan, sp.zoo, sp.oo, -sp.oo) or expr.has(sp.nan, sp.zoo):
        return False
    if expr.is_real is False or expr.is_finite is False:
        return False
    # Realness of e.g. 1/sqrt(x) is undecidable globally, yet its proven
    # real continuous domain x>0 makes it a valid real-valued basis.
    # Reject explicit imaginary factors; rely on _domain() for branch limits.
    if expr.has(sp.I):
        return False
    return True


def _make(before, result=None, *, status='ok', reason='', steps=None,
          pre_domain=None, orig_domain=None, forced_note=None):
    o = Result(status=status, before=_format(before),
               latex_before=sp.latex(before), reason=reason, steps=steps or [])
    if orig_domain is None:
        try: orig_domain = _domain(before)
        except UnsupportedMath: pass
    if orig_domain is not None: o.domain_before = sp.latex(orig_domain)
    if result is not None:
        simplified = sp.simplify(result)
        o.after = _format(simplified)
        o.latex_after = sp.latex(simplified)
        try: o.domain_after = sp.latex(_domain(simplified))
        except UnsupportedMath: pass
    if forced_note:
        o.domain_changed_note=forced_note
    elif pre_domain is not None and o.domain_after is not None:
        try:
            d_after = _domain(sp.simplify(result))
            if pre_domain != d_after:
                o.domain_changed_note = (
                    f'演算途中の定義域は {sp.latex(pre_domain)}。'
                    '確定仕様113・121により後続の演算では簡約後の関数を採用し、'
                    'この制約は履歴にのみ記録します。')
        except UnsupportedMath:
            pass
    return o


def _step(note: str, eq=None):
    return {'explanation': note, 'latex': sp.latex(eq) if eq is not None else ''}


def _osc_bounds(value):
    if isinstance(value, sp.AccumBounds):
        return value.min, value.max
    return None


def _approach_zero(expr):
    d = _domain(expr)
    right = sp.Intersection(d, sp.Interval.open(0, sp.oo)).closure.contains(0)
    left = sp.Intersection(d, sp.Interval.open(-sp.oo, 0)).closure.contains(0)
    if right not in (sp.S.true, sp.S.false) or left not in (sp.S.true, sp.S.false):
        raise UnsupportedMath('0の近傍での定義域を厳密に判定できません。')
    return bool(left), bool(right)


def _limit(expr, kind):
    """Return (status, value, explanation). 0 limit honors 81/82/111."""
    if kind in ('limit_plus_inf','limit_minus_inf','limsup_plus_inf','liminf_plus_inf'):
        point = sp.oo if kind != 'limit_minus_inf' else -sp.oo
        try: value = sp.limit(expr, X, point)
        except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
            raise UnsupportedMath('極限の厳密な計算が未対応です。') from exc
        if value.has(sp.Limit): raise UnsupportedMath('極限を厳密に求められません。')
        bounds = _osc_bounds(value)
        if kind == 'limsup_plus_inf':
            value = bounds[1] if bounds else value
        elif kind == 'liminf_plus_inf':
            value = bounds[0] if bounds else value
        elif bounds:
            return 'foul', None, '通常の極限が振動により存在しないため反則です。'
        if value in (sp.nan, sp.zoo) or value.has(sp.nan, sp.zoo):
            raise UnsupportedMath('極限値が実数として確定できません。')
        if value in (sp.oo, -sp.oo): return 'vanished', None, '無限大に発散するため基底が消滅します。'
        return 'ok', value, '極限値が確定しました。'

    if kind!='limit_zero': raise InputError('未知の極限カードです。')
    left, right = _approach_zero(expr)
    if not left and not right:
        return 'foul', None, '0へ定義域内から近づけないため反則です。'
    def one(direction):
        value=sp.limit(expr, X, 0, dir=direction)
        if value.has(sp.Limit): raise UnsupportedMath('極限を厳密に求められません。')
        return value
    try:
        vl = one('-') if left else None
        vr = one('+') if right else None
    except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
        raise UnsupportedMath('0への極限を厳密に計算できません。') from exc
    if any(_osc_bounds(v) is not None for v in (vl, vr) if v is not None):
        return 'foul', None, '振動により通常の極限は存在しないため反則です。'
    if any(v in (sp.nan,sp.zoo) or v.has(sp.nan,sp.zoo) for v in (vl,vr) if v is not None):
        raise UnsupportedMath('極限値を厳密に判定できません。')
    if left and right:
        if vl in (sp.oo,-sp.oo) and vr in (sp.oo,-sp.oo):
            return 'vanished', None, '左右で無限大に発散するため（異符号でも）基底が消滅します。'
        if vl in (sp.oo,-sp.oo) or vr in (sp.oo,-sp.oo):
            # Different behavior on two sides is not explicitly decided.
            raise UnsupportedMath('片側だけが無限大の極限の裁定は未定義です。')
        if sp.simplify(vl-vr)==0: return 'ok', vl, '左右の極限が一致しました。'
        return 'foul', None, '左右の極限値が一致しないため通常の極限は存在しません。'
    value = vl if left else vr
    if value in (sp.oo,-sp.oo):
        return 'vanished', None, '定義域内からの片側極限が無限大に発散し、基底が消滅します。'
    return 'ok', value, '定義域内からの片側極限を採用しました。'


def _is_elementary(expr):
    # Elementary functions only; special functions such as erf / Si are excluded.
    for f in expr.atoms(sp.Function):
        if f.func not in _ALLOWED_RESULT_FUNCS:
            return False
    if expr.has(sp.Integral, sp.Piecewise): return False
    return True


def available_inverse_branches(expr):
    """Only explicitly verified common families; other forms are unsupported."""
    expr=sp.simplify(expr)
    if expr==X:
        return [('identity', X, sp.S.Reals, '元の定義域：実数全体')]
    if expr==X**2:
        return [
            ('nonnegative', sp.sqrt(X), sp.Interval(0,sp.oo), '元の関数を x>=0 に制限'),
            ('nonpositive', -sp.sqrt(X), sp.Interval(-sp.oo,0), '元の関数を x<=0 に制限'),
        ]
    if expr==sp.exp(X):
        return [('standard', sp.log(X), sp.S.Reals, '元の関数 exp(x) は実数全体で単調増加')]
    if expr==sp.log(X):
        return [('standard', sp.exp(X), sp.Interval.open(0,sp.oo), '元の関数 log(x) は x>0 で単調増加')]
    # sqrt(x) -> x**2 requires preserving a branch domain x>=0 despite
    # simplification; defer until explicit per-basis domain state exists.
    if expr==sp.sin(X):
        return [('principal', sp.asin(X), sp.Interval(-sp.pi/2,sp.pi/2), '元の関数 sin(x) を [-pi/2,pi/2] に制限')]
    if expr==sp.cos(X):
        return [('principal', sp.acos(X), sp.Interval(0,sp.pi), '元の関数 cos(x) を [0,pi] に制限')]
    return []


def apply_card(before_text: str, operation: str, operand: str | None = None,
               branch: str | None = None) -> Result:
    """Evaluate exactly one mathematical card action on one basis.

    This prototype gives exhaustive safety outcomes for supported expressions;
    expressions whose correctness cannot be established are 'unsupported'.
    """
    try:
        expr = parse_formula(before_text)
    except InputError as exc:
        return Result('input_error', str(before_text), reason=str(exc))
    try:
        before_domain = _domain(expr)
        if before_domain is sp.S.EmptySet:
            return _make(expr, status='foul', reason='実数の定義域が空です。',orig_domain=before_domain)
        if operation=='diff' or operation=='diff2':
            n=1 if operation=='diff' else 2
            result=sp.simplify(sp.diff(expr, X, n))
            steps=[_step('微分法を用い、指定された階数だけ微分します。',
                         sp.Eq(sp.Derivative(expr,X,n),result,evaluate=False))]
            if _is_zero(result):
                return _make(expr, result, status='vanished', reason='演算結果が0のため基底消滅。',steps=steps,orig_domain=before_domain)
            if _domain(result) is sp.S.EmptySet or not _finite_real_expr(result):
                return _make(expr, status='foul', reason='実数の定義域が空になりました。',orig_domain=before_domain)
            return _make(expr, result, steps=steps,orig_domain=before_domain)

        if operation=='integrate':
            # Correct *real* primitive for 1/x on both x<0 and x>0.
            # SymPy's principal log(x) would incorrectly exclude x<0.
            is_one_over_x = sp.simplify(expr - 1/X) == 0
            if is_one_over_x:
                result = sp.log(sp.Abs(X))
            else:
                result = sp.integrate(expr, X, risch=True)
            if result.has(sp.Integral):
                # Some elementary cases require alternative integrators.
                result = sp.integrate(expr, X)
            if not _is_elementary(result):
                raise UnsupportedMath('積分結果が初等関数で表せると証明できません。')
            if not is_one_over_x and sp.simplify(sp.diff(result,X)-expr)!=0:
                raise UnsupportedMath('原始関数の微分検算が一致しません。')
            steps=[_step('原始関数を求め、微分して元の関数に戻ることを確認します。',
                         sp.Eq(sp.Derivative(result,X),expr,evaluate=False)),
                   _step('積分定数は確定仕様48により0とします。')]
            return _make(expr,result,status='vanished' if _is_zero(result) else 'ok',
                         reason='積分結果が0です。' if _is_zero(result) else '',steps=steps,orig_domain=before_domain)

        if operation in ('mul','div'):
            if operand is None:
                return _make(expr, status='input_error', reason='演算に必要な関数カードがありません。')
            val=parse_formula(operand)
            if operation=='div' and _is_zero(val):
                return _make(expr,status='foul',reason='明示的な÷0は反則です（117）。')
            raw=sp.Mul(expr, val if operation=='mul' else sp.Pow(val,-1,evaluate=False), evaluate=False)
            try: pre_domain=_domain(raw)
            except UnsupportedMath: pre_domain=None
            result=sp.simplify(raw)
            if _is_zero(result):
                return _make(expr, result, status='vanished',reason='結果が0のため基底消滅。',
                             steps=[_step('乗除算を行い、最終式を簡約します。',sp.Eq(sp.Symbol('R'), result))],
                             pre_domain=pre_domain,orig_domain=before_domain)
            if _domain(result) is sp.S.EmptySet or not _finite_real_expr(result):
                return _make(expr,status='foul',reason='実数の定義域が空です。',orig_domain=before_domain)
            return _make(expr,result,steps=[_step('演算カードと関数カードを順番に作用させます。',sp.Eq(sp.Symbol('R'),result))],
                         pre_domain=pre_domain,orig_domain=before_domain)

        if operation in ('limit_plus_inf','limit_minus_inf','limit_zero','limsup_plus_inf','liminf_plus_inf'):
            status, value, note=_limit(expr, operation)
            if status!='ok':
                return _make(expr,status=status,reason=note,orig_domain=before_domain,
                             steps=[_step('定義域と極限値を検証します。')])
            return _make(expr,value,status='vanished' if _is_zero(value) else 'ok',
                         reason='極限が0のため基底消滅。' if _is_zero(value) else note,
                         steps=[_step('定義域内からの極限を厳密に求めます。',sp.Eq(sp.Symbol('L'),value))],
                         orig_domain=before_domain)

        if operation in ('sqrt','log'):
            if operation=='sqrt':
                result=sp.sqrt(expr)
                rule='実数となる範囲で平方根を計算します。'
            else:
                result=sp.log(expr)
                rule='自然対数 log（底e）を作用させます。'
            # SymPy can rewrite sqrt(-exp(x)) as I*exp(x/2). The latter is
            # continuous over R but never real: complex is NOT a valid basis.
            if result.is_real is False or result.has(sp.I):
                return _make(expr,status='foul',reason='演算後の実数定義域が空です。',orig_domain=before_domain)
            d=_domain(result)
            if d is sp.S.EmptySet:
                return _make(expr,status='foul',reason='演算後の実数定義域が空です。',orig_domain=before_domain)
            if _is_zero(result):
                return _make(expr,0,status='vanished',reason='結果が0のため基底消滅。',
                             orig_domain=before_domain,steps=[_step(rule)])
            return _make(expr,result,orig_domain=before_domain,steps=[_step(rule)])

        if operation=='inverse':
            options=available_inverse_branches(expr)
            if not options:
                raise UnsupportedMath('逆関数の有効な枝を厳密に列挙できません。')
            if branch is None:
                r=_make(expr,status='input_error',reason='逆関数の枝を選んでください。',orig_domain=before_domain)
                r.branch_options=[x[0] for x in options]
                return r
            for label, inverse_expr, orig_restrict, desc in options:
                if label==branch:
                    if _domain(inverse_expr) is sp.S.EmptySet:
                        return _make(expr,status='foul',reason='逆関数の実数定義域が空です。')
                    return _make(expr,inverse_expr,reason=desc,
                                 steps=[_step('逆関数となる単調な枝を選択します。'),_step(desc)],
                                 orig_domain=before_domain)
            return _make(expr,status='input_error',reason='選択された枝は候補にありません。',orig_domain=before_domain)

        return _make(expr,status='input_error',reason='未知の演算カードです。')
    except InputError as exc:
        return _make(expr,status='input_error',reason=str(exc))
    except UnsupportedMath as exc:
        return _make(expr,status='unsupported',reason=str(exc))
    except (NotImplementedError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        return _make(expr,status='unsupported',reason='数学的な結果を厳密に確認できません。')


def apply_mixed_chain(before_text: str, cards: list[tuple[str,str]]) -> Result:
    """Apply ×/÷ paired with function cards, in order. Rules 94,96,97,109.

    Each pair is ("mul" or "div", function-card expression).  Input examples:
        [("mul", "x"), ("div", "exp(x)")]
    Explicit ÷0 always foul even if a later factor would simplify it away.
    """
    try:
        expr=parse_formula(before_text)
        if not cards or any(op not in ('mul','div') for op,_ in cards):
            return _make(expr,status='input_error',reason='乗除算のカードの組み合わせが不正です。')
        raw=expr
        for op,card in cards:
            val=parse_formula(card)
            if op=='div' and _is_zero(val):
                return _make(expr,status='foul',reason='明示的な÷0は反則です。')
            raw=sp.Mul(raw,val if op=='mul' else sp.Pow(val,-1,evaluate=False),evaluate=False)
        try: pre_d=_domain(raw)
        except UnsupportedMath: pre_d=None
        end=sp.simplify(raw)
        if _domain(end) is sp.S.EmptySet or not _finite_real_expr(end):
            return _make(expr,status='foul',reason='最終式が実数関数として定義できません。')
        return _make(expr,end,status='vanished' if _is_zero(end) else 'ok',
                     reason='最終式が0のため消滅。' if _is_zero(end) else '',
                     steps=[_step('選択順に左から乗除算を作用させ、最終式を簡約します。')],
                     pre_domain=pre_d)
    except InputError as exc:
        return Result('input_error',str(before_text),reason=str(exc))
    except UnsupportedMath as exc:
        return Result('unsupported',str(before_text),reason=str(exc))
    except (ValueError, TypeError, NotImplementedError,RecursionError) as exc:
        return Result('unsupported',str(before_text),reason='最終式を厳密に検証できません。')


def proportional_on_shared_domain(left_expr, right_expr) -> str:
    """'yes','no','unsupported': exact symbolic proportionality, no numeric guesses.

    Assumes two live nonzero bases; their domains should be nonempty.
    """
    try:
        a=parse_formula(left_expr) if isinstance(left_expr,str) else left_expr
        b=parse_formula(right_expr) if isinstance(right_expr,str) else right_expr
        common=_domain(a).intersect(_domain(b))
        if common is sp.S.EmptySet or common.is_empty is True:
            return 'no'
        # Need an interval, not a coincidental match on one point.
        if not common.has(sp.Interval) and not isinstance(common,sp.Interval) and common is not sp.S.Reals:
            return 'unsupported'
        if _is_zero(a) or _is_zero(b): return 'no'
        ratio=sp.simplify(sp.cancel(a/b))
        if ratio.free_symbols:
            dr=sp.simplify(sp.diff(ratio,X))
            if dr==0 or dr.equals(0) is True:
                ratio=sp.simplify(ratio)
            elif dr.equals(0) is False:
                return 'no'
            else: return 'unsupported'
        if ratio.free_symbols:
            return 'unsupported'
        if ratio.is_finite is not True or ratio.is_real is not True or _is_zero(ratio):
            return 'unsupported'
        proof=sp.simplify(a-ratio*b)
        if proof==0 or proof.equals(0) is True: return 'yes'
        if proof.equals(0) is False: return 'no'
        return 'unsupported'
    except (UnsupportedMath,InputError,ValueError,TypeError,NotImplementedError):
        return 'unsupported'


def apply_whole_board(bases: list[tuple[int,str]], order: int) -> dict[str, Any]:
    """Rule 92: all bases differentiated from originals; then delete zero/duplicates.

    91/107: all-or-nothing if ANY result is foul/unsupported.  New bases retain
    existing unique card numbers.  No deck or hand mutation occurs here.
    """
    if order not in (1,2): return {'status':'input_error','reason':'全体演算は1階か2階です。'}
    if len({n for n,_ in bases})!=len(bases):
        return {'status':'input_error','reason':'基底番号が重複しています。'}
    results=[]
    for no,expression in bases:
        res=apply_card(expression,'diff' if order==1 else 'diff2')
        results.append((no,res))
    unsupported=[r for _,r in results if r.status=='unsupported']
    if unsupported: return {'status':'unsupported','reason':'少なくとも1基底が計算未対応。全体演算を取り消します。'}
    fouls=[r for _,r in results if r.status in ('foul','input_error')]
    if fouls: return {'status':'foul','reason':'全体演算に反則が含まれています。'}
    kept=[]; removed=[]
    for no,r in sorted(results,key=lambda z:z[0]):
        if r.status=='vanished':
            removed.append({'id':no,'reason':'0'})
            continue
        if r.after is None:
            return {'status':'unsupported','reason':'結果が確定できません。'}
        dup=False
        for older_no,older_expr in kept:
            dep=proportional_on_shared_domain(r.after,older_expr)
            if dep=='unsupported':
                return {'status':'unsupported','reason':'線形従属の証明ができません。全体演算を取り消します。'}
            if dep=='yes':
                removed.append({'id':no,'reason':f'No.{older_no}に比例'})
                dup=True
                break
        if not dup:kept.append((no,r.after))
    return {'status':'ok','bases':[{'id':i,'expression':s} for i,s in kept],
            'removed':removed,'calculations':[{'id':n,**r.to_dict()} for n,r in results]}
