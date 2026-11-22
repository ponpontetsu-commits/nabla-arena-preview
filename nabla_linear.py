"""Sound, conservative span checks for NABLA ARENA real-valued basis functions.

A 'yes' result always includes a symbolically verified real constant linear
combination. A 'no' result has a certified rank increase (at exact domain
points), a nonzero Wronskian at a valid point, or a polynomial coefficient-rank
increase on an interval. Anything else remains 'unsupported'.
"""
from __future__ import annotations

import sympy as sp
from functools import lru_cache
# NABLA-SPEED-2026-11
from nabla_math import X, _domain, parse_formula, proportional_on_shared_domain, UnsupportedMath, InputError

_POINT_CANDIDATES = (
    sp.S.Zero, sp.S.One, -sp.S.One, sp.S(2), -sp.S(2),
    sp.S.Half, -sp.S.Half, sp.S(3), -sp.S(3),
    sp.pi / 2, -sp.pi / 2, sp.pi, -sp.pi, sp.S(4), sp.S(5),
)
_MAX_FUNCTIONS = 12


def _zero_proof(value):
    """True, False, or None; never infer nonzero from floating point tests."""
    try:
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
            return False
    except (ValueError, TypeError, NotImplementedError, RecursionError):
        pass
    return None


def _rank_proved(rows):
    """Gaussian elimination using only pivots proven nonzero exactly."""
    if not rows:
        return 0
    a = [list(row) for row in rows]
    m, n = len(a), len(a[0])
    rank = 0
    for c in range(n):
        pivot = None
        unknown = False
        for r in range(rank, m):
            z = _zero_proof(a[r][c])
            if z is False:
                pivot = r
                break
            if z is None:
                unknown = True
        if pivot is None:
            if unknown:
                return None
            continue
        a[rank], a[pivot] = a[pivot], a[rank]
        p = a[rank][c]
        for r in range(rank + 1, m):
            q = a[r][c]
            if _zero_proof(q) is True:
                a[r][c] = sp.S.Zero
                continue
            for k in range(c + 1, n):
                a[r][k] = sp.cancel(a[r][k] * p - q * a[rank][k])
            a[r][c] = sp.S.Zero
        rank += 1
        if rank == m:
            break
    return rank


def _interval_exists(domain):
    return isinstance(domain, sp.Interval) or (
        isinstance(domain, sp.Union)
        and any(isinstance(piece, sp.Interval) for piece in domain.args)
    )


@lru_cache(maxsize=512)
def _coefficients(expr):
    # sin(x)^2 + cos(x)^2 = 1: use an exact identity, never an approximation.
    expanded = sp.expand(sp.expand_trig(expr).subs(sp.cos(X)**2, 1 - sp.sin(X)**2))
    if len(str(expanded)) > 2200:
        return None
    terms = sp.Add.make_args(expanded)
    if len(terms) > 120:
        return None
    result = {}
    for term in terms:
        coeff, atom = term.as_coeff_Mul(rational=True)
        result[atom] = result.get(atom, sp.S.Zero) + coeff
    return {atom: coeff for atom, coeff in result.items() if coeff != 0}


def _verified_combination(expr, old_exprs, coefficients):
    if len(coefficients) != len(old_exprs):
        return False
    if any(c.is_real is not True or c.is_finite is not True or c.free_symbols for c in coefficients):
        return False
    diff = expr - sum((c * f for c, f in zip(coefficients, old_exprs)), sp.S.Zero)
    try:
        if sp.simplify(sp.trigsimp(diff)) == 0:
            return True
        if sp.simplify(sp.expand_trig(diff)) == 0:
            return True
    except (ValueError, TypeError, NotImplementedError, RecursionError):
        pass
    return False


def _solve_coefficients(matrix, values, target, old_exprs):
    try:
        solution, params = matrix.gauss_jordan_solve(sp.Matrix(values))
        for param in list(params):
            solution = solution.subs(param, sp.S.Zero)
        coefficients = [sp.simplify(v) for v in solution]
        if _verified_combination(target, old_exprs, coefficients):
            return coefficients
    except (ValueError, TypeError, NotImplementedError, RecursionError, IndexError):
        pass
    return None


def _symbolic_combination(target, old_exprs):
    maps = [_coefficients(f) for f in (*old_exprs, target)]
    if any(m is None for m in maps):
        return None, None
    atoms = sorted(set().union(*(m.keys() for m in maps)), key=sp.default_sort_key)
    matrix = sp.Matrix([[m.get(atom, 0) for m in maps[:-1]] for atom in atoms])
    values = [maps[-1].get(atom, 0) for atom in atoms]
    coefficients = _solve_coefficients(matrix, values, target, old_exprs)
    return coefficients, (matrix, values)


def _poly_independent(target, old_exprs, interval):
    if not interval:
        return False
    try:
        polynomials = [sp.Poly(f, X) for f in (*old_exprs, target)]
        degrees = max((p.degree() for p in polynomials), default=0)
        if degrees < 0 or degrees > 80:
            return False
        rows = [[p.nth(degree) for p in polynomials] for degree in range(degrees + 1)]
        a = _rank_proved([row[:-1] for row in rows])
        b = _rank_proved(rows)
        return a is not None and b is not None and b > a
    except (sp.PolynomialError, ValueError, TypeError, NotImplementedError, RecursionError):
        return False


# NABLA-PRECISION-PERFORMANCE-2026-11
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


@lru_cache(maxsize=4096)
# NABLA-PRECISION-PERFORMANCE-2026-11
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
    return None if any(val is None for val in values) else values


