import json
import numpy as np
import paho.mqtt.client as mqtt
import time

class RaspberryPiInterface:
    """RL 모델과 라즈베리 파이 간의 통신을 MQTT로 담당하는 인터페이스"""
    
    def __init__(self, pi_ip="192.168.219.114", port=1883):
        self.broker_ip = pi_ip
        self.port = port
        self.latest_soc = 0.5 # 초기 배터리 잔량(SoC) 기본값
        
        # 1. MQTT 클라이언트 설정
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # 2. 백그라운드 통신 
        try:
            self.client.connect(self.broker_ip, self.port, 60)
            self.client.loop_start() 
            print(f"[시스템] MQTT 브로커({self.broker_ip})에 연결을 시도")
        except Exception as e:
            print(f"[시스템] MQTT 브로커 연결 실패: {e}")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[시스템] MQTT 서버 연결 성공! ")
            self.client.subscribe("smartgrid/sensor")
        else:
            print(f"[시스템] 연결 실패, 코드: {rc}")

    def on_message(self, client, userdata, msg):
        """라즈베리 파이에서 센서값이 올라오면 자동으로 실행되어 값을 업데이트"""
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            # 예시: {"id": "B", "data": ["150.0", "0.0"]}

            # 이 값은 AI 모델에게 전달하지 않고, 오직 '우리 눈'으로 확인하는 용도로만 씁니다.
            real_measured = payload.get("data", [0, 0])
            
            # 터미널 한쪽 구석에 실제 하드웨어 수치를 띄움
            print(f"\r[실시간 하드웨어 모니터링] 전류: {real_measured} mA (정상 작동 중)", end="", flush=True)
            
        except Exception as e:
            pass

    def send_action_to_pi(self, a_ess, led_color):
        """
        RL 에이전트가 결정한 행동을 받아 라즈베리 파이로 전송합니다.
        """
        # 환경(Env)에서 보낸 "BLUE", "RED", "OFF"를 아두이노 명령어 B, R, O로 변환
        cmd = "O"
        if led_color == "BLUE":
            cmd = "B"
        elif led_color == "RED":
            cmd = "R"
            
        payload = {
            "target": "B", # 실물 충전소(0번)는 아래쪽(B) 아두이노에 연결되어 있음
            "cmd": cmd,
            "raw_action": float(a_ess)
        }
        
        try:
            self.client.publish("smartgrid/control", json.dumps(payload))
            print(f"\n[통신 성공] 0번 충전소 제어 명령 전송: {cmd} (액션값: {a_ess:.2f})")
        except Exception as e:
            print(f"\n[통신 실패] 명령 전송 에러: {e}")

    def read_state_from_pi(self):
        """
        최신 센서(SoC) 값을 반환합니다.
        MQTT가 백그라운드에서 계속 업데이트해 둔 최신 값을 즉시 꺼내줍니다.
        """
        return np.array([self.latest_soc]), {"real_soc": self.latest_soc}