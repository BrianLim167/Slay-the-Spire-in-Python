#!/usr/bin/env python3
from argparse import ArgumentParser

from game import Game

if __name__ == '__main__':
    args = ArgumentParser(description="Run a game of Slay the Spire")
    args.add_argument('-s', '--seed', type=int, help="Seed to use for the game", default=None)
    args.add_argument('--debug', action='store_true', help="Enable debug commands while playing.")
    parsed_args = args.parse_args()
    Game(seed=parsed_args.seed, debug=parsed_args.debug).start()
