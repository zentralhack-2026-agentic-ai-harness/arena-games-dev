from pathlib import Path

from arena_games_dev.beta.baselines import (
    DoNothing,
    GreedyResponse,
    ProportionalSpread,
    RandomStrategy,
)
from arena_games_dev.beta.game import BetaGame

GAME = BetaGame
BASELINES = [DoNothing, RandomStrategy, ProportionalSpread, GreedyResponse]
SPEC = Path(__file__).with_name("spec.md")

__all__ = ["BASELINES", "GAME", "SPEC", "BetaGame"]
