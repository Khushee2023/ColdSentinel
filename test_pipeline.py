import pandas as pd
from backend.pipeline import process_reading

df = pd.read_csv("data/coldsentinel.csv")
results = [process_reading(row.to_dict()) for _, row in df.iterrows()]
out = pd.DataFrame(results)

print(out.groupby(["unit_id", "status"]).size())
print()
for u in ["C", "D"]:
    first = out[(out.unit_id == u) & (out.status == "alert")].iloc[0]
    print(first.to_dict())