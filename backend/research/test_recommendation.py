from research.recommendation import Candidate, MacroRegime, rank_candidates, scoring_policy, trade_plan


def test_rank_is_deterministic_and_respects_limit():
    candidates = [Candidate(f"S{i}", 100+i, 3, 50+i*4, 70-i, 55+i*3, 50+i*2, 50+i, 80, 10, 1) for i in range(8)]
    regime = MacroRegime(17, -1, 2, -3)
    first = rank_candidates(candidates, regime, 5)
    assert first == rank_candidates(candidates, regime, 5)
    assert len(first) == 5
    assert all(item["stop"] < item["entry_high"] < item["target"] for item in first)


def test_stale_and_illiquid_names_are_excluded():
    candidates = [Candidate("GOOD",100,3,80,80,80,80,80,90,5,1), Candidate("STALE",100,3,99,99,99,99,99,90,5,1,.4), Candidate("DRY",100,3,99,99,99,99,99,10,5,1)]
    result = rank_candidates(candidates, MacroRegime(20,0,0,0), 5)
    assert [row["symbol"] for row in result] == ["GOOD"]


def test_trade_plan_uses_the_same_atr_rules_as_the_ranker():
    plan = trade_plan(100, 3, MacroRegime(18, 0, 0, 0))

    assert plan is not None
    assert round(plan.entry_low, 2) == 98.35
    assert round(plan.entry_high, 2) == 99.55
    assert plan.stop < plan.entry_low < plan.entry_high < plan.target


def test_trade_plan_requires_a_valid_price_and_atr():
    regime = MacroRegime(18, 0, 0, 0)

    assert trade_plan(100, 0, regime) is None
    assert trade_plan(0, 3, regime) is None


def test_news_is_not_scored_during_a_cold_start():
    candidates = [
        Candidate("A", 100, 3, 80, 70, 60, 50, 0, 90, 5, 1),
        Candidate("B", 100, 3, 70, 80, 50, 50, 100, 90, 5, 1),
    ]

    policy = scoring_policy(candidates)
    ranked = rank_candidates(candidates, MacroRegime(18, 0, 0, 0), 2)

    assert not policy.news_enabled
    assert policy.news_status == "뉴스 데이터 축적 중 — 미반영"
    assert all("news" not in row["reasons"] for row in ranked)


def test_news_is_enabled_after_most_candidates_have_coverage():
    candidates = [
        Candidate("A", 100, 3, 80, 70, 60, 50, 40, 90, 5, 1, news_observations=2),
        Candidate("B", 100, 3, 70, 80, 50, 50, 80, 90, 5, 1, news_observations=1),
        Candidate("C", 100, 3, 60, 60, 70, 50, 50, 90, 5, 1),
    ]

    policy = scoring_policy(candidates)

    assert policy.news_enabled
    assert policy.news_coverage_ratio == 2 / 3
