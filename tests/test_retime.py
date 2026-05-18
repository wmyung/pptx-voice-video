from pptx_voice_video.retime import semantic_pause_events


def test_semantic_pause_events_ignore_whitespace():
    text = "첫 번째 개념은 중요합니다\n두 번째 개념도 중요합니다"
    events = semantic_pause_events(text)
    assert all(e["reason"] != "whitespace" for e in events)


def test_semantic_pause_events_weight_discourse_shift():
    text = "이 결과는 중요합니다. 하지만 해석에는 주의가 필요합니다."
    events = semantic_pause_events(text)
    assert any(e["reason"] == "sentence_end_discourse_shift" for e in events)


def test_semantic_pause_events_do_not_pause_every_list_comma():
    text = "조현병, 우울증, 양극성장애, 자폐스펙트럼장애를 살펴봅니다."
    events = semantic_pause_events(text)
    comma_events = [e for e in events if e["punct"] == ","]
    assert len(comma_events) < 3
