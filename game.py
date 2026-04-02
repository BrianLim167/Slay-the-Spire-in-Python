import builtins
import random
import re
from collections import Counter

import card_catalog
import game_map
import potion_catalog
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
        return self._start_with_command_input()

    def _start_game(self):
        self.game_map.pretty_print()
        for encounter in self.game_map:
            self.play(encounter, self.game_map)
            if self.player.state == State.DEAD:
                break
            self.player.floors += 1
            self.game_map.pretty_print()

    def _start_with_command_input(self):
        original_input = builtins.input

        def show_next_encounter_choices():
            if self.game_map.current is None:
                return
            choices = self.game_map.current.children
            if not choices:
                return
            for idx, choice in enumerate(choices):
                print(f"{idx + 1}: {choice}")

        def command_input(prompt=""):
            while True:
                command = original_input(prompt)
                if self.handle_command(command):
                    if "Choose next encounter" in prompt:
                        show_next_encounter_choices()
                    continue
                return command

        builtins.input = command_input
        try:
            return self._start_game()
        finally:
            builtins.input = original_input

    def handle_command(self, command: str) -> bool:
        command = command.strip()
        if not command:
            return False
        if command.lower().startswith("deck "):
            return self._handle_collection_command(command, "deck")
        if command.lower().startswith("relic "):
            return self._handle_collection_command(command, "relic")
        if command.lower().startswith("potion "):
            return self._handle_collection_command(command, "potion")
        if command.lower().startswith("gold "):
            return self._handle_resource_command(command, "gold")
        if command.lower().startswith("hp "):
            return self._handle_resource_command(command, "hp")
        return False

    def _handle_collection_command(self, command: str, collection: str) -> bool:
        parts = command.split(maxsplit=2)
        if len(parts) < 2:
            return False
        action = parts[1].lower()
        if action == "show":
            if collection == "deck":
                self._show_deck()
            elif collection == "relic":
                self._show_relics()
            else:
                self._show_potions()
            return True
        if not self.debug:
            ansiprint(f"<red>Debug mode is required for '{collection} {action}'. Run with --debug.</red>")
            return True
        if action == "clear":
            if collection == "deck":
                self.player.deck.clear()
                ansiprint("<green>Debug:</green> Cleared deck.")
            elif collection == "relic":
                self._clear_relics()
                ansiprint("<green>Debug:</green> Cleared relics.")
            else:
                self.player.potions.clear()
                ansiprint("<green>Debug:</green> Cleared potions.")
            return True
        if action not in ("set", "add"):
            ansiprint(f"<red>Usage: {collection} <show|clear|set|add> ...</red>")
            return True
        if len(parts) < 3:
            ansiprint(f"<red>Usage: {collection} {action} <count> <name>, <name>, ...</red>")
            return True
        specs = self._parse_specs(parts[2])
        if specs is None:
            return True
        if collection == "deck":
            cards = self._build_cards_from_specs(specs)
            if cards is None:
                return True
            if action == "set":
                self.player.deck = cards
                ansiprint(f"<green>Debug:</green> Deck set to {len(self.player.deck)} cards.")
            else:
                self.player.deck.extend(cards)
                ansiprint(f"<green>Debug:</green> Added {len(cards)} cards (deck: {len(self.player.deck)}).")
        elif collection == "relic":
            relics = self._build_relics_from_specs(specs)
            if relics is None:
                return True
            if action == "set":
                self._clear_relics()
                self.player.relics = []
            added = 0
            for relic in relics:
                if any(existing.name == relic.name for existing in self.player.relics):
                    ansiprint(f"<red>Skipping duplicate relic <yellow>{relic.name}</yellow>.</red>")
                    continue
                self.player.relics.append(relic)
                # Register before publishing so relics can react to their own pickup event.
                if not relic.subscribed:
                    relic.register(self.bus)
                self.bus.publish(Message.ON_RELIC_ADD, (relic, self.player))
                added += 1
            ansiprint(f"<green>Debug:</green> Added {added} relic(s) (total: {len(self.player.relics)}).")
        else:
            potions = self._build_potions_from_specs(specs)
            if potions is None:
                return True
            if action == "set":
                self.player.potions = []
            self.player.potions.extend(potions)
            ansiprint(f"<green>Debug:</green> Added {len(potions)} potion(s) (total: {len(self.player.potions)}).")
        return True

    def _handle_resource_command(self, command: str, resource: str) -> bool:
        parts = command.split(maxsplit=2)
        if len(parts) < 2:
            return False
        action = parts[1].lower()
        if action == "show":
            if resource == "gold":
                ansiprint(f"<yellow>Gold:</yellow> {self.player.gold}")
            else:
                ansiprint(f"<light-blue>HP:</light-blue> {self.player.health}/{self.player.max_health}")
            return True
        if action not in ("add", "set"):
            ansiprint(f"<red>Usage: {resource} <show|add|set> <amount></red>")
            return True
        if not self.debug:
            ansiprint(f"<red>Debug mode is required for '{resource} {action}'. Run with --debug.</red>")
            return True
        if len(parts) < 3:
            ansiprint(f"<red>Usage: {resource} <show|add|set> <amount></red>")
            return True
        if resource == "gold":
            self._modify_gold(parts[2], action)
        else:
            self._modify_hp(parts[2], action)
        return True

    @staticmethod
    def _normalize_name(name: str) -> str:
        return "".join(char for char in name.lower() if char.isalnum())

    def _parse_specs(self, specs: str) -> list[tuple[int, str]] | None:
        parsed_specs = []
        for raw_spec in [item.strip() for item in specs.split(",") if item.strip()]:
            match = re.match(r"^(?:(\d+)\s+)?(.+)$", raw_spec, flags=re.IGNORECASE)
            if match is None:
                ansiprint(f"<red>Invalid entry '{raw_spec}'. Use '<count> <name>' or '<name>'.</red>")
                return None
            count = int(match.group(1) or 1)
            name = match.group(2).strip()
            if count <= 0 or not name:
                ansiprint(f"<red>Invalid entry '{raw_spec}'. Count must be positive and name required.</red>")
                return None
            parsed_specs.append((count, name))
        if not parsed_specs:
            ansiprint("<red>No entries provided.</red>")
            return None
        return parsed_specs

    def _show_deck(self):
        if not self.player.deck:
            ansiprint("Deck is empty.")
            return
        counts = Counter(card.name for card in self.player.deck)
        ansiprint(f"<bold>Deck</bold> ({len(self.player.deck)} cards):")
        for name, count in sorted(counts.items()):
            ansiprint(f" - {count}x {name}")

    def _show_relics(self):
        if not self.player.relics:
            ansiprint("Relics: none")
            return
        counts = Counter(relic.name for relic in self.player.relics)
        ansiprint(f"<bold>Relics</bold> ({len(self.player.relics)}):")
        for name, count in sorted(counts.items()):
            ansiprint(f" - {count}x {name}")

    def _show_potions(self):
        if not self.player.potions:
            ansiprint("Potions: none")
            return
        counts = Counter(potion.name for potion in self.player.potions)
        ansiprint(f"<bold>Potions</bold> ({len(self.player.potions)}):")
        for name, count in sorted(counts.items()):
            ansiprint(f" - {count}x {name}")

    def _build_cards_from_specs(self, specs: list[tuple[int, str]]) -> list:
        card_lookup = {
            self._normalize_name(card.name): type(card)
            for card in card_catalog.create_all_cards()
        }
        cards = []
        for count, name in specs:
            normalized = self._normalize_name(name)
            if normalized not in card_lookup:
                ansiprint(f"<red>Could not find card '{name}'.</red>")
                return None
            cards.extend(card_lookup[normalized]() for _ in range(count))
        return cards

    def _build_relics_from_specs(self, specs: list[tuple[int, str]]) -> list:
        relic_lookup = {
            self._normalize_name(relic.name): type(relic)
            for relic in relic_catalog.create_all_relics()
        }
        relics = []
        for count, name in specs:
            normalized = self._normalize_name(name)
            if normalized not in relic_lookup:
                ansiprint(f"<red>Could not find relic '{name}'.</red>")
                return None
            if count > 1:
                ansiprint(f"<red>Relics are unique; '{name}' can only be added once.</red>")
                return None
            relics.append(relic_lookup[normalized]())
        return relics

    def _build_potions_from_specs(self, specs: list[tuple[int, str]]) -> list:
        potion_lookup = {
            self._normalize_name(potion.name): type(potion)
            for potion in potion_catalog.create_all_potions()
        }
        potions = []
        for count, name in specs:
            normalized = self._normalize_name(name)
            if normalized not in potion_lookup:
                ansiprint(f"<red>Could not find potion '{name}'.</red>")
                return None
            potions.extend(potion_lookup[normalized]() for _ in range(count))
        return potions

    def _clear_relics(self):
        for relic in self.player.relics:
            if relic.subscribed:
                relic.unsubscribe()

    def _modify_hp(self, hp: str, mode: str):
        try:
            hp_amount = int(hp)
        except ValueError:
            ansiprint("<red>HP amount must be an integer.</red>")
            return
        if hp_amount <= 0:
            ansiprint("<red>HP amount must be positive.</red>")
            return
        if mode == "add":
            self.player.health_actions(hp_amount, "Heal")
            ansiprint(f"<green>Debug:</green> Healed <light-blue>{hp_amount}</light-blue> HP.")
            return
        self.player.health = min(hp_amount, self.player.max_health)
        if self.player.health <= 0:
            self.player.state = State.DEAD
        ansiprint(f"<green>Debug:</green> HP set to <light-blue>{self.player.health}</light-blue>/<light-blue>{self.player.max_health}</light-blue>.")

    def _modify_gold(self, gold: str, mode: str):
        try:
            gold_amount = int(gold)
        except ValueError:
            ansiprint("<red>Gold amount must be an integer.</red>")
            return
        if mode == "add":
            if gold_amount <= 0:
                ansiprint("<red>Gold amount must be positive.</red>")
                return
            self.player.gain_gold(gold_amount, dialogue=False)
            ansiprint(f"<green>Debug:</green> Added <yellow>{gold_amount} Gold</yellow>.")
            return
        self.player.gold = max(0, gold_amount)
        ansiprint(f"<green>Debug:</green> Gold set to <yellow>{self.player.gold}</yellow>.")

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


