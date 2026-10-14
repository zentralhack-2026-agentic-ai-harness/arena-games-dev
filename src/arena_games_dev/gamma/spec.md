# Game Gamma

## Overview

Three players compete for demand on a set of nodes. Every player can reach every node on every
turn, at no cost. Drones at a node capture a share of that node's demand proportional to the
capacity they bring, and every deployed drone costs upkeep. A player's profit is the demand it
serves minus the upkeep it pays, summed over the whole game.

When several players crowd the same node, most of that node's value is spent on upkeep.
Players who split the nodes between themselves earn much more than players who all compete
everywhere. To make such a split possible, the game alternates between two stages:

- a **negotiation stage**, where every player claims a set of nodes and answers the other
  players' claims with accept or deny;
- a **play stage** of 10 turns, where every player deploys its drones wherever it likes.

**Agreements are not binding.** The game records who claimed what and who accepted what, and
shows it to everyone, but it never stops a player from deploying anywhere. What a player does
with an agreement, its own or another's, is up to the strategy.

The demand is fixed during a play stage and reshuffled between nodes before the next
negotiation, so every split has to be negotiated again.

A match has no winner: what counts is the profit you collect, over all matches of a tournament
(see "Tournament and ranking").

This document is the complete definition of the game. You will not get the game's source code or
a simulator, so everything needed to write a strategy, or to build your own simulator, is here.
Your deliverable is one Python class, described in "Your strategy".

## Constants

Every constant in this document, as Python you can copy:

```python
N_PLAYERS = 3
N_CYCLES = 10
PLAY_TURNS_PER_CYCLE = 10  # 100 play turns in total
MAX_NEGOTIATION_ROUNDS = 5  # one round = a propose step and a respond step

DRONES_PER_PLAYER = 120
DRONE_CAPACITY = 5
UPKEEP = 2.0  # per deployed drone, per play turn
TOTAL_DEMAND = 1200  # the sum of all nodes' demand, the same in every play turn

N_NODES_RANGE = (9, 15)  # inclusive
NODE_WEIGHT_RANGE = (0.25, 1.75)
```

Total drone capacity is 3 × 120 × 5 = 1800, which is 1.5 times the total demand. A single
player's capacity (600) is half the total demand.

## Seeds

Each match is created from an integer seed. The seed fixes the number of nodes and the demand
of every cycle, before the first step. Nothing about the environment depends on what the
players do. In a tournament every table that plays the same seed faces exactly the same nodes
and demand.

You cannot reproduce a match's demand from its seed: the generator below is specified exactly in
distribution, not in its random number calls. Use it to generate demand of your own, for example
to test a strategy.

## Nodes and demand

There are `n_nodes` nodes, numbered `0` to `n_nodes - 1`. There is no graph, no base and no
travel: every drone can be at any node on every play turn.

1. Draw `n_nodes` uniformly from 9 to 15 (inclusive). It is the same for the whole match.
2. For each cycle `c = 0, ..., 9`, draw one weight per node, `w_i` uniformly from
   `NODE_WEIGHT_RANGE` (0.25 to 1.75), independently of every other cycle.
3. The demand of node `i` in cycle `c` is `TOTAL_DEMAND * w_i / sum(w)`, rounded to an `int`
   with the **largest remainder method**:
   - round every value down;
   - the units still missing to reach exactly `TOTAL_DEMAND` go, one each, to the nodes with
     the largest fractional parts (ties: lower node id first).

So the demand of every cycle is a list of `n_nodes` positive integers that **sums to exactly
1200**. A node's demand is at least 12 and at most 560 (the extremes of the weights), and
usually between 25 and 220. The demand of a cycle is the same on all
10 of its play turns. It is shown in the observation from the first negotiation step of that
cycle on. The demand of later cycles is not shown.

## Units

Each player has 120 drones, each with capacity 5. Drones are never created or destroyed.

On every play turn, each player chooses an **allocation**: how many of its drones are deployed at
each node. Drones that are not allocated to any node are in reserve: they cost nothing and earn
nothing. Any number of drones, from any players, may be at the same node. Moving drones is free
and instant: the allocation of one turn does not restrict the next.

