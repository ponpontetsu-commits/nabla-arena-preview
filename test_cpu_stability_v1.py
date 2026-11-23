"""Regression tests against the real NABLA ARENA game and server modules.

To run in repository root after patch:
    python -m unittest -v test_cpu_stability_v1
"""
import unittest
from unittest.mock import patch

import server
from nabla_game import new_game, play


class WholeBoardSerializationTests(unittest.TestCase):
    def test_unhashable_whole_board_history_is_never_passed_to_lru_cache(self):
        self.assertIsNone(server._mathml([{'id': 1, 'expression': 'x'}]))
        self.assertIsNone(server._mathml([1, 2, 3]))
        self.assertIsNone(server._mathml({'before': ['x']}))
        self.assertIsNone(server._mathml(None))

    def test_normal_formula_mathml_remains_available(self):
        self.assertIn('<math', server._mathml('x**2'))
        self.assertEqual(server._mathml('x**2'), server._mathml('x**2'))
        self.assertIn('<math', server._mathml('sin(x)'))

    def _game_with_whole_card(self, actor, code):
        game = new_game(seed=73)
        game['current'] = actor
        # A deterministic isolated test fixture: card inventory is not written.
        game['players'][actor]['hand'][0] = code
        action = {'kind': 'operate', 'card_indices': [0],
                  'target_player': 1-actor}
        result = play(game, actor, action, expected_revision=game['revision'])
        self.assertEqual(result['status'], 'ok', result.get('reason'))
        self.assertEqual(game['revision'], 0)
        self.assertEqual(result['state']['revision'], 1)
        return game, action, result

    def _assert_view(self, state, mode):
        with patch.object(server, '_STATE', {
            'game': state, 'mode': mode, 'ready': True,
            'difficulty': 'easy' if mode == 'cpu' else None,
            'deadline': None
        }):
            view = server._view()
            self.assertEqual(view['game_id'], state['game_id'])
            self.assertEqual(view['revision'], state['revision'])
            self.assertTrue(view['history'])
            self.assertIsInstance(view['history'][-1]['before'], list)
            self.assertIsInstance(view['history'][-1]['after'], list)
            for base in view['players'][0]['bases']:
                self.assertIn('<math', base['mathml'])

    def test_all_diff_by_human_rendered(self):
        _, _, result = self._game_with_whole_card(0, 'all_diff')
        self._assert_view(result['state'], 'local')

    def test_all_diff_by_cpu_rendered(self):
        _, _, result = self._game_with_whole_card(1, 'all_diff')
        self._assert_view(result['state'], 'cpu')

    def test_all_diff2_by_cpu_rendered(self):
        _, _, result = self._game_with_whole_card(1, 'all_diff2')
        self._assert_view(result['state'], 'cpu')

    def test_cpu_endpoint_commits_and_responds_to_whole_board_move(self):
        initial, action, cpu_result = self._game_with_whole_card(1, 'all_diff')
        local = {'game': initial, 'ready': True,
                 'mode': 'cpu', 'difficulty': 'easy', 'deadline': None}
        with patch.object(server, '_STATE', local), patch.object(
            server, 'safe_cpu_turn', return_value=(action, cpu_result)
        ):
            code, body = server.route_post('/api/cpu', {
                'revision': 0, 'game_id': initial['game_id']})
            self.assertEqual(code, 200)
            import json
            payload = json.loads(body)
            self.assertTrue(payload['ok'])
            self.assertEqual(payload['state']['revision'], 1)
            self.assertEqual(local['game']['revision'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
