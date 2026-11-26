#!/usr/bin/env python3
"""Dry run of the Loxo -> Spott import. Reads state/loxo/*.json and state/spott_candidates.jsonl, writes nothing to
any system. Output: state/loxo/plan.jsonl (one line per Loxo person) and a summary on stdout.

Per person: action (merge | create | check_with_navin | name_match_check | contact_only), the matched Spott id,
contacts to add, field values in Nav's standard, the pipeline history and the conversation notes to summarise."""
import json, os, re, collections, unicodedata, html

S = os.path.join(os.path.dirname(__file__), "..", "state")
L = os.path.join(S, "loxo")
CUTOFF = "2024-11-25"
CUR = {1: "USD", 2: "EUR", 4: "GBP", 7: "CHF", 9: "SEK"}
NOTE_TYPES = {"Note", "Interview Note", "Consultant Interview", "1st Client Interview", "Meeting Scheduled", "Rejected", "Pitched"}
STAGE_TYPES = {"Added to Job", "Moved to Longlist", "Moved to Outbound", "Moved to Shortlist", "Marked as Yes",
               "Moved to Rejected", "Rejected", "Moved to Interview", "Moved to Offer", "Placed", "Moved to Client Interview",
               "Submitted", "Moved to Submitted", "Hired", "Moved to Hired", "1st Client Interview", "Pitched"}


def norm(s):
    return re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).strip()


def slug(u):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", u or "", re.I)
    return m.group(1).lower().rstrip("/") if m else None


def digits(p):
    return re.sub(r"\D", "", p or "")[-9:]


def text(h):
    t = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", h or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n\s*\n+", "\n", t).strip()


people = json.load(open(os.path.join(L, "people.json")))
jobs = {j["id"]: j for j in json.load(open(os.path.join(L, "jobs.json")))}
events = json.load(open(os.path.join(L, "person_events.json")))
resumes = json.load(open(os.path.join(L, "resumes_index.json")))
cvfiles = collections.defaultdict(list)
if os.path.exists(os.path.join(L, "cvs", "_index.jsonl")):
    for l in open(os.path.join(L, "cvs", "_index.jsonl")):
        r = json.loads(l)
        if r["status"] == "ok": cvfiles[str(r["person_id"])].append(r["file"])
ev_by = collections.defaultdict(list)
for e in events: ev_by[e["person_id"]].append(e)

C = [json.loads(l) for l in open(os.path.join(S, "spott_candidates.jsonl"))]
by_li, by_em, by_ph, by_nm = {}, {}, {}, {}
for c in C:
    for u in c["linkedin"]:
        if slug(u): by_li.setdefault(slug(u), set()).add(c["id"])
    for e in c["emails"]: by_em.setdefault(e.lower(), set()).add(c["id"])
    for p in c["phones"]:
        if len(digits(p)) == 9: by_ph.setdefault(digits(p), set()).add(c["id"])
    n = norm(f"{c['first']} {c['last']}").split()
    if len(n) >= 2: by_nm.setdefault(n[0] + " " + n[-1], set()).add(c["id"])

