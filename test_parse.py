import csv
import ast

with open('Sim_Daily_Requests.csv') as f:
    reader = csv.DictReader(f)
    row = next(reader)
    for k, v in row.items():
        if k.startswith('past_') or k.startswith('forecast_'):
            val = ast.literal_eval(v)
            print(f"{k}: {len(val)}")
