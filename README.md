# DESKMATE — 키스트로크 노드 (PC 수집 프로그램)

제24회 임베디드SW경진대회 · 팀 TEAMMATE · 작품 DESKMATE
개발계획서의 **"사용자 작업 PC — 키스트로크 수집"** 노드를 구현한다.

노트북(Galaxy Book3 Pro 360, Windows)에서 키 입력 **타이밍만** 수집하고,
특징 벡터를 계산해 **MQTT로 발행**한다. 나중에 Raspberry Pi 4(중앙 허브)가 구독한다.

## 설계 원칙 (계획서 반영)
- **프라이버시**: 실제 글자는 저장/전송하지 않는다. 키 "종류"(문자/스페이스/백스페이스/엔터/기타)와
  타임스탬프만 다룬다 → 내용 복원 불가.
- **두 층위 신호**: 항상 가용한 바닥 신호(ToF·환경) 위에 얹는, 타이핑 중에만 존재하는 정밀 신호.
- **오프라인 동작**: 인터넷 불필요. 로컬 MQTT(Pi4의 Mosquitto)만 있으면 된다.
- **단독 실행 가능**: 브로커가 없으면 콘솔+파일 로깅으로 폴백 → 노트북만으로 개발/검증.

## 산출 특징 (계획서 4대 특징 + α)
| 필드 | 의미 |
|---|---|
| `dwell_ms` {mean,std} | 키 누름 유지 시간 |
| `flight_ms` {mean,std} | 연속 키 간격 (멈춤 제외) |
| `flight_cv` | 리듬 불규칙성 = std/mean (피로 지표) |
| `backspace_ratio` | 정정(백스페이스) 빈도 |
| `idle_ratio` | 입력 없는 시간 비율 (공백 비율) |
| `kpm`, `keydown_count`, `pause_count`, `typing_active` | 활동량/멈춤 |

## 구조
```
src/
  config.py     환경변수 기반 설정(브로커/토픽/윈도)
  capture.py    pynput 리스너 → KeyEvent(시간·종류·press/release)
  features.py   슬라이딩 윈도 → 특징 벡터
  publisher.py  paho-mqtt 발행(+미연결 시 로컬 로깅 폴백, LWT 상태 토픽)
  main.py       캡처→추출→발행 루프
tests/
  test_features.py   합성 이벤트로 로직 검증(키 캡처 불필요)
```

## 실행
```bash
# 1) 가상환경 + 의존성
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2) 테스트(키 입력 없이 로직 검증)
pytest tests -v

# 3) 노트북 단독 실행 (브로커 없어도 로컬 로깅으로 동작)
python src/main.py

# 4) Pi4 연동 (브로커 주소만 지정)
set DESKMATE_BROKER=192.168.0.42      # PowerShell: $env:DESKMATE_BROKER="192.168.0.42"
python src/main.py
```

## MQTT 인터페이스 (Pi4 팀과 계약)
- **특징 토픽**: `deskmate/keystroke/features` (QoS 0, JSON)
- **상태 토픽**: `deskmate/keystroke/<node_id>/status` = `online`/`offline` (retain, LWT)
- payload 예시:
```json
{
  "ts": 1690000000.123, "node_id": "pc-keystroke", "window_sec": 60.0,
  "typing_active": true, "keydown_count": 210, "kpm": 210.0,
  "dwell_ms": {"mean": 92.1, "std": 20.4},
  "flight_ms": {"mean": 178.3, "std": 55.1}, "flight_cv": 0.309,
  "backspace_ratio": 0.08, "idle_ratio": 0.12, "pause_count": 2
}
```

## 주의
- 전역 키 후킹은 백신/SmartScreen이 키로거로 의심할 수 있다 → 데모 PC에서 예외 처리.
- Windows에서는 `pynput`이 관리자 권한 없이 리스닝 가능.
