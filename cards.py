"""Confirmed 21-card, 78-card finite deck. IDs are stable internal names."""
from collections import Counter
from random import Random

CARD_COUNTS = {
    'zero': 4, 'one': 4, 'x': 4, 'x2': 4, 'exp': 4,
    'sin': 4, 'cos': 4,
    'all_diff': 3, 'all_diff2': 3,
    'diff': 4, 'integrate': 4,
    'mul': 5, 'div': 5,
    'limit_plus_inf': 3, 'limit_minus_inf': 3, 'limit_zero': 3,
    'limsup_plus_inf': 3, 'liminf_plus_inf': 3,
    'sqrt': 4, 'inverse': 3, 'log': 4,
}
assert len(CARD_COUNTS) == 21
assert sum(CARD_COUNTS.values()) == 78


def build_deck(*, seed: int | None = None) -> list[str]:
    """Create one shuffled deck. Fixed seed for repeatable tests, random for play."""
    deck = [code for code, count in CARD_COUNTS.items() for _ in range(count)]
    Random(seed).shuffle(deck)
    return deck


def deal_new_game(*, seed: int | None = None):
    deck = build_deck(seed=seed)
    return {'hands': [deck[:7], deck[7:14]], 'deck': deck[14:]}


def inspect_deck(deck: list[str]) -> dict[str, int]:
    return dict(Counter(deck))
