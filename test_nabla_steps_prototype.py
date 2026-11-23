"""Regression tests for verified elementary integration explanation."""
import unittest
import sympy as sp
from nabla_steps import _integration_steps, X

class ExplanationTests(unittest.TestCase):
    def test_elementary(self):
        cases = [(sp.Integer(1), X), (X, X**2/2),
                 (X**3, X**4/4), (sp.sin(X), -sp.cos(X)),
                 (sp.cos(X), sp.sin(X)), (sp.exp(X), sp.exp(X))]
        for before, after in cases:
            with self.subTest(before=str(before)):
                steps = _integration_steps(before, after)
                self.assertGreaterEqual(len(steps), 3)
                self.assertTrue(any(s.get('mathml') for s in steps))
    def test_invalid_answer_not_explained(self):
        steps = _integration_steps(X, X**3)
        self.assertEqual(len(steps), 1)
        self.assertIn('確認できません', steps[0]['explanation'])

if __name__ == '__main__':
    unittest.main()
