import math

import pytest

from research.technical_indicators import technical_metrics


def test_empty_history_has_no_indicators():
    assert all(value is None for value in technical_metrics([], []).values())


@pytest.mark.parametrize("length,ready", [(14, False), (15, True)])
def test_rsi_requires_fourteen_changes(length, ready):
    result = technical_metrics(list(range(1, length + 1)), [])
    assert result["rsi_14"] == (100 if ready else None)


@pytest.mark.parametrize("prices,expected", [([10] * 40, 50), (list(range(40, 0, -1)), 0)])
def test_rsi_flat_and_falling(prices, expected):
    assert technical_metrics(prices, [])["rsi_14"] == expected


def test_wilder_rsi_known_sequence():
    prices = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
              46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
    assert technical_metrics(prices[:15], [])["rsi_14"] == pytest.approx(70.4641350211)
    assert technical_metrics(prices, [])["rsi_14"] == pytest.approx(66.2496185536)


@pytest.mark.parametrize("length", [25, 26, 33, 34, 100])
def test_macd_sma_seeds_and_signal_warmup(length):
    result = technical_metrics(list(range(1, length + 1)), [])
    assert result["macd"] == (pytest.approx(7) if length >= 26 else None)
    assert result["macd_signal"] == (pytest.approx(7) if length >= 34 else None)
    assert result["macd_histogram"] == (pytest.approx(0, abs=1e-10) if length >= 34 else None)


def test_macd_response_to_price_shock():
    result = technical_metrics([100] * 34 + [110], [])
    difference = 10 * (2 / 13 - 2 / 27)
    assert result["macd"] == pytest.approx(difference)
    assert result["macd_signal"] == pytest.approx(difference * 0.2)
    assert result["macd_histogram"] == pytest.approx(difference * 0.8)


def test_bollinger_uses_latest_twenty_population_deviation():
    result = technical_metrics([999, *range(1, 21)], [])
    assert result["bollinger_middle"] == pytest.approx(10.5)
    assert result["bollinger_upper"] == pytest.approx(10.5 + 2 * math.sqrt(33.25))
    assert result["bollinger_lower"] == pytest.approx(10.5 - 2 * math.sqrt(33.25))
    assert technical_metrics([10] * 19, [])["bollinger_middle"] is None


def test_volume_ratio_excludes_latest_and_allows_zero_current_volume():
    assert technical_metrics([], [999] + [100] * 20 + [250])["volume_ratio"] == 2.5
    assert technical_metrics([], [100] * 20 + [0])["volume_ratio"] == 0
    assert technical_metrics([], [0] * 20 + [100])["volume_ratio"] is None
    assert technical_metrics([], [100] * 20)["volume_ratio"] is None


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, 0, None, True, "bad"])
def test_invalid_price_does_not_bridge_missing_bar(invalid):
    result = technical_metrics([100] * 40 + [invalid] + [100] * 14, [100] * 21)
    assert result["rsi_14"] is None
    assert result["macd"] is None
    assert result["bollinger_middle"] is None
    assert result["volume_ratio"] == 1
    assert technical_metrics([invalid] + [100] * 34, [])["macd_signal"] == 0


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, None, True])
def test_invalid_volume_does_not_break_price_metrics(invalid):
    result = technical_metrics([100] * 34, [100] * 20 + [invalid])
    assert result["volume_ratio"] is None
    assert result["rsi_14"] == 50


def test_input_sequences_are_not_modified():
    closes = list(range(1, 41))
    volumes = [100] * 40
    technical_metrics(closes, volumes)
    assert closes == list(range(1, 41))
    assert volumes == [100] * 40
