"""Regression coverage for mathematically correct infinite-limit log output."""
import unittest
from xml.etree import ElementTree as ET

from nabla_steps import answer_infinite_limit_mathml


def rendered(before, card, *, reason='無限大に発散するため基底が消滅します。', status='vanished'):
    calc = {'before': before, 'after': None, 'status': status, 'reason': reason}
    return answer_infinite_limit_mathml(calc, [card])


def xml_text(formula):
    root = ET.fromstring(formula)
    assert root.tag.endswith('math')
    return ''.join(root.itertext())


class InfiniteLimitAnswerV3(unittest.TestCase):
    def test_positive_infinity_limit_is_visible(self):
        s = xml_text(rendered('x**2', 'limit_plus_inf'))
        self.assertIn('lim', s)
        self.assertIn('∞', s)
        self.assertEqual(s.count('='), 1)

    def test_negative_infinity_sign_is_preserved(self):
        s = xml_text(rendered('-x**2', 'limit_plus_inf'))
        self.assertIn('∞', s)
        self.assertIn('-', s.replace('−', '-'))
        self.assertEqual(s.count('='), 1)

    def test_minus_infinity_input(self):
        s = xml_text(rendered('x**2', 'limit_minus_inf'))
        self.assertIn('lim', s)
        self.assertIn('∞', s)
        self.assertEqual(s.count('='), 1)

    def test_opposite_sides_do_not_get_false_two_sided_limit(self):
        s = xml_text(rendered('1/x', 'limit_zero',
            reason='左右で無限大に発散するため（異符号でも）基底が消滅します。'))
        self.assertEqual(s.count('='), 2)
        self.assertIn('lim', s)
        self.assertIn('∞', s)
        self.assertIn('−', s)

    def test_same_infinite_sides_have_one_limit(self):
        s = xml_text(rendered('1/x**2', 'limit_zero',
            reason='左右で無限大に発散するため（異符号でも）基底が消滅します。'))
        self.assertEqual(s.count('='), 1)
        self.assertIn('∞', s)

    def test_foul_is_not_fabricated(self):
        self.assertEqual(rendered('sin(x)', 'limit_plus_inf', status='foul'), '')

    def test_non_limit_is_not_fabricated(self):
        self.assertEqual(rendered('x**2', 'diff'), '')
        self.assertEqual(rendered('x**2', 'limit_plus_inf', reason='0のため消滅'), '')

    def test_finite_limit_and_uncommitted_case(self):
        self.assertEqual(rendered('sin(x)', 'limit_zero'), '')
        self.assertEqual(rendered('x**2', 'limit_plus_inf', status='unsupported'), '')

    def test_practice_response_has_limit_mathml(self):
        from server import _decorate_practice_response
        event = {'used_cards': ['limit_plus_inf'],
                 'calculations': [{'before': 'x**2', 'after': None,
                                   'status': 'vanished',
                                   'reason': '無限大に発散するため基底が消滅します。'}]}
        result = _decorate_practice_response({'state': {
            'players': [{'bases': []}], 'history': [event]}})
        mathml = result['state']['history'][0]['calculations'][0]['answer_mathml']
        self.assertIn('∞', xml_text(mathml))
        self.assertEqual(xml_text(mathml).count('='), 1)


if __name__ == '__main__':
    unittest.main()