out, stats = [], collections.Counter()
seen_li, seen_em = set(), set()
for p in people:
    pid = p["id"]
    types = {t.get("name") for t in (p.get("person_types") or [])}
    emails = [e["value"].strip() for e in (p.get("emails") or []) if e.get("value") and "@" in e["value"]]
    phones = [x["value"].strip() for x in (p.get("phones") or []) if x.get("value")]
    li = slug(p.get("linkedin_url"))
    evs = sorted(ev_by.get(pid, []), key=lambda e: e["created_at"])
    last = max([p.get("created_at") or ""] + [e["created_at"] for e in evs])[:10]
    # match
    mid, how = None, None
    if li and li in by_li: mid, how = sorted(by_li[li]), "linkedin"
    if not mid:
        for e in emails:
            if e.lower() in by_em: mid, how = sorted(by_em[e.lower()]), "email"; break
    if not mid:
        for ph in phones:
            if len(digits(ph)) == 9 and digits(ph) in by_ph: mid, how = sorted(by_ph[digits(ph)]), "phone"; break
    name_hit = None
    n = norm(p.get("name") or f"{p.get('first_name')} {p.get('last_name')}").split()
    if not mid and len(n) >= 2 and n[0] + " " + n[-1] in by_nm: name_hit = sorted(by_nm[n[0] + " " + n[-1]])
    if "Candidate" not in types and "Contact" in types: action = "contact_only"
    elif (li and li in seen_li) or any(e.lower() in seen_em for e in emails): action = "skip_loxo_duplicate"   # same person twice in Loxo
    elif mid: action = "merge"
    elif name_hit: action = "name_match_check"
    elif last < CUTOFF: action = "check_with_navin"
    else: action = "create"
    # fields (only what Loxo states)
    f = {}
    comp = p.get("compensation") or p.get("salary")
    cur = CUR.get(p.get("compensation_currency_id"))
    try: comp = float(comp) if comp else None
    except ValueError: comp = None
    if comp and cur and 10000 <= comp <= 1000000: f["base"] = comp; f["currency"] = cur
    try:
        b = float(p.get("bonus") or 0)
        if f.get("base") and b and p.get("bonus_type_id") in (None, 1) and b < 5 * f["base"]: f["ote"] = f["base"] + b
    except ValueError: pass
    f["last_contact_date"] = max([e["created_at"] for e in evs if e["activity_type"]["name"] not in ("Sent Automated Email",)] or [""])[:10] or None
    # pipelines -> relationship history
    hist = []
    for cj in p.get("candidate_jobs") or []:
        j = jobs.get(cj["id"], {})
        stages = [e for e in evs if e.get("job_id") == cj["id"] and e["activity_type"]["name"] in STAGE_TYPES]
        hist.append({"client": (j.get("company") or {}).get("name"), "role": j.get("title") or cj.get("title"),
                     "job_status": (j.get("status") or {}).get("name"),
                     "stage_reached": stages[-1]["activity_type"]["name"] if stages else "Added to Job",
                     "first": stages[0]["created_at"][:10] if stages else None, "last": stages[-1]["created_at"][:10] if stages else None})
    notes = [{"date": e["created_at"][:10], "type": e["activity_type"]["name"], "job": (jobs.get(e.get("job_id")) or {}).get("title"),
              "text": text(e.get("notes"))[:4000]} for e in evs if e["activity_type"]["name"] in NOTE_TYPES and text(e.get("notes"))]
    rec = {"loxo_id": pid, "name": p.get("name"), "first": p.get("first_name"), "last": p.get("last_name"), "types": sorted(types),
           "action": action, "spott_ids": mid or name_hit, "matched_on": how or ("name" if name_hit else None),
           "linkedin": ("https://www.linkedin.com/in/" + li) if li else None, "bad_linkedin": bool(p.get("linkedin_url") and not li),
           "emails": emails, "phones": phones, "title": p.get("current_title"), "company": p.get("current_company"),
           "city": p.get("city"), "country": p.get("country"), "last_activity": last, "fields": f, "history": hist,
           "notes": notes, "cv_files": cvfiles.get(str(pid), []), "loxo_tags": p.get("all_raw_tags"),
           "loxo_description": text(p.get("description"))[:1500], "comp_notes": p.get("compensation_notes")}
    out.append(rec)
    stats[action] += 1
    if li: seen_li.add(li)
    seen_em.update(e.lower() for e in emails)
with open(os.path.join(L, "plan.jsonl"), "w") as fh:
    for r in out: fh.write(json.dumps(r) + "\n")
print("actions:", dict(stats))
cand = [r for r in out if r["action"] in ("merge", "create")]
print("in scope (merge+create):", len(cand), "| with notes:", sum(1 for r in cand if r["notes"]), "| notes:", sum(len(r["notes"]) for r in cand),
      "| with pipeline:", sum(1 for r in cand if r["history"]), "| with CV:", sum(1 for r in cand if r["cv_files"]),
      "| with base:", sum(1 for r in cand if r["fields"].get("base")))
print("merge matched on:", dict(collections.Counter(r["matched_on"] for r in out if r["action"] == "merge")))
print("bad linkedin in scope:", sum(1 for r in cand if r["bad_linkedin"]))
