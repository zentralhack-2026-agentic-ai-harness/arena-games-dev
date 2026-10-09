# Game Beta

## Overview

Two players compete for demand on a graph over a fixed number of turns. Each turn, both players
move drones between nodes; drones present at a node capture a share of that node's demand
proportional to the capacity they bring. Every drone that is away from its home base costs
upkeep each turn. A player's profit is the demand it serves minus the upkeep it pays, summed
over the whole game. A match has no winner: what counts is the profit you collect, over all
matches of a tournament (see "Tournament and ranking").

What changes from match to match:

- **The map.** Every match is played on a different random graph with randomly placed bases.
  You learn it from the observation, at the start of the match.
- **The demand.** Demand changes from turn to turn and moves around the map. You see each node's
  demand for the current turn and the next few turns. The total demand over all nodes grows
  during the match, following a curve that is drawn at random for each match.

This document is the complete definition of the game. You will not get the game's source code or
a simulator, so everything needed to write a strategy, or to build your own simulator, is here.
Your deliverable is one Python class, described in "Your strategy".

## Constants

Every constant in this document, as Python you can copy:

```python
N_TURNS = 100
DRONES_PER_PLAYER = 30
DRONE_CAPACITY = 5
UPKEEP = 2.0  # per drone away from its own base, per turn
FORECAST_HORIZON = 5  # the forecast covers the current turn and the next 4

# map generator (see "Map")
N_NODES_RANGE = (10, 16)  # inclusive
EXTRA_EDGE_FRACTION = 0.4
MIN_BASE_DISTANCE = 3

# total demand curve (see "Demand")
D_START_RANGE = (40.0, 60.0)
D_END_RANGE = (110.0, 140.0)
CURVE_SHAPES = ("linear", "early", "late", "s_curve")
S_CURVE_MIDPOINT_RANGE = (0.3, 0.7)
S_CURVE_STEEPNESS_RANGE = (6.0, 12.0)

# per-node demand (see "Demand")
HUB_WEIGHT_SIGMA = 0.8
SHARE_AR_PHI = 0.95
SHARE_AR_SIGMA = 0.25
```

## Seeds

Each match is created from an integer seed. The seed fixes the map, the bases and the demand of
every turn, before the first turn is played. Nothing about the environment depends on what the
players do. In a tournament both players of a match, and every pairing that plays the same seed,
face exactly the same map and demand.

You cannot reproduce a match's map or demand from its seed: the generator below is specified
exactly in distribution, not in its random number calls. Use it to generate maps and demand of
your own, for example to test a strategy.

## Map

The map is an undirected, connected graph with `n_nodes` nodes, numbered `0` to `n_nodes - 1`.
Two of the nodes are bases, one per player. It is generated as follows:

1. Draw `n_nodes` uniformly from 10 to 16 (inclusive).
2. **Spanning tree.** Put the node ids in a uniformly random order `p[0], ..., p[n_nodes - 1]`.
   For `k = 1, ..., n_nodes - 1`, add the edge between `p[k]` and `p[j]`, with `j` drawn
   uniformly from `0, ..., k - 1`. This makes the graph connected.
3. **Extra edges.** Add `round(EXTRA_EDGE_FRACTION * n_nodes)` more edges (4 to 6; the value is
   never a tie). Each one connects a uniformly drawn pair of distinct nodes that are not
   connected yet.
4. **Bases.** Draw the base of player 0 uniformly from all nodes. Draw the base of player 1
   uniformly from the nodes whose shortest-path distance (in edges) from player 0's base is at
   least `MIN_BASE_DISTANCE` (3). If there is no such node, discard the graph and start again at
   step 1.

So no node is next to both bases, but the two bases can be in very different positions: one may
be central and close to the rich nodes, the other at the end of a long branch. The map is not
symmetric. Over a tournament this evens out, because every pairing plays each seed in both seats
(see "Tournament and ranking").

There are no self-loops and no duplicate edges. Every node except the two bases has demand
(see "Demand").

