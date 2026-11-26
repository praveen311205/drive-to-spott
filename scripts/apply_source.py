#!/usr/bin/env python3
"""Apply state/source_plan.jsonl to Spott: set Source where evidenced; clear Source where it says "Drive import"
and there is no evidence. Never touches a Source someone set by hand. Log: state/source_apply.jsonl (resumable)."""
import json, os, time, urllib.request
S = os.path.join(os.path.dirname(__file__), "..", "state")
SRC = "01a20d1d-605c-7886-b070-e5d6e80e3280"
def call(m, p, b=None):
    for a in range(7):
        try:
            r = urllib.request.urlopen(urllib.request.Request("https://api.gospott.com" + p, method=m, data=json.dumps(b).encode() if b is not None else None,
                                       headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"}), timeout=60).read()
            time.sleep(0.35); return json.loads(r) if r else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < 6: time.sleep(5 * 2 ** a); continue
            raise RuntimeError(f"{m} {p} {e.code}")
filled = {json.loads(l)["id"] for l in open(os.path.join(S, "spott_candidates.jsonl")) if "Source" in json.loads(l)["cf_filled"]}
logp = os.path.join(S, "source_apply.jsonl")
done = {json.loads(l)["candidate_id"] for l in open(logp)} if os.path.exists(logp) else set()
log = open(logp, "a"); c = {"set": 0, "cleared": 0, "kept": 0, "error": 0}
for l in open(os.path.join(S, "source_plan.jsonl")):
    r = json.loads(l); cid = r["candidate_id"]
    if cid in done: continue
    try:
        if r["source"]:
            call("PUT", f"/custom-attributes/candidates/{cid}/values/_bulk", {"attributes": [{"attributeDefinitionId": SRC, "value": {"viewType": "customSelect", "select": r["source"]}}]})
            act = "set"
        elif cid in filled:
            rec = call("GET", f"/candidates/{cid}")
            cur = next(((a.get("value") or {}).get("select") for a in rec.get("customAttributes") or [] if a["attributeDefinitionId"] == SRC), None)
            if cur == "Drive import":
                call("PUT", f"/custom-attributes/candidates/{cid}/values/_bulk", {"attributes": [{"attributeDefinitionId": SRC, "value": {"viewType": "customSelect", "select": None}}]})
                act = "cleared"
            else: act = "kept"
        else: continue
    except Exception as e: act = "error"
    c[act] += 1
    log.write(json.dumps({"candidate_id": cid, "action": act, "source": r["source"], "evidence": r["evidence"]}) + "\n"); log.flush()
print(c)
