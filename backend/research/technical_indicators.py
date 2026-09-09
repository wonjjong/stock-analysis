"""Daily-bar indicators, independent of market providers and Django.

Inputs are chronological (oldest first). Invalid observations reset the history;
they are never dropped to join prices across a missing trading observation.
"""

from collections.abc import Sequence
from itertools import pairwise
from math import isfinite
from statistics import pstdev


def technical_metrics(closes: Sequence[float], volumes: Sequence[float]) -> dict[str, float | None]:
    """Return latest Wilder RSI14, MACD12/26/9, Bollinger20 and volume ratio.

    Prices must be finite and positive; volumes finite and nonnegative. Each
    series uses its own valid suffix. Booleans and nonnumeric values are invalid.
    RSI needs 15 closes; a wholly flat history is neutral (50), gain-only is 100,
    and loss-only is 0. EMA seeds are SMA, so MACD needs 26 closes and its signal
    needs 34. Bands use population standard deviation, not sample deviation.
    Volume ratio is latest / mean(previous 20), excluding the latest volume;
    zero baseline or insufficient data yields None. No output is rounded.
    """
    prices = _valid_suffix(closes, positive=True)
    volume_history = _valid_suffix(volumes, positive=False)
    result = dict.fromkeys((
        "rsi_14", "macd", "macd_signal", "macd_histogram",
        "bollinger_upper", "bollinger_middle", "bollinger_lower", "volume_ratio",
    ))
    if len(prices) >= 15:
        changes = [current - previous for previous, current in pairwise(prices)]
        gain = sum(max(change, 0) / 14 for change in changes[:14])
        loss = sum(max(-change, 0) / 14 for change in changes[:14])
        for change in changes[14:]:
            gain = gain * (13 / 14) + max(change, 0) / 14
            loss = loss * (13 / 14) + max(-change, 0) / 14
        # Avoid an overflowing gain/loss ratio while preserving flat = 50.
        scale = max(gain, loss)
        result["rsi_14"] = 50.0 if scale == 0 else 100 * (gain / scale) / (gain / scale + loss / scale)
    if len(prices) >= 26:
        fast = _ema(prices, 12)
        slow = _ema(prices, 26)
        macd = [fast_value - slow_value for fast_value, slow_value in zip(fast[14:], slow, strict=True)]
        result["macd"] = macd[-1]
        if len(macd) >= 9:
            result["macd_signal"] = _ema(macd, 9)[-1]
            result["macd_histogram"] = macd[-1] - result["macd_signal"]
    if len(prices) >= 20:
        window = prices[-20:]
        middle = sum(value / 20 for value in window)
        spread = 2 * pstdev(window)
        result.update(
            bollinger_middle=middle, bollinger_upper=middle + spread, bollinger_lower=middle - spread,
        )
    if len(volume_history) >= 21:
        average = sum(value / 20 for value in volume_history[-21:-1])
        if average > 0:
            result["volume_ratio"] = volume_history[-1] / average
    return {key: value if value is None or isfinite(value) else None for key, value in result.items()}


def _valid_suffix(values: Sequence[float], *, positive: bool) -> list[float]:
    suffix = []
    for value in reversed(values):
        if isinstance(value, bool):
            break
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            break
        if not isfinite(number) or (number <= 0 if positive else number < 0):
            break
        suffix.append(number)
    return suffix[::-1]


def _ema(values: list[float], period: int) -> list[float]:
    average = sum(value / period for value in values[:period])
    result = [average]
    alpha = 2 / (period + 1)
    for value in values[period:]:
        average = alpha * value + (1 - alpha) * average
        result.append(average)
    return result
