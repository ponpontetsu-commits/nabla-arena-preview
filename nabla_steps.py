
# NABLA-MATH-PRESENTATION-2026-11
"""Verified educational calculations for NABLA ARENA.

This module only explains moves which the authoritative engine has already
committed. It never changes statuses, domains, winners or basis values.
"""
from __future__ import annotations

from copy import deepcopy
import sympy as sp

X = sp.Symbol('x', real=True)


def _parse(text):
    from nabla_math import parse_formula
    return parse_formula(str(text))


def _line(title, eq=None):
    result = {'explanation': title, 'latex': '', 'mathml': ''}
    if eq is not None:
        result['latex'] = sp.latex(eq)
        try:
            result['mathml'] = '<math xmlns="http://www.w3.org/1998/Math/MathML">' + sp.mathml(eq, printer='presentation') + '</math>'
        except (ValueError, TypeError, NotImplementedError, AttributeError):
            pass
    return result


def _eq(left, right):
    return sp.Eq(left, right, evaluate=False)


def _verified(left, right):
    """Conservatively verify algebraic equality without sampling."""
    try:
        delta = sp.simplify(left - right)
        return delta == 0 or delta.equals(0) is True
    except (ValueError, TypeError, NotImplementedError, RecursionError):
        return False


def _differentiation_steps(expr, after, order):
    result = []
    current = expr
    for i in range(order):
        derivative = sp.diff(current, X)
        label = f'{i+1}階微分を求めます。'
        if current.is_Mul and len(current.args) == 2:
            u, v = current.args
            expanded = sp.diff(u, X) * v + u * sp.diff(v, X)
            if _verified(derivative, expanded):
                result.append(_line('積の微分法：(uv)\' = u\'v + uv\' を使用します。', _eq(sp.Derivative(current, X, evaluate=False), expanded)))
        elif current.is_Add:
            expanded = sp.Add(*(sp.diff(term, X) for term in current.args))
            if _verified(derivative, expanded):
                result.append(_line('和・差の各項をそれぞれ微分します。', _eq(sp.Derivative(current, X, evaluate=False), expanded)))
        elif current.is_Pow and current.base == X and current.exp.is_number:
            result.append(_line('べき関数の微分公式を使用します。', _eq(sp.Derivative(current, X, evaluate=False), derivative)))
        result.append(_line(label, _eq(sp.Derivative(current, X, evaluate=False), derivative)))
        current = sp.simplify(derivative)
    if _verified(current, after):
        result.append(_line('整理した演算結果です。', _eq(sp.Derivative(expr, (X, order), evaluate=False), after)))
    return result


# NABLA-EXPLAIN-PROTOTYPE-2026-11-22
def _elementary_integration_steps(expr, after):
    """Only add explanations verified by differentiation and answer equality."""
    options = []
    if expr == 0:
        options.append(('0 の原始関数は定数です。ゲームでは積分定数を 0 とします。', sp.Integer(0)))
    elif expr == 1:
        options.append(('定数 1 を積分すると x です。', X))
    elif expr == X:
        options.append(('べき関数の積分公式を適用します。', X**2 / 2))
    elif expr.is_Pow and expr.base == X and expr.exp.is_number and expr.exp != -1:
        options.append(('べき関数の積分公式を適用します（指数が -1 以外）。',
                        X**(expr.exp + 1) / (expr.exp + 1)))
    elif expr == 1 / X:
        options.append(('1/x の原始関数は log|x| です（x ≠ 0）。', sp.log(sp.Abs(X))))
    elif expr == sp.sin(X):
        options.append(('sin(x) の原始関数は -cos(x) です。', -sp.cos(X)))
    elif expr == sp.cos(X):
        options.append(('cos(x) の原始関数は sin(x) です。', sp.sin(X)))
    elif expr == sp.exp(X):
        options.append(('e^x の原始関数は e^x です。', sp.exp(X)))
    elif expr.is_Mul:
        constant, rest = expr.as_independent(X, as_Add=False)
        if constant != 1 and constant.is_number:
            try:
                primitive = sp.integrate(rest, X)
                if not primitive.has(sp.Integral):
                    options.append(('定数倍を積分の外に出します。', constant * primitive))
            except (ValueError, TypeError, NotImplementedError):
                pass
    steps = []
    for label, primitive in options:
        if _verified(sp.diff(primitive, X), expr) and _verified(primitive, after):
            steps.append(_line(label, _eq(sp.Integral(expr, X), primitive)))
    return steps


