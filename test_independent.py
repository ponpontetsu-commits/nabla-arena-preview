import unittest
from collections import Counter
import sympy as sp
from nabla_upgraderules import restrict_initial_hands,draw_allowed_cards
from nabla_steps import _integration_steps,_differentiation_steps

X=sp.Symbol('x',real=True)

class IndependentHelpers(unittest.TestCase):
    def test_restriction_does_not_change_inventory(self):
        for k in range(12):
            deck=['all_diff2']*3+['x']*20+['sin']*25+['integrate']*20
            import random
            random.Random(k).shuffle(deck)
            first=Counter(deck)
            protected=restrict_initial_hands(deck)
            self.assertEqual(Counter(protected),first)
            self.assertNotIn('all_diff2',protected[:14])
            for turn in range(1,7):
                picked=draw_allowed_cards(protected,3,turn)
                self.assertNotIn('all_diff2',picked)

    def test_multiple_integration_by_parts(self):
        expr=X**2*sp.sin(X)
        result=-X**2*sp.cos(X)+2*X*sp.sin(X)+2*sp.cos(X)
        steps=_integration_steps(expr,result)
        self.assertGreaterEqual(len([s for s in steps if '部分積分' in s['explanation']]),2)
        self.assertTrue(any('C=0' in s['explanation'] for s in steps))

    def test_product_derivative(self):
        expr=X**2*sp.sin(X)
        after=2*X*sp.sin(X)+X**2*sp.cos(X)
        steps=_differentiation_steps(expr,after,1)
        self.assertTrue(any('積の微分法' in s['explanation'] for s in steps))
        self.assertTrue(any(s['mathml'] for s in steps))

if __name__=='__main__':unittest.main()
