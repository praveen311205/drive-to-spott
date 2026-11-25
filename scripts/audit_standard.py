#!/usr/bin/env python3
"""Read-only audit of Spott candidates against Nav's record standard. Writes state/audit.json and prints a summary."""
import json, os, time, urllib.request, urllib.parse, collections, re
S = os.path.join(os.path.dirname(__file__), "..", "state")
def get(q):
    r = urllib.request.urlopen(urllib.request.Request("https://api.gospott.com/candidates?" + urllib.parse.urlencode(q), headers={"x-api-key": "proxy-injected"}), timeout=90)
    time.sleep(0.3); return json.loads(r.read())
items, cur = [], None
while True:
    q = {"limit": 50}
    if cur: q["cursor"] = cur
    d = get(q); items += d["items"]; cur = d["pageInfo"].get("nextCursor")
    if not d["pageInfo"].get("hasNextPage"): break
def val(a):
    v = a.get("value") or {}
    for k in ("select", "multiSelect", "number", "date", "text", "checked"):
        if v.get(k) not in (None, [], ""): return v[k]
    return None
CHECKS = ["name", "linkedin", "email_or_phone", "title_company", "Function", "Seniority", "Segment sold to", "Source", "owner"]
rows, fill = [], collections.Counter()
for c in items:
    a = {x["label"]: val(x) for x in c.get("customAttributes") or []}
    fn, ln = c["name"]["firstName"] or "", c["name"]["lastName"] or ""
    lw = c.get("latestWorkExperience") or {}
    ok = {"name": bool(fn and ln) and not (fn.isupper() or ln.isupper()) and not re.search(r"\d", fn + ln),
          "linkedin": any(s.get("type") == "LINKEDIN" for s in c["socialMedia"]["socialMedia"]),
          "email_or_phone": bool(c["emails"]["emails"] or c["phoneNumbers"]["phoneNumbers"]),
          "title_company": bool(lw.get("title") and (lw.get("company") or {}).get("name")),
          "Function": a.get("Function") is not None, "Seniority": a.get("Seniority") is not None,
          "Segment sold to": a.get("Segment sold to") is not None, "Source": a.get("Source") is not None,
          "owner": bool((c.get("mainContact") or {}).get("user"))}
    for k, v in ok.items(): fill[k] += v
    rows.append({"id": c["id"], "name": f"{fn} {ln}", "src": c["acquisitionSource"]["acquisitionSource"], "ok": ok, "score": sum(ok.values())})
n = len(rows)
full = sum(r["score"] == len(CHECKS) for r in rows)
json.dump(rows, open(os.path.join(S, "audit.json"), "w"))
print("candidates", n, "| meet ALL checks:", full, f"({100*full/n:.0f}%)")
print("by check:", {k: f"{100*fill[k]/n:.0f}%" for k in CHECKS})
drive = [r for r in rows if r["src"] == "cv_parse"]
print("Drive/CV records:", len(drive), "| meet all:", sum(r["score"] == len(CHECKS) for r in drive), "| missing only Seniority/LinkedIn:", sum(r["score"] == len(CHECKS) - 1 and (not r["ok"]["Seniority"] or not r["ok"]["linkedin"]) for r in drive))
