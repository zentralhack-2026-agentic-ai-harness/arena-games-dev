from pathlib import Path

from arena_games_dev.alpha.baselines import DoNothing, ProportionalSpread, RandomStrategy
from arena_games_dev.alpha.game import AlphaGame

GAME = AlphaGame
BASELINES = [DoNothing, RandomStrategy, ProportionalSpread]
SPEC = Path(__file__).with_name("spec.md")

__all__ = ["BASELINES", "GAME", "SPEC", "AlphaGame"]
