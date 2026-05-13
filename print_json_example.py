import json
import csv
import ast

def get_example_json():
    sim_daily_requests = {}
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
            break # just need one day for example
            
    # Simulate step=25 (day 1, hour 1)
    # Wait, we only loaded day 0 above, let me load all
    pass

with open("Sim_Daily_Requests.csv", "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    row = next(reader)
    row = next(reader) # Day 1 (step_idx = 1)
    
    parsed_row = {}
    for k, v in row.items():
        if k.startswith("past_") or k.startswith("forecast_"):
            parsed_row[k] = ast.literal_eval(v)
        else:
            parsed_row[k] = v
            
hour = 1
result = {}
for k, v in parsed_row.items():
    if k == "target_date":
        result[k] = v
    elif k.startswith("past_"):
        result[k] = [v[hour + 24*i] for i in range(7)]
    elif k.startswith("forecast_"):
        result[k] = [v[hour + 24*i] for i in range(2)]

example_json = {
    "stations": [
        {
            "header": {
                "station_id": 0,
                "is_physical": False,
                "timestamp": "2026-05-08T15:01:00Z",
                "day_idx": 1,
                "step": 1
            },
            "payload": {
                "charger_status": [
                    {"charger_id": 1, "has_demand": True},
                    {"charger_id": 2, "has_demand": False},
                    {"charger_id": 3, "has_demand": False},
                    {"charger_id": 4, "has_demand": False},
                    {"charger_id": 5, "has_demand": False}
                ],
                "power_metrics_w": {
                    "p_pv": 1500.0,
                    "p_load": 7000.0,
                    "p_ess": 0.0,
                    "p_grid": 5500.0,
                    "p_tr": 0.0
                },
                "state_of_charge": {
                    "mode": "idle",
                    "soc": 0.5,
                    "capacity_wh": 998.0
                }
            },
            "status": {
                "is_active": True,
                "error_code": 0
            }
        },
        "..."
    ],
    "daily_requests": result
}

print(json.dumps(example_json, indent=2, ensure_ascii=False))