Every deployed drone costs `UPKEEP = 2.0` per play turn (see "Scoring").

## Your strategy

A strategy is a Python class with two methods:

```python
class MyStrategy:
    def __init__(self, player_id: int) -> None:
        self.player_id = player_id  # 0, 1 or 2

    def act(self, obs: dict):
        ...  # the action for this step; its format depends on obs["phase"]
```

- A new instance is created for every match, with `player_id` 0, 1 or 2.
- `act` is called once per **step** (see "Game structure"), between 120 and 200 times per match.
  You can keep state on `self` between steps.
- Player ids are absolute: in the observation, lists indexed by player are indexed by player
  id, and your own entry is at `obs["player_id"]`.
- If `act` raises an exception, takes too long or crashes, you forfeit (see "End of game").

## Game structure

A match consists of 10 **cycles**. Each cycle is a negotiation stage followed by a play stage:

```
cycle 0: negotiation (1 to 5 rounds) → play turns 0 to 9
cycle 1: negotiation (1 to 5 rounds) → play turns 10 to 19
...
cycle 9: negotiation (1 to 5 rounds) → play turns 90 to 99 → end of the match
```

A **step** is one call of every player's `act`, all three at the same time, with no player
seeing the others' actions for that step. Each step is one of three **phases**, given in
`obs["phase"]`:

| phase | what you do | earns or costs |
|---|---|---|
| `"propose"` | claim a set of nodes | nothing |
| `"respond"` | accept or deny each other player's claim | nothing |
| `"play"` | allocate your drones | revenue minus upkeep (see "Scoring") |

### Negotiation

A negotiation stage consists of **rounds**. Each round has two steps:

1. **Propose.** Every player submits a **claim**: a list of node ids. A claim may be empty, may
   contain any nodes, and may overlap other players' claims. The game sorts each claim and
   removes duplicates.
2. **Respond.** Every player sees all three claims of this round and answers each of the other
   two players' claims with accept (`True`) or deny (`False`).

After the respond step:

- If **every claim is accepted by both other players** (the round is **unanimous**), the
  negotiation ends and the play stage begins.
- Otherwise, if this was the 5th round, the negotiation ends anyway and the play stage begins.
- Otherwise the next round starts with a new propose step. Claims from earlier rounds do not
  carry over: every round starts with fresh claims.

A negotiation therefore takes 1 to 5 rounds, i.e. 2 to 10 steps. The game does not check
whether the claims of a unanimous round overlap: accepting a claim that overlaps your own is
allowed.

The **record** of a cycle is its last round: the three claims and every player's answers. It is
in the observation for the rest of the match (see `records`). It means only what the players
make of it. In particular, it is still a valid record if the round was not unanimous: if
players 0 and 1 accepted each other's claims and player 2 accepted nothing, the record says
exactly that.

### Play

Every play step is one **play turn**. Every player returns an allocation; then the turn's profit
is paid out (see "Scoring"). After the 10th play turn of a cycle, the next cycle begins with its
negotiation, and the demand changes to that cycle's demand. After the 10th play turn of cycle 9,
the match ends.

Agreements are not enforced: an allocation may put drones on any node, whatever the record
says.

## Observation

Every step, your strategy's `act(obs)` receives a `dict` with the same keys in every phase:

```python
{
    "phase": str,  # "propose", "respond" or "play"
    "player_id": int,  # your player id: 0, 1 or 2
    "n_players": int,  # 3
    "n_nodes": int,  # node ids are 0 .. n_nodes - 1
    "drones_per_player": int,  # 120
    "drone_capacity": int,  # 5
    "upkeep": float,  # 2.0
    "n_cycles": int,  # 10
    "play_turns_per_cycle": int,  # 10
    "max_rounds": int,  # 5
    "cycle": int,  # current cycle, 0 .. 9
    "round": int,  # current negotiation round, 0 .. 4 (during play: the last round's)
    "turn": int,  # number of play turns completed so far, 0 .. 99
    "turn_in_cycle": int,  # play turns completed in this cycle, 0 .. 9
    "demand": list[int],  # length n_nodes: this cycle's demand per node
    "claims": list[list[int]] | None,  # "respond" only: this round's claims, index = player id
    "negotiation": list[dict],  # this cycle's completed rounds, oldest first (see below)
    "records": list[dict],  # one per completed negotiation of the match, oldest first
    "allocations_last_turn": list[list[int]],  # [player id][node]: last play turn's allocations
    "profit_last_turn": list[float],  # index = player id
    "cumulative_profit": list[float],  # index = player id
    "action_valid_last_step": bool,  # whether your action in the last step was valid
}
```

