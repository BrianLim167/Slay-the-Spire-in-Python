from __future__ import annotations

import random
import time

import pytest

import definitions
import displayer
import game
from ansi_tags import ansiprint
from definitions import CardType
from tests.fixtures import sleepless
import effect_interface


def replacement_clear_screen():
    '''Replacement for game.view.clear() so that I can see the test output'''
    print("\n--------------------------\n")


def repeat_check(repeat_catcher, last_return, current_return) -> tuple[int, bool]:
    '''Check if the player is stuck in a loop
    '''
    if last_return == current_return:
        repeat_catcher += 1
    else:
        repeat_catcher = 0
    if repeat_catcher > 3:
        print("Player is stuck in a loop")
        return repeat_catcher, True
    return repeat_catcher, False

def autoplayer(game: game.Game):
    '''Returns a patched input function that can play the game, maybe.

    Usage:
        with monkeypatch.context() as m:
            m.setattr('builtins.input', autoplayer(game))
    '''
    print("Autoplayer starting...")
    mygame = game
    repeat_catcher = 0
    last_return = None
    def patched_input(*args, **kwargs):
        nonlocal mygame
        nonlocal repeat_catcher
        nonlocal last_return
        choice = None
        reason = ""
        all_possible_choices = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'e',
                'p', 'm', 'd', 'a', 's', 'x', 'f', 'y', 'n',
                'rest', 'smith', 'view deck', 'leave', 'exit', 'lift', 'toke', 'dig']
        # Handle Start Node
        if mygame.game_map.current.type == definitions.EncounterType.START:
            choice, reason = str(random.choice(range(1, len(mygame.game_map.current.children)))), "Start node"

        # Handle dead
        player = mygame.player
        if player.state == definitions.State.DEAD:
            choice, reason = '\n', "Player is dead"

        # Handle shop
        if mygame.game_map.current.type == definitions.EncounterType.SHOP:
            # print("Player is in a shop")
            #tbd
            pass

        # Handle combat
        if mygame.current_encounter:
            possible_cards = [idx+1 for idx,card in enumerate(player.hand) if card.energy_cost <= player.energy and card.playable]
            # Handle no energy
            if player.energy == 0 and player.in_combat:
                choice, reason = 'e', "No energy left"
            # Handle enemy selection
            elif args and "Choose" in args[0]:
                choice, reason = str(random.randint(1, len(mygame.current_encounter.active_enemies))), "Enemy selection"
            # Handle card selection
            elif len(possible_cards) > 0:
                choice, reason = str(random.choice(possible_cards)), "Card selection"
            elif len(possible_cards) == 0:
                choice, reason = 'e', "No cards to play"

        # Default (all options)
        if choice is None:
            choice, reason = random.choice(all_possible_choices), "Default"

        repeat_catcher, check = repeat_check(repeat_catcher, last_return, choice)
        if check:
            # Pick anything other than the last choice
            tmp = all_possible_choices.copy()
            tmp.remove(choice)
            choice, reason = random.choice(tmp), "Player is stuck in a loop"

        last_return = choice
        print(f"AutoPlayer: {choice} ({reason})")
        return choice

    return patched_input


@pytest.mark.timeout(10)
@pytest.mark.parametrize("seed", list(range(30)))
def test_e2e(seed, monkeypatch, sleepless):
    '''Test the game from start to finish
    Plays with (more or less) random inputs to test the game.
    Seems to find lots of bugs, but very hard to repeat.
    '''
    ansiprint(f"<red><bold>Seed for this run is: {seed}</bold></red>")
    mygame = game.Game(seed=seed)
    effect_interface.apply_effect(mygame.player, None, "Invulnerable", 1)   # IDDQD
    with monkeypatch.context() as m:
        m.setattr('builtins.input', autoplayer(mygame))
        displayer.clear = replacement_clear_screen

        try:
            start = time.time()
            mygame.start()
        except Exception as e:
            ansiprint(f"<red><bold>Failed with seed: {seed}</bold></red>")
            raise e
        finally:
            end = time.time()
            ansiprint(f"\n\n<green><bold>Game took {end - start:.2f} seconds</bold></green>")


def test_debug_give_commands(sleepless):
    mygame = game.Game(seed=0, debug=True)

    starting_gold = mygame.player.gold
    starting_deck = len(mygame.player.deck)
    starting_relics = len(mygame.player.relics)
    starting_health = mygame.player.health

    assert mygame.handle_debug_command("give gold 25")
    assert mygame.player.gold == starting_gold + 25

    assert mygame.handle_debug_command("give card anger")
    assert len(mygame.player.deck) == starting_deck + 1
    assert any(card.name == "Anger" for card in mygame.player.deck)

    mygame.player.health = max(1, mygame.player.health - 10)
    assert mygame.handle_debug_command("give hp 5")
    assert mygame.player.health == min(mygame.player.max_health, starting_health - 5)

    assert mygame.handle_debug_command("give relic anchor")
    assert len(mygame.player.relics) == starting_relics + 1
    assert any(relic.name == "Anchor" for relic in mygame.player.relics)


def test_debug_deck_and_relic_commands(sleepless):
    mygame = game.Game(seed=0, debug=True)

    assert mygame.handle_command("deck set 2 strike, bash")
    assert len(mygame.player.deck) == 3
    assert [card.name for card in mygame.player.deck].count("Strike") == 2
    assert [card.name for card in mygame.player.deck].count("Bash") == 1

    assert mygame.handle_command("deck add anger, 2 defend")
    assert len(mygame.player.deck) == 6
    assert [card.name for card in mygame.player.deck].count("Anger") == 1
    assert [card.name for card in mygame.player.deck].count("Defend") == 2

    assert mygame.handle_command("deck clear")
    assert len(mygame.player.deck) == 0

    assert mygame.handle_command("relic set anchor")
    assert len(mygame.player.relics) == 1
    assert mygame.player.relics[0].name == "Anchor"

    assert mygame.handle_command("relic add akabeko")
    assert len(mygame.player.relics) == 2
    assert any(relic.name == "Akabeko" for relic in mygame.player.relics)

    assert mygame.handle_command("relic clear")
    assert len(mygame.player.relics) == 0


def test_show_commands_work_without_debug(sleepless):
    mygame = game.Game(seed=0, debug=False)
    assert mygame.handle_command("deck show")
    assert mygame.handle_command("relic show")

