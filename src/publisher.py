"""특징 벡터를 MQTT로 발행. 브로커가 없으면 콘솔/파일 로깅으로 자동 폴백한다.

노트북 단독 개발 단계: 브로커 없이도 돌아가며 특징을 눈으로 확인.
Pi4 연동 단계: DESKMATE_BROKER 만 Pi4 IP로 바꾸면 그대로 발행된다.
paho-mqtt 2.x API 기준.
"""
from __future__ import annotations

import json
import os
import time

import paho.mqtt.client as mqtt


class FeaturePublisher:
    def __init__(self, host: str, port: int, topic: str, qos: int = 0,
                 node_id: str = "pc-keystroke", log_dir: str = "logs"):
        self.host = host
        self.port = port
        self.topic = topic
        self.qos = qos
        self.node_id = node_id
        self.connected = False

        os.makedirs(log_dir, exist_ok=True)
        self._log_path = os.path.join(log_dir, "features.jsonl")

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{node_id}-{int(time.time())}",
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        # 상태 토픽(LWT): 노드가 죽으면 브로커가 offline을 알림 → Pi4가 노드 생사 파악.
        self._status_topic = f"deskmate/keystroke/{node_id}/status"
        self._client.will_set(self._status_topic, "offline", qos=1, retain=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.connected = True
            client.publish(self._status_topic, "online", qos=1, retain=True)
            print(f"[mqtt] connected → {self.host}:{self.port}, topic={self.topic}")
        else:
            print(f"[mqtt] connect failed: {reason_code}")

    def _on_disconnect(self, client, userdata, *args):
        self.connected = False
        print("[mqtt] disconnected (will auto-reconnect)")

    def start(self):
        """비차단 연결. 실패해도 예외 없이 로컬 로깅으로 계속 동작."""
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            self._client.connect_async(self.host, self.port, keepalive=30)
            self._client.loop_start()
        except Exception as e:  # DNS 실패 등
            print(f"[mqtt] start error ({e}); 로컬 로깅으로 계속 진행")

    def publish(self, payload: dict):
        payload = {"ts": round(time.time(), 3), **payload}
        line = json.dumps(payload, ensure_ascii=False)

        # 항상 로컬에도 남긴다(디버깅/라벨링용 원천 로그).
        with open(self._log_path, "a", encoding="utf-8") as fp:
            fp.write(line + "\n")

        if self.connected:
            self._client.publish(self.topic, line, qos=self.qos)
            tag = "PUB"
        else:
            tag = "LOG"  # 브로커 미연결 → 로컬만
        print(f"[{tag}] {line}")

    def stop(self):
        try:
            if self.connected:
                self._client.publish(self._status_topic, "offline", qos=1, retain=True)
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass
