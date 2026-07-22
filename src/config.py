"""DESKMATE 키스트로크 노드 설정.

환경변수로 덮어쓸 수 있으므로 노트북(개발)과 Pi4 연동(운영)에서 코드를 고치지 않아도 된다.
예) 브로커만 바꿔 Pi4에 붙이기:  set DESKMATE_BROKER=192.168.0.42
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass
class Config:
    # --- 노드 식별 ---
    node_id: str = field(default_factory=lambda: _env("DESKMATE_NODE_ID", "pc-keystroke"))

    # --- MQTT 브로커 (Pi4에서 Mosquitto가 돎) ---
    # 노트북 단독 개발 중에는 브로커가 없어도 되고, 이때는 로컬 로깅으로 자동 폴백한다.
    broker_host: str = field(default_factory=lambda: _env("DESKMATE_BROKER", "localhost"))
    broker_port: int = field(default_factory=lambda: int(_env("DESKMATE_BROKER_PORT", "1883")))
    topic: str = field(default_factory=lambda: _env("DESKMATE_TOPIC", "deskmate/keystroke/features"))
    qos: int = 0

    # --- 특징 추출 윈도 ---
    window_sec: float = float(_env("DESKMATE_WINDOW_SEC", "60"))   # 슬라이딩 윈도 길이
    publish_period_sec: float = float(_env("DESKMATE_PERIOD_SEC", "5"))  # 발행 주기

    # 연속 타이핑으로 볼 최대 키 간격(초). 이보다 크면 '멈춤(pause)'으로 보고
    # flight 통계에서 제외한다 → 타이핑 리듬과 사고(思考) 멈춤을 분리.
    flight_gap_max_sec: float = 2.0

    # 이 시간 이상 입력이 없으면 idle(비타이핑)로 간주
    idle_gap_sec: float = 3.0

    # --- 로깅 ---
    log_dir: str = field(default_factory=lambda: _env("DESKMATE_LOG_DIR", "logs"))


CONFIG = Config()
