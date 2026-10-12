from pathlib import Path

from arena_games_dev.gamma.baselines import (
    DoNothing,
    FairShare,
    Greedy,
    Grim,
    Raider,
    TitForTat,
)
from arena_games_dev.gamma.game import GammaGame

GAME = GammaGame
BASELINES = [DoNothing, Greedy, FairShare, Grim, TitForTat, Raider]
SPEC = Path(__file__).with_name("spec.md")

__all__ = ["BASELINES", "GAME", "SPEC", "GammaGame"]
