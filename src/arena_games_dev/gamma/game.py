"""
Gamma Game: three players share a fully connected map and negotiate who serves which nodes.

The game runs in cycles. Each cycle starts with a negotiation stage (rounds of claims and
accept/deny answers) and continues with a play stage of PLAY_TURNS_PER_CYCLE turns, in which
every player deploys drones freely. Agreements are not binding. Demand is constant within a
cycle and reshuffled for the next one; the total demand is the same in every cycle.

Everything random (number of nodes, demand of every cycle) is drawn from the seed when the game
is created, so every table that plays a seed faces exactly the same environment.
"""

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from arena.core import Game

if TYPE_CHECKING:
    from matplotlib.figure import Figure

N_PLAYERS = 3
N_CYCLES = 10
PLAY_TURNS_PER_CYCLE = 10
MAX_NEGOTIATION_ROUNDS = 5  # one round = a propose step and a respond step

DRONE_CAPACITY = 5
UPKEEP = 2.0  # per deployed drone, per play turn
TOTAL_DEMAND = 1200  # D: the sum of all nodes' demand, the same in every play turn
RHO = 1.5  # total drone capacity of all players / TOTAL_DEMAND
DRONES_PER_PLAYER = round(RHO * TOTAL_DEMAND / (N_PLAYERS * DRONE_CAPACITY))  # 120

N_NODES_RANGE = (9, 15)  # inclusive, drawn once per game
NODE_WEIGHT_RANGE = (0.25, 1.75)  # relative node sizes, redrawn every cycle

PHASES = ("propose", "respond", "play")


@dataclass(frozen=True)
class Instance:
    """Everything a match's environment consists of, fixed at creation."""

    n_nodes: int
    demand: list[list[int]]  # demand[cycle][node], every row sums to TOTAL_DEMAND


def largest_remainder(weights: list[float], total: int) -> list[int]:
    """Integers proportional to `weights` that sum to exactly `total`.

    Every entry is first rounded down; the units still missing go to the entries with the
    largest remainders (ties: lower index first).
    """
    weight_sum = sum(weights)
    exact = [total * w / weight_sum for w in weights]
    out = [int(x) for x in exact]
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - out[i]), i))
    for i in order[: total - sum(out)]:
        out[i] += 1
    return out


def generate_instance(seed: int) -> Instance:
    """The match environment for `seed`. Every cycle's demand uses its own RNG stream."""
    map_rng = random.Random(f"gamma:{seed}:map")
    n_nodes = map_rng.randint(*N_NODES_RANGE)
    demand = []
    for cycle in range(N_CYCLES):
        rng = random.Random(f"gamma:{seed}:demand:{cycle}")
        weights = [rng.uniform(*NODE_WEIGHT_RANGE) for _ in range(n_nodes)]
        demand.append(largest_remainder(weights, TOTAL_DEMAND))
    return Instance(n_nodes, demand)


