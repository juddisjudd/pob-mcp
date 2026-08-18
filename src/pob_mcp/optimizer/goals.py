"""Scoring functions for the optimizer. Field names for DPS/EHP vary by
build (which one exists depends on the skill/defence setup), so each score
tries a list of common candidate field names in priority order rather than
hardcoding a single one -- see list_stat_keys for what's actually available
on a given loaded build."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Stats = dict[str, object]
Scorer = Callable[[Stats], float]

DPS_FIELD_CANDIDATES = ["CombinedDPS", "TotalDPS", "TotalDot", "AverageDamage"]
EHP_FIELD_CANDIDATES = ["TotalEHP", "EffectiveHitPool", "EHP"]
RESIST_CAP = 75.0


def _num(stats: Stats, key: str, default: float = 0.0) -> float:
    value = stats.get(key)
    return float(value) if isinstance(value, (int, float)) else default


def _first_present(stats: Stats, candidates: list[str]) -> float:
    for key in candidates:
        value = stats.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 0.0


def damage_score(stats: Stats) -> float:
    return _first_present(stats, DPS_FIELD_CANDIDATES)


def defence_score(stats: Stats) -> float:
    pool = _num(stats, "Life") + _num(stats, "EnergyShield") + _num(stats, "Ward")
    ehp = _first_present(stats, EHP_FIELD_CANDIDATES) or pool
    # Penalize uncapped elemental resistances proportionally to pool size, so the
    # optimizer can't "win" by dumping everything into life/ES while leaving
    # resistances uncapped.
    penalty = 0.0
    for key in ("FireResist", "ColdResist", "LightningResist"):
        value = stats.get(key)
        if isinstance(value, (int, float)) and value < RESIST_CAP:
            penalty += (RESIST_CAP - value) * 0.01 * pool
    return max(ehp, pool) - penalty


@dataclass(frozen=True)
class Baseline:
    dps: float
    defence: float


def balanced_score(stats: Stats, baseline: Baseline, dps_weight: float, defence_weight: float) -> float:
    dps_delta = (damage_score(stats) / baseline.dps - 1.0) if baseline.dps > 0 else 0.0
    defence_delta = (defence_score(stats) / baseline.defence - 1.0) if baseline.defence > 0 else 0.0
    return dps_weight * dps_delta + defence_weight * defence_delta


def make_scorer(
    goal: str,
    baseline_stats: Stats,
    dps_weight: float = 0.5,
    defence_weight: float = 0.5,
) -> Scorer:
    normalized = goal.strip().lower()
    if normalized == "damage":
        return damage_score
    if normalized in ("defence", "defense"):
        return defence_score
    if normalized == "balanced":
        baseline = Baseline(dps=damage_score(baseline_stats), defence=defence_score(baseline_stats))
        return lambda stats: balanced_score(stats, baseline, dps_weight, defence_weight)
    raise ValueError(f"unknown goal {goal!r} (expected 'damage', 'defence', or 'balanced')")
