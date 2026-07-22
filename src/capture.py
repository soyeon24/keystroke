"""키 입력 캡처 — 타임스탬프와 '키 종류'만 수집한다.

프라이버시 원칙(계획서): 실제 글자는 저장/전송하지 않는다.
- 어떤 물리 키인지는 dwell(누름시간) 계산을 위해 '메모리 안에서만' 잠깐 식별하고,
  기록으로 남기거나 밖으로 내보내는 값은 오직 (시간, 종류, press/release)뿐이다.
- 종류는 char / space / backspace / enter / other 5가지로만 분류해 내용 복원이 불가능하다.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

from pynput import keyboard


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


class KeystrokeCapture:
    """백그라운드 스레드로 키 이벤트를 모아 thread-safe 버퍼에 쌓는다."""

    def __init__(self, max_events: int = 20000):
        self._events: deque[KeyEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._listener: keyboard.Listener | None = None
        # 물리 키별 마지막 press 시각(메모리 전용, 외부로 안 나감) — dwell 계산용.
        self._down_at: dict[object, float] = {}

    def _on_press(self, key):
        t = time.monotonic()
        kind = _classify(key)
        # auto-repeat(키 꾹 누름)로 press가 연타되어도 첫 press 시각만 유지
        self._down_at.setdefault(key, t)
        with self._lock:
            self._events.append(KeyEvent(t, kind, down=True))

    def _on_release(self, key):
        t = time.monotonic()
        kind = _classify(key)
        self._down_at.pop(key, None)
        with self._lock:
            self._events.append(KeyEvent(t, kind, down=False))

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def snapshot(self, since_t: float | None = None) -> list[KeyEvent]:
        """현재 버퍼 복사본을 반환. since_t가 주어지면 그 이후 이벤트만."""
        with self._lock:
            evs = list(self._events)
        if since_t is not None:
            evs = [e for e in evs if e.t >= since_t]
        return evs
