from research.lab_preview import build_lab_preview


def test_lab_preview_is_self_contained_and_marks_itself_as_non_ai() -> None:
    preview = build_lab_preview()

    result = preview["result"]
    assert preview["is_preview"] is True
    assert preview["attempts"] == []
    assert result["snapshot"].symbol == "DEMO"
    assert result["report"].engine == "AI 미호출 미리보기"
    assert len(result["chart"]["points"]) == 120
