import ast
import itertools
import math

import pytest
from arena.match import play_match

from arena_games_dev.gamma import BASELINES, GammaGame
from arena_games_dev.gamma.baselines import (
    DoNothing,
    FairShare,
    Greedy,
    Grim,
    Raider,
    TitForTat,
    best_response,
    fair_split,
)
from arena_games_dev.gamma.game import (
    DRONES_PER_PLAYER,
    MAX_NEGOTIATION_ROUNDS,
    N_CYCLES,
    N_NODES_RANGE,
    PLAY_TURNS_PER_CYCLE,
    TOTAL_DEMAND,
    Instance,
    generate_instance,
    largest_remainder,
    node_revenue,
)


def play(players, seed: int) -> GammaGame:
    game = GammaGame(seed)
    while not game.is_over():
        game.step([p.act(game.observe(p.player_id)) for p in players])
    return game


def _instance(demand: list[int]) -> Instance:
    return Instance(len(demand), [list(demand)] * N_CYCLES)


def _negotiate(game: GammaGame, claims, answers) -> None:
    """One negotiation round: a propose step and a respond step."""
    assert game.phase == "propose"
    game.step(claims)
    assert game.phase == "respond"
    game.step(answers)


ALL_ACCEPT = [{1: True, 2: True}, {0: True, 2: True}, {0: True, 1: True}]


# ------------------------------------------------------------------ generator


def test_same_seed_same_environment():
    assert generate_instance(7) == generate_instance(7)
    assert generate_instance(7) != generate_instance(8)


@pytest.mark.parametrize("seed", range(200))
def test_generator_constraints(seed):
    inst = generate_instance(seed)
    assert N_NODES_RANGE[0] <= inst.n_nodes <= N_NODES_RANGE[1]
    assert len(inst.demand) == N_CYCLES
    for row in inst.demand:
        assert len(row) == inst.n_nodes
        assert sum(row) == TOTAL_DEMAND
        assert all(isinstance(d, int) and d > 0 for d in row)
    assert len({tuple(row) for row in inst.demand}) == N_CYCLES, "every cycle is reshuffled"


def test_largest_remainder():
    assert largest_remainder([1.0, 1.0, 1.0], 10) == [4, 3, 3]
    assert largest_remainder([1.0, 2.0, 1.0], 10) == [3, 5, 2]  # ties go to the lower index
    assert sum(largest_remainder([0.3, 1.7, 0.9, 1.1], 1200)) == 1200


def test_total_capacity_exceeds_total_demand():
    assert GammaGame.N_PLAYERS * DRONES_PER_PLAYER * GammaGame.DRONE_CAPACITY == 1.5 * TOTAL_DEMAND


# ------------------------------------------------------------------ phases


def test_observation_is_a_literal():
    game = GammaGame(3)
    players = [FairShare(i) for i in range(3)]
    while not game.is_over():
        for player_id in range(3):
            obs = game.observe(player_id)
            assert ast.literal_eval(repr(obs)) == obs
            assert obs["player_id"] == player_id
        game.step([p.act(game.observe(p.player_id)) for p in players])


def test_unanimity_ends_negotiation_after_one_round():
    game = GammaGame(instance=_instance([100] * 12))
    _negotiate(game, [[0, 1], [2], []], ALL_ACCEPT)
    assert game.phase == "play"
    assert game.records == [
        {
            "cycle": 0,
            "claims": [[0, 1], [2], []],
            "accept": [[None, True, True], [True, None, True], [True, True, None]],
            "unanimous": True,
            "rounds": 1,
        }
    ]


def test_negotiation_stops_after_max_rounds_and_keeps_the_last_round():
    game = GammaGame(instance=_instance([100] * 12))
    for r in range(MAX_NEGOTIATION_ROUNDS):
        assert game.round == r
        partial = [{1: True}, {0: True}, {}]  # 0 and 1 accept each other, 2 accepts nobody
        _negotiate(game, [[0, r], [5], [0]], partial)
    assert game.phase == "play"
    record = game.records[0]
    assert record["unanimous"] is False
    assert record["rounds"] == MAX_NEGOTIATION_ROUNDS
    assert record["claims"] == [[0, 4], [5], [0]]
    assert record["accept"] == [[None, True, False], [True, None, False], [False, False, None]]
    assert len(game.observe(0)["negotiation"]) == MAX_NEGOTIATION_ROUNDS


