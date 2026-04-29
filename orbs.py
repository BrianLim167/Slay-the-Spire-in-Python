"""Orb system for the Defect character.

Orbs occupy orb slots and have two effects:
- Passive: triggered automatically at the end of the player's turn.
- Evoke: triggered when the orb is removed (either manually or to make room).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ansi_tags import ansiprint
from pacing import sleep

if TYPE_CHECKING:
    from player import Player


class Orb:
    """Base class for all orbs."""

    name: str = "Orb"
    passive_value: int = 0
    evoke_value: int = 0

    def effective_passive(self, focus: int) -> int:
        """Return the passive value adjusted by the player's Focus."""
        return self.passive_value + focus

    def effective_evoke(self, focus: int) -> int:
        """Return the evoke value adjusted by the player's Focus."""
        return self.evoke_value + focus

    def passive(self, player: Player, enemies: list) -> None:
        """Called at the end of the player's turn for each channeled orb."""
        raise NotImplementedError

    def evoke(self, player: Player, enemies: list) -> None:
        """Called when the orb is evoked (removed from its slot)."""
        raise NotImplementedError

    def display(self, focus: int = 0) -> str:
        return f"{self.name} {self.effective_passive(focus)} {self.effective_evoke(focus)}"

    def __repr__(self) -> str:
        return f"Orb({self.name})"


class Frost(Orb):
    """Frost orb.

    Passive: Gain 2 (+Focus) Block at end of turn.
    Evoke:   Gain 5 (+Focus) Block.
    """

    name = "Frost"
    passive_value = 2
    evoke_value = 5

    def passive(self, player: Player, enemies: list) -> None:
        value = self.effective_passive(player.focus)
        if value > 0:
            player.blocking(block=value, context="Frost passive")

    def evoke(self, player: Player, enemies: list) -> None:
        value = self.effective_evoke(player.focus)
        if value > 0:
            player.blocking(block=value, context="Frost evoke")


class Lightning(Orb):
    """Lightning orb.

    Passive: Deal 3 (+Focus) damage to a random enemy at end of turn.
    Evoke:   Deal 8 (+Focus) damage to a random enemy.
    """

    name = "Lightning"
    passive_value = 3
    evoke_value = 8

    def passive(self, player: Player, enemies: list) -> None:
        value = self.effective_passive(player.focus)
        if value <= 0:
            return
        living = [e for e in enemies if getattr(e, 'health', 0) > 0]
        if not living:
            return
        target = random.choice(living)
        self._deal_orb_damage(target, value, "Lightning passive")

    def evoke(self, player: Player, enemies: list) -> None:
        value = self.effective_evoke(player.focus)
        if value <= 0:
            return
        living = [e for e in enemies if getattr(e, 'health', 0) > 0]
        if not living:
            return
        target = random.choice(living)
        self._deal_orb_damage(target, value, "Lightning evoke")

    @staticmethod
    def _deal_orb_damage(target, dmg: int, source: str) -> None:
        """Deal non-attack damage to a target. Bypasses Vulnerable/Weak/etc."""
        if dmg <= target.block:
            target.block -= dmg
            ansiprint(f"<true-blue>{source}</true-blue> dealt {dmg} damage to {target.name} (<light-blue>Blocked</light-blue>)")
        else:
            dmg_after_block = dmg - target.block
            ansiprint(f"<true-blue>{source}</true-blue> dealt {dmg_after_block} damage(<light-blue>{target.block} Blocked</light-blue>) to {target.name}")
            target.block = 0
            target.health -= dmg_after_block
            if target.health <= 0:
                target.die()