def _point_sampling(target, old_exprs, domain):
    n = len(old_exprs)
    sample_rows = []
    for point in _POINT_CANDIDATES:
        try:
            if domain.contains(point) is not sp.S.true:
                continue
            row = _at_point([*old_exprs, target], point)
        except (ValueError, TypeError, NotImplementedError, RecursionError):
            continue
        if row is None:
            continue
        sample_rows.append(row)
        old_rank = _rank_proved([r[:-1] for r in sample_rows])
        new_rank = _rank_proved(sample_rows)
        if old_rank is not None and new_rank is not None and new_rank > old_rank:
            return 'no', None
        if old_rank == n and len(sample_rows) <= n + 2:
            coefficients = _solve_coefficients(
                sp.Matrix([r[:-1] for r in sample_rows]),
                [r[-1] for r in sample_rows], target, old_exprs
            )
            if coefficients is not None:
                return 'yes', coefficients
        if len(sample_rows) >= n + 4:
            break
    return 'unsupported', None


def _wronskian_independent(target, old_exprs, domain):
    expressions = [*old_exprs, target]
    n = len(expressions)
    if n > 6:
        return False
    try:
        derivatives = [[sp.diff(f, X, k) for f in expressions] for k in range(n)]
        for point in _POINT_CANDIDATES[:11]:
            if domain.contains(point) is not sp.S.true:
                continue
            rows = []
            for derivative_row in derivatives:
                values = _at_point(derivative_row, point)
                if values is None:
                    break
                rows.append(values)
            if len(rows) == n and _rank_proved(rows) == n:
                return True
    except (ValueError, TypeError, NotImplementedError, RecursionError, OverflowError):
        pass
    return False


def relation_to_span(candidate, older):
    """Test if candidate belongs to real span of older [(basis_id, formula)].

    Returns {'status': 'yes'|'no'|'unsupported', 'coefficients': {id: string}}.
    An explicit certificate is verified before any 'yes' result.
    """
    if not older:
        return {'status': 'no', 'coefficients': {}}
    try:
        target = parse_formula(candidate) if isinstance(candidate, str) else candidate
        pairs = [(id_, parse_formula(f) if isinstance(f, str) else f) for id_, f in older]
        if len(pairs) + 1 > _MAX_FUNCTIONS:
            return {'status': 'unsupported', 'coefficients': {}}
        domain = _domain(target)
        for _, f in pairs:
            domain = domain.intersect(_domain(f))
        if domain.is_empty is True or domain is sp.S.EmptySet:
            return {'status': 'unsupported', 'coefficients': {}}
        old_exprs = [f for _, f in pairs]
        # Prefer certified, low-cost tests when existing bases are polynomials.
        # General symbolic solving, sampling and Wronskian remain as fallbacks.
        if target.is_polynomial(X) is True and _poly_independent(target, old_exprs, _interval_exists(domain)):
            return {'status': 'no', 'coefficients': {}}
        if _polynomial_degree_witness(target, old_exprs, domain):
            return {'status': 'no', 'coefficients': {}}
        for id_, f in pairs:
            if proportional_on_shared_domain(target, f) == 'yes':
                # Re-verify even the fast path, using a real constant certificate.
                ratio = sp.simplify(sp.cancel(target / f))
                coeffs = [ratio if i == id_ else sp.S.Zero for i, _ in pairs]
                if _verified_combination(target, old_exprs, coeffs):
                    return {'status': 'yes', 'coefficients': {id_: str(ratio)}}
        coeffs, _ = _symbolic_combination(target, old_exprs)
        if coeffs is not None:
            return {'status': 'yes', 'coefficients': {
                id_: str(c) for (id_, _), c in zip(pairs, coeffs) if c != 0
            }}
        if _poly_independent(target, old_exprs, _interval_exists(domain)):
            return {'status': 'no', 'coefficients': {}}
        # A nonzero Wronskian at a valid domain point proves independence.
        # Attempt this inexpensive exact certificate BEFORE extensive sampling.
        if _wronskian_independent(target, old_exprs, domain):
            return {'status': 'no', 'coefficients': {}}
        sampled, coeffs = _point_sampling(target, old_exprs, domain)
        if sampled == 'yes':
            return {'status': 'yes', 'coefficients': {
                id_: str(c) for (id_, _), c in zip(pairs, coeffs) if c != 0
            }}
        if sampled == 'no':
            return {'status': 'no', 'coefficients': {}}
        return {'status': 'unsupported', 'coefficients': {}}
    except (UnsupportedMath, InputError, ValueError, TypeError, NotImplementedError, RecursionError, OverflowError, ZeroDivisionError):
        return {'status': 'unsupported', 'coefficients': {}}


def relation_reason(result):
    """Short explanation using the verified real combination certificate."""
    coefficients = result.get('coefficients') or {}
    if len(coefficients) == 1:
        basis = next(iter(coefficients))
        return f'No.{basis}に比例'
    if coefficients:
        return '、'.join('No.' + str(k) for k in coefficients) + 'の線形結合'
    return '既存基底の線形結合'


# Exact relation results, including valid proof coefficients, are immutable
# across repeated CPU candidates and turns. Cache a compact immutable form.
_relation_to_span_uncached = relation_to_span

@lru_cache(maxsize=768)
def _cached_relation_to_span(candidate, older):
    result = _relation_to_span_uncached(candidate, older)
    return (result['status'], tuple(result['coefficients'].items()))


def relation_to_span(candidate, older):
    try:
        status, coefficients = _cached_relation_to_span(candidate, tuple(older))
        return {'status': status, 'coefficients': dict(coefficients)}
    except TypeError:
        return _relation_to_span_uncached(candidate, older)
