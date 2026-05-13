import csv
import ast

def load_daily_requests():
    daily_reqs = {}
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
                daily_reqs[step_idx] = parsed_row
        print(f"Loaded {len(daily_reqs)} daily requests.")
        return daily_reqs
    except Exception as e:
        print(f"Failed to load daily requests: {e}")
        return {}

def get_requests_for_step(daily_reqs, day_idx, hour):
    if day_idx not in daily_reqs:
        return {}
    row = daily_reqs[day_idx]
    result = {}
    for k, v in row.items():
        if k == "target_date":
            result[k] = v
        elif k.startswith("past_"):
            result[k] = [v[hour + 24*i] for i in range(7)]
        elif k.startswith("forecast_"):
            result[k] = [v[hour + 24*i] for i in range(2)]
    return result

d = load_daily_requests()
res = get_requests_for_step(d, 0, 1)
print(res)
