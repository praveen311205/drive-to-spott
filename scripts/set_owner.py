#!/usr/bin/env python3
"""Set mainContact (owner) = Navin on every Drive-import candidate (those with a successful field write).
Log: state/owner_apply.jsonl (resumable)."""
import json, os, time, urllib.request
S = os.path.join(os.path.dirname(__file__), "..", "state")
NAVIN = "user_3LKSME63LBqHEQAVSj1tyQJCgyf"
ids = {json.loads(l)["cid"] for l in open(os.path.join(S, "field_apply_api.jsonl")) if json.loads(l)["status"] == "ok"}
logp = os.path.join(S, "owner_apply.jsonl")
done = {json.loads(l)["cid"] for l in open(logp) if json.loads(l)["status"] == "ok"} if os.path.exists(logp) else set()
log = open(logp, "a"); ok = err = 0
for cid in sorted(ids - done):
    req = urllib.request.Request(f"https://api.gospott.com/candidates/{cid}", method="PATCH",
          data=json.dumps({"mainContact": {"userId": NAVIN}}).encode(),
          headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"})
    st, msg = "error", ""
    for a in range(4):
        try: urllib.request.urlopen(req, timeout=60); st = "ok"; break
        except urllib.error.HTTPError as e:
            msg = f"{e.code}"; time.sleep(2 ** a) if e.code in (429, 500, 502, 503) else None
            if e.code not in (429, 500, 502, 503): break
    time.sleep(0.3)
    log.write(json.dumps({"cid": cid, "status": st, "msg": msg}) + "\n"); log.flush(); ok += st == "ok"; err += st != "ok"
print("owner set:", ok, "errors:", err, "already:", len(done))
