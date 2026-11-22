"""NABLA ARENA: apply certified multibasis linear-algebra extension.

Upload nabla_linear.py FIRST, then this script to nabla-arena-update.
The existing workflow executes this script and validates/commits the changes.
The stable main branch is never modified.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
MARK = 'NABLA-LINEAR-SPAN-2026-11'


def replace_one(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected one matching block; found {count}')
    return source.replace(old, new, 1)


def upgrade():
    linear = ROOT / 'nabla_linear.py'
    game_file = ROOT / 'nabla_game.py'
    math_file = ROOT / 'nabla_math.py'
    if not (linear.is_file() and game_file.is_file() and math_file.is_file()):
        raise RuntimeError('Missing required files. Upload nabla_linear.py before nabla_upgrade.py.')
    ast.parse(linear.read_text(encoding='utf-8'), filename='nabla_linear.py')
    game = game_file.read_text(encoding='utf-8')
    math = math_file.read_text(encoding='utf-8')
    if MARK in game and MARK in math:
        print('Certified linear-span upgrade is already applied. No changes needed.')
        return
    if MARK in game or MARK in math:
        raise RuntimeError('Partial upgrade detected. No files changed.')
    if 'NABLA-REVISION-2026-11' not in game:
        raise RuntimeError('The stage-3 revision must already be installed; no files changed.')

    # General span checking replaces pairwise proportional checks in game actions.
    game = replace_one(
        game,
        'from nabla_math import (\n    apply_card, apply_mixed_chain, apply_whole_board,\n    proportional_on_shared_domain,\n)',
        'from nabla_math import (\n    apply_card, apply_mixed_chain, apply_whole_board,\n    proportional_on_shared_domain,\n)\nfrom nabla_linear import relation_to_span, relation_reason\n# ' + MARK,
        'game import extension'
    )
    game = replace_one(
        game,
        """def _proportional_to_older(formula, board, except_id=None):
    for existing in board:
        if existing['id'] == except_id: continue
        same = proportional_on_shared_domain(formula, existing['expression'])
        if same == 'unsupported': return ('unsupported', None)
        if same == 'yes': return ('yes', existing['id'])
    return ('no', None)""",
        """def _proportional_to_older(formula, board, except_id=None):
    # Test membership in the ENTIRE span, not just pairwise proportions.
    older = [(base['id'], base['expression']) for base in board
             if base['id'] != except_id]
    result = relation_to_span(formula, older)
    return (result['status'], relation_reason(result) if result['status'] == 'yes' else None)""",
        'multibasis game checking'
    )
    game = replace_one(
        game,
        "event['removed'].append({'id':new_number, 'reason':f'No.{same_id}に比例'})",
        "event['removed'].append({'id':new_number, 'reason':same_id})",
        'added basis elimination reason'
    )
    game = replace_one(
        game,
        "event['removed'].append({'id':event['basis_id'], 'reason':f'No.{match}に比例'})",
        "event['removed'].append({'id':event['basis_id'], 'reason':match})",
        'operated basis elimination reason'
    )

    # Whole-board differentiation must also test dependence on all earlier bases.
    math = replace_one(
        math,
        '    kept=[]; removed=[]\n    for no,r in sorted(results,key=lambda z:z[0]):',
        '    from nabla_linear import relation_to_span, relation_reason\n    # ' + MARK + '\n    kept=[]; removed=[]\n    for no,r in sorted(results,key=lambda z:z[0]):',
        'whole-board linear extension'
    )
    math = replace_one(
        math,
        """        dup=False
        for older_no,older_expr in kept:
            dep=proportional_on_shared_domain(r.after,older_expr)
            if dep=='unsupported':
                return {'status':'unsupported','reason':'線形従属の証明ができません。全体演算を取り消します。'}
            if dep=='yes':
                removed.append({'id':no,'reason':f'No.{older_no}に比例'})
                dup=True
                break
        if not dup:kept.append((no,r.after))""",
        """        dep = relation_to_span(r.after, kept)
        if dep['status'] == 'unsupported':
            return {'status':'unsupported','reason':'線形関係を厳密に判定できません。全体演算を取り消します。'}
        if dep['status'] == 'yes':
            removed.append({'id':no, 'reason':relation_reason(dep)})
            continue
        kept.append((no, r.after))""",
        'whole-board multibasis relation'
    )
    for name, source in [('nabla_game.py', game), ('nabla_math.py', math)]:
        ast.parse(source, filename=name)

    # Check all anchors and syntax before writing either target.
    for path, source in [(game_file, game), (math_file, math)]:
        tmp = path.with_name(path.name + '.nabla-linear-pending')
        tmp.write_text(source, encoding='utf-8')
    for path in [game_file, math_file]:
        path.with_name(path.name + '.nabla-linear-pending').replace(path)
    print('Certified multibasis engine installed into nabla_game.py and nabla_math.py.')

    # Regression smoke tests. Raising fails the GitHub Actions job and stops commit.
    from nabla_linear import relation_to_span
    cases = [
        ('1+x', ['1','x'], 'yes'),
        ('x**2', ['1','x'], 'no'),
        ('sin(x)+cos(x)', ['sin(x)','cos(x)'], 'yes'),
        ('1', ['sin(x)**2','cos(x)**2'], 'yes'),
        ('exp(x)', ['1','x'], 'no'),
        ('sin(x)', ['1','x','x**2'], 'no'),
        ('log(x)+1', ['log(x)','1'], 'yes'),
    ]
    for candidate, originals, expected in cases:
        result = relation_to_span(candidate, [(i+1, expr) for i,expr in enumerate(originals)])
        if result['status'] != expected:
            raise AssertionError(f'Linear regression: {candidate} vs {originals}: {result}, expected {expected}')
    print('Verified linear-algebra smoke tests:', len(cases))


if __name__ == '__main__':
    try:
        upgrade()
    except Exception as exc:
        print('NABLA linear upgrade failed: ' + str(exc), file=sys.stderr)
        sys.exit(1)
