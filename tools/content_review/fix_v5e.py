import json
P = json.load(open("/audit/v5e_P.json"))
for e in P.values():
    if "dadd" in e: e["dadd"] = [tuple(x) for x in e["dadd"]]
