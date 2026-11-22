"""NABLA ARENA precision-first performance upgrade — combined release.

For the existing feature branch 'nabla-arena-update' ONLY.
Upload THIS file as nabla_upgrade.py using GitHub's Upload files page on
that branch. The existing Actions workflow executes it and validates changes.
Never upload to main; the stable game must remain untouched.

Changes:
- Use certified polynomial/derivative independence witnesses before expensive methods.
- Prefer cheap exact zero checks; memoize function evaluations at exact points.
- Cache mathematically exact MathML renderings on the server.
- Apply full-span verification to manual practice edits as well as card actions.
- Preserve conservative unsupported verdicts, domains, and all game rules.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MARK = 'NABLA-PRECISION-PERFORMANCE-2026-11'
BASE_MARK = 'NABLA-SPEED-2026-11'


def replace_one(src: str, before: str, after: str, label: str) -> str:
    n = src.count(before)
    if n != 1:
        raise RuntimeError(f'{label}: exact match expected once; got {n}. No files changed.')
    return src.replace(before, after, 1)


def run():
    paths = {name: ROOT / name for name in ('nabla_linear.py', 'server.py', 'nabla_practice.py')}
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f'Missing {name}; no files changed.')
    before = {name: path.read_text(encoding='utf-8') for name, path in paths.items()}
    if all(MARK in text for text in before.values()):
        print('Speed patch 2 already installed; no changes necessary.')
        return
    if any(MARK in text for text in before.values()):
        raise RuntimeError('Partial speed-2 installation; refusing to write.')
    if BASE_MARK not in before['nabla_linear.py'] or 'NABLA-REVISION-2026-11' not in before['server.py']:
        raise RuntimeError('Required prior upgrades are missing; refusing to write.')

    linear = before['nabla_linear.py']
    # SymPy assumptions are sufficient proofs when explicitly True or False.
    # Avoid calling the more expensive simplify() for proven elementary cases.
    linear = replace_one(linear,
        '''    try:
        z = sp.simplify(value)
        if z == 0 or z.is_zero is True:
            return True
        if z.is_zero is False or z.is_positive is True or z.is_negative is True:
            return False''',
        '''    try:
        if value == 0 or getattr(value, 'is_zero', None) is True:
            return True
        if (getattr(value, 'is_zero', None) is False
                or getattr(value, 'is_positive', None) is True
                or getattr(value, 'is_negative', None) is True):
            return False
        z = sp.simplify(value)
        if z == 0 or z.is_zero is True:
            return True
        if z.is_zero is False or z.is_positive is True or z.is_negative is True:
            return False''',
        'certified zero fast path')
    linear = replace_one(linear,
        '\ndef _at_point(expressions, point):',
        '''
# ''' + MARK + '''
def _polynomial_degree_witness(target, old_exprs, domain):
    """Sufficient, exact linear-independence certificate on an open interval.

    If existing functions are polynomials of degree <= d, every real constant
    combination has derivative (d+1) identically zero. A provably nonzero
    (d+1)st derivative of the candidate at a regular interior point proves
    independence. Never claim dependence or use approximate thresholds here.
    """
    if not _interval_exists(domain):
        return False
    if target.has(sp.Piecewise, sp.Abs, sp.sign, sp.floor, sp.ceiling):
        return False
    try:
        polys = [sp.Poly(f, X) for f in old_exprs]
        degree = max((p.degree() for p in polys if not p.is_zero), default=-1)
        if degree < 0 or degree > 9:
            return False
        derivative = sp.diff(target, X, degree + 1)
        if derivative == 0:
            return False
        interior = domain.interior
        for point in _POINT_CANDIDATES[:9]:
            if interior.contains(point) is not sp.S.true:
                continue
            evaluated = _at_point((derivative,), point)
            if evaluated and _zero_proof(evaluated[0]) is False:
                return True
    except (sp.PolynomialError, ValueError, TypeError,
            NotImplementedError, RecursionError, OverflowError, AttributeError):
        pass
    return False


def _at_point(expressions, point):''',
        'exact derivative proof')

    # All cached values are exact SymPy expressions, never floating approximations.
    # This is effective across repeated candidate checks against unchanged bases.
    linear = replace_one(linear,
        '''def _at_point(expressions, point):
    values = []
    for expr in expressions:
        try:
            val = sp.simplify(expr.subs(X, point))
            if val.has(sp.nan, sp.zoo, sp.oo, -sp.oo) or val.is_real is not True or val.is_finite is not True:
                return None
            values.append(val)
        except (ValueError, TypeError, NotImplementedError, RecursionError, OverflowError):
            return None
    return values''',
        '''@lru_cache(maxsize=4096)
# ''' + MARK + '''
def _exact_value_at(expr, point):
    try:
        val = expr.subs(X, point)
        if val.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
            return None
        if val.is_real is True and val.is_finite is True:
            return val
        val = sp.simplify(val)
        if (val.has(sp.nan, sp.zoo, sp.oo, -sp.oo)
                or val.is_real is not True or val.is_finite is not True):
            return None
        return val
    except (ValueError, TypeError, NotImplementedError, RecursionError, OverflowError):
        return None


def _at_point(expressions, point):
    values = [_exact_value_at(expr, point) for expr in expressions]
    return None if any(val is None for val in values) else values''',
        'exact evaluation cache')

    linear = replace_one(linear,
        '''        old_exprs = [f for _, f in pairs]
        for id_, f in pairs:''',
        '''        old_exprs = [f for _, f in pairs]
        # Prefer certified, low-cost tests when existing bases are polynomials.
        # General symbolic solving, sampling and Wronskian remain as fallbacks.
        if target.is_polynomial(X) is True and _poly_independent(target, old_exprs, _interval_exists(domain)):
            return {'status': 'no', 'coefficients': {}}
        if _polynomial_degree_witness(target, old_exprs, domain):
            return {'status': 'no', 'coefficients': {}}
        for id_, f in pairs:''',
        'polynomial-first decision')

    server = before['server.py']
    server = replace_one(server,
        'import threading\n',
        'import threading\nfrom functools import lru_cache\n# ' + MARK + '\n',
        'server mathml cache import')
    server = replace_one(server,
        'def _mathml(expression):',
        '@lru_cache(maxsize=1024)\ndef _mathml(expression):',
        'server mathml cache')

    # Existing practice manual edits were still checking pairwise proportionality,
    # unlike card actions and whole-board operations. Unify the strict rule.
    practice = before['nabla_practice.py']
    practice = replace_one(practice,
        'from nabla_math import proportional_on_shared_domain',
        'from nabla_linear import relation_to_span\n# ' + MARK,
        'manual practice import')
    practice = replace_one(practice,
        '''        for other in board:
            dep=proportional_on_shared_domain(expr,other['expression'])
            if dep=='yes':
                raise ValueError('線形従属する基底は追加できません。')
            if dep=='unsupported':
                raise ValueError('基底の線形独立性を厳密に確認できません。')''',
        '''        dep = relation_to_span(expr, [(b['id'], b['expression']) for b in board])
        if dep['status'] == 'yes':
            raise ValueError('線形従属する基底は追加できません。')
        if dep['status'] == 'unsupported':
            raise ValueError('基底の線形独立性を厳密に確認できません。')''',
        'manual practice full-span checking')

    for name, content in [('nabla_linear.py', linear), ('server.py', server),
                          ('nabla_practice.py', practice)]:
        ast.parse(content, filename=name)

    # All source anchors and Python syntax are verified before writing.
    for name, content in [('nabla_linear.py', linear), ('server.py', server), ('nabla_practice.py', practice)]:
        path = paths[name]
        path.with_name(path.name + '.nabla-speed2-pending').write_text(content, encoding='utf-8')
    for name, path in paths.items():
        path.with_name(path.name + '.nabla-speed2-pending').replace(path)

    # The current workflow stages server.py but not nabla_linear.py by default.
    # Add it explicitly, without changing branch settings or the original main.
    subprocess.run(['git', 'add', 'nabla_linear.py', 'nabla_practice.py'], cwd=ROOT, check=True)

    # CI smoke tests: exact verdict preservation including nonpairwise dependence.
    from nabla_linear import relation_to_span
    examples = [
        ('x**3', ['1','x','x**2'], 'no'),
        ('sin(x)', ['1','x','x**2'], 'no'),
        ('exp(x)', ['1','x','x**2'], 'no'),
        ('sin(x)**2', ['1','x','x**2'], 'no'),
        ('log(x)', ['1','x','x**2'], 'no'),
        ('sqrt(x)', ['1','x','x**2'], 'no'),
        ('x', ['1','x','x**2'], 'yes'),
        ('1+x', ['1','x'], 'yes'),
        ('sin(x)+cos(x)', ['sin(x)','cos(x)'], 'yes'),
        ('cos(x)**2', ['1','sin(x)**2'], 'yes'),
        ('1', ['sin(x)**2','cos(x)**2'], 'yes'),
        ('cos(x)**2', ['1','x','x**2','sin(x)**2'], 'yes'),
    ]
    for candidate, older, expected in examples:
        result = relation_to_span(candidate, [(i + 1, expr) for i, expr in enumerate(older)])
        if result['status'] != expected:
            raise AssertionError(f'Unexpected {candidate} on {older}: {result}; expected {expected}')
    more_examples = [
        ('cos(x)', ['1', 'sin(x)**2'], 'no'),
        ('cos(x)**2', ['1', 'sin(x)**2'], 'yes'),
        ('1+x+x**2', ['1','x','x**2'], 'yes'),
        ('exp(2*x)', ['1','x','x**2'], 'no'),
        ('sin(x)**3', ['1','x','x**2'], 'no'),
        ('sin(x)', ['sin(x)**2','cos(x)**2'], 'no'),
    ]
    for candidate, older, expected in more_examples:
        result = relation_to_span(candidate, [(i + 1, expr) for i, expr in enumerate(older)])
        if result['status'] != expected:
            raise AssertionError(f'Unexpected {candidate} on {older}: {result}; expected {expected}')
    from nabla_practice import Practice
    p = Practice()
    assert [player['dimension'] for player in p.view()['players']] == [3, 3]
    print('MAX-PERF verified', len(examples) + len(more_examples), 'exact mathematical sample cases.')
    print('Exact eval cache, MathML cache, polynomial witnesses and practice span checks installed.')


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        print('NABLA MAX-PERF FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
