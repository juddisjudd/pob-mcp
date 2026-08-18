"""Greedy local-search optimizer loop.

Each iteration: snapshot the build, generate candidate moves for the
requested scope, try each one (recalculating via PoB's real engine),
score it, roll back to the snapshot, then commit whichever single move
scored best -- if any did better than the current score. Stops when no
move improves the score, or after max_iterations. This is a heuristic
hill-climb, not a global optimum: it only ever adds tree nodes or swaps
one gem/item at a time, never explores deallocating/respeccing, and can
get stuck in a local optimum a wider search might escape.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..bridge import BridgeProcess
from .goals import make_scorer
from .moves import Move, generate_gem_moves, generate_item_moves, generate_tree_moves

MAX_CANDIDATES_PER_ITERATION = 80
VALID_SCOPES = {"tree", "gems", "items"}


@dataclass
class OptimizeResult:
    goal: str
    baseline_stats: dict
    final_stats: dict
    baseline_score: float
    final_score: float
    applied_moves: list[str]
    iterations_run: int
    stopped_reason: str


async def _generate_candidates(bridge: BridgeProcess, scope: list[str], tree_search_radius: int) -> list[Move]:
    candidates: list[Move] = []
    if "tree" in scope:
        candidates += await generate_tree_moves(bridge, tree_search_radius)
    if "gems" in scope:
        candidates += await generate_gem_moves(bridge)
    if "items" in scope:
        candidates += await generate_item_moves(bridge)
    return candidates


async def optimize(
    bridge: BridgeProcess,
    goal: str,
    scope: list[str],
    max_iterations: int = 15,
    dps_weight: float = 0.5,
    defence_weight: float = 0.5,
    tree_search_radius: int = 8,
) -> OptimizeResult:
    unknown = set(scope) - VALID_SCOPES
    if unknown:
        raise ValueError(f"unknown scope entries: {sorted(unknown)} (expected any of {sorted(VALID_SCOPES)})")

    baseline_stats = (await bridge.call("get_stats"))["stats"]
    scorer = make_scorer(goal, baseline_stats, dps_weight, defence_weight)
    baseline_score = scorer(baseline_stats)
    current_score = baseline_score
    applied: list[str] = []
    stopped_reason = "reached max_iterations"
    iterations_run = 0

    for iteration in range(max_iterations):
        iterations_run = iteration + 1
        snapshot = await bridge.snapshot()
        candidates = await _generate_candidates(bridge, scope, tree_search_radius)

        if not candidates:
            stopped_reason = "no candidate moves available for the requested scope"
            break
        if len(candidates) > MAX_CANDIDATES_PER_ITERATION:
            candidates = random.sample(candidates, MAX_CANDIDATES_PER_ITERATION)

        best_move: Move | None = None
        best_score = current_score
        for move in candidates:
            score: float | None
            try:
                await move.apply(bridge)
                stats = (await bridge.call("get_stats"))["stats"]
                score = scorer(stats)
            except Exception:
                score = None
            finally:
                await bridge.restore(snapshot)
            if score is not None and score > best_score:
                best_score = score
                best_move = move

        if best_move is None:
            stopped_reason = "no further improving move found"
            break

        await best_move.apply(bridge)
        current_score = best_score
        applied.append(best_move.label)

    final_stats = (await bridge.call("get_stats"))["stats"]
    return OptimizeResult(
        goal=goal,
        baseline_stats=baseline_stats,
        final_stats=final_stats,
        baseline_score=baseline_score,
        final_score=current_score,
        applied_moves=applied,
        iterations_run=iterations_run,
        stopped_reason=stopped_reason,
    )
