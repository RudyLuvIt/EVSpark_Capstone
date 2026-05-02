import csv
import json

def parse_csv(filepath):
    days_data = {}
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            day_idx = i // 24
            step_idx = i % 24
            day_key = f"day{day_idx}"
            if day_key not in days_data:
                days_data[day_key] = {}
            days_data[day_key][str(step_idx)] = row

    with open('parsed_data.json', 'w') as f:
        json.dump(days_data, f, indent=4)

parse_csv('Capstone_Data.csv')