def _integration_steps(expr, after):
    # Verify against the authoritative answer before explaining the primitive.
    if not _verified(sp.diff(after, X), expr):
        return [_line('原始関数の追加説明を厳密に確認できません。')]
    steps = _elementary_integration_steps(expr, after)
    if expr.is_Add:
        steps.append(_line('積分の線形性を使い、項ごとに積分します。',
                           _eq(sp.Integral(expr, X), sp.Add(*(sp.Integral(t, X) for t in expr.args)))))
    # Repeated integration by parts for a polynomial times sin(x) or cos(x).
    # Every intermediate equation is derivative-verified independently.
    rem=expr
    accum=sp.Integer(0)
    for iteration in range(5):
        trig=next((f for f in (sp.sin(X),sp.cos(X)) if rem.has(f)),None)
        if trig is None:
            break
        u=sp.cancel(rem/trig)
        try:
            degree=sp.degree(u,X)
        except (sp.PolynomialError,TypeError):
            break
        if degree is None or degree<=0 or degree>8:
            break
        v=sp.integrate(trig,X)
        next_accum=sp.expand(accum+u*v)
        next_rem=sp.expand(-sp.diff(u,X)*v)
        if not _verified(sp.diff(next_accum,X)+next_rem,expr):
            break
        accum,rem=next_accum,next_rem
        expression=accum+sp.Integral(rem,X)
        steps.append(_line('部分積分法を用いて積分を一段階簡単にします。',
                           _eq(sp.Integral(expr,X),expression)))
    if steps and not rem.has(sp.Integral):
        primitive=sp.integrate(rem,X)
        if not primitive.has(sp.Integral):
            combined=sp.simplify(accum+primitive)
            if _verified(sp.diff(combined,X),expr) and _verified(combined,after):
                steps.append(_line('残った積分を計算して式を整理します。',
                                   _eq(sp.Integral(expr,X),combined)))
    steps.append(_line('原始関数を求めます。',_eq(sp.Integral(expr,X),after)))
    steps.append(_line('通常の不定積分では積分定数 +C を付けます。ゲーム上は C=0 とします。'))
    return steps


def _operation_name(card):
    return {'diff': 'diff', 'diff2': 'diff2', 'all_diff': 'diff',
            'all_diff2': 'diff2', 'integrate':'integrate',
            'mul':'mul', 'div':'div', 'sqrt':'sqrt', 'log':'log',
            'inverse':'inverse', 'limit_plus_inf':'limit',
            'limit_minus_inf':'limit', 'limit_zero':'limit',
            'limsup_plus_inf':'limit', 'liminf_plus_inf':'limit'}.get(card,card)


def _mixed_operation_steps(expr, after, codes):
    """Exact stepwise multiplication/division, verified against final result."""
    from nabla_game import FUNCTIONS
    if not codes or len(codes)%2:
        return [_line('指定順に左から乗算・除算を行いました。')]
    current=expr
    lines=[]
    for i in range(0,len(codes),2):
        op, factor_code = codes[i:i+2]
        if op not in ('mul','div') or factor_code not in FUNCTIONS:
            return [_line('指定順に左から乗算・除算を行いました。')]
        factor=_parse(FUNCTIONS[factor_code])
        if op=='div' and factor == 0:
            return [_line('0による除算は認められません。')]
        raw=sp.Mul(current,factor if op=='mul' else sp.Pow(factor,-1,evaluate=False),evaluate=False)
        simplified=sp.simplify(raw)
        if not _verified(raw,simplified):
            return [_line('演算過程を厳密に展開できません。確定済みの演算結果を確認してください。')]
        lines.append(_line('乗算します。' if op=='mul' else '除算します。定義域の制約にも注意します。',_eq(raw,simplified)))
        current=simplified
    if _verified(current,after):
        lines.append(_line('最終結果を整理します。',_eq(current,after)))
    else:
        lines.append(_line('中間結果と確定済みの結果の一致を確認できません。'))
    return lines


