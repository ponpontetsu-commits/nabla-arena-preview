"""Card protection and rollout compatibility without changing original draws."""
from __future__ import annotations
import json

SPECIAL='all_diff2'
VERSION=3


def restrict_initial_hands(deck):
    """Condition initial random deal on no special card in the first 14 slots.

    Stable in-place reordering preserves the complete 78-card inventory.
    """
    deck=list(deck)
    for index in range(min(14,len(deck))):
        if deck[index]==SPECIAL:
            alternate=next((i for i in range(14,len(deck)) if deck[i]!=SPECIAL),None)
            if alternate is None:
                raise ValueError('初期手札を構築できません。')
            deck[index],deck[alternate]=deck[alternate],deck[index]
    return deck


def draw_allowed_cards(deck, requested, global_turn):
    """Keep physical card replacement count unchanged; only filter first 6 moves.

    First 6 actions correspond to each player's first 3 turns. Global turn 7
    is the first turn where both players have completed their 3rd turn.
    """
    total=min(max(0,int(requested)),len(deck))
    if global_turn<=6:
        for i in range(total):
            if deck[i]==SPECIAL:
                alternate=next((j for j in range(total,len(deck)) if deck[j]!=SPECIAL),None)
                if alternate is None:
                    # The 78-card deck contains only three specials, so this
                    # cannot happen during normal first-six-turn play.
                    raise ValueError('序盤の抽選に有効なカードがありません。')
                deck[i],deck[alternate]=deck[alternate],deck[i]
    drawn=deck[:total]
    del deck[:total]
    return drawn


def invalidate_old_rooms(store):
    """Immediately close pre-v3 active matches without changing any winner.

    Must run only in the final deployment using its OWN database. Staging must
    never share the production DATABASE_URL.
    """
    try:
        rows=store._run('SELECT code,payload FROM nabla_rooms').fetchall()
        for code,payload in rows:
            room=json.loads(payload)
            if room.get('phase') not in ('waiting','playing'):
                continue
            game=room.get('game')
            if not isinstance(game,dict) or game.get('version',0)<VERSION:
                store._run('DELETE FROM nabla_rooms WHERE code=?',(code,))
        if not store.postgres:
            store.conn.commit()
    except Exception:
        # Startup must fail rather than half-publish old incompatible games.
        raise RuntimeError('旧対戦データの整理に失敗したため、安全のため起動を中止します。')
