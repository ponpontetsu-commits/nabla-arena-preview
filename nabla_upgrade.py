"""NABLA ARENA speed patch (feature branch only).

Upload this one file as `nabla_upgrade.py` to the `nabla-arena-update`
branch. Existing GitHub Actions workflow executes it, tests changes, stages
all new files, and commits if validation passes. It does not alter main.

Speed strategy:
* Prove independence by an exact nonzero Wronskian witness before expensive
  point-by-point symbolic elimination (same mathematical meaning).
* Reduce cos(x)^2 using the exact identity 1-sin(x)^2 so familiar trigonometric
  linear relations are certified with a short symbolic proof.
* Cache only deterministic exact computations (bounded LRU caches).
* Update selection controls in-place rather than recreating the entire practice
  screen on every tap, preserving DOM values, scroll, and touch targets.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MARK = 'NABLA-SPEED-2026-11'


def replace_one(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected one matching block, found {count}')
    return source.replace(old, new, 1)


def upgrade():
    paths = {name: ROOT / name for name in (
        'nabla_math.py', 'nabla_linear.py', 'nabla_upgrade_ui.js'
    )}
    if any(not p.is_file() for p in paths.values()):
        raise RuntimeError('Expected game math, linear, and UI modules are missing.')
    src = {name: p.read_text(encoding='utf-8') for name, p in paths.items()}
    if all(MARK in s for s in src.values()):
        print('NABLA ARENA speed patch already installed.')
        return
    if any(MARK in s for s in src.values()):
        raise RuntimeError('Partial performance upgrade detected; did not change files.')
    if 'NABLA-LINEAR-SPAN-2026-11' not in src['nabla_math.py']:
        raise RuntimeError('Certified linear-span extension has not been installed.')

    linear = src['nabla_linear.py']
    linear = replace_one(
        linear,
        'import sympy as sp\n',
        'import sympy as sp\nfrom functools import lru_cache\n# ' + MARK + '\n',
        'linear functools import',
    )
    linear = replace_one(
        linear,
        'def _coefficients(expr):\n    expanded = sp.expand(sp.expand_trig(expr))',
        '''@lru_cache(maxsize=512)
def _coefficients(expr):
    # sin(x)^2 + cos(x)^2 = 1: use an exact identity, never an approximation.
    expanded = sp.expand(sp.expand_trig(expr).subs(sp.cos(X)**2, 1 - sp.sin(X)**2))''',
        'exact trig identity and coefficient cache',
    )
    linear = replace_one(
        linear,
        """        sampled, coeffs = _point_sampling(target, old_exprs, domain)
        if sampled == 'yes':
            return {'status': 'yes', 'coefficients': {
                id_: str(c) for (id_, _), c in zip(pairs, coeffs) if c != 0
            }}
        if sampled == 'no' or _wronskian_independent(target, old_exprs, domain):
            return {'status': 'no', 'coefficients': {}}""",
        """        # A nonzero Wronskian at a valid domain point proves independence.
        # Attempt this inexpensive exact certificate BEFORE extensive sampling.
        if _wronskian_independent(target, old_exprs, domain):
            return {'status': 'no', 'coefficients': {}}
        sampled, coeffs = _point_sampling(target, old_exprs, domain)
        if sampled == 'yes':
            return {'status': 'yes', 'coefficients': {
                id_: str(c) for (id_, _), c in zip(pairs, coeffs) if c != 0
            }}
        if sampled == 'no':
            return {'status': 'no', 'coefficients': {}}""",
        'independence proof order',
    )
    linear += '''

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
'''

    math = src['nabla_math.py']
    math = replace_one(
        math,
        'import sympy as sp\n',
        'import sympy as sp\nfrom functools import lru_cache\n# ' + MARK + '\n',
        'math functools import',
    )
    math = replace_one(math, 'def parse_formula(text: str) -> sp.Expr:',
                       '@lru_cache(maxsize=1024)\ndef parse_formula(text: str) -> sp.Expr:',
                       'parser cache')
    math = replace_one(math, 'def _domain(expr):',
                       '@lru_cache(maxsize=1024)\ndef _domain(expr):',
                       'real domain cache')
    math = replace_one(math, 'def proportional_on_shared_domain(left_expr, right_expr) -> str:',
                       '@lru_cache(maxsize=1024)\ndef proportional_on_shared_domain(left_expr, right_expr) -> str:',
                       'proportionality cache')

    ui = src['nabla_upgrade_ui.js']
    ui = replace_one(ui,
        " const flag = 'nabla_educational_steps';",
        " const flag = 'nabla_educational_steps';\n // " + MARK,
        'UI marker')
    ui = replace_one(ui,
        ''' function options(p){return p.bases.map(b=>`<option value="${b.id}">No.${b.id}：${esc(b.expression)}</option>`).join('')}
 function renderPractice(){''',
        ''' function options(p){return p.bases.map(b=>`<option value="${b.id}">No.${b.id}：${esc(b.expression)}</option>`).join('')}
 // Keep the visible selection in sync without recreating the whole page.
 function refreshPracticeSelection(){
    const display = root.querySelector('#practiceSelection');
    if(display) display.textContent = chosen.length ? chosen.map(c=>DICT[c]||c).join(' → ') : '未選択';
    root.querySelectorAll('[data-pcard]').forEach(b=>b.classList.toggle('chosen',chosen.includes(b.dataset.pcard)));
 }
 function refreshPracticeTargetBasis(){
    const input = root.querySelector('#practiceBasis');
    if(!input || !pstate) return;
    input.innerHTML = '<option value="">場全体／追加</option>'+
      (pstate.players[targetSeat]?.bases||[]).map(b=>`<option value="${b.id}">No.${b.id}：${esc(b.expression)}</option>`).join('');
    input.value='';
 }
 function renderPractice(){''',
        'UI incremental selection helpers')
    ui = replace_one(ui,
        '''<p>選択：<strong>${chosen.length?chosen.map(c=>esc(DICT[c]||c)).join(' → '):'未選択'}</strong> <button id="practiceClear">選択解除</button></p>''',
        '''<p>選択：<strong id="practiceSelection">${chosen.length?chosen.map(c=>esc(DICT[c]||c)).join(' → '):'未選択'}</strong> <button id="practiceClear">選択解除</button></p>''',
        'UI selection display ID')
    ui = replace_one(ui,
        '''     chosen.push(b.dataset.pcard);renderPractice();''',
        '''     chosen.push(b.dataset.pcard);refreshPracticeSelection();''',
        'UI card click')
    ui = replace_one(ui,
        "root.querySelector('#practiceClear').addEventListener('click',()=>{chosen=[];renderPractice()});",
        "root.querySelector('#practiceClear').addEventListener('click',()=>{chosen=[];refreshPracticeSelection()});",
        'UI selection clear')
    ui = replace_one(ui,
        "root.querySelector('#practiceActor').addEventListener('change',e=>{actorSeat=Number(e.target.value);renderPractice()});",
        "root.querySelector('#practiceActor').addEventListener('change',e=>{actorSeat=Number(e.target.value)});",
        'UI actor change')
    ui = replace_one(ui,
        "root.querySelector('#practiceTarget').addEventListener('change',e=>{targetSeat=Number(e.target.value);targetBasis=null;renderPractice()});",
        "root.querySelector('#practiceTarget').addEventListener('change',e=>{targetSeat=Number(e.target.value);targetBasis=null;refreshPracticeTargetBasis()});",
        'UI target change')
    ui = replace_one(ui,
        "handlePracticeOperation(()=>practiceAPI('operate',action)).then(()=>{chosen=[];renderPractice()});",
        "handlePracticeOperation(()=>practiceAPI('operate',action)).then(()=>{chosen=[];refreshPracticeSelection()});",
        'UI redundant redraw after operation')

    changes={'nabla_linear.py':linear,'nabla_math.py':math,'nabla_upgrade_ui.js':ui}
    for name in ('nabla_linear.py', 'nabla_math.py'):
        ast.parse(changes[name],filename=name)
    for name, text in changes.items():
        staged=paths[name].with_name(paths[name].name + '.nabla-speed-pending')
        staged.write_text(text,encoding='utf-8')
    for name in changes:
        paths[name].with_name(paths[name].name + '.nabla-speed-pending').replace(paths[name])

    # Existing workflow adds only a fixed set of files; explicitly stage the
    # new UI and math engine so the green CI run actually commits both.
    subprocess.run(['git','add','nabla_linear.py','nabla_upgrade_ui.js'],cwd=ROOT,check=True)
    print('NABLA SPEEDPATCH updated math caches, exact certificate order, and practice selection UI.')


if __name__=='__main__':
    try:
        upgrade()
    except Exception as e:
        print('SPEEDPATCH FAILED: '+str(e),file=sys.stderr)
        sys.exit(1)