def _friendly_math_text(value):
    """Avoid printing raw LaTeX commands as prose; leave math data untouched."""
    text=str(value)
    for original,replacement in (
        (r'\mathbb{R}','ℝ'), (r'\infty','∞'), (r'\cup',' ∪ '),
        (r'\cap',' ∩ '), (r'\left',''), (r'\right',''),
        (r'\geq','≥'), (r'\leq','≤'), (r'\neq','≠'),
        (r'\{','{'), (r'\}','}'), (r'\pi','π'),
    ):
        text=text.replace(original,replacement)
    return text

def _derive(before, after, operation, event):
    items=[]
    try:
        expr=_parse(before)
        result=_parse(after) if after is not None else None
        if result is not None and operation in ('diff','diff2'):
            items.extend(_differentiation_steps(expr,result,2 if operation=='diff2' else 1))
        elif result is not None and operation == 'integrate':
            items.extend(_integration_steps(expr,result))
        elif result is not None and operation in ('mul','div'):
            items.extend(_mixed_operation_steps(expr,result,event.get('used_cards') or []))
        elif operation == 'limit':
            items.append(_line('元の定義域から接近可能な方向と極限の存在を判定します。'))
            if result is not None:
                items.append(_line('極限の演算結果です。',_eq(sp.Symbol('L'),result)))
        elif operation == 'sqrt' and result is not None:
            if expr == X**2:
                items.append(_line('実数上で √(x²)=|x| です。',_eq(sp.sqrt(X**2),sp.Abs(X))))
            items.append(_line('平方根の実数定義域を確認します。',_eq(sp.sqrt(expr),result)))
        elif operation == 'log' and result is not None:
            items.append(_line('log は自然対数です。真数が正となる範囲を確認します。'))
            if sp.log(expr) != result:
                items.append(_line('自然対数を整理します。',_eq(sp.log(expr),result)))
        elif operation == 'inverse' and result is not None:
            items.append(_line('元の関数の定義域と逆関数の枝を確認します。'))
            composed=sp.simplify(expr.subs(X,result))
            if _verified(composed, X):
                items.append(_line('元の関数と逆関数の合成を確認します。',_eq(composed,X)))
            else:
                items.append(_line('合成による確認には枝・定義域の条件が必要です。'))
        elif result is not None:
            items.append(_line('厳密な結果を表示します。',_eq(sp.Symbol('R'),result)))
    except (ValueError, TypeError, NotImplementedError, RecursionError, OverflowError):
        items.append(_line('詳細な式変形は厳密に生成できません。ゲームの判定結果は変更しません。'))
    return items[:16]


def explain_event(event):
    """Return serializable explanation payload for exactly one history event."""
    if not isinstance(event, dict):
        return {'calculations': []}
    cards=event.get('used_cards') or []
    operation=_operation_name(cards[0]) if cards else None
    result=[]
    for calc in event.get('calculations') or []:
        before=calc.get('before')
        after=calc.get('after')
        supplemental=_derive(before,after,operation,event) if before is not None else []
        steps=supplemental or [_line('計算過程を厳密に展開できないため、既存の判定結果を表示します。')]
        domain=calc.get('domain_before')
        if domain:
            steps.insert(0, _line('演算前の定義域：'+_friendly_math_text(domain)))
        if calc.get('domain_after') and calc.get('domain_after') != domain:
            steps.append(_line('演算後の定義域：'+_friendly_math_text(calc['domain_after'])))
        if calc.get('domain_changed_note'):
            steps.append(_line(_friendly_math_text(calc['domain_changed_note'])))
        if calc.get('reason'):
            steps.append(_line('判定：'+str(calc['reason'])))
        result.append({'id':calc.get('id'), 'steps':steps[:20]})
    return {'event_id':event.get('id'), 'calculations':result}


# NABLA-ANSWER-LOG-V2-2026-11-23
# Short display-only expressions derived from committed (authoritative) outcomes.
# Preserve explain_event() and its verified educational detail for optional viewing.
from functools import lru_cache as _answer_lru_cache
import html as _answer_html


def _answer_piece(expr):
    return _answer_html.unescape(sp.mathml(expr, printer='presentation'))


def _answer_xml(parts):
    # Each piece comes from SymPy's MathML printer or fixed XML tokens.
    return ('<math xmlns="http://www.w3.org/1998/Math/MathML">'
            '<mrow>' + ''.join(parts) + '</mrow></math>')


