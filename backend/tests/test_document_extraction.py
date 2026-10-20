from backend.features.documents.extraction import decode_text, extract_candidates


def test_text_date_extraction_is_deterministic_and_validates_dates():
    text = "家长会 2026年10月8日 19:00\n错误日期 2026-02-31\n缴费截止 2026-10-09"
    assert decode_text(text.encode(), "notice.txt", "text/plain") == text
    items = extract_candidates(text, "notice")
    assert [(item["target_type"], item["proposed_date"]) for item in items] == [
        ("event", "2026-10-08"),
        ("todo", "2026-10-09"),
    ]
    assert decode_text(b"binary", "notice.pdf", "application/pdf") is None