The map does not change during a match. It is in every observation: `n_nodes`, `edges`,
`player_base` and `opponent_base`.

## Demand

Each turn `t` (from `0` to `N_TURNS - 1 = 99`), every node `i` has a demand `demand[t][i] ≥ 0`.
Both bases have demand `0` on every turn. The demand of the other nodes is the **total demand**
`D(t)` of that turn, split between them by **weights** `w_i(t)`.

### Total demand

```
D(t) = D_start + (D_end - D_start) * s(t / 99)
```

At the start of the match, draw:

- `D_start` uniformly from `D_START_RANGE` (40 to 60),
- `D_end` uniformly from `D_END_RANGE` (110 to 140),
- the shape `s` uniformly from the four `CURVE_SHAPES`.

Each shape is a non-decreasing function on `[0, 1]` with `s(0) = 0` and `s(1) = 1`:

| shape     | `s(x)`                                        | growth                         |
|-----------|-----------------------------------------------|--------------------------------|
| `linear`  | `x`                                           | steady                         |
| `early`   | `1 - (1 - x)**2`                              | fast at first, then levels off |
| `late`    | `x**2`                                        | slow at first, then fast       |
| `s_curve` | `(L(x) - L(0)) / (L(1) - L(0))`               | slow, fast, slow               |

with `L(x) = 1 / (1 + exp(-k * (x - m)))`, where the midpoint `m` is drawn uniformly from
`S_CURVE_MIDPOINT_RANGE` (0.3 to 0.7) and the steepness `k` uniformly from
`S_CURVE_STEEPNESS_RANGE` (6 to 12).

So the total demand grows from somewhere between 40 and 60 on turn 0 to somewhere between 110 and
140 on turn 99. **The observation does not tell you `D_start`, `D_end`, the shape or its
parameters.** You only see the demand of the forecast window (see "Observation").

### Weights

Each non-base node `i` has a fixed **hub weight** and a **drift** that changes every turn:

```
hub_i      = exp(HUB_WEIGHT_SIGMA * g_i)                              # g_i ~ N(0, 1), drawn once
drift_i(0) = 0
drift_i(t + 1) = SHARE_AR_PHI * drift_i(t) + SHARE_AR_SIGMA * e_i(t)   # e_i(t) ~ N(0, 1)
w_i(t)     = hub_i * exp(drift_i(t))
```

All `g_i` and `e_i(t)` are independent standard normal draws. Hub weights make some nodes rich
for the whole match; the drift moves demand between nodes over time, slowly (`SHARE_AR_PHI =
0.95`) but with noticeable changes from one turn to the next.

### Demand per node

```
demand[t][i] = round(D(t) * w_i(t) / W(t), 1)      # W(t) = sum of w_j(t) over all non-base nodes j
```

