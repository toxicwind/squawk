import json

path = "/home/toxic/pens/Pens/ranch/squawk/oracle/work/kb-attestation-cache.json"
with open(path, "r") as f:
    data = json.load(f)

kb_sha = data.get("kb_sha")
fetched_ts = data.get("fetched_ts")
crews = data.get("crews", [])
num_crews = len(crews)

print(f"kb_sha: {kb_sha}")
print(f"fetched_ts: {fetched_ts}")
print(f"Number of crews: {num_crews}")
