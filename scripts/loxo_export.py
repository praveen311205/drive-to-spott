#!/usr/bin/env python3
"""Back up GTM Talent's Loxo data through the Loxo API into state/loxo/ (gitignored).
Key is injected by the network proxy for app.loxo.co. Lists: people (scroll), companies (scroll), jobs (pages)."""
import json, os, time, urllib.request, urllib.parse
BASE = "https://app.loxo.co/api/gtm-talent-b-v"
OUT = os.path.join(os.path.dirname(__file__), "..", "state", "loxo")
os.makedirs(OUT, exist_ok=True)
def get(path, **q):
    url = f"{BASE}/{path}" + ("?" + urllib.parse.urlencode(q) if q else "")
    for a in range(5):
        try:
            req = urllib.request.Request(url, headers={"Authorization": "Bearer proxy-injected", "Accept": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=90)); time.sleep(0.2); return r
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and a < 4: time.sleep(2 ** a + 1); continue
            raise
def scroll(kind, key):
    out, sid = [], None
    while True:
        q = {"per_page": 100}
        if sid: q["scroll_id"] = sid
        d = get(kind, **q); items = d.get(key) or []
        if not items: break
        out += items; sid = d.get("scroll_id")
        print(kind, len(out), "/", d.get("total_count"), flush=True)
        if not sid or len(out) >= (d.get("total_count") or 10**9): break
    return out
def pages(kind, key="results"):
    out, p = [], 1
    while True:
        d = get(kind, per_page=100, page=p); out += d.get(key) or []
        if p >= (d.get("total_pages") or 1): break
        p += 1
    return out
import sys
what = sys.argv[1:] or ["people", "companies", "jobs"]
if "people" in what:
    ppl = scroll("people", "people"); json.dump(ppl, open(f"{OUT}/people.json", "w"))
if "companies" in what:
    co = scroll("companies", "companies"); json.dump(co, open(f"{OUT}/companies.json", "w"))
if "jobs" in what:
    jobs = pages("jobs"); json.dump(jobs, open(f"{OUT}/jobs.json", "w")); print("jobs", len(jobs))
if "events" in what:
    ev = scroll("person_events", "person_events"); json.dump(ev, open(f"{OUT}/person_events.json", "w"))
if "resumes" in what:
    ppl = json.load(open(f"{OUT}/people.json")); res = {}
    pth = f"{OUT}/resumes_index.json"
    if os.path.exists(pth): res = json.load(open(pth))
    for i, p in enumerate(ppl):
        k = str(p["id"])
        if k in res: continue
        try: res[k] = get(f"people/{k}/resumes")
        except Exception as e: res[k] = {"error": str(e)[:200]}
        if i % 100 == 0:
            json.dump(res, open(pth, "w")); print("resumes indexed", len(res), flush=True)
    json.dump(res, open(pth, "w")); print("resumes indexed", len(res))
