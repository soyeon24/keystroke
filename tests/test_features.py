"""합성 이벤트로 특징 추출 검증 — 실제 키 캡처 없이 파이프라인 로직만 테스트."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from capture import KeyEvent, KeyKind  # noqa: E402
from features import extract  # noqa: E402


def _typing(start=0.0, n=20, flight=0.15, dwell=0.09, kind=KeyKind.CHAR):
    """일정 리듬으로 치는 타이핑 이벤트 생성(press/release 쌍)."""
    evs = []
    t = start
    for _ in range(n):
        evs.append(KeyEvent(t, kind, down=True))
        evs.append(KeyEvent(t + dwell, kind, down=False))
        t += flight
    return evs


def test_empty_is_idle():
    f = extract([], node_id="t", window_sec=60, now_t=100.0)
    assert f.typing_active is False
    assert f.keydown_count == 0
    assert f.idle_ratio == 1.0


def test_steady_typing():
    evs = _typing(start=41.0, n=30, flight=0.15, dwell=0.09)
    f = extract(evs, node_id="t", window_sec=60, now_t=60.0)
    assert f.typing_active is True
    assert f.keydown_count == 30
    # dwell ≈ 90ms
    assert 80 <= f.dwell_ms.mean <= 100
    # flight ≈ 150ms, 규칙적이라 cv가 작아야 함
    assert 140 <= f.flight_ms.mean <= 160
    assert f.flight_cv < 0.1


def test_irregular_typing_has_higher_cv():
    # 불규칙 리듬: flight를 흔든다
    evs = []
    t = 41.0
    for i, fl in enumerate([0.1, 0.4, 0.12, 0.5, 0.09, 0.6, 0.11, 0.45] * 3):
        evs.append(KeyEvent(t, KeyKind.CHAR, down=True))
        evs.append(KeyEvent(t + 0.08, KeyKind.CHAR, down=False))
        t += fl
    f_irr = extract(evs, node_id="t", window_sec=60, now_t=60.0)
    f_steady = extract(_typing(41.0, 24, 0.15, 0.08), node_id="t", window_sec=60, now_t=60.0)
    assert f_irr.flight_cv > f_steady.flight_cv


def test_backspace_ratio():
    evs = _typing(41.0, 10, 0.15, 0.08, kind=KeyKind.CHAR)
    evs += _typing(43.0, 5, 0.15, 0.08, kind=KeyKind.BACKSPACE)
    f = extract(evs, node_id="t", window_sec=60, now_t=60.0)
    assert abs(f.backspace_ratio - (5 / 15)) < 0.01


def test_idle_ratio_and_pause():
    # 55초에 잠깐 5개만 침 → 대부분 idle
    evs = _typing(55.0, 5, 0.15, 0.08)
    f = extract(evs, node_id="t", window_sec=60, now_t=60.0)
    assert f.idle_ratio > 0.8


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