def node_revenue(drones: list[int], demand: float) -> list[float]:
    """Split one node's demand between the players, proportional to capacity.

    capacity_i = drones_i * drone_capacity
    served_i   = capacity_i * demand / max(total_capacity, demand)
    """
    capacity = [d * DRONE_CAPACITY for d in drones]
    total = sum(capacity)
    if demand == 0 or total == 0:
        return [0.0] * len(drones)
    return [c * demand / max(total, demand) for c in capacity]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class GammaGame(Game):
    n_players = N_PLAYERS  # seats, read by arena
    N_PLAYERS = N_PLAYERS
    N_CYCLES = N_CYCLES
    PLAY_TURNS_PER_CYCLE = PLAY_TURNS_PER_CYCLE
    N_TURNS = N_CYCLES * PLAY_TURNS_PER_CYCLE
    MAX_NEGOTIATION_ROUNDS = MAX_NEGOTIATION_ROUNDS
    DRONES_PER_PLAYER = DRONES_PER_PLAYER
    DRONE_CAPACITY = DRONE_CAPACITY
    UPKEEP = UPKEEP
    TOTAL_DEMAND = TOTAL_DEMAND

    def __init__(self, seed: int | None = None, instance: Instance | None = None) -> None:
        """Create the match for `seed`; `instance` overrides the generator (for tests)."""
        super().__init__(seed)
        if instance is None:
            if seed is None:
                seed = random.SystemRandom().randrange(2**31)
            instance = generate_instance(seed)
        self.instance = instance
        self.n_nodes = instance.n_nodes
        self.demand = instance.demand

        n = self.N_PLAYERS
        self.phase = "propose"
        self.cycle = 0
        self.round = 0
        self.turn = 0  # play turns completed
        self.turn_in_cycle = 0

        # Negotiation of the current cycle: one {"claims", "accept"} entry per completed round.
        self.negotiation: list[dict] = []
        # Every cycle's negotiation (entry c is cycle c's list), for analysis and rendering.
        self.negotiation_log: list[list[dict]] = [self.negotiation]
        self.claims: list[list[int]] | None = None  # this round's claims, during "respond"
        # One record per completed negotiation (the current cycle's included, once in play).
        self.records: list[dict] = []

        self.allocation = [[0] * self.n_nodes for _ in range(n)]
        self.revenue_last_turn = [0.0] * n
        self.upkeep_last_turn = [0.0] * n
        self.profit_last_turn = [0.0] * n
        self.cumulative_profit = [0.0] * n
        self.action_valid_last_step = [True] * n
        # One entry per play turn: (allocations, profits), for analysis and rendering.
        self.history: list[tuple[list[list[int]], list[float]]] = []

    # ------------------------------------------------------------------ observation

    def observe(self, player_id: int) -> dict:
        return {
            "phase": self.phase,
            "player_id": player_id,
            "n_players": self.N_PLAYERS,
            "n_nodes": self.n_nodes,
            "drones_per_player": self.DRONES_PER_PLAYER,
            "drone_capacity": self.DRONE_CAPACITY,
            "upkeep": self.UPKEEP,
            "n_cycles": self.N_CYCLES,
            "play_turns_per_cycle": self.PLAY_TURNS_PER_CYCLE,
            "max_rounds": self.MAX_NEGOTIATION_ROUNDS,
            "cycle": self.cycle,
            "round": self.round,
            "turn": self.turn,
            "turn_in_cycle": self.turn_in_cycle,
            "demand": list(self.demand[self.cycle]),
            "claims": None if self.claims is None else [list(c) for c in self.claims],
            "negotiation": _copy_rounds(self.negotiation),
            "records": _copy_rounds(self.records),
            "allocations_last_turn": [list(a) for a in self.allocation],
            "profit_last_turn": list(self.profit_last_turn),
            "cumulative_profit": list(self.cumulative_profit),
            "action_valid_last_step": self.action_valid_last_step[player_id],
        }

    # ------------------------------------------------------------------ step

    def step(self, actions: list[Any]) -> None:
        if len(actions) != self.N_PLAYERS:
            raise ValueError(f"expected {self.N_PLAYERS} actions, got {len(actions)}")
        if self.phase == "propose":
            self._step_propose(actions)
        elif self.phase == "respond":
            self._step_respond(actions)
        else:
            self._step_play(actions)

    def _step_propose(self, actions: list[Any]) -> None:
        claims = []
        for player_id, action in enumerate(actions):
            claim = self._parse_claim(action)
            self.action_valid_last_step[player_id] = claim is not None
            claims.append(claim if claim is not None else [])
        self.claims = claims
        self.phase = "respond"

    def _step_respond(self, actions: list[Any]) -> None:
        assert self.claims is not None
        n = self.N_PLAYERS
        accept: list[list[bool | None]] = [[None] * n for _ in range(n)]
        for player_id, action in enumerate(actions):
            answers = self._parse_answers(action, player_id)
            self.action_valid_last_step[player_id] = answers is not None
            for other in range(n):
                if other != player_id:
                    accept[player_id][other] = bool(answers and answers.get(other, False))

        self.negotiation.append({"claims": self.claims, "accept": accept})
        self.claims = None
        unanimous = all(accept[i][j] for i in range(n) for j in range(n) if i != j)
        if unanimous or self.round == self.MAX_NEGOTIATION_ROUNDS - 1:
            last = self.negotiation[-1]
            self.records.append(
                {
                    "cycle": self.cycle,
                    "claims": last["claims"],
                    "accept": last["accept"],
                    "unanimous": unanimous,
                    "rounds": len(self.negotiation),
                }
            )
            self.phase = "play"
        else:
            self.round += 1
            self.phase = "propose"

    def _step_play(self, actions: list[Any]) -> None:
        for player_id, action in enumerate(actions):
            allocation = self._parse_allocation(action)
            self.action_valid_last_step[player_id] = allocation is not None
            if allocation is not None:  # an invalid action (or None) keeps the last allocation
                self.allocation[player_id] = allocation

        n = self.N_PLAYERS
        demand = self.demand[self.cycle]
        revenue = [0.0] * n
        for node in range(self.n_nodes):
            served = node_revenue([self.allocation[p][node] for p in range(n)], demand[node])
            for p in range(n):
                revenue[p] += served[p]
        self.revenue_last_turn = revenue
        self.upkeep_last_turn = [self.UPKEEP * sum(a) for a in self.allocation]
        self.profit_last_turn = [r - u for r, u in zip(revenue, self.upkeep_last_turn, strict=True)]
        for p in range(n):
            self.cumulative_profit[p] += self.profit_last_turn[p]
        self.history.append(([list(a) for a in self.allocation], list(self.profit_last_turn)))

        self.turn += 1
        self.turn_in_cycle += 1
        if self.turn_in_cycle == self.PLAY_TURNS_PER_CYCLE and self.cycle < self.N_CYCLES - 1:
            self.cycle += 1
            self.round = 0
            self.turn_in_cycle = 0
            self.negotiation = []
            self.negotiation_log.append(self.negotiation)
            self.phase = "propose"

    def is_over(self) -> bool:
        return self.turn >= self.N_TURNS

    def scores(self) -> list[float]:
        return list(self.cumulative_profit)

    # ------------------------------------------------------------------ rendering

    def render(self, cycle: int | None = None, names: list[str] | None = None) -> "Figure":
        """One cycle (default: the current one): every negotiation round, then the play stage.
        See arena_games_dev.gamma.render. Needs the optional `render` extra (matplotlib)."""
        from arena_games_dev.gamma.render import render_cycle

        return render_cycle(self, cycle, names)

    def render_match(self, names: list[str] | None = None) -> "Figure":
        """Overview of the whole match so far. Needs the optional `render` extra."""
        from arena_games_dev.gamma.render import render_match

        return render_match(self, names)

    # ------------------------------------------------------------------ action parsing

    def _parse_claim(self, action: Any) -> list[int] | None:
        """A list of node ids, sorted and without duplicates; None if malformed."""
        if not isinstance(action, list):
            return None
        if not all(_is_int(v) and 0 <= v < self.n_nodes for v in action):
            return None
        return sorted(set(action))

    def _parse_answers(self, action: Any, player_id: int) -> dict[int, bool] | None:
        """{other player id: bool}; keys may be missing (deny). None if malformed."""
        if not isinstance(action, dict):
            return None
        for key, value in action.items():
            if not _is_int(key) or key == player_id or not 0 <= key < self.N_PLAYERS:
                return None
            if not isinstance(value, bool):
                return None
        return action

    def _parse_allocation(self, action: Any) -> list[int] | None:
        """n_nodes non-negative ints that sum to at most the fleet; None if malformed."""
        if not isinstance(action, list) or len(action) != self.n_nodes:
            return None
        if not all(_is_int(v) and v >= 0 for v in action):
            return None
        if sum(action) > self.DRONES_PER_PLAYER:
            return None
        return list(action)


def _copy_rounds(rounds: list[dict]) -> list[dict]:
    """Deep enough copy of negotiation entries and records for an observation."""
    return [
        {
            **r,
            "claims": [list(c) for c in r["claims"]],
            "accept": [list(row) for row in r["accept"]],
        }
        for r in rounds
    ]
