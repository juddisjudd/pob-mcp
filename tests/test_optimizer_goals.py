"""Pure unit tests for optimizer scoring. No bridge process required."""

from __future__ import annotations

import pytest

from pob_mcp.optimizer.goals import damage_score, defence_score, make_scorer


def test_damage_score_prefers_combined_dps_over_total_dps() -> None:
    stats = {"CombinedDPS": 100.0, "TotalDPS": 50.0}
    assert damage_score(stats) == 100.0


def test_damage_score_falls_back_through_candidates() -> None:
    stats = {"CombinedDPS": 0, "TotalDPS": 0, "TotalDot": 42.0}
    assert damage_score(stats) == 42.0


def test_damage_score_defaults_to_zero_when_nothing_present() -> None:
    assert damage_score({}) == 0.0


def test_defence_score_uses_life_plus_es_plus_ward_as_floor() -> None:
    stats = {"Life": 1000.0, "EnergyShield": 500.0, "Ward": 0.0}
    assert defence_score(stats) == 1500.0


def test_defence_score_prefers_explicit_ehp_field_when_larger() -> None:
    stats = {"Life": 1000.0, "EnergyShield": 0.0, "TotalEHP": 4000.0}
    assert defence_score(stats) == 4000.0


def test_defence_score_penalizes_uncapped_resistances() -> None:
    capped = {"Life": 1000.0, "FireResist": 75.0, "ColdResist": 75.0, "LightningResist": 75.0}
    uncapped = {"Life": 1000.0, "FireResist": 0.0, "ColdResist": 75.0, "LightningResist": 75.0}
    assert defence_score(uncapped) < defence_score(capped)


def test_make_scorer_damage_and_defence() -> None:
    stats = {"CombinedDPS": 10.0, "Life": 500.0}
    assert make_scorer("damage", stats)(stats) == damage_score(stats)
    assert make_scorer("defence", stats)(stats) == defence_score(stats)
    assert make_scorer("defense", stats)(stats) == defence_score(stats)  # US spelling alias


def test_make_scorer_balanced_is_zero_at_baseline() -> None:
    baseline = {"CombinedDPS": 100.0, "Life": 1000.0}
    scorer = make_scorer("balanced", baseline, dps_weight=0.5, defence_weight=0.5)
    assert scorer(baseline) == pytest.approx(0.0)


def test_make_scorer_balanced_rewards_improvement_on_both_axes() -> None:
    baseline = {"CombinedDPS": 100.0, "Life": 1000.0}
    improved = {"CombinedDPS": 150.0, "Life": 1100.0}
    scorer = make_scorer("balanced", baseline, dps_weight=0.5, defence_weight=0.5)
    assert scorer(improved) > 0


def test_make_scorer_rejects_unknown_goal() -> None:
    with pytest.raises(ValueError):
        make_scorer("unobtainium", {})
