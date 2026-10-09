"""Reference strategies for Beta.

The map differs per match, so every strategy builds its graph from the first observation.
"""

import heapq
import random
from collections import Counter

from arena.core import Strategy

from arena_games_dev.beta.game import DRONE_CAPACITY, DRONES_PER_PLAYER, UPKEEP, hop_distances


class _MapAware(Strategy):
    """Caches neighbours and hop distances from the first observation."""

    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.neighbours: list[list[int]] | None = None
        self.dist: list[list[int]] = []

    def _setup(self, obs: dict) -> None:
        if self.neighbours is not None:
            return
        n = obs["n_nodes"]
        self.neighbours = [[] for _ in range(n)]
        for u, v in obs["edges"]:
            self.neighbours[u].append(v)
            self.neighbours[v].append(u)
        self.dist = hop_distances(n, obs["edges"])

    def _move_towards(self, drones: list[int], target: list[int]) -> list[tuple[int, int, int]]:
        """Move surplus drones one hop towards the nearest deficit nodes.

        Surplus and deficit are greedily paired by distance (closest pairs first); every
        paired drone takes one hop along a shortest path. All moves are legal.
        """
        assert self.neighbours is not None
        surplus = {n: drones[n] - t for n, t in enumerate(target) if drones[n] > t}
        deficit = {n: t - drones[n] for n, t in enumerate(target) if drones[n] < t}

        moves: Counter[tuple[int, int]] = Counter()
        pairs = sorted((self.dist[s][d], s, d) for s in surplus for d in deficit)
        for _, src, dst in pairs:
            k = min(surplus[src], deficit[dst])
            if k == 0:
                continue
            surplus[src] -= k
            deficit[dst] -= k
            hop = min(
                v for v in self.neighbours[src] if self.dist[v][dst] == self.dist[src][dst] - 1
            )
            moves[(src, hop)] += k
        return [(src, hop, k) for (src, hop), k in moves.items()]


class DoNothing(Strategy):
    """Never moves. Pays no upkeep and earns nothing: always exactly 0."""

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        return []


class RandomStrategy(_MapAware):
    """Scatters drones randomly over each occupied node and its neighbours.

    The RNG is seeded from player_id so matches stay reproducible.
    """

    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.rng = random.Random(player_id)

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        self._setup(obs)
        assert self.neighbours is not None
        moves = []
        for node, count in enumerate(obs["player_drones"]):
            if count <= 0:
                continue
            options = [node, *self.neighbours[node]]
            weights = [self.rng.random() for _ in options]
            destinations = Counter(self.rng.choices(options, weights=weights, k=count))
            for to_node, n in destinations.items():
                if to_node != node:
                    moves.append((node, to_node, n))
        return moves


class ProportionalSpread(_MapAware):
    """Alpha's ProportionalSpread, re-targeted every turn: all drones out, spread by demand.

    Ignores upkeep and the opponent. The target splits the whole fleet over the nodes in
    proportion to this turn's demand (largest remainder).
    """

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        self._setup(obs)
        demand = [f[0] for f in obs["demand_forecast"]]
        total = sum(demand)
        exact = [DRONES_PER_PLAYER * d / total for d in demand]
        target = [int(x) for x in exact]
        by_remainder = sorted(range(len(demand)), key=lambda n: target[n] - exact[n])
        for node in by_remainder[: DRONES_PER_PLAYER - sum(target)]:
            target[node] += 1
        return self._move_towards(obs["player_drones"], target)


def _served(own: int, other: int, demand: float) -> float:
    """Revenue of `own` drones against `other` drones at a node with `demand`."""
    cap, total = own * DRONE_CAPACITY, (own + other) * DRONE_CAPACITY
    if cap == 0 or demand == 0:
        return 0.0
    return cap * demand / max(total, demand)


class GreedyResponse(_MapAware):
    """Best response to where the opponent is now, net of upkeep, ignoring travel.

    Each turn, for every node, the demand is the mean of the forecast window. Drones are
    assigned one at a time to the node where the next drone adds the most revenue minus
    upkeep, against the opponent's current drones there, as long as that gain is positive
    (revenue is concave in own drones, so this greedy allocation is exact for one turn).
    Unassigned drones go home. Every drone then moves one hop towards its target.

    What it ignores: upkeep paid while travelling, how long demand lasts, and the
    opponent's reaction.
    """

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        self._setup(obs)
        base = obs["player_base"]
        opponent = obs["opponent_drones"]
        demand = [sum(f) / len(f) for f in obs["demand_forecast"]]

        target = [0] * obs["n_nodes"]

        def gain(node: int) -> float:
            k = target[node]
            return (
                _served(k + 1, opponent[node], demand[node])
                - _served(k, opponent[node], demand[node])
                - UPKEEP
            )

        heap = [(-gain(n), n) for n in range(obs["n_nodes"]) if n != base and demand[n] > 0]
        heapq.heapify(heap)
        for _ in range(DRONES_PER_PLAYER):
            if not heap:
                break
            neg_gain, node = heapq.heappop(heap)
            if -neg_gain <= 0:
                break
            target[node] += 1
            heapq.heappush(heap, (-gain(node), node))

        target[base] = DRONES_PER_PLAYER - sum(target)
        return self._move_towards(obs["player_drones"], target)
