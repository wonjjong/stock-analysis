"""규칙 기반 분석과 robots 판정 동일성."""

from __future__ import annotations

from news.crawler.analysis import analyze_news_locally
from news.crawler.robots import robots_allows


def test_analysis_cases_match(parity: dict) -> None:
    problems: list[str] = []
    for case in parity["analysis"]:
        expected = case["result"]
        actual = analyze_news_locally(case["text"], "MARKET", "시장 전체")
        for key, want in expected.items():
            got = actual.get(key)
            # JS 는 정수도 float 로 직렬화하지 않지만, 나눗셈이 들어간 confidence 는
            # float 이 될 수 있어 수치는 근사 비교한다.
            if isinstance(want, (int, float)) and not isinstance(want, bool):
                if abs(float(got) - float(want)) > 1e-9:
                    problems.append(f"  {case['text'][:24]}… {key}: 기대 {want} / 실제 {got}")
            elif got != want:
                problems.append(f"  {case['text'][:24]}… {key}:\n    기대 {want!r}\n    실제 {got!r}")
    assert not problems, "분석 불일치 {}건:\n{}".format(len(problems), "\n".join(problems))


def test_robots_cases_match(parity: dict) -> None:
    for case in parity["robots"]:
        actual = robots_allows(case["text"], case["url"])
        assert actual == case["allowed"], f"robots:\n{case['text']}\nurl={case['url']}"


def test_sentence_split_without_variable_lookbehind() -> None:
    """
    가변폭 lookbehind 를 고정폭 둘로 재구성한 것이 같은 지점에서 나누는지.
    삭제된 Python 프로토타입의 `replace("다. ", "다.| ")` 우회는 이 단정을 통과하지 못한다.
    """
    text = (
        "삼성전자가 실적을 발표했다. 영업이익이 컨센서스를 크게 상회하는 수준으로 나왔다. "
        "What about English? Yes it splits here too."
    )
    result = analyze_news_locally(text, "005930", "삼성전자")
    assert len(result["keyEvidence"]) >= 2
    assert all("|" not in item for item in result["keyEvidence"])
