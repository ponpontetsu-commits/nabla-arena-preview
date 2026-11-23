"""Read-only audit: checks whether preview features are wired into main sources.

This does not test real browser rendering, mathematical correctness, or remote
DB connectivity. Designed to prevent accidental omissions during deployment.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REQUIRED = {
    'index.html': [
        '/app.js', '/nabla_upgrade_ui.js', '/nabla_upgrade.css',
    ],
    'nabla_upgrade_ui.js': [
        '練習モード（自由演算）', 'nablaPractice', "practiceAPI('start'",
        # Actual request is constructed dynamically; test the helper itself.
        'api(\'practice/\'+operation',
    ],
    'server.py': [
        'dispatch_practice', "path.startswith('/api/practice/')",
        'answer_infinite_limit_mathml', 'safe_cpu_turn',
    ],
    'nabla_game.py': [
        'apply_whole_board', 'relation_to_span', 'ALL_OPERATIONS',
    ],
    'nabla_math.py': [
        'continuous_domain', 'manualintegrate', 'apply_whole_board',
    ],
    'nabla_linear.py': ['relation_to_span', '_verified_combination'],
    'nabla_practice.py': ['class Practice', 'def dispatch('],
    'nabla_cpu2.py': ['def choose_cpu_action(', 'def take_cpu_turn('],
    'nabla_steps.py': ['def answer_mathml(', 'def answer_infinite_limit_mathml('],
    'sandbox_math.py': ["mp.get_context('spawn')", 'def safe_cpu_turn('],
    'online_rooms.py': ['DATABASE_URL', 'class OnlineRooms'],
}


def audit():
    missing = []
    for filename, patterns in REQUIRED.items():
        path = ROOT / filename
        if not path.is_file():
            missing.append(f'{filename}: file missing')
            continue
        source = path.read_text(encoding='utf-8')
        for pattern in patterns:
            if pattern not in source:
                missing.append(f'{filename}: missing {pattern!r}')
        if not any(item.startswith(filename + ':') for item in missing):
            print(f'WIRED {filename}')
    if missing:
        for problem in missing:
            print('NOT CONFIRMED:', problem, file=sys.stderr)
        return 1
    print('PASS static feature wiring. Real frontend/backend behavior remains unverified.')
    return 0


if __name__ == '__main__':
    sys.exit(audit())
