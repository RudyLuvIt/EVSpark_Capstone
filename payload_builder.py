import json
import copy
from datetime import datetime, timedelta

def build_ai_server_request(day_idx, current_step, sim_daily_requests, stations_data, template_path="backend_full_schedule_request_20260502_FIXED.json"):
    with open(template_path, "r", encoding="utf-8") as f:
        req = json.load(f)
        
    row = sim_daily_requests.get(day_idx, {})
    
    # 시연을 위해 현재 실제 날짜를 기준으로 target_date 설정
    # day_idx = 0일 때, target_date는 '내일'이 되며 request_timestamp는 '오늘 22시'가 됩니다.
    now = datetime.now()
    base_target = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    target_date = base_target + timedelta(days=day_idx)
        
    req["request_id"] = f"gateway-request-day{day_idx}-step{current_step}"
    
    current_time = target_date - timedelta(days=1) + timedelta(hours=22)
    req["request_timestamp"] = current_time.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    req["schedule_target_date"] = target_date.strftime("%Y-%m-%d")
    req["target_window"]["start"] = target_date.strftime("%Y-%m-%dT00:00:00+09:00")
    req["target_window"]["end"] = (target_date + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00+09:00")
    
    station_names = {0: "LH강남힐스테이트", 1: "LH서울지사", 2: "강남구청 공영주차장", 3: "강남한양수자인", 4: "도곡렉슬 아파트"}
    
    # Update stations current_state and chargers
    for st in req.get("stations", []):
        st_id = st["station_id"]
        if st_id < len(stations_data):
            sd = stations_data[st_id]
            st["current_state"]["timestamp"] = req["request_timestamp"]
            st["current_state"]["soc"] = sd["payload"]["state_of_charge"]["soc"]
            st["current_state"]["ess_soc"] = sd["payload"]["state_of_charge"]["soc"]
            st["current_state"]["p_pv_kw"] = sd["payload"]["power_metrics_w"]["p_pv"] / 1000.0
            st["current_state"]["p_load_kw"] = sd["payload"]["power_metrics_w"]["p_load"] / 1000.0
            st["current_state"]["p_grid_kw"] = sd["payload"]["power_metrics_w"]["p_grid"] / 1000.0
            
            for c_idx, c_st in enumerate(st.get("chargers", [])):
                if c_idx < len(sd["payload"]["charger_status"]):
                    has_demand = sd["payload"]["charger_status"][c_idx]["has_demand"]
                    c_st["has_demand"] = has_demand
                    c_st["is_active"] = has_demand
                    if not has_demand:
                        c_st["current_power_kw"] = 0.0
                        c_st["power_demand_kw"] = 0.0
                    else:
                        c_st["power_demand_kw"] = 7.0 if c_st.get("type") == "slow" else 50.0
                        c_st["current_power_kw"] = c_st["power_demand_kw"]
    
    # Rebuild historical arrays
    # Past data length is now 190
    past_start_time = target_date - timedelta(days=8)
    
    demand_past_hourly = []
    pv_past_hourly = []
    demand_past_weather = []
    pv_past_weather = []
    
    # helper for weather
    def safe_get_list(key, default_val=0.0, length=190):
        val = row.get(key, [default_val]*length)
        if not val: val = [default_val]*length
        return val

    # weather keys
    p_tmp = safe_get_list("past_weather_TMP")
    p_reh = safe_get_list("past_weather_REH")
    p_sky = safe_get_list("past_weather_SKY")
    p_pcp = safe_get_list("past_weather_PCP")
    p_sno = safe_get_list("past_weather_SNO")
    p_wsd = safe_get_list("past_weather_WSD")
    p_vec = safe_get_list("past_weather_VEC")
    p_pty = safe_get_list("past_weather_PTY")
    p_prs = safe_get_list("past_weather_PRS")
    p_slp = safe_get_list("past_weather_SLP")
    p_sr  = safe_get_list("past_pv_solar_radiation")
    
    for i in range(190):
        slot_time = past_start_time + timedelta(hours=i)
        ts_str = slot_time.strftime("%Y-%m-%dT%H:00:00+09:00")
        tm_str = slot_time.strftime("%Y%m%d%H00")
        slot_start = slot_time.hour
        slot_end = (slot_time.hour + 1) % 24
        if slot_end == 0: slot_end = 24
        
        # Add past weather to demand_past_weather_hourly (1 item per hour, independent of station)
        weather_obj = {
            "timestamp": ts_str,
            "tm": tm_str,
            "source": "ASOS_108",
            "location_name": "Seoul/Gangnam",
            "temperature_c": float(p_tmp[i]) if i < len(p_tmp) else 0.0,
            "humidity_pct": float(p_reh[i]) if i < len(p_reh) else 0.0,
            "cloud_amount": float(p_sky[i]) if i < len(p_sky) else 0.0,
            "precipitation_mm": float(p_pcp[i]) if i < len(p_pcp) else 0.0,
            "snow_cm": float(p_sno[i]) if i < len(p_sno) else 0.0,
            "wind_speed_ms": float(p_wsd[i]) if i < len(p_wsd) else 0.0,
            "wind_direction_deg": float(p_vec[i]) if i < len(p_vec) else 0.0,
            "current_PTY": float(p_pty[i]) if i < len(p_pty) else 0.0,
            "pressure_hpa": float(p_prs[i]) if i < len(p_prs) else 0.0,
            "sea_level_pressure_hpa": float(p_slp[i]) if i < len(p_slp) else 0.0,
            "solar_radiation_mj_m2": float(p_sr[i]) if i < len(p_sr) else 0.0
        }
        demand_past_weather.append(weather_obj)
        pv_past_weather.append(weather_obj)
        
        for st_id in range(5):
            # demand
            demand_val = row.get(f"past_demand_kw_s{st_id}", [0]*190)
            val_d = demand_val[i] if i < len(demand_val) else 0.0
            demand_past_hourly.append({
                "station_id": st_id,
                "station_name": station_names.get(st_id, f"Station {st_id}"),
                "timestamp": ts_str,
                "tm": tm_str,
                "slot_start": slot_start,
                "slot_end": slot_end,
                "demand_kwh": float(val_d)
            })
            # pv
            pv_val = row.get(f"past_pv_generation_kw_s{st_id}", [0]*190)
            val_p = pv_val[i] if i < len(pv_val) else 0.0
            pv_past_hourly.append({
                "station_id": st_id,
                "station_name": station_names.get(st_id, f"Station {st_id}"),
                "timestamp": ts_str,
                "tm": tm_str,
                "slot_start": slot_start,
                "slot_end": slot_end,
                "gen_kwh": float(val_p),
                "pv_generation_kwh": float(val_p)
            })
            
    req["demand_past_demand_hourly"] = demand_past_hourly
    req["pv_past_generation_hourly"] = pv_past_hourly
    req["demand_past_weather_hourly"] = demand_past_weather
    req["pv_past_weather_hourly"] = pv_past_weather
    
    # Forecast arrays (48 hours)
    forecast_start_time = target_date
    weather_forecast = []
    demand_forecast_hourly = []
    pv_forecast_hourly = []
    
    f_tmp = safe_get_list("forecast_TMP", 0.0, 48)
    f_pop = safe_get_list("forecast_POP", 0.0, 48)
    f_sky = safe_get_list("forecast_SKY", 0.0, 48)
    f_pty = safe_get_list("forecast_PTY", 0.0, 48)
    f_pcp = safe_get_list("forecast_PCP", 0.0, 48)
    f_sno = safe_get_list("forecast_SNO", 0.0, 48)
    f_reh = safe_get_list("forecast_REH", 0.0, 48)
    f_wsd = safe_get_list("forecast_WSD", 0.0, 48)
    f_vec = safe_get_list("forecast_VEC", 0.0, 48)
    f_uuu = safe_get_list("forecast_UUU", 0.0, 48)
    f_vvv = safe_get_list("forecast_VVV", 0.0, 48)
    f_tmn = safe_get_list("forecast_TMN", 0.0, 48)
    f_tmx = safe_get_list("forecast_TMX", 0.0, 48)
    
    for i in range(48):
        slot_time = forecast_start_time + timedelta(hours=i)
        ts_str = slot_time.strftime("%Y-%m-%dT%H:00:00+09:00")
        tm_str = slot_time.strftime("%Y%m%d%H00")
        slot_start = slot_time.hour
        slot_end = (slot_time.hour + 1) % 24
        if slot_end == 0: slot_end = 24
        
        weather_obj = {
            "timestamp": ts_str,
            "tm": tm_str,
            "source": "KMA_SHORT_TERM",
            "temperature_c": float(f_tmp[i]) if i < len(f_tmp) else 0.0,
            "pop_pct": float(f_pop[i]) if i < len(f_pop) else 0.0,
            "cloud_amount": float(f_sky[i]) if i < len(f_sky) else 0.0,
            "pty": float(f_pty[i]) if i < len(f_pty) else 0.0,
            "precipitation_mm": float(f_pcp[i]) if i < len(f_pcp) else 0.0,
            "snow_cm": float(f_sno[i]) if i < len(f_sno) else 0.0,
            "humidity_pct": float(f_reh[i]) if i < len(f_reh) else 0.0,
            "wind_speed_ms": float(f_wsd[i]) if i < len(f_wsd) else 0.0,
            "wind_direction_deg": float(f_vec[i]) if i < len(f_vec) else 0.0,
            "uuu": float(f_uuu[i]) if i < len(f_uuu) else 0.0,
            "vvv": float(f_vvv[i]) if i < len(f_vvv) else 0.0,
            "tmn": float(f_tmn[i]) if i < len(f_tmn) else 0.0,
            "tmx": float(f_tmx[i]) if i < len(f_tmx) else 0.0
        }
        weather_forecast.append(weather_obj)
        
        for st_id in range(5):
            # forecast demand
            demand_val = row.get(f"forecast_demand_kw_s{st_id}", [0]*48)
            val_d = demand_val[i] if i < len(demand_val) else 0.0
            demand_forecast_hourly.append({
                "station_id": st_id,
                "station_name": station_names.get(st_id, f"Station {st_id}"),
                "timestamp": ts_str,
                "tm": tm_str,
                "slot_start": slot_start,
                "slot_end": slot_end,
                "demand_kwh": float(val_d)
            })
            
            # forecast pv
            pv_val = row.get(f"forecast_pv_generation_kw_s{st_id}", [0]*48)
            val_p = pv_val[i] if i < len(pv_val) else 0.0
            pv_forecast_hourly.append({
                "station_id": st_id,
                "station_name": station_names.get(st_id, f"Station {st_id}"),
                "timestamp": ts_str,
                "tm": tm_str,
                "slot_start": slot_start,
                "slot_end": slot_end,
                "gen_kwh": float(val_p),
                "pv_generation_kwh": float(val_p)
            })
        
    req["demand_forecast_short_term_hourly"] = demand_forecast_hourly
    req["pv_forecast_short_term_hourly"] = pv_forecast_hourly
    req["weather_forecast_short_term_hourly"] = weather_forecast
    
    return req

if __name__ == "__main__":
    # Test
    # Load sim_daily_requests mock
    import ast, csv
    sim_daily_requests = {}
    with open("Sim_Daily_Requests.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            parsed_row = {}
            for k, v in r.items():
                if k.startswith("past_") or k.startswith("forecast_"):
                    parsed_row[k] = ast.literal_eval(v)
                else:
                    parsed_row[k] = v
            sim_daily_requests[0] = parsed_row
            break
            
    stations_data = [
        {"payload": {"state_of_charge": {"soc": 0.5}, "power_metrics_w": {"p_pv": 100, "p_load": 200, "p_grid": 300}, "charger_status": [{"has_demand": True, "type": "fast"}]*5}}
    ] * 5
    
    out = build_ai_server_request(0, 22, sim_daily_requests, stations_data)
    print("Keys built:", out.keys())
    print("Demand past length:", len(out["demand_past_demand_hourly"]))
    print("PV past length:", len(out["pv_past_generation_hourly"]))
    print("Weather past length:", len(out["demand_past_weather_hourly"]))
    print("Weather forecast length:", len(out.get("weather_forecast_short_term_hourly", [])))
    
    with open("sample_ai_server_request.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved sample_ai_server_request.json")
