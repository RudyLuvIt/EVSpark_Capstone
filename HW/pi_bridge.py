import serial
import time
import threading
import json
import paho.mqtt.client as mqtt

# ==========================================
# 1. 설정 (자신의 환경에 맞게 수정하세요)
# ==========================================
PORT_A = '/dev/ttyUSB0'  # 위쪽 아두이노 (부하 3, 4, 5)
PORT_B = '/dev/ttyUSB1'  # 아래쪽 아두이노 (부하 1, 2)
BAUD_RATE = 9600

MQTT_BROKER = "100.90.73.122"  # ⚠️ 실제 MQTT 서버(또는 AI 서버)의 IP 주소로 변경!
MQTT_PORT = 1883
TOPIC_CONTROL = "smartgrid/control" # 명령을 받을 토픽
TOPIC_SENSOR = "smartgrid/sensor"   # 센서값을 보낼 토픽

# ==========================================
# 2. 하드웨어 연결
# ==========================================
ser_A, ser_B = None, None
try: ser_A = serial.Serial(PORT_A, BAUD_RATE, timeout=0.1)
except: print(f"⚠️ A 포트({PORT_A}) 연결 실패")

try: ser_B = serial.Serial(PORT_B, BAUD_RATE, timeout=0.1)
except: print(f"⚠️ B 포트({PORT_B}) 연결 실패")
time.sleep(2)

# ==========================================
# 3. MQTT 통신 설정 및 제어 로직
# ==========================================
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"✅ MQTT 서버 연결 성공! (코드: {rc})")
    client.subscribe(TOPIC_CONTROL) # 제어 명령 토픽 구독 시작
    print(f"📡 '{TOPIC_CONTROL}' 토픽에서 AI의 스케줄링 명령을 기다립니다...")

def on_message(client, userdata, msg):
    """
    AI 모델이 보낸 스케줄링 결과를 받아 아두이노로 전달하는 핵심 함수!
    (예상되는 수신 데이터 형식 JSON: {"target": "A", "cmd": "B"})
    """
    payload = msg.payload.decode('utf-8')
    try:
        data = json.loads(payload)
        target = data.get("target")
        cmd = data.get("cmd")

        if cmd in ['B', 'R', 'G', 'O']:
            if target == 'A' and ser_A:
                ser_A.write(cmd.encode('utf-8'))
                print(f"⚡ [명령 수신] 위쪽(A) 아두이노 릴레이 작동 -> '{cmd}'")
            elif target == 'B' and ser_B:
                ser_B.write(cmd.encode('utf-8'))
                print(f"⚡ [명령 수신] 아래쪽(B) 아두이노 릴레이 작동 -> '{cmd}'")
        else:
            print("❌ 알 수 없는 명령입니다 (B, R, O만 가능).")
    except json.JSONDecodeError:
        print(f"❌ JSON 형식이 아닙니다: {payload}")

# MQTT 클라이언트 생성 및 콜백 함수 연결
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
except AttributeError:
    client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# ==========================================
# 4. 센서 데이터 수집 및 전송 (백그라운드)
# ==========================================
def read_and_publish_sensor_data():
    """아두이노의 계측값을 읽어서 실시간으로 MQTT 서버로 전송합니다."""
    while True:
        try:
            if ser_A and ser_A.in_waiting > 0:
                data_A = ser_A.readline().decode('utf-8').rstrip()
                if data_A.startswith("A:"):
                    # 예: A:0.00,0.00,0.00 -> MQTT 서버로 쏨
                    client.publish(TOPIC_SENSOR, json.dumps({"group": "A", "values": data_A}))
                    
            if ser_B and ser_B.in_waiting > 0:
                data_B = ser_B.readline().decode('utf-8').rstrip()
                if data_B.startswith("B:"):
                    client.publish(TOPIC_SENSOR, json.dumps({"group": "B", "values": data_B}))
        except Exception:
            pass
        time.sleep(0.1)

# 백그라운드 스레드 시작
threading.Thread(target=read_and_publish_sensor_data, daemon=True).start()

# ==========================================
# 5. 메인 실행 루프
# ==========================================
print("--- 스마트 마이크로그리드 시스템 가동 ---")
try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    # client.loop_forever()를 쓰면 이 줄에서 무한 대기하며 MQTT를 처리합니다.
    client.loop_forever() 
except KeyboardInterrupt:
    print("\n시스템을 종료합니다.")
except Exception as e:
    print(f"서버 연결 에러: {e}")
finally:
    if ser_A: ser_A.close()
    if ser_B: ser_B.close()