def test_cycle_structure():
    game = GammaGame(5)
    phases = []
    while not game.is_over():
        phases.append((game.phase, game.cycle, game.turn_in_cycle))
        game.step([[], {}, [0] * game.n_nodes])  # matching formats do not matter here
    # Nobody accepts anything: every cycle has the full 5 rounds, then 10 play turns.
    per_cycle = ["propose", "respond"] * MAX_NEGOTIATION_ROUNDS + ["play"] * PLAY_TURNS_PER_CYCLE
    assert [p for p, _, _ in phases] == per_cycle * N_CYCLES
    assert [c for _, c, _ in phases] == [c for c in range(N_CYCLES) for _ in range(len(per_cycle))]
    assert game.turn == N_CYCLES * PLAY_TURNS_PER_CYCLE
    assert len(game.records) == N_CYCLES
    assert len(game.history) == game.N_TURNS


def test_observation_during_respond_shows_this_rounds_claims():
    game = GammaGame(instance=_instance([100] * 12))
    obs = game.observe(1)
    assert obs["phase"] == "propose" and obs["claims"] is None and obs["negotiation"] == []
    game.step([[3, 1, 1], [2], []])
    obs = game.observe(1)
    assert obs["phase"] == "respond"
    assert obs["claims"] == [[1, 3], [2], []]  # sorted, duplicates removed


# ------------------------------------------------------------------ actions


def test_malformed_claims_become_empty():
    game = GammaGame(instance=_instance([100] * 12))
    game.step([[0, 12], (1,), [True]])  # out of range, not a list, bool
    assert game.claims == [[], [], []]
    assert game.action_valid_last_step == [False, False, False]


def test_malformed_answers_deny_everything():
    game = GammaGame(instance=_instance([100] * 12))
    game.step([[0], [1], [2]])
    game.step([{0: True, 1: True}, {0: 1}, None])  # own id, non-bool value, None
    assert game.negotiation[0]["accept"] == [
        [None, False, False],
        [False, None, False],
        [False, False, None],
    ]
    assert game.action_valid_last_step == [False, False, False]


def test_missing_answers_count_as_deny():
    game = GammaGame(instance=_instance([100] * 12))
    game.step([[0], [1], [2]])
    game.step([{1: True}, {}, {0: False, 1: True}])
    assert game.negotiation[0]["accept"] == [
        [None, True, False],
        [False, None, False],
        [False, True, None],
    ]
    assert game.action_valid_last_step == [True, True, True]


def test_malformed_allocations_deploy_nothing():
    game = GammaGame(instance=_instance([100] * 3))
    _negotiate(game, [[], [], []], ALL_ACCEPT)
    game.step([[40, 41, 40], [10, 0], [1.0, 0, 0]])  # over the fleet, too short, float
    assert game.allocation == [[0, 0, 0]] * 3
    assert game.profit_last_turn == [0.0, 0.0, 0.0]
    assert game.action_valid_last_step == [False, False, False]


# ------------------------------------------------------------------ scoring


def test_node_revenue_examples_from_spec():
    assert node_revenue([20, 0, 0], 100) == [100.0, 0.0, 0.0]
    assert node_revenue([10, 0, 0], 100) == [50.0, 0.0, 0.0]
    assert node_revenue([20, 10, 10], 100) == pytest.approx([50.0, 25.0, 25.0])
    assert node_revenue([0, 0, 0], 100) == [0.0, 0.0, 0.0]


def test_play_turn_scoring_example_from_spec():
    game = GammaGame(instance=_instance([100, 60, 40]))
    _negotiate(game, [[0], [1], [2]], ALL_ACCEPT)
    game.step([[20, 0, 0], [5, 12, 0], [0, 0, 8]])
    assert game.revenue_last_turn == pytest.approx([80.0, 80.0, 40.0])
    assert game.upkeep_last_turn == [40.0, 34.0, 16.0]
    assert game.profit_last_turn == pytest.approx([40.0, 46.0, 24.0])
    obs = game.observe(2)
    assert obs["allocations_last_turn"] == [[20, 0, 0], [5, 12, 0], [0, 0, 8]]
    assert obs["turn"] == 1 and obs["turn_in_cycle"] == 1


