from research.recommendation import Candidate, MacroRegime, rank_candidates


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
