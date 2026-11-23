"""Regression tests for concise MathML answer lines, not game-rule changes."""
import unittest
from xml.etree import ElementTree as ET

import sympy as sp

from nabla_steps import answer_mathml, explain_event

X = sp.Symbol('x', real=True)


def strip_mathml(formula):
    element = ET.fromstring(formula)
    assert element.tag.endswith('math')
    return ''.join(element.itertext())


class AnswerLogV2Tests(unittest.TestCase):
    def test_power_integral_is_one_equation(self):
        s = strip_mathml(answer_mathml('x**2', 'x**3/3', ['integrate']))
        self.assertEqual(s.count('='), 1)
        self.assertIn('3', s)
        self.assertIn('x', s)
        self.assertTrue(any(t in s for t in ('∫', '∫')))

    def test_simple_derivative_is_one_equation(self):
        s = strip_mathml(answer_mathml('x**3', '3*x**2', ['diff']))
        self.assertEqual(s.count('='), 1)
        self.assertIn('3', s)

    def test_product_derivative_has_verified_middle(self):
        s = strip_mathml(answer_mathml('x**2*sin(x)',
            'x*(x*cos(x)+2*sin(x))', ['diff']))
        self.assertEqual(s.count('='), 2)
        self.assertIn('sin', s)
        self.assertIn('cos', s)

    def test_integration_by_parts_only_when_verified(self):
        primitive = '-x**2*cos(x)+2*x*sin(x)+2*cos(x)'
        s = strip_mathml(answer_mathml('x**2*sin(x)',primitive,['integrate']))
        # Several useful equalities, not extended prose.
        self.assertGreaterEqual(s.count('='), 2)
        self.assertIn('∫', s)
        self.assertIn('cos', s)

    def test_sqrt_and_log_have_explicit_operators(self):
        sqrt_line = strip_mathml(answer_mathml('x**2','Abs(x)',['sqrt']))
        self.assertIn('=',sqrt_line)
        log_line = strip_mathml(answer_mathml('exp(x)','x',['log']))
        self.assertIn('log',log_line)

    def test_zero_limit_uses_limit_symbol(self):
        s = strip_mathml(answer_mathml('sin(x)','0',['limit_zero']))
        self.assertIn('lim',s)
        self.assertIn('=',s)

    def test_chain_rule_second_diff_is_not_first_diff(self):
        s = strip_mathml(answer_mathml('x**3', '6*x', ['all_diff2']))
        self.assertEqual(s.count('='), 1)
        self.assertIn('6', s)
        self.assertIn('2', s)

    def test_multiplication_displays_card_factor(self):
        s = strip_mathml(answer_mathml('x**2','x**2*sin(x)', ['mul','sin']))
        self.assertEqual(s.count('='), 1)
        self.assertIn('sin',s)
        self.assertIn('×',s)

    def test_chain_displays_left_to_right(self):
        s = strip_mathml(answer_mathml('x**2','x**3*exp(-x)',
                                        ['mul','x','div','exp']))
        self.assertEqual(s.count('='),1)
        self.assertIn('×',s)
        self.assertIn('÷',s)

    def test_lim_sup_is_explicit(self):
        s = strip_mathml(answer_mathml('sin(x)', '1', ['limsup_plus_inf']))
        self.assertIn('limsup',s)
        self.assertIn('=',s)

    def test_inverse_not_equated_to_original_function(self):
        s = strip_mathml(answer_mathml('exp(x)','log(x)',['inverse']))
        self.assertEqual(s.count('='),2)
        self.assertIn('log',s)

    def test_undefined_answer_does_not_fabricate(self):
        self.assertEqual(answer_mathml('x',None,['limit_plus_inf']),'')
        self.assertEqual(answer_mathml('x','x',[]),'')
        self.assertEqual(answer_mathml('bad input','0',['diff']),'')

    def test_old_explanations_still_available(self):
        ev = {'id':'test-1','used_cards':['integrate'],
              'calculations':[{'before':'x*cos(x)',
                               'after':'x*sin(x)+cos(x)'}]}
        detail = explain_event(ev)
        self.assertTrue(any('C=0' in step['explanation']
                            for step in detail['calculations'][0]['steps']))

    def test_practice_decorator_returns_inline_answer(self):
        from server import _decorate_practice_response
        payload = {'state':{'players':[{'bases':[]}],
                   'history':[{'used_cards':['integrate'],
                               'calculations':[{'before':'x**2','after':'x**3/3'}]}]}}
        result = _decorate_practice_response(payload)
        calc = result['state']['history'][0]['calculations'][0]
        self.assertIn('<math',calc['answer_mathml'])
        self.assertEqual(strip_mathml(calc['answer_mathml']).count('='),1)


if __name__=='__main__':
    unittest.main()
