"""본문 추출 동일성. 크롤러 쪽 text.py 와 동작이 다른 지점을 명시적으로 확인한다."""

from __future__ import annotations

from news.crawler.body import MAX_BODY_CHARS, extract_body
from news.crawler.text import clean_text


def test_body_cases_match(parity: dict) -> None:
    """TS 구현의 실제 출력을 고정한 것. 입력과 출력이 짝으로 들어 있다."""
    cases = parity.get("bodyCases")
    if not cases:
        import pytest

        pytest.skip("정답지에 본문 추출 기준값이 없습니다.")
    problems: list[str] = []
    for case in cases:
        actual = extract_body(case["html"])
        if actual != case["body"]:
            problems.append(
                f"  입력 {case['html'][:50]}…\n    기대 {case['body'][:70]!r}"
                f"\n    실제 {actual[:70]!r}"
            )
    assert not problems, "본문 추출 불일치 {}건:\n{}".format(
        len(problems), "\n".join(problems)
    )


def test_paragraphs_are_collected_and_boilerplate_dropped() -> None:
    html = (
        "<div><p>첫 문단입니다. 충분히 길어서 최소 길이를 넘습니다.</p>"
        "<p>두 번째 문단입니다. 이것도 최소 길이를 넘깁니다.</p>"
        "<script>alert(1)</script>"
        "<p>무단 전재 및 재배포 금지 - 저작권자 연합뉴스</p></div>"
    )
    body = extract_body(html)
    assert "첫 문단입니다" in body
    assert "두 번째 문단입니다" in body
    assert "무단" not in body, "저작권 문구가 본문에 섞였습니다"
    assert "alert" not in body, "script 내용이 본문에 섞였습니다"


def test_short_paragraphs_fall_through_to_block() -> None:
    """
    20자 미만 문단은 문단 목록에서 빠진다. 그러면 문단이 2개 미만이 되어 **최장 블록
    폴백**이 걸리고 결국 블록 전체가 본문이 된다. TS 도 같은 결과를 낸다(정답지 확인).
    """
    body = extract_body("<div><p>짧음</p><p>이것도짧다</p></div>")
    assert body == "짧음 이것도짧다"


def test_falls_back_to_longest_block() -> None:
    """문단이 2개 미만이면 가장 글자가 많은 블록으로 대체한다."""
    long_text = "문단 태그가 없는 아주 긴 블록입니다. " * 20
    html = f"<div>{long_text}</div><div>짧은 블록</div>"
    body = extract_body(html)
    assert "아주 긴 블록" in body
    assert len(body) > 100


def test_body_is_capped() -> None:
    html = "<div>" + "<p>" + ("가" * 500 + " ") * 40 + "</p>" + "</div>"
    assert len(extract_body(html)) <= MAX_BODY_CHARS


def test_unknown_entity_becomes_space_unlike_crawler() -> None:
    """
    본문 추출은 알 수 없는 named 엔티티를 **공백**으로 바꾸고, 크롤러 쪽 clean_text 는
    `&entity;` 로 되돌린다. 원본이 별도 구현을 둔 차이라 유지한다.
    """
    html = "<div><p>가격이 &euro;100 입니다. 충분히 긴 문단입니다 여기.</p>" \
           "<p>두 번째 문단도 충분히 길게 씁니다 여기까지.</p></div>"
    body = extract_body(html)
    assert "&euro;" not in body
    # 크롤러 쪽은 되돌린다
    assert "&euro;" in clean_text("가격이 &euro;100")


def test_numeric_entities_are_decoded() -> None:
    html = "<div><p>&#44032;&#45208;&#45796; 로 시작하는 충분히 긴 문단입니다.</p>" \
           "<p>두 번째 문단도 충분한 길이를 갖도록 씁니다.</p></div>"
    assert "가나다" in extract_body(html)
