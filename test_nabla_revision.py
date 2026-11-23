"""Run with python -m unittest discover -s tests -v after upgrading."""
import random
import unittest
from collections import Counter

from cards import CARD_COUNTS, build_deck
from nabla_upgraderules import restrict_initial_hands,draw_allowed_cards
from nabla_game import new_game,play
from nabla_practice import Practice
from nabla_steps import explain_event


class CardProtection(unittest.TestCase):
    def test_inventory_and_opening(self):
        for seed in range(12):
            original=build_deck(seed=seed)
            restricted=restrict_initial_hands(original)
            self.assertEqual(Counter(original),Counter(restricted))
            self.assertNotIn('all_diff2',restricted[:14])
            game=new_game(seed=seed)
            self.assertNotIn('all_diff2',game['players'][0]['hand'])
            self.assertNotIn('all_diff2',game['players'][1]['hand'])

    def test_first_three_turns_then_release(self):
        for seed in range(10):
            deck=restrict_initial_hands(build_deck(seed=seed))[14:]
            for turn in range(1,7):
                picked=draw_allowed_cards(deck,3,turn)
                self.assertNotIn('all_diff2',picked)
            self.assertEqual(len(deck),78-14-18)
            # The special cards were only postponed, not removed.
            self.assertEqual(sum(x=='all_diff2' for x in deck),3)

    def test_replacement_count_unchanged(self):
        deck=restrict_initial_hands(build_deck(seed=4))[14:]
        count=len(deck)
        cards=draw_allowed_cards(deck,4,2)
        self.assertEqual(len(cards),4)
        self.assertEqual(len(deck),count-4)


class PracticeModeTests(unittest.TestCase):
    def test_initial_board_and_undo(self):
        practice=Practice()
        start=practice.view()
        self.assertEqual(start['current_node'],'0')
        self.assertEqual([p['dimension'] for p in start['players']],[3,3])
        response=practice.operate({'actor':0,'target_player':1,'cards':['diff'],'basis_id':2})
        self.assertTrue(response['ok'],response)
        node=response['state']['current_node']
        self.assertNotEqual(node,'0')
        self.assertTrue(practice.restore('0')['ok'])
        branch=practice.edit({'seat':0,'operation':'remove','basis_id':2})
        self.assertTrue(branch['ok'])
        self.assertNotEqual(branch['state']['current_node'],node)
        self.assertEqual(len(branch['state']['nodes']),3)

    def test_foul_does_not_end_practice(self):
        practice=Practice()
        response=practice.operate({'actor':0,'target_player':1,
                                   'cards':['div','zero'],'basis_id':2})
        self.assertEqual(response['status'],'foul')
        self.assertEqual(practice.view()['current_node'],'0')

    def test_manual_dependent_basis_rejected(self):
        practice=Practice()
        response=practice.edit({'seat':0,'operation':'add','code':'x'})
        self.assertFalse(response['ok'])


class ExplanationTests(unittest.TestCase):
    def test_derivative_steps(self):
        e={'id':'3-1','used_cards':['diff'],
           'calculations':[{'before':'x**2*sin(x)','after':'2*x*sin(x)+x**2*cos(x)'}]}
        result=explain_event(e)
        self.assertEqual(result['event_id'],'3-1')
        self.assertTrue(any('微分' in s['explanation'] for s in result['calculations'][0]['steps']))
        self.assertTrue(any(s.get('mathml') for s in result['calculations'][0]['steps']))

    def test_integral_constant_is_zero_in_game(self):
        e={'id':'3-2','used_cards':['integrate'],
           'calculations':[{'before':'x*cos(x)','after':'x*sin(x)+cos(x)'}]}
        result=explain_event(e)
        steps=result['calculations'][0]['steps']
        self.assertTrue(any('C=0' in s['explanation'] for s in steps))


if __name__=='__main__':unittest.main()
