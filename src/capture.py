"""입력 캡처 — 키보드/마우스의 타임스탬프와 '종류'만 수집한다.

프라이버시 원칙(계획서): 실제 내용은 저장/전송하지 않는다.
- 키보드: 어떤 물리 키인지는 dwell 계산을 위해 '메모리 안에서만' 잠깐 식별하고,
  기록/전송 값은 (시간, 종류, press/release)뿐. 종류는 char/space/backspace/enter/other.
- 마우스: 좌표(x,y)·클릭한 버튼·스크롤 내용은 절대 보지 않는다. '이동/클릭/스크롤이
  일어났다'는 사실(시간, 종류)만 기록 → 활동량만 알 수 있고 무엇을 했는지는 복원 불가.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

from pynput import keyboard, mouse


class KeyKind(str, Enum):
    CHAR = "char"          # 문자/숫자/기호 (내용은 구분 안 함)
    SPACE = "space"
    BACKSPACE = "backspace"
    ENTER = "enter"
    OTHER = "other"        # shift, ctrl, 방향키 등


@dataclass(frozen=True)
class KeyEvent:
    t: float          # time.monotonic() 기준 타임스탬프(초)
    kind: KeyKind
    down: bool        # True=press, False=release


@dataclass(frozen=True)
class MouseEvent:
    t: float          # time.monotonic() 기준 타임스탬프(초)
    kind: str         # "move" | "click" | "scroll" (좌표·버튼은 저장 안 함)


def _classify(key) -> KeyKind:
    """pynput 키 객체를 '종류'로만 매핑. 실제 문자 값은 반환하지 않는다."""
    if key == keyboard.Key.space:
        return KeyKind.SPACE
    if key == keyboard.Key.backspace:
        return KeyKind.BACKSPACE
    if key in (keyboard.Key.enter,):
        return KeyKind.ENTER
    # KeyCode(문자/숫자/기호)는 char로 뭉뚱그린다 — 어떤 글자인지는 절대 보지 않는다.
    if isinstance(key, keyboard.KeyCode):
        return KeyKind.CHAR
    return KeyKind.OTHER


class InputCapture:
    """백그라운드 스레드로 키보드+마우스 이벤트를 thread-safe 버퍼에 쌓는다."""

    def __init__(self, max_events: int = 20000, move_throttle_sec: float = 0.05):
        self._events: deque[KeyEvent] = deque(maxlen=max_events)
        self._mouse: deque[MouseEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._kb: keyboard.Listener | None = None
        self._ms: mouse.Listener | None = None
        # 물리 키별 마지막 press 시각(메모리 전용, 외부로 안 나감) — dwell 계산용.
        self._down_at: dict[object, float] = {}
        # 마우스 이동은 초당 수백 번 발생하므로 이 간격으로 다운샘플(활동량만 필요).
        self._move_throttle = move_throttle_sec
        self._last_move_t = 0.0

    # ---------- 키보드 ----------
    def _on_press(self, key):
        t = time.monotonic()
        kind = _classify(key)
        self._down_at.setdefault(key, t)  # auto-repeat 연타는 첫 press만
        with self._lock:
            self._events.append(KeyEvent(t, kind, down=True))

    def _on_release(self, key):
        t = time.monotonic()
        kind = _classify(key)
        self._down_at.pop(key, None)
        with self._lock:
            self._events.append(KeyEvent(t, kind, down=False))

    # ---------- 마우스 (좌표/버튼은 무시, 활동만) ----------
    def _on_move(self, x, y):
        t = time.monotonic()
        if t - self._last_move_t < self._move_throttle:
            return  # 다운샘플: 잦은 이동 이벤트 폭주 방지
        self._last_move_t = t
        with self._lock:
            self._mouse.append(MouseEvent(t, "move"))

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return  # press 순간만 1회 기록
        t = time.monotonic()
        with self._lock:
            self._mouse.append(MouseEvent(t, "click"))

    def _on_scroll(self, x, y, dx, dy):
        t = time.monotonic()
        with self._lock:
            self._mouse.append(MouseEvent(t, "scroll"))

    # ---------- 수명주기 ----------
    def start(self):
        self._kb = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._ms = mouse.Listener(
            on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll
        )
        self._kb.start()
        self._ms.start()

    def stop(self):
        for lst in (self._kb, self._ms):
            if lst is not None:
                lst.stop()
        self._kb = self._ms = None

    # ---------- 조회 ----------
    def snapshot(self, since_t: float | None = None) -> list[KeyEvent]:
        """키보드 이벤트 복사본. since_t가 주어지면 그 이후만."""
        with self._lock:
            evs = list(self._events)
        if since_t is not None:
            evs = [e for e in evs if e.t >= since_t]
        return evs

    def mouse_snapshot(self, since_t: float | None = None) -> list[MouseEvent]:
        """마우스 이벤트 복사본. since_t가 주어지면 그 이후만."""
        with self._lock:
            evs = list(self._mouse)
        if since_t is not None:
            evs = [e for e in evs if e.t >= since_t]
        return evs


# 하위호환 별칭(이전 이름을 쓰던 코드 대비)
KeystrokeCapture = InputCapture
