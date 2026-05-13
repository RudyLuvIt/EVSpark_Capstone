import time
import json
import csv
import ast
import paho.mqtt.client as mqtt
import numpy as np
import threading
import random
import payload_builder

# ==========================================
# 1. 설정
# ==========================================
# 클라우드(백엔드 AWS) MQTT 설정
AWS_MQTT_BROKER = "3.38.103.218"
AWS_MQTT_PORT = 1883

# MQTT 토픽 설정
TOPIC_TELEMETRY = "smartgrid/telemetry"   # 1초 주기 상태 보고 (Publish -> AWS)
TOPIC_ACTION = "simulate/action"         # 백엔드로부터 1스텝 행동 수신 (Subscribe <- AWS)

# 환경 변수 (시연용)
NUM_STATIONS = 5
E_C = np.full(NUM_STATIONS, 998.0) 
SOC_MIN, SOC_MAX = 0.1, 0.9
E_CH_MAX, E_DIS_MAX = 90.0, 90.0
P_PER_CHARGER = 7.0
REAL_TIME_PER_STEP = 10 # 시뮬레이션 1시간 = 현실 10초

# ==========================================
# 2. 전역 상태 변수 (두 스레드가 공유)
# ==========================================
current_soc = np.array([0.5] * NUM_STATIONS, dtype=np.float32)
current_step = 0                  # 현재 진행 중인 시간 (0~23)
current_day_idx = 0               # 현재 진행 중인 시뮬레이션 일차 (day0, day1...)
active_schedule = {}              # 현재 시간에 실제로 적용 중인 스케줄
pending_schedule = {}             # 백엔드에서 방금 수신하여 대기 중인 스케줄
received_stations = set()         # 개별로 수신된 스테이션 ID를 추적하는 집합
schedule_received = False         # 24시간 스케줄 수신 여부 플래그
is_running = True                 # 프로그램 종료 플래그
last_sent_mode_0 = None           # 시뮬레이션 상태 변경 로깅용

# CSV 데이터 로드
all_csv_data = {}
sim_daily_requests = {}

