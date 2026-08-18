"""Tests for the optimize_build tool's response-shaping helpers (not the
search itself -- see test_optimizer_goals.py / test_optimizer_moves.py for
that, and test_bridge_protocol.py for a live end-to-end run)."""

from __future__ import annotations

from pob_mcp.optimizer.tool import _filter_stats


def test_filter_stats_returns_full_dict_when_no_fields_given() -> None:
    stats = {"Life": 100, "Mana": 50, "TotalDPS": 1234.5}
    assert _filter_stats(stats, None) == stats
    assert _filter_stats(stats, []) == stats


def test_filter_stats_restricts_to_requested_keys() -> None:
    stats = {"Life": 100, "Mana": 50, "TotalDPS": 1234.5, "EnergyShield": 0}
    assert _filter_stats(stats, ["Life", "TotalDPS"]) == {"Life": 100, "TotalDPS": 1234.5}


def test_filter_stats_missing_key_becomes_none_not_a_keyerror() -> None:
    stats = {"Life": 100}
    assert _filter_stats(stats, ["Life", "NotARealStat"]) == {"Life": 100, "NotARealStat": None}
