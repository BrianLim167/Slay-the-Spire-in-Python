#!/usr/bin/env python3
from argparse import ArgumentParser

from game import Game
from pacing import set_speed_multiplier

if __name__ == '__main__':
    args = ArgumentParser(description="Run a game of Slay the Spire")
    args.add_argument('-s', '--seed', type=int, help="Seed to use for the game", default=None)
    args.add_argument('--debug', action='store_true', help="Enable debug commands while playing.")
    args.add_argument('--speed', type=float, default=0.1, help="Delay multiplier. 0 disables delays, 0.1 is 10x faster.")
    parsed_args = args.parse_args()
    set_speed_multiplier(parsed_args.speed)
    Game(seed=parsed_args.seed, debug=parsed_args.debug).start()
