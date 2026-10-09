import ast
import itertools
import math
from datetime import datetime
from pathlib import Path

import pytest

from arena_games_dev.beta import BASELINES, BetaGame
from arena_games_dev.beta.baselines import DoNothing, GreedyResponse, ProportionalSpread
from arena_games_dev.beta.game import (
    MIN_BASE_DISTANCE,
    N_NODES_RANGE,
    N_TURNS,
    Instance,
    generate_instance,
    hop_distances,
)

OUTPUTS_DIR = Path(__file__).resolve().parents[1] / "outputs"


def play(players, seed: int) -> BetaGame:
    game = BetaGame(seed)
    while not game.is_over():
        game.step([p.act(game.observe(p.player_id)) for p in players])
    return game


def test_same_seed_same_environment():
    assert generate_instance(7) == generate_instance(7)
    assert generate_instance(7) != generate_instance(8)


@pytest.mark.parametrize("seed", range(200))
def test_generator_constraints(seed):
    inst = generate_instance(seed)
    n = inst.n_nodes
    assert N_NODES_RANGE[0] <= n <= N_NODES_RANGE[1]

    assert all(0 <= u < v < n for u, v in inst.edges)
    assert len(set(inst.edges)) == len(inst.edges) == (n - 1) + round(0.4 * n)
    assert inst.edges == sorted(inst.edges)

    dist = hop_distances(n, inst.edges)
    assert all(d >= 0 for row in dist for d in row), "graph must be connected"
    b0, b1 = inst.bases
    assert dist[b0][b1] >= MIN_BASE_DISTANCE

    assert len(inst.demand) == N_TURNS
    for turn, row in enumerate(inst.demand):
        assert len(row) == n
        assert row[b0] == row[b1] == 0.0
        assert all(d >= 0 for d in row)
        assert inst.curve is not None
        assert sum(row) == pytest.approx(inst.curve.total(turn), abs=0.05 * n)


def test_total_demand_grows_within_ranges():
    for seed in range(50):
        curve = generate_instance(seed).curve
        assert curve is not None
        totals = [curve.total(t) for t in range(N_TURNS)]
        assert 40 <= totals[0] <= 60
        assert 110 <= totals[-1] <= 140
        assert all(b >= a - 1e-9 for a, b in itertools.pairwise(totals))


def test_observation_is_a_literal_and_from_the_players_view():
    game = BetaGame(3)
    for player_id in range(2):
        obs = game.observe(player_id)
        assert ast.literal_eval(repr(obs)) == obs
        assert obs["player_base"] == game.bases[player_id]
        assert obs["opponent_base"] == game.bases[1 - player_id]
        assert obs["player_drones"][obs["player_base"]] == 30


def test_forecast_window_shrinks_at_the_end():
    game = BetaGame(5)
    while not game.is_over():
        obs = game.observe(0)
        horizon = min(5, N_TURNS - game.turn)
        assert all(len(f) == horizon for f in obs["demand_forecast"])
        for node, f in enumerate(obs["demand_forecast"]):
            assert f == [game.demand[game.turn + k][node] for k in range(horizon)]
        game.step([[], []])


def test_worked_example_from_spec():
    game = BetaGame(14)
    obs = game.observe(0)
    assert obs["n_nodes"] == 10
    assert obs["edges"] == [
        (0, 8), (1, 2), (1, 4), (1, 8), (1, 9), (2, 7), (3, 4),
        (3, 6), (4, 6), (4, 7), (5, 9), (6, 7), (7, 9),
    ]  # fmt: skip
    assert (obs["player_base"], obs["opponent_base"]) == (8, 3)
    assert obs["demand_forecast"][0] == [13.0, 16.5, 9.5, 8.9, 11.1]
    assert obs["demand_forecast"][4] == [12.3, 8.0, 13.0, 13.1, 11.7]

    game.step([[(8, 0, 3), (8, 1, 1)], [(3, 4, 4), (3, 6, 1)]])
    assert game.revenue_last_turn == pytest.approx([13.6, 14.9])
    assert game.upkeep_last_turn == [8.0, 10.0]

    obs = game.observe(0)
    assert obs["turn"] == 1
    assert obs["player_drones"] == [3, 1, 0, 0, 0, 0, 0, 0, 26, 0]
    assert obs["opponent_drones"] == [0, 0, 0, 25, 4, 0, 1, 0, 0, 0]
    assert obs["player_profit_last_turn"] == pytest.approx(5.6)
    assert obs["opponent_cumulative_profit"] == pytest.approx(4.9)
    assert obs["demand_forecast"][0] == [16.5, 9.5, 8.9, 11.1, 9.0]


