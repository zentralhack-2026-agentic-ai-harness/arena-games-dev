"""
Rendering for Gamma: one figure per cycle (every negotiation round, then the play stage) and
one overview figure per match. Needs the optional `render` extra (matplotlib).

Run as a module to play and render one match for every table of baselines, self tables
included (each table seats the baselines in BASELINES order):

    uv run python -m arena_games_dev.gamma.render --seed 1

This writes, under outputs/gamma_<timestamp>/, one directory per table with overview.png and
cycle_01.png .. cycle_10.png, plus index.html (all tables with their scores) and summary.txt.
With --match, it renders one match of any three strategies instead:

    uv run python -m arena_games_dev.gamma.render --seed 0 \\
        --match a=bots/a.py:Strategy Grim=arena_games_dev.gamma.baselines:Grim b=bots/b.py:Strategy
"""

import argparse
import html
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from itertools import combinations_with_replacement
from pathlib import Path
from typing import TYPE_CHECKING

from arena_games_dev.gamma.game import GammaGame

if TYPE_CHECKING:
    from matplotlib.axes import Axes

PLAYER_COLORS = ["#2a78d6", "#eb6834", "#8a55c9"]
INK, MUTED, GRID, SURFACE = "#1a1a19", "#6b6a64", "#c9c8c0", "#ffffff"
EMPTY = "#f1f0ea"
DEMAND_FILL = "#f2c14e"
ACCEPT, ACCEPT_FILL = "#2f8a4c", "#d5ecdb"
DENY, DENY_FILL = "#c8473d", "#f6d9d6"

OUTPUTS_DIR = Path(__file__).resolve().parents[3] / "outputs"


# ------------------------------------------------------------------ analysis


def cycle_turns(game: GammaGame, cycle: int) -> list[int]:
    """The play turns of `cycle` that have been played."""
    first = cycle * game.PLAY_TURNS_PER_CYCLE
    return list(range(first, min(first + game.PLAY_TURNS_PER_CYCLE, len(game.history))))


