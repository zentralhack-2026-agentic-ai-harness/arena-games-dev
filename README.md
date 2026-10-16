# arena-games-dev

The two development games of Zentral Hack 2026. Use them to build and test your harness. They are
not scored: the evaluation uses hidden games that your harness has never seen.

## Games

| game    | what it exercises                                                                    |
|---------|--------------------------------------------------------------------------------------|
| `alpha` | the basics: a fixed map, fixed demand, competing for shares of each node's demand    |
| `beta`  | planning: a random map per match, upkeep per drone, growing demand with a forecast   |

Both are 2-player matches over 100 turns. The player with the higher score wins, and the
tournament ranks results (win, draw, loss), not margins. The hidden games follow the same
contract, so what you learn here carries over.

## What each game contains

| file           | what                                                                      |
|----------------|---------------------------------------------------------------------------|
| `spec.md`      | the complete written definition of the game                               |
| `game.py`      | the simulator, an [`arena.Game`](https://github.com/zentralhack-2026-agentic-ai-harness/arena) |
| `baselines.py` | simple reference strategies                                               |
| `__init__.py`  | exports `GAME`, `BASELINES` and `SPEC` (the path to `spec.md`)            |

## The spec is all your harness gets

At evaluation time your harness receives only the `spec.md` of an unseen game: no source code, no
simulator, no baselines. The code here is for *you* to read, to understand the format and to check
your harness's work on the dev games. Your harness must not rely on it.

So treat the two `spec.md` files as the real reference. They show what a spec looks like:
the rules, the observation and action formats, the strategy interface, worked examples, and how
matches and the tournament are scored.
