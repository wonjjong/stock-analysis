from research.market_data import moving_averages, price_chart_points


def test_moving_averages_reports_a_bullish_alignment() -> None:
    averages = moving_averages(list(range(1, 121)), 120)

    assert averages.ma_20 == 110.5
    assert averages.ma_60 == 90.5
    assert averages.ma_100 == 70.5
    assert averages.alignment == "정배열"
    assert averages.price_above_ma_20 is True
    assert averages.price_above_ma_60 is True
    assert averages.price_above_ma_100 is True


def test_moving_averages_reports_a_bearish_alignment_and_missing_history() -> None:
    bearish = moving_averages(list(range(120, 0, -1)), 1)
    short = moving_averages(list(range(1, 60)), 59)

    assert bearish.alignment == "역배열"
    assert bearish.price_above_ma_20 is False
    assert short.ma_60 is None
    assert short.alignment == "이평 데이터 부족"


def test_price_chart_points_keeps_recent_history_with_rolling_averages() -> None:
    rows = [
        (f"2026-01-{day:03d}", float(day - .5), float(day + .5), float(day - 1), float(day))
        for day in range(1, 151)
    ]

    points = price_chart_points(rows, limit=120)

    assert len(points) == 120
    assert points[0].date == "2026-01-031"
    assert points[-1].open == 149.5
    assert points[-1].high == 150.5
    assert points[-1].low == 149
    assert points[-1].close == 150
    assert points[-1].ma_20 == 140.5
    assert points[-1].ma_60 == 120.5
    assert points[-1].ma_100 == 100.5
