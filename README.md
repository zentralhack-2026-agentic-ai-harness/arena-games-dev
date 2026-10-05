# arena-games-dev

The development games for Zentral Hack 2026. Each game is a subpackage with:

| file           | what                                                                 |
|----------------|----------------------------------------------------------------------|
| `spec.md`      | the complete written definition; the only thing a harness ever gets |
| `game.py`      | the simulator, an [`arena.Game`](https://github.com/<org>/arena)     |
| `baselines.py` | reference strategies                                                 |
| `__init__.py`  | exports `GAME`, `BASELINES` and `SPEC` (path to `spec.md`)           |

The source is here so that *you* can read it. Your harness must not: at evaluation time it only
receives the `spec.md` of a game it has never seen.

## Develop

```bash
uv sync --extra render
uv run pytest
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
