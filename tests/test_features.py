"""합성 이벤트로 특징 추출 검증 — 실제 키 캡처 없이 파이프라인 로직만 테스트."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from capture import InputCapture, KeyEvent, KeyKind, MouseEvent  # noqa: E402
from features import extract  # noqa: E402


def _mouse(start=0.0, n=10, step=0.2, kind="move"):
    return [MouseEvent(start + i * step, kind) for i in range(n)]


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


def test_reading_no_input_at_all():
    # 글 읽기: 키보드도 마우스도 없음 → 전부 비활성
    f = extract([], node_id="t", window_sec=60, now_t=100.0, mouse_events=[])
    assert f.typing_active is False
    assert f.mouse_active is False
    assert f.input_active is False


def test_mouse_work_without_typing():
    # 마우스 작업: 키보드 없음, 마우스 활발 → input_active True, typing_active False
    mevs = _mouse(start=41.0, n=30, step=0.5, kind="move")
    mevs += [MouseEvent(42.0, "click"), MouseEvent(45.0, "click")]
    f = extract([], node_id="t", window_sec=60, now_t=60.0, mouse_events=mevs)
    assert f.typing_active is False
    assert f.mouse_active is True
    assert f.input_active is True
    assert f.mouse_event_rate > 0
    assert f.mouse_click_rate > 0


def test_typing_sets_input_active_even_without_mouse():
    evs = _typing(41.0, 20, 0.15, 0.08)
    f = extract(evs, node_id="t", window_sec=60, now_t=60.0, mouse_events=[])
    assert f.typing_active is True
    assert f.input_active is True
    assert f.mouse_active is False


def test_autorepeat_hold_counts_as_one_keydown():
    # 화살표 꾹 누름을 흉내: press 반복이 여러 번 들어와도 keydown은 1번만 기록되어야 함.
    cap = InputCapture()
    for _ in range(50):          # OS auto-repeat 50회
        cap._on_press("arrow")   # release 전이므로 첫 1회만 유효
    cap._on_release("arrow")
    downs = [e for e in cap.snapshot() if e.down]
    ups = [e for e in cap.snapshot() if not e.down]
    assert len(downs) == 1       # 반복이 부풀리지 않음
    assert len(ups) == 1
    # 뗐다가 다시 누르면 새 타건으로 정상 카운트
    cap._on_press("arrow")
    assert len([e for e in cap.snapshot() if e.down]) == 2


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