def _answer_parts(expr, result, code, cards):
    """Return MathML pieces; never determine or change the game result."""
    m = _answer_piece
    eq = '<mo>=</mo>'
    if code in ('diff', 'all_diff', 'all_diff2'):
        order = 2 if code == 'all_diff2' else 1
        left = sp.Derivative(expr, (X, order), evaluate=False)
        parts = [m(left)]
        if order == 1 and expr.is_Mul and sp.count_ops(expr) <= 20:
            # Only include a useful product-rule intermediate if exactly verified.
            expanded = sp.expand(sp.diff(expr, X))
            if (expanded != result and len(str(expanded)) <= 160
                    and _verified(expanded, result)):
                parts.extend([eq, m(expanded)])
        return parts + [eq, m(result)]
    if code == 'integrate':
        parts = [m(sp.Integral(expr, X))]
        # One or two genuine integration-by-parts equalities for nontrivial cases.
        if expr.is_Mul and sp.count_ops(expr) <= 25:
            remaining, accumulated = expr, sp.S.Zero
            for _ in range(2):
                trig = next((t for t in (sp.sin(X), sp.cos(X)) if remaining.has(t)), None)
                if trig is None:
                    break
                u = sp.cancel(remaining / trig)
                if not u.is_polynomial(X):
                    break
                degree = sp.degree(u, X)
                if degree is None or not 1 <= degree <= 3:
                    break
                v = sp.integrate(trig, X)
                accumulated = sp.expand(accumulated + u * v)
                remaining = sp.expand(-sp.diff(u, X) * v)
                partial = accumulated + sp.Integral(remaining, X)
                if len(str(partial)) > 165 or not _verified(sp.diff(partial, X), expr):
                    break
                parts.extend([eq, m(partial)])
        return parts + [eq, m(result)]
    if code in ('mul', 'div'):
        from nabla_game import FUNCTIONS
        if len(cards) % 2 or not cards:
            return [m(result)]
        factors = []
        raw = expr
        for i in range(0, len(cards), 2):
            operation, function = cards[i:i+2]
            if operation not in ('mul', 'div') or function not in FUNCTIONS:
                return [m(result)]
            factor = _parse(FUNCTIONS[function])
            if operation == 'div' and factor == 0:
                return [m(result)]
            raw = sp.Mul(raw, factor if operation == 'mul' else
                         sp.Pow(factor, -1, evaluate=False), evaluate=False)
            factors.append((operation, factor))
        if not _verified(raw, result):
            return [m(result)]
        parts = [('<mfenced>' + m(expr) + '</mfenced>') if expr.is_Add else m(expr)]
        for operation, factor in factors:
            parts.append('<mo>×</mo>' if operation == 'mul' else '<mo>÷</mo>')
            parts.append(m(factor))
        return parts + [eq, m(result)]
    if code in ('limit_zero', 'limit_plus_inf', 'limit_minus_inf',
                'limsup_plus_inf', 'liminf_plus_inf'):
        point = sp.S.Zero if code == 'limit_zero' else (
            -sp.oo if code == 'limit_minus_inf' else sp.oo)
        if code in ('limsup_plus_inf', 'liminf_plus_inf'):
            symbol = 'limsup' if code == 'limsup_plus_inf' else 'liminf'
            left = ('<munder><mi>' + symbol + '</mi><mrow><mi>x</mi>'
                    '<mo>→</mo>' + m(point) + '</mrow></munder>' + m(expr))
            return [left, eq, m(result)]
        return [m(sp.Limit(expr, X, point)), eq, m(result)]
    if code == 'sqrt':
        return [m(sp.Pow(expr, sp.Rational(1, 2), evaluate=False)), eq, m(result)]
    if code == 'log':
        return [m(sp.log(expr, evaluate=False)), eq, m(result)]
    if code == 'inverse':
        # Two separate assertions (not the invalid equation f(x)=f^-1(x)).
        return (['<mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo>', eq, m(expr),
                 '<mspace width="1em"/>',
                 '<msup><mi>f</mi><mrow><mo>−</mo><mn>1</mn></mrow></msup>'
                 '<mo>(</mo><mi>x</mi><mo>)</mo>', eq, m(result)])
    return [m(expr), '<mo>→</mo>', m(result)]


