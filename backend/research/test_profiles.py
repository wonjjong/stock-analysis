"""공시 프로필 파서 검증. 실제 응답을 축약한 픽스처만 쓴다."""

from __future__ import annotations

from research.dart_profile import account_evidence, parse_single_account, select_accounts
from research.sec_profile import build_filer_profile, profile_evidence
from research.services.company_index import CompanyRef


def _submissions(forms: list[tuple[str, str, str]], **overrides) -> dict:
    """forms 는 (폼, 제출일, 보고기준일) 목록."""
    payload = {
        "cik": 1878848,
        "name": "IREN Ltd",
        "tickers": ["IREN"],
        "exchanges": ["Nasdaq"],
        "sicDescription": "Finance Services",
        "stateOfIncorporation": "C3",
        "fiscalYearEnd": "0630",
        "filings": {
            "recent": {
                "form": [item[0] for item in forms],
                "filingDate": [item[1] for item in forms],
                "reportDate": [item[2] for item in forms],
                "accessionNumber": [f"0001-23-{i:06d}" for i in range(len(forms))],
                "primaryDocument": ["main.htm"] * len(forms),
            }
        },
    }
    payload.update(overrides)
    return payload


# IREN 실측 형태: 6-K 위주에 10-K/10-Q 가 없다.
IREN_FORMS = [("6-K", "2025-08-01", "2025-06-30")] * 3 + [("8-K", "2025-07-01", "2025-06-25")]
APPLE_FORMS = [("10-K", "2024-11-01", "2024-09-28"), ("10-Q", "2024-08-02", "2024-06-29")]


def test_six_k_only_filer_uses_foreign_forms():
    profile = build_filer_profile(_submissions(IREN_FORMS))
    assert profile.reporting_regime == "미국 기준 외국법인 양식(6-K 중심)"
    assert profile.files_foreign_forms


def test_domestic_forms_are_detected_from_10k():
    profile = build_filer_profile(_submissions(APPLE_FORMS))
    assert profile.reporting_regime == "미국 내국법인 양식(10-K·10-Q)"
    assert not profile.files_foreign_forms


def test_incorporation_is_independent_of_reporting_forms():
    """IREN 처럼 호주 법인이 10-K 로 보고하는 경우를 '내국법인'으로 뭉뚱그리지 않는다."""
    profile = build_filer_profile(_submissions(APPLE_FORMS, stateOfIncorporation="C3"))
    assert profile.is_non_us_incorporated
    assert profile.reporting_regime == "미국 내국법인 양식(10-K·10-Q)"
    summary = next(e for e in profile_evidence(profile, "now") if e.id == "sec:profile").summary
    assert "미국 밖에서 설립된 법인이지만 미국 내국법인 양식으로 보고한다" in summary


def test_us_state_of_incorporation_is_not_flagged_as_non_us():
    profile = build_filer_profile(_submissions(APPLE_FORMS, stateOfIncorporation="DE"))
    assert not profile.is_non_us_incorporated


def test_regime_change_is_detected_and_warns_about_accounting_basis():
    """IREN 은 2024년까지 20-F, 2025년부터 10-K 다. 그 사이 IFRS→US-GAAP 이 바뀌었다."""
    forms = [("10-K", "2026-08-27", "2026-06-30"), ("10-Q", "2026-05-01", "2026-03-31")]
    forms += [("20-F", "2024-09-01", "2024-06-30"), ("6-K", "2024-03-01", "2024-02-28")]
    profile = build_filer_profile(_submissions(forms), limit=2)
    assert profile.changed_regime
    summary = next(e for e in profile_evidence(profile, "now") if e.id == "sec:profile").summary
    assert "회계기준(IFRS/US-GAAP)도 함께 바뀌었을 수 있다" in summary


def test_form_counts_are_tallied():
    assert build_filer_profile(_submissions(IREN_FORMS)).form_counts == {"6-K": 3, "8-K": 1}


def test_latest_annual_prefers_the_annual_form():
    profile = build_filer_profile(_submissions(APPLE_FORMS))
    assert profile.latest_annual is not None
    assert profile.latest_annual.form == "10-K"


def test_filing_url_drops_dashes_and_leading_zeros():
    profile = build_filer_profile(_submissions(APPLE_FORMS))
    assert profile.recent_filings[0].url.startswith("https://www.sec.gov/Archives/edgar/data/1878848/")
    assert "-" not in profile.recent_filings[0].url.rsplit("/", 2)[1]


def test_evidence_separates_event_time_from_disclosure_time():
    profile = build_filer_profile(_submissions(APPLE_FORMS))
    evidence = profile_evidence(profile, "2026-09-04T00:00:00Z")
    filing = next(item for item in evidence if item.id.startswith("sec:filing:"))
    assert filing.observed_at == "2024-09-28"  # periodOfReport
    assert filing.available_at == "2024-11-01"  # filingDate


def test_foreign_form_evidence_mentions_missing_quarterly_duty():
    profile = build_filer_profile(_submissions(IREN_FORMS))
    identity = next(e for e in profile_evidence(profile, "now") if e.id == "sec:profile")
    assert "분기 실적 공시 의무가 없어" in identity.summary


def test_empty_submissions_do_not_crash():
    profile = build_filer_profile({})
    assert profile.reporting_regime == "미상"
    assert profile.recent_filings == ()


# --- DART ---

DART_PAYLOAD = {
    "list": [
        {"account_nm": "매출액", "fs_div": "OFS", "thstrm_amount": "1,000", "frmtrm_amount": "900"},
        {"account_nm": "매출액", "fs_div": "CFS", "thstrm_amount": "2,000", "frmtrm_amount": "1,800"},
        {"account_nm": "영업이익", "fs_div": "CFS", "thstrm_amount": "-500", "frmtrm_amount": "-"},
    ]
}


def test_amounts_strip_commas_and_treat_dash_as_missing():
    accounts = parse_single_account(DART_PAYLOAD)
    assert accounts[0].current == 1000.0
    assert accounts[2].current == -500.0
    assert accounts[2].previous is None


def test_consolidated_statement_wins_over_separate():
    assert select_accounts(parse_single_account(DART_PAYLOAD))["매출액"].current == 2000.0


def test_account_evidence_summarises_key_lines():
    company = CompanyRef(market="KR", key="00126380", ticker="005930", name="삼성전자")
    evidence = account_evidence(company, parse_single_account(DART_PAYLOAD), "2023", "11011", "now")
    assert evidence[0].observed_at == "2023-12-31"
    assert "매출액=2,000원" in evidence[0].summary


def test_empty_dart_payload_yields_no_evidence():
    company = CompanyRef(market="KR", key="00126380", ticker="005930", name="삼성전자")
    assert account_evidence(company, parse_single_account({}), "2023", "11011", "now") == []


def test_profile_without_annual_report_anchors_on_the_latest_filing():
    """펀드처럼 10-K/20-F 를 내지 않는 발행사도 observed_at 이 날짜여야 한다."""
    profile = build_filer_profile(_submissions([("NPORT-P", "2026-08-28", "2026-06-30")]))
    identity = next(item for item in profile_evidence(profile, "now") if item.id == "sec:profile")
    assert identity.observed_at == "2026-06-30"
