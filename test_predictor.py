import pandas as pd
from backend.predictor import score_reading, FEATURES

df = pd.read_csv("data/coldsentinel.csv")

for i in [0, 100, 302, 303]:
    row = df.iloc[i]
    out = score_reading(row[FEATURES].to_dict())
    print(i, row["unit_id"], out)