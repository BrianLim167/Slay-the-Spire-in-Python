import builtins
import random

import card_catalog
import game_map
import relic_catalog
from ansi_tags import ansiprint
from combat import Combat
from definitions import CombatTier, EncounterType, State
from enemy import Enemy
from events import choose_event
from message_bus_tools import Message, bus
from player import Player
from rest_site import RestSite
from shop import Shop


class Game:
    def __init__(self, seed=None, debug=False):
        self.bus = bus
        self.bus.reset()
        if seed is not None:
            random.seed(seed)
        self.debug = debug
        self.player = Player.create_player()
        self.game_map = game_map.create_first_map()
        Enemy.player = self.player
        self.current_encounter = None

    def start(self):
        if self.debug:
            return self._start_with_debug_input()
        return self._start_game()

    def _start_game(self):
        self.game_map.pretty_print()
        for encounter in self.game_map:
            self.play(encounter, self.game_map)
            if self.player.state == State.DEAD:
                break
            self.player.floors += 1
            self.game_map.pretty_print()

    def _start_with_debug_input(self):
        original_input = builtins.input

        def debug_input(prompt=""):
            while True:
                command = original_input(prompt)
                if self.handle_debug_command(command):
                    continue
                return command

        builtins.input = debug_input
        try:
            return self._start_game()
        finally:
            builtins.input = original_input

    def handle_debug_command(self, command: str) -> bool:
        if not self.debug:
            return False
        command = command.strip()
        if not command:
            return False
        parts = command.split(maxsplit=2)
        if parts[0].lower() != "give":
            return False
        if len(parts) < 3:
            ansiprint("<red>Usage: give <card|relic|hp|gold> <value></red>")
            return True

        resource_type = parts[1].lower()
        resource_value = parts[2].strip()
        if resource_type == "card":
            self._give_card(resource_value)
        elif resource_type == "relic":
            self._give_relic(resource_value)
        elif resource_type == "hp":
            self._give_hp(resource_value)
        elif resource_type == "gold":
            self._give_gold(resource_value)
        else:
            ansiprint("<red>Unknown debug resource. Use: card, relic, hp, or gold.</red>")
        return True

    @staticmethod
    def _normalize_name(name: str) -> str:
        return "".join(char for char in name.lower() if char.isalnum())

    def _give_card(self, card_name: str):
        requested = self._normalize_name(card_name)
        card = next(
            (candidate for candidate in card_catalog.create_all_cards() if self._normalize_name(candidate.name) == requested),
            None,
        )
        if card is None:
            ansiprint(f"<red>Could not find card '{card_name}'.</red>")
            return
        self.player.deck.append(card)
        self.bus.publish(Message.ON_CARD_ADD, (self.player, card))
        ansiprint(f"<green>Debug:</green> Added card <yellow>{card.name}</yellow> to deck.")

    def _give_relic(self, relic_name: str):
        requested = self._normalize_name(relic_name)
        relic = next(
            (candidate for candidate in relic_catalog.create_all_relics() if self._normalize_name(candidate.name) == requested),
            None,
        )
        if relic is None:
            ansiprint(f"<red>Could not find relic '{relic_name}'.</red>")
            return
        if any(existing.name == relic.name for existing in self.player.relics):
            ansiprint(f"<red>You already have <yellow>{relic.name}</yellow>.</red>")
            return
        self.player.relics.append(relic)
        self.bus.publish(Message.ON_RELIC_ADD, (relic, self.player))
        ansiprint(f"<green>Debug:</green> Added relic <yellow>{relic.name}</yellow>.")

    def _give_hp(self, hp: str):
        try:
            hp_amount = int(hp)
        except ValueError:
            ansiprint("<red>HP amount must be an integer.</red>")
            return
        if hp_amount <= 0:
            ansiprint("<red>HP amount must be positive.</red>")
            return
        self.player.health_actions(hp_amount, "Heal")
        ansiprint(f"<green>Debug:</green> Healed <light-blue>{hp_amount}</light-blue> HP.")

    def _give_gold(self, gold: str):
        try:
            gold_amount = int(gold)
        except ValueError:
            ansiprint("<red>Gold amount must be an integer.</red>")
            return
        if gold_amount <= 0:
            ansiprint("<red>Gold amount must be positive.</red>")
            return
        self.player.gain_gold(gold_amount, dialogue=False)
        ansiprint(f"<green>Debug:</green> Added <yellow>{gold_amount} Gold</yellow>.")

    def play(self, encounter: game_map.Encounter, the_map: game_map.GameMap):
        if encounter.type == EncounterType.START:
            pass
        elif encounter.type == EncounterType.REST_SITE:
            return RestSite(self.player).rest_site()
        elif encounter.type == EncounterType.UNKNOWN:
            return self.unknown(self.game_map)
        elif encounter.type in (EncounterType.BOSS, EncounterType.ELITE, EncounterType.NORMAL):
            mapping = {
                EncounterType.BOSS: CombatTier.BOSS,
                EncounterType.ELITE: CombatTier.ELITE,
                EncounterType.NORMAL: CombatTier.NORMAL,
            }
            self.current_encounter = Combat(tier=mapping[encounter.type], player=self.player, game_map=self.game_map)
            retval = self.current_encounter.combat()
            self.current_encounter = None
            return retval
        elif encounter.type == EncounterType.SHOP:
            return Shop(self.player).loop()
        else:
            raise game_map.MapError(f"Encounter type {encounter.type} is not valid.")

    def unknown(self, game_map) -> None:
        # Chances
        normal_combat: float = 0.1
        treasure_room: float = 0.02
        merchant: float = 0.03
        random_number = random.random()

        if random_number < treasure_room:
            treasure_room = 0.02
            normal_combat += 0.1
            merchant += 0.03
        elif random_number < merchant:
            merchant = 0.03
            treasure_room += 0.02
            normal_combat += 0.1
        elif random_number < normal_combat:
            normal_combat = 0.1
            treasure_room += 0.02
            merchant += 0.03
            self.current_encounter = Combat(player=self.player, tier=CombatTier.NORMAL, game_map=self.game_map)
            retval = self.current_encounter.combat()
            self.current_encounter = None
            return retval
        else:
            # Chooses an event if nothing else is chosen
            ansiprint(self.player)
            chosen_event = choose_event(game_map, self.player)
            chosen_event()

    def pretty_print(self):
        print(f"{self.game_map.current.type}")
        if self.current_encounter:
            print(f"Current encounter: {self.current_encounter}")


