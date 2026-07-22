"""DESKMATE 키스트로크 노드 엔트리포인트.

캡처 → 특징추출 → 발행 루프. Ctrl+C로 종료.
사용:  python src/main.py
Pi4 연동:  set DESKMATE_BROKER=<Pi4 IP>  후 실행.
"""
from __future__ import annotations

import signal
import time

from capture import KeystrokeCapture
from config import CONFIG
from features import extract
from publisher import FeaturePublisher


def main():
    cfg = CONFIG
    print("=" * 60)
    print("DESKMATE keystroke node")
    print(f"  node_id     : {cfg.node_id}")
    print(f"  broker      : {cfg.broker_host}:{cfg.broker_port}")
    print(f"  topic       : {cfg.topic}")
    print(f"  window/period: {cfg.window_sec}s / {cfg.publish_period_sec}s")
    print("  (키 값은 저장/전송하지 않음 — 타이밍과 종류만)")
    print("=" * 60)

    capture = KeystrokeCapture()
    publisher = FeaturePublisher(
        host=cfg.broker_host, port=cfg.broker_port, topic=cfg.topic,
        qos=cfg.qos, node_id=cfg.node_id, log_dir=cfg.log_dir,
    )

    running = {"on": True}

    def _handle_sigint(sig, frame):
        running["on"] = False

    signal.signal(signal.SIGINT, _handle_sigint)

    capture.start()
    publisher.start()

    try:
        while running["on"]:
            time.sleep(cfg.publish_period_sec)
            now_t = time.monotonic()
            events = capture.snapshot(since_t=now_t - cfg.window_sec)
            feats = extract(
                events,
                node_id=cfg.node_id,
                window_sec=cfg.window_sec,
                now_t=now_t,
                flight_gap_max_sec=cfg.flight_gap_max_sec,
                idle_gap_sec=cfg.idle_gap_sec,
            )
            publisher.publish(feats.to_dict())
    finally:
        print("\n[node] shutting down...")
        capture.stop()
        publisher.stop()


if __name__ == "__main__":
    main()
