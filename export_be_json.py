import csv
import json
from datetime import datetime

CSV_FILE = "Capstone_Data.csv"
OUTPUT_FILE = "Capstone_Data_BE.json"

NUM_STATIONS = 5
P_PER_CHARGER = 7.0
E_C = [998.0] * NUM_STATIONS
SOC_DEFAULT = 0.5

def generate_be_json():
    be_data = {}
    
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                day_idx = i // 24
                step = i % 24
                day_key = f"day{day_idx}"
                
                if day_key not in be_data:
                    be_data[day_key] = {}
                
                step_key = str(step)
                be_data[day_key][step_key] = []
                
                for st in range(NUM_STATIONS):
                    # 태양광 및 충전기 수요 플래그 읽기
                    p_pv = float(row[f"pv_{st}"])
                    
                    charger_status = []
                    has_demand_count = 0
                    for c in range(5):
                        demand = int(row[f"s{st}_c{c+1}"])
                        charger_status.append({
                            "charger_id": c + 1,
                            "has_demand": bool(demand)
                        })
                        if demand:
                            has_demand_count += 1
                            
                    p_load = has_demand_count * P_PER_CHARGER
                    
                    # BE 단으로 보낼 JSON 데이터 포맷 구성
                    payload = {
                        "header": {
                            "station_id": st,
                            "is_physical": (st == 0),
                            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                        },
                        "payload": {
                            "charger_status": charger_status,
                            "power_metrics_w": {
                                "p_pv": round(p_pv, 2),
                                "p_load": round(p_load, 2),
                                "p_ess": 0.0,
                                "p_grid": 0.0,
                                "p_tr": 0.0
                            },
                            "state_of_charge": {
                                "soc": SOC_DEFAULT,
                                "capacity_wh": E_C[st]
                            }
                            # tou_price 도 참고용으로 추가 가능
                        },
                        "status": {
                            "is_active": True,
                            "error_code": 0
                        },
                        "meta": {
                            "tou_price": float(row["tou_price"])
                        }
                    }
                    be_data[day_key][step_key].append(payload)
                    
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(be_data, f, indent=2)
            
        print(f"✅ 성공적으로 데이터를 파싱하여 '{OUTPUT_FILE}' 에 저장했습니다.")
        print(f"📊 총 추출된 날짜 수: {len(be_data)}일 (day0 ~ day{len(be_data)-1})")
        
    except FileNotFoundError:
        print(f"❌ {CSV_FILE} 파일을 찾을 수 없습니다.")
    except Exception as e:
        print(f"❌ 데이터 파싱 중 오류 발생: {e}")

if __name__ == "__main__":
    generate_be_json()
