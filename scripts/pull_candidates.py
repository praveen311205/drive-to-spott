#!/usr/bin/env python3
"""Pull every Spott candidate into state/spott_candidates.jsonl (compact). Key is injected by the proxy."""
import json, sys, time, urllib.request, urllib.parse, os
BASE = "https://api.gospott.com/candidates"
out = open(os.path.join(os.path.dirname(__file__), "..", "state", "spott_candidates.jsonl"), "w")
cursor, n = None, 0
while True:
    q = {"limit": 50}
    if cursor: q["cursor"] = cursor
    req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(q), headers={"x-api-key": "proxy-injected"})
    for attempt in range(4):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=60)); break
        except Exception as e:
            if attempt == 3: raise
            time.sleep(2 ** attempt)
    for c in d["items"]:
        lw = c.get("latestWorkExperience") or {}
        out.write(json.dumps({
            "id": c["id"], "first": c["name"]["firstName"], "last": c["name"]["lastName"],
            "emails": [e["email"] for e in c["emails"]["emails"]],
            "phones": [p["phoneNumber"] for p in c["phoneNumbers"]["phoneNumbers"]],
            "linkedin": [s["url"] for s in c["socialMedia"]["socialMedia"] if s.get("type") == "LINKEDIN"],
            "title": lw.get("title"), "company": (lw.get("company") or {}).get("name"), "end": lw.get("endDate"),
            "source": c["acquisitionSource"]["acquisitionSource"], "created": c["createdAt"],
            "client_contact": c.get("hasClientContacts"),
            "cf_filled": [a["label"] for a in c.get("customAttributes", []) if any(v not in (None, [], "", False) for k, v in (a.get("value") or {}).items() if k != "viewType")],
        }) + "\n")
        n += 1
    cursor = d["pageInfo"].get("nextCursor")
    if not d["pageInfo"].get("hasNextPage"): break
print("candidates:", n)
