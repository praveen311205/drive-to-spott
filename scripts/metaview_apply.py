#!/usr/bin/env python3
"""Apply state/metaview/plan.jsonl to Spott (REST API, no AI). Usage: metaview_apply.py [--dry]
Candidates: one note per call ("YYYY-MM-DD – Metaview", 3-5 lines; skipped if the record already has a note that day),
  empty fields only, Source from explicit evidence (referral / inbound / event replace a Source that was only inferred).
  New people (full name + email, call within 24 months) are created once (grouped by email), owner Navin.
Companies: note on the company; companies not in Spott are created as Prospect.
Everything else (first name only, unidentified, older than 24 months) -> state/metaview/review.jsonl.
Log: state/metaview/apply_log.jsonl (resumable)."""
import json, os, re, sys, time, html, collections, urllib.request, urllib.parse
S = os.path.join(os.path.dirname(__file__), "..", "state"); D = os.path.join(S, "metaview")
API = "https://api.gospott.com"; NAVIN = "user_3LKSME63LBqHEQAVSj1tyQJCgyf"; DRY = "--dry" in sys.argv; CUTOFF = "2024-11-27"
PROSPECT = "1e38b262-b0a5-4440-bde6-b80114a558c5"


def call(m, p, b=None):
    if DRY and m != "GET": return {"id": "DRY"}
    for a in range(7):
        try:
            r = urllib.request.urlopen(urllib.request.Request(API + p, method=m, data=json.dumps(b).encode() if b is not None else None,
                                       headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"}), timeout=60).read()
            time.sleep(0.35)
            if not r: return {}
            try: return json.loads(r)
            except ValueError:
                mm = re.search(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", r)
                return {"id": mm.group(0).decode()} if mm else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < 6: time.sleep(5 * 2 ** a); continue
            raise RuntimeError(f"{m} {p} -> {e.code} {e.read()[:250].decode(errors='ignore')}")


defs = {}
for d in sorted(json.load(open(f"{S}/custom_fields.json"))["custom_fields_candidate"]["items"], key=lambda d: d.get("createdAt") or ""):
    defs[d["label"]] = d
def opt(label, text):
    opts = (defs[label].get("definition") or {}).get("options") or []
    t = (text or "").lower()
    if label == "Status":
        return "Open to offers" if "open" in t or "passive" in t else ("Not looking" if "not" in t else ("Active" if "activ" in t else None))
    if label == "Work setup":
        return next((o for o in ("Hybrid", "Remote", "Office") if o.lower() in t), None)
    if label == "Notice period":
        for o in opts:
            if o.lower() == t.strip(): return o
        m = re.search(r"(\d+)\s*(week|month)", t)
        if m:
            cand = f"{m.group(1)} {m.group(2)}{'s' if m.group(1) != '1' else ''}"
            return cand if cand in opts else "Other"
        if "immediate" in t: return "Immediate"
        return "Other" if t else None
    if label == "Work rights":
        for k, o in (("eu", "EU citizen"), ("uk", "UK right to work"), ("us ", "US right to work"), ("sponsor", "Needs sponsorship")):
            if k in t + " ": return o
        return None
    return text if text in opts else None
LANG = {"swedish": "Nordic (Swedish/Danish/Norwegian)", "danish": "Nordic (Swedish/Danish/Norwegian)", "norwegian": "Nordic (Swedish/Danish/Norwegian)"}
def attrs(f, existing):
    out = []
    def empty(lab): return existing.get(defs[lab]["id"]) in (None, "", [], False)
    def put(lab, val):
        out.append({"attributeDefinitionId": defs[lab]["id"], "value": val})
    for k, lab in (("status", "Status"), ("work_setup", "Work setup"), ("notice_period", "Notice period"), ("work_rights", "Work rights")):
        if f.get(k) and empty(lab):
            o = opt(lab, f[k])
            if o: put(lab, {"viewType": "customSelect", "select": o})
    if f.get("currency") and empty("Currency") and f["currency"] in defs["Currency"]["definition"]["options"]:
        put("Currency", {"viewType": "customSelect", "select": f["currency"]})
    for k, lab in (("base", "Base"), ("ote", "OTE")):
        if f.get(k) and empty(lab): put(lab, {"viewType": "customNumber", "number": float(f[k])})
    if f.get("next_step") and empty("Next step"): put("Next step", {"viewType": "customText", "text": f["next_step"][:500]})
    if f.get("rip_and_replace") and empty("Rip-and-replace"):
        put("Rip-and-replace", {"viewType": "customCheckbox", "checked": True})
        if f.get("rip_and_replace_incumbent") and empty("Rip-and-replace incumbent"): put("Rip-and-replace incumbent", {"viewType": "customText", "text": f["rip_and_replace_incumbent"][:300]})
    if f.get("languages"):
        opts = defs["Language"]["definition"]["options"]; cur = [x for x in (existing.get(defs["Language"]["id"]) or []) if x]
        add = []
        for w in re.split(r"[,/;]| and ", f["languages"]):
            w = w.strip().lower(); o = LANG.get(w) or next((x for x in opts if x.lower() == w), None)
            if o and o not in cur + add: add.append(o)
        if add: put("Language", {"viewType": "customMultiSelect", "multiSelect": cur + add})
    return out
SRC = {"REFERRAL": "Referral", "INBOUND_APPLICATION": "Inbound application", "LINKEDIN_OUTREACH": "LinkedIn outreach", "OTHER_OUTREACH": "Other", "EVENT": "Event"}
STRONG = {"Referral", "Inbound application", "Event"}
def source_of(how):
    lab = (how or "").split("|")[0].split(":")[0].strip().upper()
    return SRC.get(lab), (how or "")[:200]
def proper(s): return s.title() if s and (s.isupper() or s.islower()) else s

plan = [json.loads(l) for l in open(f"{D}/plan.jsonl")]
logp = f"{D}/apply_log{'_dry' if DRY else ''}.jsonl"
done = {json.loads(l)["conv"] for l in open(logp) if json.loads(l)["status"] in ("ok", "review", "skipped")} if os.path.exists(logp) else set()
created_by_email = {json.loads(l)["created_email"]: json.loads(l)["candidate_id"] for l in open(logp) if json.loads(l).get("created_email")} if os.path.exists(logp) else {}
created_co = {json.loads(l)["created_company"]: json.loads(l)["company_id"] for l in open(logp) if json.loads(l).get("created_company")} if os.path.exists(logp) else {}
log = open(logp, "a"); st = collections.Counter()
def write(r): log.write(json.dumps(r) + "\n"); log.flush(); st[f"{r['kind']}:{r['status']}:{r.get('how','')}"] += 1
plan.sort(key=lambda r: r["date"])          # oldest first, so notes land in order
for r in plan:
    if r["conv"] in done: continue
    a = r["action"]; out = {"conv": r["conv"], "kind": a.split(":")[0], "status": "ok", "how": "", "issues": ""}
    try:
        if a.startswith("skip"):
            out.update(status="skipped", how=r["type"]); write(out); continue
        if a.startswith("candidate"):
            cid = r.get("candidate_id")
            if not cid:
                key = (r.get("emails") or [None])[0]
                if a != "candidate: new (full name + email)":
                    out.update(status="review", how=a.split(": ")[1], issues=f"{r.get('name')} {r.get('emails')} {r['date']} {r.get('url')}"); write(out); continue
                if r["date"] < CUTOFF:
                    out.update(status="review", how="older than 24 months", issues=f"{r.get('name')} {r.get('emails')} {r['date']}"); write(out); continue
                cid = created_by_email.get(key)
                if not cid:
                    parts = r["name"].split(); body = {"firstName": proper(parts[0]), "lastName": proper(" ".join(parts[1:])), "mainContact": {"userId": NAVIN},
                                                      "emails": [{"email": e, "purpose": "personal", "isPrimary": i == 0} for i, e in enumerate(r["emails"][:3])]}
                    if r.get("linkedin"): body["socialMedia"] = [{"url": r["linkedin"].split("?")[0], "type": "LINKEDIN"}]
                    try: cid = call("POST", "/candidates", body).get("id")
                    except RuntimeError as e:
                        if "409" in str(e):
                            body.pop("emails"); body.pop("socialMedia", None); cid = call("POST", "/candidates", body).get("id"); out["issues"] += " email already on another record;"
                        else: raise
                    created_by_email[key] = cid; out["created_email"] = key; out["how"] = "created"
                    unk = [{"attributeDefinitionId": defs[l]["id"], "value": v} for l, v in (("Function", {"viewType": "customSelect", "select": "Unknown"}),
                           ("Segment sold to", {"viewType": "customMultiSelect", "multiSelect": ["Unknown"]}), ("Work rights", {"viewType": "customSelect", "select": "Unknown"}))]
                    call("PUT", f"/custom-attributes/candidates/{cid}/values/_bulk", {"attributes": unk})
            out["candidate_id"] = cid; out["how"] = out["how"] or "matched"
            rec = call("GET", f"/candidates/{cid}") if cid != "DRY" else {"customAttributes": []}
            existing = {}
            for x in rec.get("customAttributes") or []:
                v = x.get("value") or {}
                existing[x["attributeDefinitionId"]] = v.get("select") or v.get("multiSelect") or v.get("number") or v.get("date") or v.get("text") or v.get("checked")
            notes = call("GET", "/notes?" + urllib.parse.urlencode({"candidateId": cid, "limit": 50})).get("items", []) if cid != "DRY" else []
            if r.get("note") and not any((n.get("title") or "").startswith(r["date"]) for n in notes):
                call("POST", "/notes", {"title": f"{r['date']} – Metaview", "content": "".join(f"<p>{html.escape(x)}</p>" for x in r["note"][:5]) + f"<p>Recording: {html.escape(r.get('url') or '')}</p>",
                                        "links": [{"entityType": "candidate", "entityId": cid}]})
                out["note"] = True
            at = attrs(r.get("fields") or {}, existing)
            src, why = source_of(r.get("how"))
            cur_src = existing.get(defs["Source"]["id"])
            if src and (cur_src in (None, "") or (src in STRONG and cur_src in ("LinkedIn outreach", "Other"))):
                at.append({"attributeDefinitionId": defs["Source"]["id"], "value": {"viewType": "customSelect", "select": src}}); out["source"] = src; out["source_evidence"] = why
            lc = defs["Last contact date"]["id"]
            if not existing.get(lc) or str(existing[lc])[:10] < r["date"]:
                at.append({"attributeDefinitionId": lc, "value": {"viewType": "customDate", "date": r["date"]}})
            if at: call("PUT", f"/custom-attributes/candidates/{cid}/values/_bulk", {"attributes": at}); out["fields"] = len(at)
        else:
            coid = r.get("company_id")
            if not coid:
                k = re.sub(r"[^a-z0-9]", "", (r.get("company") or "").lower())
                if not k or k in ("na", "unknown"):
                    out.update(status="review", how="no company name", issues=r.get("company_note", "")[:200]); write(out); continue
                coid = created_co.get(k)
                if not coid:
                    coid = call("POST", "/clients", {"name": r["company"].strip()[:120], "description": "", "domain": None, "foundedYear": None, "industry": None, "size": None, "specialties": []}).get("id")
                    call("PATCH", f"/clients/{coid}", {"stageId": PROSPECT}); created_co[k] = coid; out["created_company"] = k; out["how"] = "company created (Prospect)"
            out["company_id"] = coid; out["how"] = out["how"] or "company matched"
            label = "role intake" if r["type"] == "ROLE_INTAKE" else "client call"
            parts = [x.strip() for x in (r.get("company_note") or "").split("|")]
            body = "".join(f"<p>{html.escape(x)}</p>" for x in parts[1:] if x) + f"<p>Recording: {html.escape(r.get('url') or '')}</p>"
            call("POST", "/notes", {"title": f"{r['date']} – Metaview ({label})", "content": body, "links": [{"entityType": "client", "entityId": coid}]})
    except Exception as e:
        out["status"] = "error"; out["issues"] += str(e)[:250]
    write(out)
print(dict(st))