During a play turn, `turn` is the number of the turn being played: on play turn 37 (the 8th turn
of cycle 3), `turn` is 37 and `turn_in_cycle` is 7.

**`negotiation`** lists the completed rounds of the current cycle. Each entry is:

```python
{
    "claims": [[...], [...], [...]],  # index = player id, each sorted, without duplicates
    "accept": [[None, bool, bool], [bool, None, bool], [bool, bool, None]],
}
```

`accept[i][j]` is `True` if player `i` accepted player `j`'s claim. The diagonal is `None`. In the
propose step of round `r` the list has `r` entries; in the respond step it also has `r` entries
(the current round is in `claims`); during play it has all rounds of the cycle.

**`records`** has one entry per completed negotiation, i.e. per cycle whose play stage has
started. `records[c]` is the record of cycle `c`, so during play the current cycle's record is
`records[-1]`:

```python
{
    "cycle": int,
    "claims": [[...], [...], [...]],  # the last round's claims
    "accept": [[None, ...], ...],  # the last round's answers
    "unanimous": bool,  # whether the last round was unanimous
    "rounds": int,  # how many rounds the negotiation took, 1 .. 5
}
```

**`allocations_last_turn`**, **`profit_last_turn`** and **`cumulative_profit`** describe the
last play turn and stay unchanged during negotiation steps. In particular, during a
negotiation they show the last turn of the previous cycle, and on the first play turn of a cycle
the allocations are still those of the previous cycle (on different demand). Before the first
play turn of the match, all allocations are `0` and all profits `0.0`.

**`action_valid_last_step`** refers to your action in the previous step, whatever its phase. On
the first step of the match it is `True`.

You see all players' allocations, profits and negotiation actions. You do not see the demand of
later cycles.

## Action

The action is what `act` returns for one step. Its format depends on the phase:

| phase | action | example |
|---|---|---|
| `"propose"` | a `list` of node ids (`int`) | `[0, 4, 7]` |
| `"respond"` | a `dict` from player id (`int`) to `bool` | `{1: True, 2: False}` |
| `"play"` | a `list` of `n_nodes` non-negative `int`s with a sum of at most 120 | `[40, 0, 0, 25, 0, 0, 0, 0, 0]` |

Details:

- **Propose:** every item must be a node id, `0` to `n_nodes - 1`. Duplicates are allowed and
  removed. `[]` claims nothing.
- **Respond:** the keys must be the ids of the other players (not your own). A missing key
  counts as deny, so `{}` denies both claims.
- **Play:** entry `i` is the number of your drones at node `i` for this turn. Drones not
  allocated stay in reserve.

All values must be plain Python `int`s and `bool`s. `bool` is not accepted where an `int` is
expected, numpy integers such as `np.int64` are not accepted anywhere, and a tuple is not a
list. Convert them with `int(...)` and `list(...)`.

**An invalid action is replaced as a whole**, and the next observation has
`action_valid_last_step = False`:

| phase | an invalid action counts as |
|---|---|
| `"propose"` | the empty claim `[]` |
| `"respond"` | `{}`: deny both claims |
| `"play"` | your last valid allocation (all zeros before your first one): your drones stay where they are |

A play action is invalid if it is not a list of exactly `n_nodes` non-negative ints, or if its
sum is more than 120. There is no partial application: a play action over the fleet size
leaves all your drones where they were.

## Scoring

