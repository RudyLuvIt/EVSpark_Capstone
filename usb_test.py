import paho.mqtt.client as mqtt
import json
import time

MQTT_BROKER = "100.90.73.122"
MQTT_PORT = 1883
TOPIC_SENSOR = "smartgrid/sensor"
TOPIC_CONTROL = "smartgrid/control"  # 릴레이 제어용 토픽 추가

previous_states = [False] * 5
current_values = [0.0] * 5

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"라즈베리 파이 MQTT 브로커({MQTT_BROKER})에 연결 성공!")
        client.subscribe(TOPIC_SENSOR)
        
        print("센서 인식을 위해 모든 릴레이 전원을 켭니다 (충전 모드)...")
        client.publish(TOPIC_CONTROL, json.dumps({"target": "A", "cmd": "B"}))
        client.publish(TOPIC_CONTROL, json.dumps({"target": "B", "cmd": "B"}))
        
        print("센서 데이터(USB 전류)를 기다리고 있습니다.")
        print("이제 핸드폰이나 기기를 USB에 연결해 보세요!\n")
        print("-" * 50)
    else:
        print(f"연결 실패! 코드: {rc}")

def on_message(client, userdata, msg):
    global current_values, previous_states
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        group = payload.get("group")
        values_str = payload.get("values", "")
        
        updated = False
        if group == "A" and values_str.startswith("A:"):
            parts = values_str[2:].split(",")
            if len(parts) == 3:
                current_values[2] = float(parts[0])
                current_values[3] = float(parts[1])
                current_values[4] = float(parts[2])
                updated = True
        elif group == "B" and values_str.startswith("B:"):
            parts = values_str[2:].split(",")
            if len(parts) == 2:
                current_values[0] = float(parts[0])
                current_values[1] = float(parts[1])
                updated = True
        
        if updated:
            check_and_print_changes()
            
    except Exception as e:
        pass

def check_and_print_changes():
    global previous_states, current_values
    
    status_str = " | ".join([f"CH{i+1}: {current_values[i]:.1f}mA" for i in range(5)])
    print(f"\r실시간 전류: {status_str}", end="", flush=True)
    
    for i in range(5):
        is_connected = current_values[i] > 10.0
        
        if is_connected != previous_states[i]:
            print() 
            if is_connected:
                print(f"충전기 {i+1}번 기기 연결됨! 전류가 흐릅니다. (전류: {current_values[i]:.2f} mA)")
            else:
                print(f"충전기 {i+1}번 기기 분리됨. (전류: {current_values[i]:.2f} mA)")
            previous_states[i] = is_connected

if __name__ == "__main__":
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()
        
    client.on_connect = on_connect
    client.on_message = on_message
    
    print("브로커에 연결 중...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n테스트를 종료합니다. 안전을 위해 모든 릴레이를 끕니다(O 모드)...")
        # 종료 시 릴레이 원상 복구 (끄기)
        client.publish(TOPIC_CONTROL, json.dumps({"target": "A", "cmd": "O"}))
        client.publish(TOPIC_CONTROL, json.dumps({"target": "B", "cmd": "O"}))
        # 메시지가 전송될 수 있도록 잠시 대기
        time.sleep(0.5)
        client.disconnect()
        print("릴레이 전원 차단 완료. 프로그램이 완전히 종료되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")
