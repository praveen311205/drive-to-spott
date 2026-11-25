#!/usr/bin/env python3
"""Apply state/field_plan.json through the Spott REST API: one PUT per candidate with all its field values.
Multi-selects are merged per candidate (the API replaces). Log: state/field_apply_api.jsonl (resumable).
Usage: apply_fields.py [--only <candidate_id>] [--dry]"""
import json, os, sys, time, urllib.request, collections
S = os.path.join(os.path.dirname(__file__), "..", "state")
plan = json.load(open(os.path.join(S, "field_plan.json")))
per = collections.defaultdict(dict)   # cid -> defId -> value
for e in plan:
    v = e["value"]; k = v["kind"]
    for cid in e["recordIds"]:
        d = per[cid]
        if k == "multiSelect":
            cur = d.setdefault(e["definitionId"], {"viewType": "customMultiSelect", "multiSelect": []})
            for x in v["multiSelect"]:
                if x not in cur["multiSelect"]: cur["multiSelect"].append(x)
        else:
            d[e["definitionId"]] = {"viewType": "custom" + k[0].upper() + k[1:], k: v[k]}
# a real value beats "Unknown" in a multi-select
for d in per.values():
    for v in d.values():
        if v["viewType"] == "customMultiSelect" and len(v["multiSelect"]) > 1 and "Unknown" in v["multiSelect"]:
            v["multiSelect"].remove("Unknown")
logp = os.path.join(S, "field_apply_api.jsonl")
done = set()
if os.path.exists(logp):
    for l in open(logp):
        r = json.loads(l)
        if r["status"] == "ok": done.add(r["cid"])
only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
log = open(logp, "a"); ok = err = 0
for cid, d in per.items():
    if only and cid != only: continue
    if cid in done and not only: continue
    body = {"attributes": [{"attributeDefinitionId": k, "value": v} for k, v in d.items()]}
    if "--dry" in sys.argv: print(json.dumps(body)[:600]); continue
    req = urllib.request.Request(f"https://api.gospott.com/custom-attributes/candidates/{cid}/values/_bulk",
                                 data=json.dumps(body).encode(), method="PUT",
                                 headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            urllib.request.urlopen(req, timeout=60); status, msg = "ok", ""; break
        except urllib.error.HTTPError as e:
            status, msg = "error", f"{e.code} {e.read()[:300].decode(errors='ignore')}"
            if e.code in (429, 500, 502, 503, 504): time.sleep(2 ** attempt); continue
            break
        except Exception as e:
            status, msg = "error", str(e)[:300]; time.sleep(2 ** attempt)
    time.sleep(0.3)
    log.write(json.dumps({"cid": cid, "status": status, "n": len(d), "msg": msg}) + "\n"); log.flush()
    ok += status == "ok"; err += status != "ok"
print("candidates:", len(per), "| ok:", ok, "| errors:", err, "| previously done:", len(done))
