import paho.mqtt.client as mqtt
import json
import time

# 라즈베리 파이의 IP 주소 (게이트웨이 코드와 동일하게 설정)
MQTT_BROKER = "100.90.73.122"
MQTT_PORT = 1883
TOPIC_CONTROL = "smartgrid/control"

def test_led():
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()  # 백그라운드 네트워크 루프 시작 (publish 전송 보장)
        print(f"✅ 라즈베리 파이 MQTT 브로커({MQTT_BROKER})에 연결되었습니다.\n")

        commands = [
            # 1. 윗쪽(A) 릴레이 켜기 (B/R/G)
            {"target": "A", "cmd": "B", "desc": "A 아두이노 충전(B) 모드 - 파란불"},
            {"target": "A", "cmd": "R", "desc": "A 아두이노 방전(R) 모드 - 빨간불"},
            {"target": "A", "cmd": "G", "desc": "A 아두이노 대기(G) 모드 - 초록불"},
            {"target": "A", "cmd": "O", "desc": "A 아두이노 끄기(O)"},
            
            # 2. 아랫쪽(B) 릴레이 켜기 (B/R/G) - 게이트웨이가 제어하는 타겟
            {"target": "B", "cmd": "B", "desc": "B 아두이노 충전(B) 모드 - 파란불"},
            {"target": "B", "cmd": "R", "desc": "B 아두이노 방전(R) 모드 - 빨간불"},
            {"target": "B", "cmd": "G", "desc": "B 아두이노 대기(G) 모드 - 초록불"},
            {"target": "B", "cmd": "O", "desc": "B 아두이노 끄기(O)"},
        ]

        for c in commands:
            msg = json.dumps({"target": c["target"], "cmd": c["cmd"]})
            print(f"📡 전송: {c['desc']} -> {msg}")
            client.publish(TOPIC_CONTROL, msg)
            time.sleep(3) # 3초 대기하며 LED 상태 확인

        print("\n✅ LED 테스트가 완료되었습니다.")
        time.sleep(0.5)  # 마지막 메시지 전송 완료 대기
        client.loop_stop()
        client.disconnect()

    except Exception as e:
        print(f"❌ 연결 실패! 라즈베리 파이가 켜져있고 브로커가 동작 중인지 확인하세요: {e}")

if __name__ == "__main__":
    test_led()