def load_daily_requests():
    global sim_daily_requests
    try:
        with open("Sim_Daily_Requests.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                step_idx = int(row["step_idx"])
                parsed_row = {}
                for k, v in row.items():
                    if k.startswith("past_") or k.startswith("forecast_"):
                        parsed_row[k] = ast.literal_eval(v)
                    else:
                        parsed_row[k] = v
                sim_daily_requests[step_idx] = parsed_row
        print(f"✅ Daily Requests 로드 완료: 총 {len(sim_daily_requests)}일치")
    except Exception as e:
        print(f"❌ Daily Requests 로드 실패: {e}")

def load_csv_data():
    global all_csv_data
    try:
        with open("Sim_Live_Data.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_step = int(row["step"])
                secs = int(row["secs"])
                
                # 시뮬레이션 1스텝(1시간) = 현실 10초(REAL_TIME_PER_STEP)
                # 즉 3600초 분량의 원본 데이터를 10개의 프레임(0초, 360초, 720초...)으로 샘플링
                interval = 3600 // REAL_TIME_PER_STEP
                if secs % interval != 0:
                    continue
                    
                sec_idx = secs // interval
                if sec_idx >= REAL_TIME_PER_STEP:
                    sec_idx = REAL_TIME_PER_STEP - 1
                    
                day_idx = raw_step // 24
                step = raw_step % 24
                day_key = f"day{day_idx}"
                
                if day_key not in all_csv_data:
                    all_csv_data[day_key] = {
                        "pv": np.zeros((24, REAL_TIME_PER_STEP, NUM_STATIONS)),
                        "flags": np.zeros((24, REAL_TIME_PER_STEP, NUM_STATIONS, 5), dtype=int),
                        "weather": [[{} for _ in range(REAL_TIME_PER_STEP)] for _ in range(24)]
                    }
                    
                for st in range(NUM_STATIONS):
                    all_csv_data[day_key]["pv"][step, sec_idx, st] = float(row[f"pv_{st}"])
                    for c in range(5):
                        all_csv_data[day_key]["flags"][step, sec_idx, st, c] = int(row[f"s{st}_c{c+1}"])
                        
                all_csv_data[day_key]["weather"][step][sec_idx] = {
                    "temperature_c": float(row.get("temperature_c", 0.0)),
                    "humidity_pct": float(row.get("humidity_pct", 0.0)),
                    "cloud_amount": float(row.get("cloud_amount", 0.0)),
                    "precipitation_mm": float(row.get("precipitation_mm", 0.0)),
                    "snow_cm": float(row.get("snow_cm", 0.0)),
                    "wind_speed_ms": float(row.get("wind_speed_ms", 0.0)),
                    "wind_direction_deg": float(row.get("wind_direction_deg", 0.0)),
                    "pressure_hpa": float(row.get("pressure_hpa", 0.0)),
                    "sea_level_pressure_hpa": float(row.get("sea_level_pressure_hpa", 0.0)),
                    "solar_radiation_mj_m2": float(row.get("solar_radiation_mj_m2", 0.0)),
                    "current_PTY": float(row.get("current_PTY", 0.0))
                }
        print(f"✅ CSV 데이터 로드 완료: 총 {len(all_csv_data)}일 데이터 (초단위 샘플링 적용 완료)")
    except Exception as e:
        print(f"❌ CSV 로드 실패: {e}")

load_csv_data()
load_daily_requests()

# get_requests_for_step removed as we now send the full row at step 22

# ==========================================
# 3. MQTT 콜백 (AWS)
# ==========================================
def on_connect_aws(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"✅ [AWS] 백엔드 통신용 브로커 연결 성공!")
        client.subscribe(TOPIC_ACTION)
        print(f"📡 [AWS] '{TOPIC_ACTION}' 토픽에서 1스텝 행동 명령 대기 중...")
    else:
        print(f"❌ [AWS] 연결 실패, 코드: {reason_code}")

def on_disconnect_aws(client, userdata, disconnect_flags, reason_code, properties):
    print(f"\n🚨 [긴급/AWS] 백엔드 연결이 끊어졌습니다! (코드: {reason_code})")

def on_message_aws(client, userdata, msg):
    """백엔드에서 24시간 스케줄이 도착하면 실행됨"""
    global pending_schedule, schedule_received, received_stations
    if msg.topic == TOPIC_ACTION:
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            
            # 1. 이전 방식: 한 번에 모든 스테이션 배열이 들어오는 경우 (optimized_schedule.json 포맷)
            if "station_day_ahead_schedule" in payload:
                stations_schedule = payload.get("station_day_ahead_schedule", [])
                if stations_schedule:
                    temp_schedule = {step: {} for step in range(24)}
                    for station_data in stations_schedule:
                        st_id = station_data.get("station_id")
                        hourly_plan = station_data.get("hourly_plan", [])
                        for plan in hourly_plan:
                            hour = plan.get("hour")
                            if hour is not None and 0 <= hour < 24:
                                power_w = float(plan.get("ess_power_kw", 0.0)) * 1000.0
                                grid_usage_w = float(plan.get("grid_usage_kw", 0.0)) * 1000.0
                                mode = plan.get("ess_mode", "idle")
                                transfer_power_kw = sum(t.get("transfer_power_kw", 0.0) for t in plan.get("transfer", []))
                                temp_schedule[hour][st_id] = {
                                    "mode": mode,
                                    "power_w": power_w,
                                    "grid_usage_w": grid_usage_w,
                                    "transfer_power_w": transfer_power_kw * 1000.0
                                }
                    pending_schedule = temp_schedule
                    schedule_received = True
                    print(f"🎉 [AWS 수신] 백엔드로부터 총 24시간 분량의 전체 일일 스케줄을 한 번에 받았습니다!")
                    return

            # 2. 새로운 방식: 각 스테이션별로 개별 메시지가 들어오는 경우
            elif payload.get("type") == "day_ahead_schedule" or "hourly_plan" in payload:
                # 첫 수신이거나 이전에 이미 다 받아서 처리가 끝났다면 초기화
                if not pending_schedule or schedule_received:
                    pending_schedule = {step: {} for step in range(24)}
                    received_stations.clear()
                    schedule_received = False
                
                st_id = payload.get("station_id")
                hourly_plan = payload.get("hourly_plan", [])
                
                for plan in hourly_plan:
                    hour = plan.get("hour")
                    if hour is not None and 0 <= hour < 24:
                        power_w = float(plan.get("ess_power_kw", 0.0)) * 1000.0
                        grid_usage_w = float(plan.get("grid_usage_kw", 0.0)) * 1000.0
                        mode = plan.get("ess_mode", "idle")
                        transfer_power_kw = sum(t.get("transfer_power_kw", 0.0) for t in plan.get("transfer", []))
                        
                        pending_schedule[hour][st_id] = {
                            "mode": mode,
                            "power_w": power_w,
                            "grid_usage_w": grid_usage_w,
                            "transfer_power_w": transfer_power_kw * 1000.0
                        }
                        
                if st_id is not None:
                    received_stations.add(st_id)
                    print(f"📥 [AWS 수신] 스테이션 {st_id}의 스케줄을 받았습니다. (현재 {len(received_stations)}/{NUM_STATIONS}개 수신 완료)")
                
                if len(received_stations) >= NUM_STATIONS:
                    schedule_received = True
                    print(f"🎉 [AWS 수신] 모든 스테이션({NUM_STATIONS}개)의 일일 스케줄 수신 완료! (대기열에 추가됨)")
            else:
                print(f"⚠️ [경고] 알 수 없는 Action 페이로드 포맷입니다. 수신된 키: {list(payload.keys())}")
                
        except Exception as e:
            print(f"❌ [AWS] Action 파싱 에러: {e}")

# ==========================================
# 4. [Thread 1] 1초 주기 모니터링 루프 (AWS 전송)
# ==========================================
def telemetry_loop(aws_client):
    global current_soc, current_step, active_schedule, is_running, current_day_idx, last_sent_mode_0
    
    last_step = -1
    sec_idx = 0
    
    while is_running:
        # 스텝이 넘어가면 초(sec_idx) 카운터 초기화
        if current_step != last_step:
            sec_idx = 0
            last_step = current_step
            
        day_key = f"day{current_day_idx}"
        if day_key in all_csv_data:
            current_pv = all_csv_data[day_key]["pv"][current_step][sec_idx]
            current_flags = all_csv_data[day_key]["flags"][current_step][sec_idx]
            current_weather = all_csv_data[day_key]["weather"][current_step][sec_idx]
        else:
            current_pv = np.zeros(NUM_STATIONS)
            current_flags = np.zeros((NUM_STATIONS, 5), dtype=int)
            current_weather = {}
            
        # 현재 활성화된 스케줄에서 이번 스텝의 행동 리스트 추출 (없으면 대기 상태로 빈 딕셔너리 반환)
        actions_for_step = active_schedule.get(current_step, {})

        # 1. 만약 이번 스텝의 행동이 있다면 SoC 서서히 업데이트
        if actions_for_step:
            for st_id, act in actions_for_step.items():
                if 0 <= st_id < NUM_STATIONS:
                    p_w = act.get("power_w", 0.0)
                    mode = act.get("mode", "idle")
                    
                    # 🛡️ Rule-based 안전 제어 (SoC Limit Override)
                    if "charge" in mode and current_soc[st_id] >= SOC_MAX:
                        mode = "idle"
                        p_w = 0.0
                    elif "discharge" in mode and current_soc[st_id] <= SOC_MIN:
                        mode = "idle"
                        p_w = 0.0
                    
                    # 하드웨어 최대 충방전 전력으로 클램프 (AI가 큰 kW 값을 내려보내도 실제 배터리 한계 이내로 제한)
                    if "charge" in mode:
                        p_w = min(p_w, E_CH_MAX)
                    elif "discharge" in mode:
                        p_w = min(p_w, E_DIS_MAX)
                    
                    # charge면 더하고 discharge면 빼서 반영
                    change = p_w if "charge" in mode else -p_w if "discharge" in mode else 0.0
                    
                    # 10초(1시간)에 걸쳐 나누어서 SoC 업데이트: ΔSoC = P[W] × 1[h] / E_C[Wh] / steps
                    current_soc[st_id] = np.clip(current_soc[st_id] + (change / E_C[st_id] / REAL_TIME_PER_STEP), SOC_MIN, SOC_MAX)

        # 2. 5개 스테이션의 상태 데이터를 하나의 리스트로 조립
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        stations_data = []

        for i in range(NUM_STATIONS):
            p_pv_i = max(0, current_pv[i] + random.uniform(-0.5, 0.5))
            p_load_i = max(0, np.sum(current_flags[i]) * P_PER_CHARGER + random.uniform(-0.3, 0.3))

            p_ess_i = 0.0
            p_grid_i = 0.0
            p_tr_i = 0.0
            ess_mode = "idle"

            # 행동을 시행 중일 때만 Power metrics에 단순히 숫자 표기만 실시
            st_act = actions_for_step.get(i)
            
            if st_act:
                ess_mode = st_act.get("mode", "idle")
                raw_ess_w = st_act.get("power_w", 0.0)
                
                # 🛡️ Rule-based 안전 제어 (SoC Limit Override)
                if "charge" in ess_mode and current_soc[i] >= SOC_MAX:
                    ess_mode = "idle"
                    raw_ess_w = 0.0
                elif "discharge" in ess_mode and current_soc[i] <= SOC_MIN:
                    ess_mode = "idle"
                    raw_ess_w = 0.0
                
                # 텔레메트리 표기용도 동일하게 클램프 적용
                if "charge" in ess_mode:
                    raw_ess_w = min(raw_ess_w, E_CH_MAX)
                elif "discharge" in ess_mode:
                    raw_ess_w = min(raw_ess_w, E_DIS_MAX)
                
                # 방전일 때 양수(+), 충전일 때 음수(-) 표기
                p_ess_i = raw_ess_w if "discharge" in ess_mode else -raw_ess_w if "charge" in ess_mode else 0.0
                
                p_grid_i = st_act.get("grid_usage_w", 0.0)
                p_tr_i = st_act.get("transfer_power_w", 0.0)

                # 0번 스테이션 시뮬레이션 로깅 (모드가 바뀔 때만)
                if i == 0:
                    if ess_mode != last_sent_mode_0:
                        if last_sent_mode_0 is not None:
                            print(f"🚨 [안전 제어] 소프트웨어 상태 변경: {last_sent_mode_0} -> {ess_mode} (보호 로직 적용)")
                        last_sent_mode_0 = ess_mode

            charger_status_list = [
                {"charger_id": int(idx + 1), "has_demand": bool(current_flags[i][idx])}
                for idx in range(5)
            ]

            station_info = {
                "header": {
                    "station_id": i,
                    "is_physical": False, # 모든 스테이션을 소프트웨어 시뮬레이션으로 설정
                    "timestamp": timestamp,
                    "day_idx": current_day_idx,
                    "step": current_step
                },
                "payload": {
                    "charger_status": charger_status_list,
                    "power_metrics_w": {
                        "p_pv": round(float(p_pv_i), 2),
                        "p_load": round(float(p_load_i), 2),
                        "p_ess": round(float(p_ess_i), 2),
                        "p_grid": round(float(p_grid_i), 2),
                        "p_tr": round(float(p_tr_i), 2)
                    },
                    "state_of_charge": {
                        "mode": ess_mode,
                        "soc": round(float(current_soc[i]), 4),
                        "capacity_wh": float(E_C[i])
                    }
                },
                "status": {"is_active": True, "error_code": 0}
            }
            stations_data.append(station_info)

        # 3. AWS로 1초마다 데이터 Publish
        telemetry_payload = {
            "stations": stations_data,
            "weather": current_weather
        }
        
        if current_step == 22 and sec_idx == 0 and current_day_idx in sim_daily_requests:
            try:
                ai_request_payload = payload_builder.build_ai_server_request(
                    current_day_idx, 
                    current_step, 
                    sim_daily_requests, 
                    stations_data
                )
                aws_client.publish(TOPIC_TELEMETRY, json.dumps(ai_request_payload))
                print(f"📡 [AI 서버 요청] 22시 정각, 전체 스케줄 요청 페이로드를 전송했습니다.")
            except Exception as e:
                print(f"❌ [AI 서버 요청 실패] 페이로드 생성 오류: {e}")
                aws_client.publish(TOPIC_TELEMETRY, json.dumps(telemetry_payload))
        else:
            aws_client.publish(TOPIC_TELEMETRY, json.dumps(telemetry_payload))
            
        print(f"[{time.strftime('%H:%M:%S')}] 📡 데이터 전송 (시뮬레이션 시간: day{current_day_idx} {current_step}시 {sec_idx * 6}분)")
        
        # 1초 경과 처리
        sec_idx = min(sec_idx + 1, REAL_TIME_PER_STEP - 1)
        time.sleep(1)

# ==========================================
# 5. [Thread 2] 메인 시뮬레이션 지휘 루프 (Step-by-Step)
# ==========================================
def main_step_loop():
    global current_step, pending_schedule, active_schedule, schedule_received, is_running, current_day_idx
    
    while is_running:
        day_key = f"day{current_day_idx}"
        if day_key not in all_csv_data:
            print("🔄 모든 시뮬레이션 일자 데이터를 소진했습니다. 다시 day0으로 돌아갑니다.")
            current_day_idx = 0
            current_step = 0
            continue
            
        print(f"\n=== [시뮬레이션 day{current_day_idx}] 24시간 스케줄(Action) 대기 중 ===")
        
        # 백엔드로부터 이번 날의 24시간 스케줄이 도착할 때까지 무한 대기
        # (임시: AI 서버 응답 대기 및 경고 문구 출력 제외)
        # while not schedule_received and is_running:
        #     if not failsafe_triggered and (time.time() - wait_start) > 180:
        #         print("\n🚨 [타임아웃 경고] 3분 이상 AI 서버 응답이 없습니다! 시스템 로직을 다시 한 번 확인해주세요.")
        #         failsafe_triggered = True
        #     time.sleep(0.1)
            
        if not is_running:
            break
            
        # 2. 스케줄 수신 완료! 
        # 만약 현재 스텝이 0보다 크면(중간부터 시작했다면), 남은 시간을 Idle로 흘려보냄
        if current_step > 0:
            print(f"\n⏳ 현재 {current_step}시입니다. 다음 날 0시가 될 때까지 아무 작업도 하지 않고(Idle) 대기합니다.")
            active_schedule = {} # 빈 스케줄로 텔레메트리 전송
            start_step = current_step if current_step < 24 else 0
            
            for step in range(start_step, 24):
                if not is_running: break
                current_step = step
                print(f"\n--- [day{current_day_idx} - {current_step}시 (대기)] ---")
                print("🖥️ [대기 모드] 스케줄 실행 전 남은 시간 동안 유휴(Idle) 상태를 유지합니다.")
                time.sleep(REAL_TIME_PER_STEP)
                
            if is_running:
                print(f"\n🏁 day{current_day_idx}의 대기 하루가 완료되었습니다.")
                current_step = 0
                current_day_idx += 1
                
                day_key = f"day{current_day_idx}"
                if day_key not in all_csv_data:
                    print("🔄 모든 시뮬레이션 일자 데이터를 소진했습니다. 다시 day0으로 돌아갑니다.")
                    current_day_idx = 0
                    current_step = 0
                    continue # 다시 루프 처음으로 돌아가서 새로운 스케줄을 기다림
                    
        # 3. 이제 확실하게 current_step == 0 인 상태. (또는 Idle 대기를 마친 상태)
        # 받은 스케줄(pending_schedule)을 실제 적용할 스케줄(active_schedule)로 복사!
        active_schedule = pending_schedule
        
        # 미리 다음 날 스케줄을 받을 수 있도록 대기열과 플래그 초기화
        schedule_received = False
        pending_schedule = {}
        
        print(f"\n🚀 day{current_day_idx} 스케줄 수신 완료 및 실행! 0시부터 23시까지 스케줄에 따라 움직입니다.")
        
        for step in range(0, 24):
            if not is_running: break
            
            current_step = step
            actions_for_step = active_schedule.get(current_step, {})
            
            print(f"\n--- [day{current_day_idx} - {current_step}시] ---")
            try:
                if actions_for_step:
                    for st_id, act in actions_for_step.items():
                        mode_i = act.get("mode", "idle")
                        print(f"🖥️ [스케줄러] 스테이션 {st_id} 지시 Mode: {mode_i}")
                else:
                    print(f"⚠️ 이번 스텝에 대한 행동 데이터가 없습니다.")
            except Exception as e:
                print(f"⚠️ 행동 파싱 에러: {e}")
                
            # 1스텝(1시간) 실행 (시연용 10초 대기)
            # 이 시간동안 telemetry_loop가 10초에 걸쳐 SoC를 부드럽게 업데이트
            time.sleep(REAL_TIME_PER_STEP)
            
        # 4. 다음 날로 이동
        if is_running:
            print(f"\n🏁 day{current_day_idx}의 시뮬레이션 하루가 완료되었습니다.")
            current_step = 0
            current_day_idx += 1

# ==========================================
# 6. 프로그램 시작점
# ==========================================
if __name__ == "__main__":
    try:
        input_total_step = input("시작할 스텝(step)을 입력하세요 (예: 0, 24, 100... / 엔터 시 기본값 0): ").strip()
        total_step = int(input_total_step) if input_total_step else 0
        
        current_day_idx = total_step // 24
        current_step = total_step % 24
    except ValueError:
        print("잘못된 숫자가 입력되었습니다. 기본값(step 0)으로 시작합니다.")
        current_day_idx = 0
        current_step = 0

    print(f"👉 설정 완료: 총 {total_step} 스텝부터 시작 (day{current_day_idx} - {current_step}시)\n")

    # AWS MQTT 클라이언트 설정
    try:
        aws_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        aws_client = mqtt.Client()
    aws_client.on_connect = on_connect_aws
    aws_client.on_disconnect = on_disconnect_aws
    aws_client.on_message = on_message_aws
    
    try:
        # 브로커 연결 및 루프 시작
        aws_client.connect(AWS_MQTT_BROKER, AWS_MQTT_PORT, 60)
        aws_client.loop_start() 
        
        # 1초 상태 보고(Telemetry) 스레드 시작 (AWS로 전송)
        t_telemetry = threading.Thread(target=telemetry_loop, args=(aws_client,), daemon=True)
        t_telemetry.start()
        
        # 메인 시뮬레이션 지휘 루프 시작
        main_step_loop()
        
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
        is_running = False
        aws_client.loop_stop()
        aws_client.disconnect()