def _line_instance(demand_at_2: float) -> Instance:
    # 0 - 1 - 2 - 3 - 4, bases 0 and 4, demand only at node 2.
    row = [0.0, 0.0, demand_at_2, 0.0, 0.0]
    return Instance(5, [(0, 1), (1, 2), (2, 3), (3, 4)], [0, 4], [row] * N_TURNS)


def test_scoring_examples_from_spec():
    game = BetaGame(instance=_line_instance(12.0))
    game.step([[(0, 1, 2)], [(4, 3, 3)]])
    game.step([[(1, 2, 2)], [(3, 2, 3)]])
    assert game.revenue_last_turn == pytest.approx([4.8, 7.2])
    assert game.profit_last_turn == pytest.approx([0.8, 1.2])

    alone = BetaGame(instance=_line_instance(12.0))
    alone.step([[(0, 1, 3)], []])
    alone.step([[(1, 2, 3)], []])
    assert alone.profit_last_turn == pytest.approx([6.0, 0.0])


def test_upkeep_counts_every_drone_away_from_home():
    game = BetaGame(instance=_line_instance(0.0))
    game.step([[(0, 1, 30)], [(4, 3, 1)]])
    assert game.profit_last_turn == [-60.0, -2.0]
    game.step([[(1, 0, 30)], [(3, 2, 1)]])
    assert game.profit_last_turn == [0.0, -2.0]


def test_illegal_and_malformed_moves():
    game = BetaGame(instance=_line_instance(10.0))
    # (0, 2) is not an edge; count too large; drones cannot move two hops in one turn.
    game.step([[(0, 2, 1), (0, 1, 31), (0, 1, 5), (1, 2, 5)], [(4, 3, True)]])
    assert game.n_invalid_actions_last_turn == [3, 0]
    assert game.action_format_correct_last_turn == [True, False]
    assert game.drone_allocation[0] == [25, 5, 0, 0, 0]
    assert game.drone_allocation[1] == [0, 0, 0, 0, 30]


def test_do_nothing_scores_zero():
    game = play([DoNothing(0), DoNothing(1)], seed=0)
    assert game.scores() == [0.0, 0.0]


@pytest.mark.parametrize("seed", range(5))
def test_baselines_play_legally(seed):
    for a in BASELINES:
        for b in BASELINES:
            game = BetaGame(seed)
            players = [a(0), b(1)]
            while not game.is_over():
                game.step([p.act(game.observe(p.player_id)) for p in players])
                assert game.n_invalid_actions_last_turn == [0, 0]
                assert game.action_format_correct_last_turn == [True, True]
                assert [sum(d) for d in game.drone_allocation] == [30, 30]
            assert all(math.isfinite(s) for s in game.scores())


def test_greedy_response_vs_proportional_spread_frames():
    pytest.importorskip("matplotlib")

    out_dir = OUTPUTS_DIR / f"beta_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    out_dir.mkdir(parents=True)

    game = BetaGame(14)
    players = [GreedyResponse(0), ProportionalSpread(1)]

    def save_frame() -> None:
        fig = game.render()
        fig.savefig(out_dir / f"turn_{game.turn:03d}.png")

    save_frame()
    while not game.is_over():
        game.step([p.act(game.observe(p.player_id)) for p in players])
        save_frame()

    assert len(list(out_dir.glob("*.png"))) == N_TURNS + 1
