"""NABLA ARENA: idempotent patch for the existing nabla_steps.py.
Run from the repository root: python nabla_steps_patch.py
"""
from pathlib import Path

PATH = Path(__file__).with_name('nabla_steps.py')
ANCHOR = 'def _integration_steps(expr, after):'
MARKER = '    steps = []\n    if expr.is_Add:'
VERSION = '# NABLA-EXPLAIN-PROTOTYPE-2026-11-22'

ADDITION = '''# NABLA-EXPLAIN-PROTOTYPE-2026-11-22
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


'''

def main():
    if not PATH.is_file():
        raise SystemExit('ERROR: nabla_steps.py が同じフォルダにありません。')
    src = PATH.read_text(encoding='utf-8')
    if VERSION in src:
        print('Already patched; no changes.')
        return
    if src.count(ANCHOR) != 1 or src.count(MARKER) != 1:
        raise SystemExit('ERROR: 対象ファイルの構造が想定と異なります。変更しません。')
    updated = src.replace(ANCHOR, ADDITION + ANCHOR).replace(
        MARKER, '    steps = _elementary_integration_steps(expr, after)\n    if expr.is_Add:', 1)
    compile(updated, str(PATH), 'exec')
    PATH.write_text(updated, encoding='utf-8')
    print('Patched nabla_steps.py')

if __name__ == '__main__':
    main()
