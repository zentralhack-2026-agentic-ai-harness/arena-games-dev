# arena-games-dev

The development games for Zentral Hack 2026. Each game is a subpackage with:

| file           | what                                                                 |
|----------------|----------------------------------------------------------------------|
| `spec.md`      | the complete written definition; the only thing a harness ever gets |
| `game.py`      | the simulator, an [`arena.Game`](https://github.com/zentralhack-2026-agentic-ai-harness/arena) |
| `baselines.py` | reference strategies                                                 |
| `__init__.py`  | exports `GAME`, `BASELINES` and `SPEC` (path to `spec.md`)           |

The source is here so that *you* can read it. Your harness must not: at evaluation time it only
receives the `spec.md` of a game it has never seen.

## Use as a dependency

```bash
uv add git+https://github.com/zentralhack-2026-agentic-ai-harness/arena-games-dev
```

This pulls in [`arena`](https://github.com/zentralhack-2026-agentic-ai-harness/arena), the engine
and CLI, as well.

## Develop

Requires [uv](https://docs.astral.sh/uv/). Python 3.13 is pinned in `.python-version`.

```bash
uv sync --extra render   # matplotlib, for the games' render() and the frame-dump tests
uv run pytest
```

`arena` is installed from its GitHub `main` branch, at the commit pinned in `uv.lock`. To pick up
a newer `arena`:

```bash
uv lock --upgrade-package arena && uv sync --extra render
```

To work on both repos at once, check them out side by side and layer your local `arena` over
the pinned one for a single command (nothing in this repo changes):

```bash
uv run --with-editable ../arena pytest
uv run --with-editable ../arena arena run --game arena_games_dev.alpha:AlphaGame ...
```

## Play

```bash
uv run arena run --game arena_games_dev.alpha:AlphaGame \
              --strategies arena_games_dev.alpha.baselines:DoNothing \
                           arena_games_dev.alpha.baselines:ProportionalSpread \
                           my_bot.py:MyBot
```

## Games

| game  | status |
|-------|--------|
| alpha | done   |
| beta  | draft: random map, upkeep, growing demand with a forecast window; balancing open |

## Render a match

Every game has `render()`, which returns a matplotlib figure of the current state. The tests dump
one PNG per turn to `outputs/` (gitignored), e.g. for beta:

```bash
uv run pytest tests/test_beta.py -k frames
```

Or for any seed and strategies:

```python
from arena_games_dev.beta import BetaGame
from arena_games_dev.beta.baselines import GreedyResponse, ProportionalSpread

game, players = BetaGame(seed=3), [GreedyResponse(0), ProportionalSpread(1)]
while not game.is_over():
    game.step([p.act(game.observe(p.player_id)) for p in players])
game.render().savefig("beta_seed3.png")
```
