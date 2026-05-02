import paho.mqtt.client as mqtt
import json
import time

MQTT_BROKER = "192.168.219.114"
MQTT_PORT = 1883

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("\n✅ 로컬 MQTT 브로커 연결 성공!")
        client.subscribe("smartgrid/sensor")
        print("📡 센서 데이터 대기 중... 지금 USB를 꽂거나 빼보세요!\n")
    else:
        print(f"❌ 연결 실패 (코드: {rc})")

def on_message(client, userdata, msg):
    # 센서 토픽에서 메시지가 오면 실시간으로 출력합니다.
    if msg.topic == "smartgrid/sensor":
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            group = payload.get("group")
            values = payload.get("values")
            
            # 터미널 한 줄에 계속 덮어쓰면서 깔끔하게 보여줍니다.
            print(f"\r🔌 [실시간 센서] 보드 {group} 측정값: {values}               ", end="", flush=True)
        except Exception as e:
            pass

def main():
    print("="*55)
    print(" 🛠️ 하드웨어 단독 시뮬레이션 및 테스트 프로그램 🛠️")
    print("="*55)
    print("1. [입력 테스트] 보드의 USB 포트에 장치를 꽂거나 빼면")
    print("   화면에 전류값(mA)이 실시간으로 뜹니다.")
    print("2. [출력 테스트] LED/릴레이 테스트를 위해 아래 명령어를 입력하세요.")
    print("   👉 A B : 위쪽 보드(A) 파란색(충전) 켜기")
    print("   👉 A R : 위쪽 보드(A) 빨간색(방전) 켜기")
    print("   👉 A O : 위쪽 보드(A) LED 끄기")
    print("   👉 B B / B R / B O : 아래쪽 보드(B) 제어")
    print("   👉 Q   : 프로그램 종료")
    print("="*55)

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # 백그라운드에서 센서값 수신 시작
    except Exception as e:
        print(f"\n❌ MQTT 서버({MQTT_BROKER})에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요.")
        return

    # 사용자 입력 루프 (LED 제어용)
    while True:
        try:
            # 엔터를 치면 입력을 받습니다.
            user_input = input("\n명령어 입력 (예: A B) > ").strip().upper()
            if user_input == 'Q':
                break
            
            parts = user_input.split()
            if len(parts) == 2:
                target = parts[0]
                cmd = parts[1]
                
                if target in ['A', 'B'] and cmd in ['B', 'R', 'O']:
                    payload = {"target": target, "cmd": cmd}
                    client.publish("smartgrid/control", json.dumps(payload))
                    print(f"📤 [명령 전송 완료] {target} 보드에 '{cmd}' 명령을 내렸습니다!")
                else:
                    print("⚠️ 잘못된 명령어입니다. (Target: A/B, Cmd: B/R/O)")
            else:
                if user_input:
                    print("⚠️ 'A B' 처럼 사이에 띄어쓰기를 넣어주세요.")
                    
        except KeyboardInterrupt:
            break

    print("\n테스트를 종료합니다.")
    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()
