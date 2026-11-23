#!/usr/bin/env python3
"""Apply NABLA ARENA concise answer-log UI changes to the 2026-11-23 prototype.

The script is strict, atomic at the patch-generation stage and idempotent.
It writes nothing until every source-file anchor is validated.  It never edits
nabla_math.py, nabla_game.py, cards.py, CPU code, or the production branch.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

MARK = 'NABLA-ANSWER-LOG-V2-2026-11-23'
ROOT = Path(__file__).resolve().parent

ANSWER_GENERATOR = r'''

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
'''


def single_replace(src: str, old: str, new: str, where: str) -> str:
    n = src.count(old)
    if n != 1:
        raise RuntimeError(f'{where}: expected exactly one matching anchor; found {n}')
    return src.replace(old, new, 1)


def transform():
    filenames = ['nabla_steps.py', 'server.py', 'app.js', 'nabla_upgrade_ui.js']
    original = {name: (ROOT / name).read_text(encoding='utf-8') for name in filenames}
    flags = {name: MARK in content for name, content in original.items()}
    if all(flags.values()):
        print('Already patched: all four files have the V2 marker')
        return False
    if any(flags.values()):
        raise RuntimeError('Partial patch detected: some files have V2 marker. No changes made.')

    changed = dict(original)
    changed['nabla_steps.py'] = original['nabla_steps.py'] + ANSWER_GENERATOR

    # Server: decorate copies of events for normal, online, and practice views.
    server = original['server.py']
    server = single_replace(server,
        'from nabla_steps import explain_event\n',
        'from nabla_steps import explain_event, answer_mathml\n', 'server import')
    pattern = re.compile(r"(?P<indent>^[ ]*)for calc in (?P<ev>item|event)\.get\('calculations',\s*\[\]\):\n", re.M)
    hits = list(pattern.finditer(server))
    if len(hits) != 3 or [m.group('ev') for m in hits] != ['item', 'item', 'event']:
        raise RuntimeError(f'server: unexpected calculation loops ({len(hits)})')
    def decorate(m):
        ind, ev = m.group('indent'), m.group('ev')
        return (m.group(0) + ind + '    calc[\'answer_mathml\'] = answer_mathml('\
                'calc.get(\'before\'), calc.get(\'after\'), '\
                f'{ev}.get(\'used_cards\'))\n')
    server = pattern.sub(decorate, server)
    changed['server.py'] = server + '\n# ' + MARK + '\n'

    app = original['app.js']
    start = '  if(calc.before!==undefined&&calc.before!==null)html+=`<div class="log-label">演算前</div><div class="math-line">${math(calc.before,calc.before_mathml)}</div>`;\n'
    middle = '  for(const step of calc.steps||[]){if(step.explanation)html+=`<div class="event-text">${enc(step.explanation)}</div>`;}\n'
    end = '  if(calc.after!==undefined&&calc.after!==null)html+=`<div class="log-label">演算後</div><div class="math-line">${math(calc.after,calc.after_mathml)}</div>`;\n'
    replacement = '''  // The server formats the committed operation as one concise equation.
  // Do not recompute the action or repeat verbose narration in the main log.
  if(calc.answer_mathml)html+=`<div class="math-line nabla-answer-line">${calc.answer_mathml}</div>`;
  else if(calc.after!==undefined&&calc.after!==null)html+=`<div class="math-line">${math(calc.after,calc.after_mathml)}</div>`;
  else if(calc.before!==undefined&&calc.before!==null)html+=`<div class="math-line">${math(calc.before,calc.before_mathml)}</div>`;
'''
    app = single_replace(app, start + middle + end, replacement, 'app calculation renderer')
    changed['app.js'] = app + '\n// ' + MARK + '\n'

    upgrade = original['nabla_upgrade_ui.js']
    # A new storage key ensures old "details on" preferences do not re-enable
    # verbose explanations automatically after upgrading. Optional opt-in stays.
    upgrade = single_replace(upgrade,
        "const flag = 'nabla_educational_steps';", "const flag = 'nabla_answer_extra_details_v2';", 'settings key')
    upgrade = single_replace(upgrade,
        "let stepsOn = localStorage.getItem(flag)!=='off';", "let stepsOn = localStorage.getItem(flag)==='on';", 'details default')
    upgrade = single_replace(upgrade,
        '途中計算：${stepsOn?', '追加の詳しい解説：${stepsOn?', 'settings label')
    old = '''       if(calc.before!=null)content+=`<div class="practice-math-label">演算前</div><div class="practice-math-line">${practiceMath(calc.before,calc.before_mathml)}</div>`;
       if(calc.after!=null)content+=`<div class="practice-math-label">演算後</div><div class="practice-math-line">${practiceMath(calc.after,calc.after_mathml)}</div>`;
'''
    new = '''       if(calc.answer_mathml)content+=`<div class="practice-math-line nabla-answer-line">${calc.answer_mathml}</div>`;
       else if(calc.after!=null)content+=`<div class="practice-math-line">${practiceMath(calc.after,calc.after_mathml)}</div>`;
       else if(calc.before!=null)content+=`<div class="practice-math-line">${practiceMath(calc.before,calc.before_mathml)}</div>`;
'''
    upgrade = single_replace(upgrade, old, new, 'practice calculation renderer')
    changed['nabla_upgrade_ui.js'] = upgrade + '\n// ' + MARK + '\n'

    # Preflight compilation of all modified Python files BEFORE any writing.
    for name in ('nabla_steps.py', 'server.py'):
        compile(changed[name], name, 'exec')
    for name in filenames:
        (ROOT / name).write_text(changed[name], encoding='utf-8')
    print('Patched:', ', '.join(filenames))
    return True


# NABLA-LIMIT-ANSWER-V3-2026-11-23: read-only display for divergent limits.
# No rule, CPU, or state transition is modified by this patch.

LIMIT_V3_MARK = 'NABLA-LIMIT-ANSWER-V3-2026-11-23'

LIMIT_V3_GENERATOR = r'''

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
'''


def transform_v3():
    targets = ['nabla_steps.py', 'server.py']
    original = {name: (ROOT / name).read_text(encoding='utf-8') for name in targets}
    flags = {name: LIMIT_V3_MARK in original[name] for name in targets}
    if all(flags.values()):
        print('Already patched: divergent-limit display V3')
        return False
    if any(flags.values()):
        raise RuntimeError('Partial V3 patch detected; no changes written.')
    if not all(MARK in original[name] for name in targets):
        raise RuntimeError('V2 answer-log code is required; no changes written.')

    changed = dict(original)
    changed['nabla_steps.py'] = original['nabla_steps.py'] + LIMIT_V3_GENERATOR
    server = original['server.py']
    server = single_replace(server,
        'from nabla_steps import explain_event, answer_mathml\n',
        'from nabla_steps import explain_event, answer_mathml, answer_infinite_limit_mathml\n',
        'V3 server import')
    for owner, count in [('item', 2), ('event', 1)]:
        old = ("calc['answer_mathml'] = answer_mathml(calc.get('before'), "
               "calc.get('after'), " + owner + ".get('used_cards'))")
        new = ("calc['answer_mathml'] = (answer_mathml(calc.get('before'), "
               "calc.get('after'), " + owner + ".get('used_cards')) or "
               "answer_infinite_limit_mathml(calc, " + owner + ".get('used_cards')))")
        if server.count(old) != count:
            raise RuntimeError('V3 server decorator expected ' + str(count) +
                               ' occurrences for ' + owner)
        server = server.replace(old, new)
    changed['server.py'] = server + '\n# ' + LIMIT_V3_MARK + '\n'
    for name in targets:
        compile(changed[name], name, 'exec')
    for name in targets:
        (ROOT / name).write_text(changed[name], encoding='utf-8')
    print('Patched divergent-limit display:', ', '.join(targets))
    return True


if __name__ == '__main__':
    try:
        transform()
        transform_v3()
    except Exception as exc:
        print('Patch NOT applied:', exc, file=sys.stderr)
        sys.exit(1)
