from app.domain.recommendation import Candidate, MacroRegime

MOCK_CANDIDATES = [
    Candidate("005930", 87400, 2350, 83, 67, 81, 89, 84, 98, 7, .91),
    Candidate("000660", 286500, 9200, 89, 55, 92, 94, 87, 96, 13, 1.18),
    Candidate("105560", 118900, 3100, 78, 91, 70, 77, 66, 92, 6, .72),
    Candidate("012450", 946000, 34500, 82, 43, 85, 80, 88, 82, 17, 1.25),
    Candidate("035420", 271000, 7800, 72, 70, 68, 73, 80, 95, 11, .94),
    Candidate("005380", 319000, 8500, 80, 84, 65, 76, 63, 93, 8, .86),
]
MOCK_REGIME = MacroRegime(vix=16.17, usdkrw_change_20d=-.9, us10y_change_bp_20d=7, credit_spread_change_bp_20d=-4)
