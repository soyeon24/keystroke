"""입력 타이밍 → 특징 벡터.

계획서의 4대 키보드 특징을 산출한다:
  1) dwell(키 누름 유지 시간)  2) flight(키 간격)과 분산
  3) 공백 비율(입력 없는 시간 비율)  4) 정정(백스페이스) 빈도
추가로 리듬 불규칙성(cv), 타이핑 속도(kpm), 그리고 마우스 활동을 낸다.

마우스는 "글 읽기(입력 전무) vs 마우스 작업(입력 있음)"을 PC 단에서 구분해주는 신호다.
입력은 capture의 KeyEvent/MouseEvent 리스트라서 캡처 방식과 무관하게 단위 테스트가 가능하다.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

from capture import KeyEvent, KeyKind, MouseEvent


@dataclass
class Stat:
    mean: float = 0.0
    std: float = 0.0

    @classmethod
    def of(cls, xs: list[float]) -> "Stat":
        if not xs:
            return cls()
        if len(xs) == 1:
            return cls(mean=round(xs[0], 2), std=0.0)
        return cls(
            mean=round(statistics.fmean(xs), 2),
            std=round(statistics.pstdev(xs), 2),
        )


@dataclass
class Features:
    node_id: str
    window_sec: float
    # --- 통합 입력 ---
    input_active: bool = False         # 키보드든 마우스든 뭐라도 입력 중
    typing_active: bool = False        # 키보드 입력이 있었나
    mouse_active: bool = False         # 마우스 입력이 있었나
    # --- 키보드 ---
    keydown_count: int = 0
    kpm: float = 0.0                   # keys per minute
    dwell_ms: Stat = field(default_factory=Stat)
    flight_ms: Stat = field(default_factory=Stat)
    flight_cv: float = 0.0             # 리듬 불규칙성 = std/mean
    backspace_ratio: float = 0.0       # 백스페이스 / 전체 keydown
    idle_ratio: float = 0.0            # 윈도 중 키 입력 없는 시간 비율
    pause_count: int = 0               # idle_gap 이상 멈춘 횟수
    # --- 마우스 (활동량만, 좌표 없음) ---
    mouse_event_rate: float = 0.0      # 분당 마우스 이벤트 수(이동 다운샘플됨)
    mouse_click_rate: float = 0.0      # 분당 클릭 수
    mouse_scroll_rate: float = 0.0     # 분당 스크롤 수

    def to_dict(self) -> dict:
        return asdict(self)


def extract(
    events: list[KeyEvent],
    node_id: str,
    window_sec: float,
    now_t: float,
    mouse_events: list[MouseEvent] | None = None,
    flight_gap_max_sec: float = 2.0,
    idle_gap_sec: float = 3.0,
) -> Features:
    """[now_t - window_sec, now_t] 구간 이벤트에서 특징을 뽑는다."""
    start_t = now_t - window_sec
    evs = [e for e in events if start_t <= e.t <= now_t]

    f = Features(node_id=node_id, window_sec=round(window_sec, 2))

    # ---------- 마우스 (키보드 유무와 무관하게 항상 계산) ----------
    mevs = [e for e in (mouse_events or []) if start_t <= e.t <= now_t]
    if mevs:
        f.mouse_active = True
        f.mouse_event_rate = round(len(mevs) / window_sec * 60.0, 1)
        f.mouse_click_rate = round(
            sum(1 for e in mevs if e.kind == "click") / window_sec * 60.0, 1
        )
        f.mouse_scroll_rate = round(
            sum(1 for e in mevs if e.kind == "scroll") / window_sec * 60.0, 1
        )

    # ---------- 키보드 ----------
    downs = [e for e in evs if e.down]
    f.keydown_count = len(downs)
    if not downs:
        f.idle_ratio = 1.0
        f.input_active = f.mouse_active     # 키보드는 없어도 마우스 작업 중일 수 있음
        return f

    f.typing_active = True
    f.input_active = True
    f.kpm = round(len(downs) / window_sec * 60.0, 1)

    # --- 백스페이스 비율 ---
    bs = sum(1 for e in downs if e.kind == KeyKind.BACKSPACE)
    f.backspace_ratio = round(bs / len(downs), 4)

    # --- dwell: 같은 종류의 press→다음 release 매칭(근사) ---
    dwell_ms: list[float] = []
    pending: dict[KeyKind, list[float]] = {}
    for e in evs:
        if e.down:
            pending.setdefault(e.kind, []).append(e.t)
        else:
            q = pending.get(e.kind)
            if q:
                dt = (e.t - q.pop(0)) * 1000.0
                if 0 < dt < 2000:   # 비정상적으로 긴 값(꾹 누름 등)은 제외
                    dwell_ms.append(dt)
    f.dwell_ms = Stat.of(dwell_ms)

    # --- flight: 연속 keydown 간격. 멈춤(> flight_gap_max)은 리듬 통계서 제외 ---
    down_times = [e.t for e in downs]
    flights_ms: list[float] = []
    pauses = 0
    for a, b in zip(down_times, down_times[1:]):
        gap = b - a
        if gap >= idle_gap_sec:
            pauses += 1
        if gap <= flight_gap_max_sec:
            flights_ms.append(gap * 1000.0)
    f.flight_ms = Stat.of(flights_ms)
    f.flight_cv = round(f.flight_ms.std / f.flight_ms.mean, 3) if f.flight_ms.mean else 0.0
    f.pause_count = pauses

    # --- 공백(idle) 비율: 입력 사이 idle_gap 초과분 + 앞뒤 여백을 합산 ---
    idle = 0.0
    idle += max(0.0, down_times[0] - start_t)          # 윈도 시작~첫 입력
    idle += max(0.0, now_t - down_times[-1])            # 마지막 입력~윈도 끝
    for a, b in zip(down_times, down_times[1:]):
        gap = b - a
        if gap > idle_gap_sec:
            idle += gap
    f.idle_ratio = round(min(1.0, idle / window_sec), 4)

    return f