Only play turns are scored. After all three allocations of a play turn are known, each player's
profit for the turn is its **revenue** minus its **upkeep**.

**Revenue.** Each node's demand of this cycle is split between the players at that node:

```
capacity_i = drones_i * DRONE_CAPACITY
served_i   = capacity_i * demand / max(total_capacity, demand)
```

`total_capacity` is the sum of all three players' capacity at that node. The formula has two
cases:

- **Demand exceeds total capacity** (`total_capacity < demand`): every player serves its full
  capacity, `served_i = capacity_i`, and part of the demand goes unserved.
- **Total capacity meets or exceeds demand** (`total_capacity >= demand`): the demand is shared
  in proportion to capacity, `served_i = demand * capacity_i / total_capacity`.

A node with no drones contributes nothing. Your revenue for a turn is the sum of `served_i` over
all nodes.

**Upkeep.** You pay `UPKEEP = 2.0` for each drone in your allocation:

```
upkeep_i = UPKEEP * sum(allocation_i)
profit_i = revenue_i - upkeep_i
```

Profit can be negative. Your score in a match is the sum of your profits over all 100 play
turns. A player that never deploys scores exactly `0`.

For example, at a node with demand 100:

- 20 drones alone serve the whole demand (capacity 100), for a profit of `100 - 40 = 60`.
- 10 drones alone serve `50` (capacity 50 < 100), for a profit of `50 - 20 = 30`.
- 20, 10 and 10 drones from the three players (total capacity 200) serve `50`, `25` and `25`.
  After upkeep that is `10`, `5` and `5`: of the node's value of 60 for a single player, only 20
  is left.

### Worked example: one play turn

Three nodes with demand `[100, 60, 40]`. The players play:

- player 0: `[20, 0, 0]`
- player 1: `[5, 12, 0]`
- player 2: `[0, 0, 8]`

| node | demand | drones (P0, P1, P2) | total capacity | served (P0, P1, P2) |
|-----:|-------:|--------------------:|---------------:|--------------------:|
| 0    | 100    | 20, 5, 0            | 125            | 80, 20, 0           |
| 1    | 60     | 0, 12, 0            | 60             | 0, 60, 0            |
| 2    | 40     | 0, 0, 8             | 40             | 0, 0, 40            |

| player | revenue | deployed | upkeep | profit |
|-------:|--------:|---------:|-------:|-------:|
| P0     | 80.0    | 20       | 40.0   | 40.0   |
| P1     | 80.0    | 17       | 34.0   | 46.0   |
| P2     | 40.0    | 8        | 16.0   | 24.0   |

Player 1's 5 drones on node 0 earned 20 for 10 of upkeep, and cost player 0 another 20 of
revenue.

Profits are Python floats and can carry rounding error in their last digits; compare them with a
tolerance.

## End of game

The match ends after the 100th play turn (the 10th play turn of cycle 9). There is no winner:
each player's result is its score, the profit it collected.

Your strategy forfeits the rest of the match if it raises an exception, takes longer than
1 second for one call of `act` (10 seconds for `__init__`), or crashes. From that step on your
action is `None`, which is invalid in every phase (see "Action"): you claim nothing, you deny
every claim (so no later negotiation can be unanimous), and your drones stay deployed as on your
last valid play turn. They still take their share of each node's demand and still cost upkeep,
and both still count for your score. The match always plays on to the end, even if every player
has forfeited.

## Tournament and ranking

Your strategy plays a tournament at tables of three. Tables are drawn from all strategies in the
tournament (those of the other participants and a few reference strategies), so that every
strategy meets every other one about equally often, and a table never seats two copies of the
same strategy. Every table plays the same set of seeds, and each seed in all three seat
rotations, so every strategy plays every seat. A strategy does not learn which strategies it is
playing against.

Your result in a tournament is your **profit share**: the total profit your strategy collected in
all its matches, divided by the total profit collected by all strategies in the tournament.
Winning or losing a match does not count, only profit does: your own profit counts in full, the
other players' profit only through the tournament's total, which it shares with every other
strategy. Across games, the profit shares are averaged.