def test_do_nothing_scores_zero():
    game = play([DoNothing(i) for i in range(3)], seed=0)
    assert game.scores() == [0.0, 0.0, 0.0]


# ------------------------------------------------------------------ baselines


def test_fair_split_is_balanced_and_disjoint():
    for seed in range(50):
        demand = generate_instance(seed).demand[0]
        parts = fair_split(demand, 3)
        assert sorted(itertools.chain(*parts)) == list(range(len(demand)))
        values = [sum(demand[v] for v in part) for part in parts]
        assert max(values) - min(values) <= max(demand)


def test_best_response_is_exact_on_one_node():
    # Brute force against 7 other drones at a node with demand 100.
    def profit(k):
        return node_revenue([k, 7], 100)[0] - 2.0 * k

    best = max(range(DRONES_PER_PLAYER + 1), key=profit)
    assert best_response([100], [7], DRONES_PER_PLAYER) == [best]
    assert best_response([100], [0], DRONES_PER_PLAYER) == [20]  # monopoly: capacity = demand
    assert best_response([100, 50], [0, 0], DRONES_PER_PLAYER, allowed={1}) == [0, 10]


@pytest.mark.parametrize("seed", range(3))
def test_baselines_play_legally_in_every_seat(seed):
    for table in itertools.product(BASELINES, repeat=3):
        game = GammaGame(seed)
        players = [cls(i) for i, cls in enumerate(table)]
        while not game.is_over():
            game.step([p.act(game.observe(p.player_id)) for p in players])
            assert game.action_valid_last_step == [True, True, True], table
        assert all(math.isfinite(s) for s in game.scores())


def test_fair_share_cartel_beats_greedy_competition():
    cartel = play([FairShare(i) for i in range(3)], seed=0)
    competition = play([Greedy(i) for i in range(3)], seed=0)
    assert all(r["unanimous"] and r["rounds"] == 1 for r in cartel.records)
    assert min(cartel.scores()) > 1.4 * max(competition.scores())


@pytest.mark.parametrize("punisher", [Grim, TitForTat])
def test_raid_on_the_last_turn_of_a_cycle_is_detected(punisher):
    game = GammaGame(0)
    players = [punisher(0), punisher(1), Raider(2)]
    while not (game.cycle == 1 and game.negotiation):  # until cycle 1's first round is done
        game.step([p.act(game.observe(p.player_id)) for p in players])
    # The raid on turn 9 is noticed in cycle 1's negotiation: both deny the raider's claim.
    accept = game.negotiation[0]["accept"]
    assert accept[0][2] is False and accept[1][2] is False
    assert accept[0][1] is True and accept[1][0] is True


def test_tit_for_tat_forgives_after_the_next_cycle():
    game = GammaGame(0)
    # Player 2 raids only in cycle 0 (Raider, then FairShare from cycle 1 on).
    players = [TitForTat(0), TitForTat(1), Raider(2)]
    while not (game.cycle == 2 and game.negotiation):  # until cycle 2's first round is done
        if game.cycle == 1 and isinstance(players[2], Raider):
            fair = FairShare(2)
            fair.last_turn_seen = players[2].last_turn_seen
            players[2] = fair
        game.step([p.act(game.observe(p.player_id)) for p in players])
    assert game.records[1]["accept"][0][2] is False  # punished in cycle 1
    assert game.negotiation[0]["accept"][0][2] is True  # forgiven in cycle 2


def test_arena_plays_a_three_seat_match():
    result = play_match(GammaGame, [FairShare, Greedy, Raider], seed=1)
    assert result.forfeit is None
    assert len(result.scores) == 3
    assert result.turns > GammaGame.N_TURNS  # play turns plus negotiation steps


def test_arena_plays_an_isolated_three_seat_match():
    # Isolated workers receive observations and return actions as Python literals, including
    # the respond phase's {player_id: bool} dicts.
    result = play_match(GammaGame, [FairShare, Grim, Raider], seed=2, isolate=True)
    assert result.forfeit is None, result.error
    in_process = play_match(GammaGame, [FairShare, Grim, Raider], seed=2)
    assert result.scores == in_process.scores