Demand is rounded to one decimal (Python's `round`). Because of rounding, the demands of a turn
add up to `D(t)` only approximately. A node's demand can round to `0.0`.

## Units

Each player has 30 drones, and all of them start at their base. Every drone has capacity 5.

Drones are never created or destroyed, so each player has exactly 30 drones for the whole game.
Any number of drones, from either player, may be at the same node. Drones may move onto any node,
including the opponent's base.

A drone is **deployed** when it is not on its own player's base. Every deployed drone costs
`UPKEEP = 2.0` per turn (see "Scoring"), including drones on the opponent's base and drones on
nodes without demand. Drones on their own base cost nothing and earn nothing.

## Your strategy

A strategy is a Python class with two methods:

```python
class MyStrategy:
    def __init__(self, player_id: int) -> None:
        self.player_id = player_id  # 0 or 1

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        return []  # this turn's moves; see "Observation" and "Action"
```

- A new instance is created for every match, with `player_id` 0 or 1.
- `act` is called once per turn, 100 times per match. You can keep state on `self` between turns.
- The map is not known in `__init__`. It is in every observation; a strategy that needs
  precomputed data about the map (distances, paths) typically builds it on the first call of
  `act` and keeps it on `self`.
- Everything in the observation is from your point of view (`player_*` fields are yours,
  `opponent_*` fields are the opponent's), so you do not need `player_id` to play.
- If `act` raises an exception, takes too long or crashes, you forfeit the rest of the match (see
  "End of game").

## Turn order

Each turn:

1. both players' `act(obs)` are called with the observation for the current turn,
2. each returns its action (a list of moves),
3. both players' moves are applied, then that turn's profit is paid out (see "Scoring"), then
   the turn number goes up by one.

Moves are simultaneous: neither player sees the other's moves for this turn before choosing its
own. Each player only moves its own drones, so the order in which the two players' moves are
applied makes no difference.

**Each drone moves at most one edge per turn.** A move can only use drones that were at
`from_node` at the start of the turn. Drones that arrive at a node during a turn cannot move on
until the next turn. For example, if your base is node 8 and it is connected to node 0, which is
connected to node 5, then `[(8, 0, 20), (0, 5, 20)]` from the start position moves 20 drones to
node 0, and the second move is illegal.

The payout of turn `t` uses `demand[t]`, the demand of that same turn, and the drone positions
after that turn's moves.

## Observation

Each turn your strategy's `act(obs)` receives a `dict`:

```python
{
    "turn": int,  # current turn, starting at 0
    "n_nodes": int,  # number of nodes; node ids are 0 .. n_nodes - 1
    "edges": list[tuple[int, int]],  # every undirected edge once, as (u, v) with u < v, sorted
    "player_base": int,  # node id of your base
    "opponent_base": int,  # node id of the opponent's base
    "demand_forecast": list[list[float]],  # length n_nodes, see below
    "player_drones": list[int],  # length n_nodes, index = node id: your drones at that node
    "opponent_drones": list[int],  # length n_nodes, index = node id: opponent's drones at that node
    "player_profit_last_turn": float,  # your profit in the last turn (can be negative)
    "opponent_profit_last_turn": float,  # the opponent's profit in the last turn
    "player_cumulative_profit": float,  # your total profit so far
    "opponent_cumulative_profit": float,  # the opponent's total profit so far
    "n_invalid_actions_last_turn": int,  # number of your illegal moves in the last turn
    "action_format_correct_last_turn": bool,  # whether your last action was well-formed
}
```

**`demand_forecast`** has one list per node: `demand_forecast[i][k]` is `demand[turn + k][i]`,
the demand of node `i` on turn `turn + k`.

- `k = 0` is the demand of the **current turn**: the one your moves of this turn will be paid on.
- Each list has `min(FORECAST_HORIZON, N_TURNS - turn)` entries: 5, except on the last four turns
  (on turn 99 only the current turn is left).
- The forecast is exact: these are the values the payouts will use.
- Both bases are included, with demand `0.0`.

You see the whole map, the positions of all drones and both players' profits. You do not see
demand beyond the forecast window or the parameters of the demand curve. The total number of
turns is not in the observation (see "End of game").

On turn 0 there is no last turn yet: all `*_profit_last_turn` and `*_cumulative_profit` fields
are `0.0`, `n_invalid_actions_last_turn` is `0`, and `action_format_correct_last_turn` is `True`.

## Action

Terms used below: an **action** is what `act` returns for one turn. It is a list of **moves**.

```python
[(from_node, to_node, count), ...]
```

- Each move sends `count` of your drones from `from_node` to `to_node` along one edge.
- An empty list means "do nothing". Drones that are not moved stay where they are.
- Moves in the list are applied in order.

Two things can go wrong, and next turn's observation reports them separately.

**Malformed action:** the whole action is ignored for that turn, as if you had returned `[]`.
Next turn, `action_format_correct_last_turn` is `False` and `n_invalid_actions_last_turn` is `0`,
because no move was looked at. The format is checked strictly:

- the action must be a `list` (not a tuple, not `None`, not any other type),
- each move must be a `tuple` of exactly 3 items (a list like `[0, 1, 5]` is malformed),
- each item must be a plain Python `int`. `bool` values and numpy integers such as `np.int64`
  are malformed. Convert them with `int(...)`.

**Illegal move:** the action is well-formed, but one move breaks a rule. Only that move is
skipped, the rest of the list still applies, and it adds 1 to `n_invalid_actions_last_turn`. A
move is illegal if:

- `from_node` or `to_node` is not a node id (`0` to `n_nodes - 1`),
- `from_node` and `to_node` are not connected by an edge (this includes `from_node == to_node`),
- `count` is negative,
- `count` is more than the drones you still have at `from_node` from the start of the turn, after
  earlier moves in the same list (see "Turn order").

A move with `count` 0 is legal and does nothing.

## Scoring

After all moves are applied, each player's profit for the turn is its **revenue** minus its
**upkeep**.

**Revenue.** Each node's demand of this turn is split between the players at that node:

```
capacity_i = drones_i * drone_capacity                       # drone_capacity = 5
served_i   = capacity_i * demand / max(total_capacity, demand)
```

`total_capacity` is the sum of both players' capacity at that node. The formula has two cases:

- **Demand exceeds total capacity** (`total_capacity < demand`): every player serves its full
  capacity, `served_i = capacity_i`, and part of the demand goes unserved.
- **Total capacity meets or exceeds demand** (`total_capacity >= demand`): the demand is shared
  in proportion to capacity, `served_i = demand * capacity_i / total_capacity`.

A node with no demand or no drones contributes nothing. Your revenue for a turn is the sum of
`served_i` over all nodes.

**Upkeep.** You pay `UPKEEP = 2.0` for each of your drones that is not on your own base after
this turn's moves:

```
upkeep_i = UPKEEP * (DRONES_PER_PLAYER - drones_i at own base)
profit_i = revenue_i - upkeep_i
```

Profit can be negative. Your score in a match is the sum of your profits over all turns. A player
that never moves scores exactly `0`.

For example, at a node with demand 12.0:

- 2 drones alone serve `min(10, 12) = 10`, for a profit of `10 - 2 * 2.0 = 6.0` from that node.
- 3 drones alone serve `12` (capacity 15 meets the demand), for a profit of `12 - 6.0 = 6.0`: the
  third drone pays its upkeep but adds only 2 of revenue.
- 2 of your drones against 3 of the opponent's serve `12 * 10 / 25 = 4.8` for you and `7.2` for
  the opponent. After upkeep that is `0.8` for you and `1.2` for the opponent: most of the
  node's value is spent on upkeep.

### Worked example: turns 0 and 1

This is a real map (`n_nodes = 10`) with a "late" demand curve. Player 0's observation on turn 0
is:

```python
{
    "turn": 0,
    "n_nodes": 10,
    "edges": [(0, 8), (1, 2), (1, 4), (1, 8), (1, 9), (2, 7), (3, 4), (3, 6), (4, 6), (4, 7),
              (5, 9), (6, 7), (7, 9)],
    "player_base": 8,
    "opponent_base": 3,
    "demand_forecast": [
        [13.0, 16.5, 9.5, 8.9, 11.1],  # node 0
        [0.6, 0.5, 0.7, 0.5, 0.6],  # node 1
        [2.0, 1.6, 2.5, 2.3, 2.1],  # node 2
        [0.0, 0.0, 0.0, 0.0, 0.0],  # node 3: player 1's base
        [12.3, 8.0, 13.0, 13.1, 11.7],  # node 4
        [7.0, 8.8, 10.2, 8.7, 7.4],  # node 5
        [2.6, 2.9, 3.8, 5.3, 6.1],  # node 6
        [1.1, 0.6, 1.0, 0.8, 1.1],  # node 7
        [0.0, 0.0, 0.0, 0.0, 0.0],  # node 8: player 0's base
        [4.7, 4.4, 2.9, 3.8, 3.6],  # node 9
    ],
    "player_drones":   [0, 0, 0, 0, 0, 0, 0, 0, 30, 0],
    "opponent_drones": [0, 0, 0, 30, 0, 0, 0, 0, 0, 0],
    "player_profit_last_turn": 0.0,
    "opponent_profit_last_turn": 0.0,
    "player_cumulative_profit": 0.0,
    "opponent_cumulative_profit": 0.0,
    "n_invalid_actions_last_turn": 0,
    "action_format_correct_last_turn": True,
}
```

Player 1's observation is the same, except that `player_base` is `3`, `opponent_base` is `8`,
and the two drone lists are swapped.

- Player 0 plays `[(8, 0, 3), (8, 1, 1)]`.
- Player 1 plays `[(3, 4, 4), (3, 6, 1)]`.

No node is contested. The payout uses the turn-0 demand (`demand_forecast[i][0]`):

| node | demand | drones | capacity | served |
|-----:|-------:|-------:|---------:|-------:|
| 0    | 13.0   | P0: 3  | 15       | 13.0   |
| 1    | 0.6    | P0: 1  | 5        | 0.6    |
| 4    | 12.3   | P1: 4  | 20       | 12.3   |
| 6    | 2.6    | P1: 1  | 5        | 2.6    |

| player | revenue | deployed | upkeep | profit |
|-------:|--------:|---------:|-------:|-------:|
| P0     | 13.6    | 4        | 8.0    | 5.6    |
| P1     | 14.9    | 5        | 10.0   | 4.9    |

Player 0's drone on node 1 lost money (0.6 revenue for 2.0 upkeep), and so did its third drone
on node 0. Player 0's observation on turn 1 is then:

```python
{
    "turn": 1,
    "n_nodes": 10,
    "edges": [...],  # unchanged
    "player_base": 8,
    "opponent_base": 3,
    "demand_forecast": [
        [16.5, 9.5, 8.9, 11.1, 9.0],  # node 0: the window moved on by one turn
        [0.5, 0.7, 0.5, 0.6, 0.5],
        [1.6, 2.5, 2.3, 2.1, 1.9],
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [8.0, 13.0, 13.1, 11.7, 13.8],
        [8.8, 10.2, 8.7, 7.4, 8.1],
        [2.9, 3.8, 5.3, 6.1, 6.1],
        [0.6, 1.0, 0.8, 1.1, 1.5],
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [4.4, 2.9, 3.8, 3.6, 2.8],
    ],
    "player_drones":   [3, 1, 0, 0, 0, 0, 0, 0, 26, 0],
    "opponent_drones": [0, 0, 0, 25, 4, 0, 1, 0, 0, 0],
    "player_profit_last_turn": 5.6,
    "opponent_profit_last_turn": 4.9,
    "player_cumulative_profit": 5.6,
    "opponent_cumulative_profit": 4.9,
    "n_invalid_actions_last_turn": 0,
    "action_format_correct_last_turn": True,
}
```

Profits are Python floats and can carry rounding error in their last digits (for example
`5.6000000000000005`); compare them with a tolerance.

## End of game

The game ends after 100 turns (turns 0 to 99). There is no winner: each player's result is its
score, the profit it collected.

Your strategy forfeits the rest of the match if it raises an exception, takes longer than
1 second for one call of `act` (10 seconds for `__init__`), or crashes. You keep the profit
collected until then. From that turn on your moves are empty: your drones stay where they are and
still take their share of each node's demand, but nothing they collect or cost counts for you
any more. The opponent plays on to the end.

## Tournament and ranking

Your strategy plays a tournament: every strategy in it (those of the other participants and a few
reference strategies) plays every other one, in both seats, on the same set of seeds. A separate
tournament is played for each game and each budget setting.

Your result in a tournament is your **profit share**: the total profit your strategy collected in
all its matches, divided by the total profit collected by all strategies in the tournament.
Winning or losing a match does not count, only profit does: your own profit counts in full, an
opponent's profit only through the tournament's total, which it shares with every other strategy.
Across games, the profit shares are averaged.