@_answer_lru_cache(maxsize=512)
def _answer_mathml_cached(before, after, cards):
    try:
        if before is None or after is None or not cards:
            return ''
        expr, result = _parse(before), _parse(after)
        code = cards[0]
        # A sequence of one-type differentiation cards yields one calculation
        # per card; use the original derivative operator at each step.
        if code == 'diff':
            code = 'diff'
        pieces = _answer_parts(expr, result, code, cards)
        return _answer_xml(pieces)
    except (ValueError, TypeError, AttributeError, NotImplementedError,
            RecursionError, OverflowError, ZeroDivisionError):
        # The UI always has the authoritative after value as its fallback.
        return ''


def answer_mathml(before, after, used_cards):
    """Answer-line MathML for one confirmed calculation; display only.

    No action validation, board changes, or new result adjudication occurs here.
    A blank result tells the UI to render its saved authoritative answer.
    """
    return _answer_mathml_cached(before, after, tuple(used_cards or ()))


# NABLA-LIMIT-ANSWER-V3-2026-11-23
# Render verified divergent-limit event data without changing the math outcome.
def answer_infinite_limit_mathml(calc, used_cards):
    """Only for an already committed, infinite-limit basis disappearance.

    A divergent limit's authoritative after is None, so the regular answer
    formatter cannot construct a finite equality. Recalculate ONLY the signed
    display value and keep the committed vanished status as the prerequisite.
    The game engine, board, and event data are not mutated here.
    """
    try:
        if not isinstance(calc, dict) or calc.get('status') != 'vanished':
            return ''
        if calc.get('after') is not None or not isinstance(calc.get('before'), str):
            return ''
        if not isinstance(used_cards, (list, tuple)) or len(used_cards) != 1:
            return ''
        code = used_cards[0]
        if code not in ('limit_plus_inf', 'limit_minus_inf', 'limit_zero',
                        'limsup_plus_inf', 'liminf_plus_inf'):
            return ''
        if '無限大' not in str(calc.get('reason') or '') and '発散' not in str(calc.get('reason') or ''):
            return ''
        expr = _parse(calc['before'])
        if sp.count_ops(expr) > 40:
            return ''
        if code != 'limit_zero':
            point = -sp.oo if code == 'limit_minus_inf' else sp.oo
            val = sp.limit(expr, X, point)
            if code in ('limsup_plus_inf', 'liminf_plus_inf'):
                from nabla_math import _osc_bounds
                bounds = _osc_bounds(val)
                if bounds is not None:
                    val = bounds[1] if code == 'limsup_plus_inf' else bounds[0]
            if val not in (sp.oo, -sp.oo):
                return ''
            return _answer_xml(_answer_parts(expr, val, code, used_cards))

        from nabla_math import _approach_zero
        can_left, can_right = _approach_zero(expr)
        if not can_left and not can_right:
            return ''
        values = {}
        if can_left:
            values['-'] = sp.limit(expr, X, sp.S.Zero, dir='-')
        if can_right:
            values['+'] = sp.limit(expr, X, sp.S.Zero, dir='+')
        if not values or any(val not in (sp.oo, -sp.oo) for val in values.values()):
            return ''
        if len(values) == 2 and values['-'] == values['+']:
            # Both sides have the SAME infinite signed limit.
            return _answer_xml(_answer_parts(expr, values['+'], code, used_cards))

        # Different signed limits cannot be written as one ordinary limit.
        # A single accessible side must also be labelled explicitly.
        pieces = []
        for side in ('-', '+'):
            if side not in values:
                continue
            sign = '−' if side == '-' else '+'
            zero_side = '<msup><mn>0</mn><mo>' + sign + '</mo></msup>'
            lhs = ('<munder><mi>lim</mi><mrow><mi>x</mi><mo>→</mo>' +
                   zero_side + '</mrow></munder>' + _answer_piece(expr))
            if pieces:
                pieces.append('<mspace width="1em"/>')
            pieces.extend([lhs, '<mo>=</mo>', _answer_piece(values[side])])
        return _answer_xml(pieces)
    except Exception:
        # Display-only failure must never prevent a legal match from rendering.
        return ''
