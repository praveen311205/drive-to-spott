#!/usr/bin/env python3
"""Download every Loxo CV into state/loxo/cvs/ (fresh signed link per person). Resumable; index in cvs/_index.jsonl."""
import json, os, re, time, urllib.request
BASE = "https://app.loxo.co/api/gtm-talent-b-v"
D = os.path.join(os.path.dirname(__file__), "..", "state", "loxo")
OUT = os.path.join(D, "cvs"); os.makedirs(OUT, exist_ok=True)
idx = os.path.join(OUT, "_index.jsonl")
done = set()
if os.path.exists(idx):
    for l in open(idx):
        r = json.loads(l)
        if r["status"] == "ok": done.add(str(r["resume_id"]))
res = json.load(open(os.path.join(D, "resumes_index.json")))
log = open(idx, "a"); ok = err = 0
def api(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer proxy-injected", "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))
for pid, lst in res.items():
    if not isinstance(lst, list) or not lst: continue
    if all(str(x["id"]) in done for x in lst): continue
    try: fresh = api(f"/people/{pid}/resumes")
    except Exception as e:
        log.write(json.dumps({"person_id": pid, "resume_id": None, "status": "error", "msg": str(e)[:150]}) + "\n"); err += 1; continue
    for x in fresh:
        if str(x["id"]) in done: continue
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", x.get("name") or "cv")[:80]
        fn = f"{pid}_{x['id']}_{name}"
        st, msg = "error", ""
        for a in range(3):
            try:
                data = urllib.request.urlopen(x["download_url"], timeout=120).read()
                open(os.path.join(OUT, fn), "wb").write(data); st = "ok"; break
            except Exception as e:
                msg = str(e)[:150]; time.sleep(2 ** a)
        log.write(json.dumps({"person_id": pid, "resume_id": x["id"], "file": fn, "status": st, "msg": msg}) + "\n"); log.flush()
        ok += st == "ok"; err += st != "ok"
    time.sleep(0.15)
print("downloaded", ok, "errors", err, "previously", len(done))