def trespasses(game: GammaGame, turn: int) -> list[set[int]]:
    """Per player: the nodes on which it had drones in play turn `turn` although they are in
    another player's final claim of that cycle, a claim it accepted (as the baselines judge it)."""
    record = game.records[turn // game.PLAY_TURNS_PER_CYCLE]
    allocations = game.history[turn][0]
    n = game.N_PLAYERS
    return [
        {
            node
            for owner in range(n)
            if owner != p and record["accept"][p][owner]
            for node in record["claims"][owner]
            if allocations[p][node] > 0
        }
        for p in range(n)
    ]


def _names(game: GammaGame, names: list[str] | None) -> list[str]:
    return names or [f"P{p}" for p in range(game.N_PLAYERS)]


def _seats(names: list[str]) -> str:
    return "    ".join(f"P{p} = {name}" for p, name in enumerate(names))


# ------------------------------------------------------------------ cycle figure


def render_cycle(game: GammaGame, cycle: int | None = None, names: list[str] | None = None):
    """Figure of one cycle (default: the current one) as far as it has been played.

    Left: every negotiation round, top to bottom. Each round shows the three claims (a row per
    player, a column per node, filled where the player claims the node) and the answers to
    them (✓ / ✗: did the column player accept the row player's claim?). Right: the play stage
    of the cycle and the cumulative profit of the match.
    """
    from matplotlib.figure import Figure

    cycle = game.cycle if cycle is None else cycle
    names = _names(game, names)
    fig = Figure(figsize=(17, 9.5), dpi=110, layout="constrained")
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(3, 2, width_ratios=[1.05, 1], height_ratios=[1.35, 0.8, 1])
    _draw_negotiation(fig.add_subplot(gs[:, 0]), game, cycle)
    _draw_play(fig.add_subplot(gs[0, 1]), game, cycle)
    _draw_turn_profit(fig.add_subplot(gs[1, 1]), game, cycle)
    _draw_cumulative(fig.add_subplot(gs[2, 1]), game, cycle, names)

    seed = "" if game.seed is None else f"  ·  seed {game.seed}"
    fig.suptitle(
        f"Gamma  ·  cycle {cycle + 1} / {game.N_CYCLES}{seed}\n{_seats(names)}",
        x=0.01,
        ha="left",
        fontsize=14,
        fontweight="bold",
        color=INK,
    )
    return fig


def _draw_negotiation(ax: "Axes", game: GammaGame, cycle: int) -> None:
    from matplotlib.patches import Rectangle

    n, n_players = game.n_nodes, game.N_PLAYERS
    demand = game.demand[cycle]
    total = sum(demand)
    rounds = list(game.negotiation_log[cycle]) if cycle < len(game.negotiation_log) else []
    if cycle == game.cycle and game.claims is not None:
        rounds.append({"claims": game.claims, "accept": None})  # answers not given yet
    done = cycle < len(game.records)

    vx = n + 0.8  # first answer column
    sx = vx + n_players + 0.4  # claimed-demand column
    block = 4.4  # height of one round
    top = 2.2  # first round starts here

    def cell(x, y, fc, ec="none", lw=0.0):
        ax.add_patch(Rectangle((x + 0.06, y + 0.06), 0.88, 0.88, fc=fc, ec=ec, lw=lw))

    def text(x, y, s, **kw):
        kw = {"ha": "center", "va": "center", "fontsize": 7.5, "color": INK, **kw}
        ax.text(x, y, s, **kw)

    # Header: node ids and this cycle's demand.
    max_demand = max(demand) or 1
    for k in range(n):
        share = demand[k] / max_demand
        ax.add_patch(
            Rectangle((k + 0.06, 0.9), 0.88, 0.9, fc=DEMAND_FILL, alpha=0.12 + 0.78 * share, lw=0)
        )
        text(k + 0.5, 0.45, str(k), fontweight="bold", fontsize=8.5)
        text(k + 0.5, 1.35, str(demand[k]), fontsize=7)
    text(-0.15, 0.45, "node", ha="right", color=MUTED)
    text(-0.15, 1.35, "demand", ha="right", color=MUTED)
    text(vx + n_players / 2, 0.45, "accepted by", color=MUTED)
    for j in range(n_players):
        text(vx + j + 0.5, 1.35, f"P{j}", fontweight="bold", color=PLAYER_COLORS[j])
    text(sx, 1.35, "claimed demand", ha="left", color=MUTED)

    for r in range(game.MAX_NEGOTIATION_ROUNDS):
        yb = top + r * block
        if r >= len(rounds):
            if done:
                text(-1.4, yb + 0.4, f"Round {r + 1}", ha="left", color=GRID, fontsize=10)
                text(1.6, yb + 0.4, "not played", ha="left", color=GRID, fontsize=9)
            continue
        claims, accept = rounds[r]["claims"], rounds[r]["accept"]
        unanimous = accept is not None and all(
            accept[i][j] for i in range(n_players) for j in range(n_players) if i != j
        )
        final = done and r == len(rounds) - 1
        if accept is None:
            status, color = "claims made, answers pending", MUTED
        elif unanimous:
            status, color = "unanimous: every claim accepted → play", ACCEPT
        elif final:
            status, color = "round limit reached, no agreement → play", DENY
        else:
            status, color = "not unanimous → next round", MUTED
        text(-1.4, yb + 0.4, f"Round {r + 1}", ha="left", fontsize=10, fontweight="bold")
        text(1.6, yb + 0.4, status, ha="left", fontsize=9, color=color, fontweight="bold")
        if final:
            ax.add_patch(
                Rectangle((-1.5, yb), sx + 4.4, 3.95, fc="none", ec=INK, lw=1.4, ls=(0, (4, 2)))
            )

        for i in range(n_players):
            y = yb + 0.75 + i
            text(-0.15, y + 0.5, f"P{i}", ha="right", fontweight="bold", color=PLAYER_COLORS[i])
            mine = set(claims[i])
            for k in range(n):
                if k in mine:
                    contested = sum(k in c for c in claims) > 1
                    cell(k, y, PLAYER_COLORS[i], ec=DENY if contested else "none", lw=2.2)
                else:
                    cell(k, y, EMPTY)
            for j in range(n_players):
                if j == i:
                    cell(vx + j, y, EMPTY)
                    text(vx + j + 0.5, y + 0.5, "-", color=MUTED)
                elif accept is None:
                    cell(vx + j, y, EMPTY)
                    text(vx + j + 0.5, y + 0.5, "?", color=MUTED)
                elif accept[j][i]:
                    cell(vx + j, y, ACCEPT_FILL)
                    text(vx + j + 0.5, y + 0.5, "✓", color=ACCEPT, fontsize=10, fontweight="bold")
                else:
                    cell(vx + j, y, DENY_FILL)
                    text(vx + j + 0.5, y + 0.5, "✗", color=DENY, fontsize=10, fontweight="bold")
            claimed = sum(demand[k] for k in mine)
            label = f"{claimed} ({claimed / total:.0%})" if mine else "no claim"
            text(sx, y + 0.5, label, ha="left", color=INK if mine else MUTED)

    bottom = top + game.MAX_NEGOTIATION_ROUNDS * block
    text(
        -1.4,
        bottom + 0.3,
        "Row = a player's claim (filled: node claimed;"
        " red edge: claimed by more than one player).\n"
        "Answers: ✓ / ✗ = did the column player accept the row player's claim?\n"
        "Dashed box: the final round; its claims and answers are what stands during play.",
        ha="left",
        va="top",
        fontsize=8,
        color=MUTED,
    )
    ax.set_xlim(-1.6, sx + 4.6)
    ax.set_ylim(bottom + 1.6, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Negotiation", loc="left", fontsize=12, fontweight="bold", color=INK)


def _draw_play(ax: "Axes", game: GammaGame, cycle: int) -> None:
    turns = cycle_turns(game, cycle)
    n, n_players = game.n_nodes, game.N_PLAYERS
    demand = game.demand[cycle]
    _style(ax)
    ax.set_title(
        f"Play stage: mean capacity deployed per node over {len(turns)} turns\n"
        "black line: demand  ·  hatched: on another player's claim this player accepted"
        "  ·  squares: final claims",
        loc="left",
        fontsize=9,
        color=INK,
    )
    ax.set_xticks(range(n))
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_xlabel("node", fontsize=8, color=MUTED)
    if not turns:
        ax.set_ylim(0, max(demand) * 1.15)
        ax.text(0.5, 0.5, "not played yet", transform=ax.transAxes, ha="center", color=MUTED)
        for k in range(n):
            ax.hlines(demand[k], k - 0.42, k + 0.42, color=INK, lw=2)
        return

    trespassed = [set() for _ in range(n_players)]
    for t in turns:
        for p, nodes in enumerate(trespasses(game, t)):
            trespassed[p] |= nodes
    base = [0.0] * n
    for p in range(n_players):
        heights = [
            game.DRONE_CAPACITY * sum(game.history[t][0][p][k] for t in turns) / len(turns)
            for k in range(n)
        ]
        ax.bar(range(n), heights, 0.75, bottom=base, color=PLAYER_COLORS[p], lw=0)
        for k in trespassed[p]:
            ax.bar(k, heights[k], 0.75, bottom=base[k], fc="none", ec=SURFACE, hatch="////", lw=0)
        base = [b + h for b, h in zip(base, heights, strict=True)]
    for k in range(n):
        ax.hlines(demand[k], k - 0.42, k + 0.42, color=INK, lw=2, zorder=4)
    ymax = max(max(base), max(demand)) * 1.12
    # The final claims, as colored squares under each node.
    record = game.records[cycle]
    for i in range(n_players):
        nodes = record["claims"][i]
        ax.scatter(
            nodes,
            [-ymax * (0.05 + 0.055 * i)] * len(nodes),
            marker="s",
            s=22,
            color=PLAYER_COLORS[i],
            clip_on=False,
        )
    ax.set_ylim(-ymax * 0.2, ymax)
    ax.axhline(0, color=GRID, lw=1)


def _draw_turn_profit(ax: "Axes", game: GammaGame, cycle: int) -> None:
    turns = cycle_turns(game, cycle)
    _style(ax)
    ax.axhline(0, color=GRID, lw=1)
    x = [t - cycle * game.PLAY_TURNS_PER_CYCLE + 1 for t in turns]
    for p in range(game.N_PLAYERS):
        ax.plot(x, [game.history[t][1][p] for t in turns], color=PLAYER_COLORS[p], lw=2, marker="o")
    ax.set_xlim(0.5, game.PLAY_TURNS_PER_CYCLE + 0.5)
    ax.set_xticks(range(1, game.PLAY_TURNS_PER_CYCLE + 1))
    ax.set_title("Profit per play turn of this cycle", loc="left", fontsize=9, color=INK)


def _draw_cumulative(ax: "Axes", game: GammaGame, cycle: int | None, names: list[str]) -> None:
    """Cumulative profit over the match; `cycle` (if any) is highlighted, and the legend gives
    every player's total (and its profit in `cycle`)."""
    _style(ax)
    per_cycle = game.PLAY_TURNS_PER_CYCLE
    for c in range(game.N_CYCLES):
        if c == cycle:
            ax.axvspan(c * per_cycle, (c + 1) * per_cycle, color=DEMAND_FILL, alpha=0.3, lw=0)
        elif c % 2:
            ax.axvspan(c * per_cycle, (c + 1) * per_cycle, color=EMPTY, lw=0)
    for c, record in enumerate(game.records):
        mark = f"✓{record['rounds']}" if record["unanimous"] else f"✗{record['rounds']}"
        ax.text(
            (c + 0.5) * per_cycle,
            0.93,
            mark,
            transform=ax.get_xaxis_transform(),
            ha="center",
            fontsize=8,
            fontweight="bold",
            color=ACCEPT if record["unanimous"] else DENY,
        )
    ax.axhline(0, color=GRID, lw=1)
    if game.history:
        x = range(1, len(game.history) + 1)
        for p in range(game.N_PLAYERS):
            total, ys = 0.0, []
            for _, profits in game.history:
                total += profits[p]
                ys.append(total)
            label = f"P{p} {names[p]}: {game.cumulative_profit[p]:,.0f}"
            if cycle is not None:
                profit = sum(game.history[t][1][p] for t in cycle_turns(game, cycle))
                label += f"  (cycle {cycle + 1}: {profit:+,.0f})"
            ax.plot(x, ys, color=PLAYER_COLORS[p], lw=2, label=label)
        ax.legend(loc="upper left", bbox_to_anchor=(0, 0.88), frameon=False, fontsize=8.5)
    ax.set_xlim(0, game.N_TURNS)
    ax.set_xticks(range(0, game.N_TURNS + 1, per_cycle))
    ax.set_xlabel("play turn", fontsize=8, color=MUTED)
    ax.set_title(
        "Cumulative profit  (✓k: agreed in round k; ✗5: no agreement)",
        loc="left",
        fontsize=9,
        color=INK,
    )


def _style(ax: "Axes") -> None:
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.grid(color=GRID, linewidth=0.5, alpha=0.5)
    for spine in ax.spines.values():
        spine.set_color(GRID)


# ------------------------------------------------------------------ match overview


def render_match(game: GammaGame, names: list[str] | None = None):
    """Overview of a whole match: the final claims of every cycle, the profit per cycle,
    the negotiation rounds per cycle and the cumulative profit."""
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle

    names = _names(game, names)
    n, n_players = game.n_nodes, game.N_PLAYERS
    fig = Figure(figsize=(16, 9), dpi=110, layout="constrained")
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(3, 2, width_ratios=[0.8, 1])
    ax_claims = fig.add_subplot(gs[:, 0])
    ax_cum = fig.add_subplot(gs[0, 1])
    ax_cycle = fig.add_subplot(gs[1, 1])
    ax_rounds = fig.add_subplot(gs[2, 1], sharex=ax_cycle)

    # --- final claims per cycle: each node cell split in one third per player
    for c, record in enumerate(game.records):
        tres = [set() for _ in range(n_players)]
        for t in cycle_turns(game, c):
            for p, nodes in enumerate(trespasses(game, t)):
                tres[p] |= nodes
        for k in range(n):
            ax_claims.add_patch(Rectangle((k + 0.05, c + 0.08), 0.9, 0.84, fc=EMPTY, lw=0))
            for i in range(n_players):
                if k in record["claims"][i]:
                    ax_claims.add_patch(
                        Rectangle(
                            (k + 0.05 + 0.3 * i, c + 0.08), 0.3, 0.84, fc=PLAYER_COLORS[i], lw=0
                        )
                    )
            raiders = [p for p in range(n_players) if k in tres[p]]
            for m, p in enumerate(raiders):
                ax_claims.scatter(
                    k + 0.5 + 0.25 * (m - (len(raiders) - 1) / 2),
                    c + 0.5,
                    marker="X",
                    s=55,
                    color=PLAYER_COLORS[p],
                    edgecolors=SURFACE,
                    linewidths=0.8,
                    zorder=3,
                )
        mark = f"✓ round {record['rounds']}" if record["unanimous"] else "✗ no agreement"
        ax_claims.text(
            n + 0.2,
            c + 0.5,
            mark,
            va="center",
            fontsize=8,
            fontweight="bold",
            color=ACCEPT if record["unanimous"] else DENY,
        )
    ax_claims.set_xlim(0, n + 2.6)
    ax_claims.set_ylim(game.N_CYCLES, 0)
    ax_claims.set_xticks([k + 0.5 for k in range(n)], [str(k) for k in range(n)])
    ax_claims.set_yticks(
        [c + 0.5 for c in range(game.N_CYCLES)], [f"cycle {c + 1}" for c in range(game.N_CYCLES)]
    )
    ax_claims.tick_params(length=0, labelsize=8, colors=MUTED)
    for spine in ax_claims.spines.values():
        spine.set_visible(False)
    ax_claims.set_xlabel("node", fontsize=8, color=MUTED)
    ax_claims.set_title(
        "Final claims per cycle (a third of the cell per player)\n"
        "X: drones on another player's claim that this player accepted",
        loc="left",
        fontsize=9,
        color=INK,
    )

    # --- cumulative profit, profit per cycle, rounds per cycle
    _draw_cumulative(ax_cum, game, None, names)
    _style(ax_cycle)
    width = 0.8 / n_players
    for p in range(n_players):
        profits = [
            sum(game.history[t][1][p] for t in cycle_turns(game, c))
            for c in range(len(game.records))
        ]
        x = [c + 1 + (p - (n_players - 1) / 2) * width for c in range(len(profits))]
        ax_cycle.bar(x, profits, width, color=PLAYER_COLORS[p], lw=0)
    ax_cycle.axhline(0, color=GRID, lw=1)
    ax_cycle.set_title("Profit per cycle", loc="left", fontsize=9, color=INK)
    _style(ax_rounds)
    rounds = [r["rounds"] for r in game.records]
    colors = [ACCEPT if r["unanimous"] else DENY for r in game.records]
    ax_rounds.bar(range(1, len(rounds) + 1), rounds, 0.6, color=colors, lw=0)
    ax_rounds.set_ylim(0, game.MAX_NEGOTIATION_ROUNDS + 0.5)
    ax_rounds.set_xticks(range(1, game.N_CYCLES + 1))
    ax_rounds.set_xlim(0.4, game.N_CYCLES + 0.6)
    ax_rounds.set_xlabel("cycle", fontsize=8, color=MUTED)
    ax_rounds.set_title(
        "Negotiation rounds per cycle (green: unanimous; red: round limit, no agreement)",
        loc="left",
        fontsize=9,
        color=INK,
    )

    seed = "" if game.seed is None else f"  ·  seed {game.seed}"
    fig.suptitle(
        f"Gamma  ·  match overview{seed}\n{_seats(names)}",
        x=0.01,
        ha="left",
        fontsize=14,
        fontweight="bold",
        color=INK,
    )
    return fig


# ------------------------------------------------------------------ playing and saving


def load_strategy(target: str) -> type:
    """A strategy class from "path/to/file.py:Name" or "package.module:Name"."""
    import importlib
    import importlib.util

    location, _, name = target.rpartition(":")
    if location.endswith(".py"):
        path = Path(location).resolve()
        spec = importlib.util.spec_from_file_location(f"_gamma_entrant_{abs(hash(path))}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(location)
    return getattr(module, name)


def play(classes: list[type], seed: int) -> GammaGame:
    """Play one match in this process, seat i = classes[i]."""
    game = GammaGame(seed)
    players = [cls(player_id) for player_id, cls in enumerate(classes)]
    while not game.is_over():
        game.step([p.act(game.observe(seat)) for seat, p in enumerate(players)])
    return game


def render_game(names: list[str], strategies: list, seed: int, table_dir: Path) -> dict:
    """Play one match (strategies: classes or targets, by seat) and save overview.png and
    cycle_01.png .. cycle_10.png to `table_dir`, labelled with `names`."""
    classes = [load_strategy(s) if isinstance(s, str) else s for s in strategies]
    game = play(classes, seed)
    table_dir.mkdir(parents=True, exist_ok=True)
    render_match(game, names).savefig(table_dir / "overview.png")
    for c in range(game.N_CYCLES):
        render_cycle(game, c, names).savefig(table_dir / f"cycle_{c + 1:02d}.png")
    return {
        "names": list(names),
        "seed": seed,
        "dir": table_dir.name,
        "scores": game.scores(),
        "unanimous": sum(r["unanimous"] for r in game.records),
    }


def _render_job(job: tuple[list[str], list, int, Path]) -> dict:
    return render_game(*job)


def render_games(
    out_dir: Path,
    games: list[tuple[str, list[str], list, int]],
    title: str,
    jobs: int | None = None,
) -> list[dict]:
    """Render several matches in parallel: each game is (directory, names, strategies, seed).
    Writes index.html and summary.txt to `out_dir` as well."""
    work = [(names, strategies, seed, out_dir / d) for d, names, strategies, seed in games]
    with ProcessPoolExecutor(jobs or os.cpu_count()) as pool:
        results = list(pool.map(_render_job, work))
    _write_index(out_dir, results, title)
    return results


def render_tables(out_dir: Path, seed: int, jobs: int | None = None) -> list[dict]:
    """One match per table of baselines (self tables included), all on `seed`."""
    from arena_games_dev.gamma import BASELINES

    tables = combinations_with_replacement(BASELINES, 3)
    games = [
        (
            f"{i:02d}_{'_'.join(c.__name__ for c in classes)}",
            [c.__name__ for c in classes],
            list(classes),
            seed,
        )
        for i, classes in enumerate(tables)
    ]
    return render_games(out_dir, games, f"Gamma baseline tables, seed {seed}", jobs)


def _write_index(out_dir: Path, results: list[dict], title: str) -> None:
    scale = GammaGame.N_TURNS * GammaGame.TOTAL_DEMAND  # scores as a share of D per turn
    lines = [f"{title}. Score: profit per play turn as a share of D."]
    rows = []
    for i, r in enumerate(results):
        pairs = list(zip(r["names"], r["scores"], strict=True))
        scores = "  ".join(f"{name} {score / scale:.3f}" for name, score in pairs)
        lines.append(f"{i:2d}  seed {r['seed']}  unanimous {r['unanimous']:2d}/10  {scores}")
        cells = "".join(
            f'<td style="color:{PLAYER_COLORS[p]}"><b>{html.escape(name)}</b><br>'
            f"{score:,.0f} &middot; {score / scale:.3f}</td>"
            for p, (name, score) in enumerate(pairs)
        )
        cycles = " ".join(f'<a href="{r["dir"]}/cycle_{c:02d}.png">{c}</a>' for c in range(1, 11))
        rows.append(
            f"<tr><td>{i}</td><td>{html.escape(r['dir'])}</td><td>{r['seed']}</td>{cells}"
            f"<td>{r['unanimous']}/10</td>"
            f'<td><a href="{r["dir"]}/overview.png"><img src="{r["dir"]}/overview.png"></a></td>'
            f"<td>{cycles}</td></tr>"
        )
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n")
    (out_dir / "index.html").write_text(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; color: {INK}; background: {SURFACE}; margin: 24px; }}
table {{ border-collapse: collapse; }}
td, th {{ padding: 6px 10px; border-bottom: 1px solid {GRID}; vertical-align: middle; }}
th {{ text-align: left; color: {MUTED}; font-weight: 600; }}
img {{ width: 360px; display: block; }}
a {{ color: {INK}; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p>One match per row. Score: total profit &middot; profit per play turn as a share of D.
Unanimous: cycles whose negotiation ended with every claim accepted.</p>
<table>
<tr><th>#</th><th>match</th><th>seed</th><th>P0</th><th>P1</th><th>P2</th><th>unanimous</th>
<th>overview</th><th>cycles</th></tr>
{"".join(rows)}
</table></body></html>
"""
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument(
        "--match",
        nargs=3,
        metavar="[NAME=]TARGET",
        help="render one match of these three strategies (path/to/file.py:Name or "
        "package.module:Name, by seat) instead of the baseline tables",
    )
    args = parser.parse_args(argv)
    out_dir = args.out or OUTPUTS_DIR / f"gamma_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.match:
        names, targets = [], []
        for spec in args.match:
            name, _, target = spec.rpartition("=")
            names.append(name or target.rpartition(":")[2])
            targets.append(target)
        games = [("match", names, targets, args.seed)]
        results = render_games(out_dir, games, f"Gamma match, seed {args.seed}", 1)
    else:
        results = render_tables(out_dir, args.seed, args.jobs)
    print((out_dir / "summary.txt").read_text(), end="")
    print(f"{len(results)} matches rendered to {out_dir}")


if __name__ == "__main__":
    main()
