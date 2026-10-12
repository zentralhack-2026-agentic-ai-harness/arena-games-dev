"""Reference strategies for Gamma.

They are deliberately simple: every cooperative baseline claims the same fixed claim in every
round and judges other claims by one rule. None of them bargains.

Building blocks:

- `best_response`: the most profitable allocation against the other players' allocations of
  the last turn, optionally restricted to some nodes.
- `fair_split`: a deterministic balanced three-way split of the nodes. The cooperative
  baselines all use it, so they agree with each other; other strategies need not.
"""

import heapq

from arena.core import Strategy

from arena_games_dev.gamma.game import node_revenue


def best_response(
    demand: list[int],
    others: list[int],
    fleet: int,
    allowed: set[int] | None = None,
) -> list[int]:
    """Profit-maximising allocation against `others` (total drones of the others per node).

    Drones are added one at a time to the node where the next drone adds the most revenue
    minus upkeep, while that gain is positive. Revenue is concave in own drones, so this
    greedy allocation is exact for one turn. Nodes outside `allowed` get no drones.
    """
    n = len(demand)
    alloc = [0] * n

    def revenue(node: int, k: int) -> float:
        return node_revenue([k, others[node]], demand[node])[0]

    def gain(node: int) -> float:
        k = alloc[node]
        return revenue(node, k + 1) - revenue(node, k) - 2.0

    nodes = range(n) if allowed is None else sorted(allowed)
    heap = [(-gain(v), v) for v in nodes if demand[v] > 0]
    heapq.heapify(heap)
    for _ in range(fleet):
        if not heap:
            break
        neg_gain, node = heapq.heappop(heap)
        if -neg_gain <= 0:
            break
        alloc[node] += 1
        heapq.heappush(heap, (-gain(node), node))
    return alloc


def fair_split(demand: list[int], n_players: int) -> list[list[int]]:
    """Nodes by demand, largest first (ties: lower id), each to the player with the least
    demand so far (ties: lower player id). Returns one sorted node list per player."""
    parts: list[list[int]] = [[] for _ in range(n_players)]
    totals = [0] * n_players
    for node in sorted(range(len(demand)), key=lambda v: (-demand[v], v)):
        p = min(range(n_players), key=lambda q: (totals[q], q))
        parts[p].append(node)
        totals[p] += demand[node]
    return [sorted(part) for part in parts]


def _others_total(obs: dict) -> list[int]:
    me = obs["player_id"]
    allocations = obs["allocations_last_turn"]
    return [
        sum(allocations[p][node] for p in range(obs["n_players"]) if p != me)
        for node in range(obs["n_nodes"])
    ]


class DoNothing(Strategy):
    """Claims nothing, denies everything, never deploys. Always scores exactly 0."""

    def act(self, obs: dict):
        if obs["phase"] == "propose":
            return []
        if obs["phase"] == "respond":
            return {}
        return [0] * obs["n_nodes"]


class Greedy(Strategy):
    """Ignores negotiation: claims nothing and denies every claim. In play, best response to
    the other players' allocations of the last turn, on every node."""

    def act(self, obs: dict):
        if obs["phase"] == "propose":
            return []
        if obs["phase"] == "respond":
            return {}
        return best_response(obs["demand"], _others_total(obs), obs["drones_per_player"])


class FairShare(Strategy):
    """The naive cooperator.

    - Propose: its own part of `fair_split`, the same claim in every round.
    - Respond: accepts every claim that does not overlap its own claim.
    - Play: stays off every node in a claim it accepted in this cycle's final round, and
      plays the best response to last turn's allocations everywhere else. On its own nodes
      that is a monopoly if nobody intrudes, and a defence if somebody does.

    It never punishes. Subclasses fill `hostile` (players whose claims it denies and whose
    nodes it ignores) and change `raiding` (turns on which it ignores all claims).
    """

    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.hostile: set[int] = set()
        self.last_turn_seen = 0

    def act(self, obs: dict):
        if obs["turn"] > self.last_turn_seen:
            self.last_turn_seen = obs["turn"]
            self.after_play_turn(obs)
        if obs["phase"] == "propose":
            return self.claim(obs)
        if obs["phase"] == "respond":
            mine = set(self.claim(obs))
            return {
                other: other not in self.hostile and not mine & set(claim)
                for other, claim in enumerate(obs["claims"])
                if other != self.player_id
            }
        return self.play(obs)

    def claim(self, obs: dict) -> list[int]:
        return fair_split(obs["demand"], obs["n_players"])[self.player_id]

    def after_play_turn(self, obs: dict) -> None:
        """Hook: called once per play turn, at the first observation that shows its result."""

    def raiding(self, obs: dict) -> bool:
        return False

    def foreign_nodes(self, obs: dict) -> set[int]:
        """Nodes of claims this player accepted in the current cycle's final round."""
        record = obs["records"][-1]
        accepted = record["accept"][self.player_id]
        return {
            node
            for other, claim in enumerate(record["claims"])
            if other != self.player_id and accepted[other] and other not in self.hostile
            for node in claim
        }

    def play(self, obs: dict) -> list[int]:
        foreign = set() if self.raiding(obs) else self.foreign_nodes(obs)
        allowed = set(range(obs["n_nodes"])) - foreign
        return best_response(obs["demand"], _others_total(obs), obs["drones_per_player"], allowed)


def trespassers(obs: dict, me: int) -> set[int]:
    """Players that had drones, in the last play turn, on this player's claim after accepting
    that claim in the final round of that turn's cycle."""
    if obs["turn"] == 0:
        return set()
    record = obs["records"][(obs["turn"] - 1) // obs["play_turns_per_cycle"]]
    mine = record["claims"][me]
    allocations = obs["allocations_last_turn"]
    return {
        other
        for other in range(obs["n_players"])
        if other != me
        and record["accept"][other][me]
        and any(allocations[other][node] > 0 for node in mine)
    }


class Grim(FairShare):
    """FairShare until a player trespasses on its accepted claim; that player is hostile for
    the rest of the game (its claims are denied and its nodes no longer respected)."""

    def after_play_turn(self, obs: dict) -> None:
        self.hostile |= trespassers(obs, self.player_id)


class TitForTat(FairShare):
    """FairShare that punishes a trespasser until the end of the cycle after the trespass
    (that cycle's negotiation included), then forgives."""

    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.hostile_until: dict[int, int] = {}  # player -> last cycle of its punishment

    def act(self, obs: dict):
        self.hostile = {p for p, last in self.hostile_until.items() if obs["cycle"] <= last}
        return super().act(obs)

    def after_play_turn(self, obs: dict) -> None:
        trespass_cycle = (obs["turn"] - 1) // obs["play_turns_per_cycle"]
        for other in trespassers(obs, self.player_id):
            self.hostile_until[other] = trespass_cycle + 1
            self.hostile.add(other)


class Raider(FairShare):
    """FairShare, except on the last play turn of every cycle, when it plays the best
    response on every node, including the ones it agreed to leave alone."""

    def raiding(self, obs: dict) -> bool:
        return obs["turn_in_cycle"] == obs["play_turns_per_cycle"] - 1
