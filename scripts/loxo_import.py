#!/usr/bin/env python3
"""Import Loxo people into Spott through the Spott REST API (no AI). Works from state/loxo/plan.jsonl
(scripts/loxo_plan.py) and the note summaries state/loxo/*notes_sum*.jsonl.

Usage: loxo_import.py --ids state/loxo/test20.json [--dry]
Per person (action merge|create only):
  merge  -> existing Spott record: add missing emails/phones/LinkedIn, attach the Loxo CV if the record has none
  create -> new record from the CV (Spott parses it), else from name + contacts; owner Navin
  then   -> one note per Loxo conversation ("YYYY-MM-DD – call|Loxo", 3-5 lines), one dated note per Loxo pipeline,
            field values (pay, currency, notice, status, last contact date) in Nav's standard, never overwriting
Log: state/loxo/import_log.jsonl (resumable by loxo_id).
"""
import json, os, re, sys, time, uuid, html, glob, urllib.request, urllib.parse

S = os.path.join(os.path.dirname(__file__), "..", "state")
L = os.path.join(S, "loxo")
API = "https://api.gospott.com"
NAVIN = "user_3LKSME63LBqHEQAVSj1tyQJCgyf"
DRY = "--dry" in sys.argv
IDS = set(json.load(open(sys.argv[sys.argv.index("--ids") + 1]))) if "--ids" in sys.argv else None
CALL_TYPES = {"Consultant Interview", "Interview Note", "1st Client Interview"}


def call(method, path, body=None, raw=None, ctype="application/json"):
    if DRY and method != "GET": return {"id": "DRY"}
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API + path, method=method, data=data, headers={"x-api-key": "proxy-injected", "Content-Type": ctype})
    for a in range(5):
        try:
            r = urllib.request.urlopen(req, timeout=120).read(); time.sleep(0.3)
            if not r: return {}
            try: return json.loads(r)
            except ValueError:
                m = re.search(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", r)
                return {"id": m.group(0).decode()} if m else {"_raw": r[:200].decode(errors="ignore")}
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and a < 4: time.sleep(2 ** a + 1); continue
            raise RuntimeError(f"{method} {path} -> {e.code} {e.read()[:300].decode(errors='ignore')}")


def multipart(field, fname, blob, extra=None):
    b = uuid.uuid4().hex
    pre = "".join(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n" for k, v in (extra or {}).items()).encode()
    ct = "application/pdf" if blob[:4] == b"%PDF" else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if blob[:2] == b"PK" else "application/msword")
    body = pre + (f"--{b}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{fname}\"\r\nContent-Type: {ct}\r\n\r\n").encode() + blob + f"\r\n--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


CC = {"France": "33", "Germany": "49", "United Kingdom": "44", "UK": "44", "Netherlands": "31", "Sweden": "46", "Spain": "34",
      "Italy": "39", "Belgium": "32", "Switzerland": "41", "Austria": "43", "Portugal": "351", "Ireland": "353", "Denmark": "45",
      "Norway": "47", "Poland": "48", "Finland": "358"}


def e164(p, country=None):
    d = re.sub(r"[^\d+]", "", p or "")
    if d.startswith("00"): d = "+" + d[2:]
    if not d.startswith("+") and d.startswith("0") and CC.get(country or ""): d = "+" + CC[country] + d[1:]
    return d if d.startswith("+") and 9 <= len(d) <= 16 else None


def proper(s):
    s = (s or "").strip()
    return s.title() if s and (s.isupper() or s.islower()) else s


defs = {}
for d in sorted(json.load(open(os.path.join(S, "custom_fields.json")))["custom_fields_candidate"]["items"], key=lambda d: d.get("createdAt") or ""):
    defs[d["label"]] = d
FMAP = {"base": "Base", "ote": "OTE", "currency": "Currency", "notice_period": "Notice period", "work_setup": "Work setup",
        "status": "Status", "last_contact_date": "Last contact date", "languages": "Language", "work_rights": "Work rights",
        "next_step": "Next step", "rip_and_replace": "Rip-and-replace", "rip_and_replace_incumbent": "Rip-and-replace incumbent"}
LANG = {"Swedish": "Nordic (Swedish/Danish/Norwegian)", "Danish": "Nordic (Swedish/Danish/Norwegian)", "Norwegian": "Nordic (Swedish/Danish/Norwegian)"}


def attrs(fields, existing):
    out, rej = [], []
    for k, v in fields.items():
        lab = FMAP.get(k)
        if not lab or v in (None, "", []): continue
        d = defs.get(lab)
        if not d: rej.append(f"{k}: no field"); continue
        cur = existing.get(d["id"])
        if cur not in (None, [], "", {}) and k != "last_contact_date": continue      # never overwrite
        vt, opts = d["viewType"], (d.get("definition") or {}).get("options") or []
        if vt == "customSelect":
            v = "Other" if str(v).lower().startswith("other") and "Other" in opts else v
            if v in opts: out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "select": v}})
            else: rej.append(f"{k}={v}")
        elif vt == "customMultiSelect":
            vals = [LANG.get(x, x) for x in (v if isinstance(v, list) else [v])]
            good = [x for x in vals if x in opts] or (["Other"] if "Other" in opts else [])
            if good: out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "multiSelect": sorted(set((cur or []) + good))}})
        elif vt == "customNumber":
            out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "number": float(v)}})
        elif vt == "customCheckbox":
            if isinstance(v, bool): out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "checked": v}})
        elif vt == "customText":
            out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "text": str(v)[:500]}})
        elif vt == "customDate":
            if cur and isinstance(cur, str) and cur >= str(v)[:10]: continue      # keep a later last-contact date
            out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "date": str(v)[:10]}})
    return out, rej


plan = [json.loads(l) for l in open(os.path.join(L, "plan.jsonl"))]
sums = {}
for f in glob.glob(os.path.join(L, "*notes_sum*.jsonl")) + glob.glob(os.path.join(L, "nbatch", "*_sum.jsonl")):
    for l in open(f):
        if l.strip():
            r = json.loads(l); sums[(r["loxo_id"], r["i"])] = r
SHARD = sys.argv[sys.argv.index("--shard") + 1] if "--shard" in sys.argv else None      # "k/N": process loxo_id % N == k
logp = os.path.join(L, "import_log_dry.jsonl" if DRY else (f"import_log_s{SHARD.split('/')[0]}.jsonl" if SHARD else "import_log.jsonl"))
done = set()
for lf in glob.glob(os.path.join(L, "import_log*.jsonl")):
    if "dry" in lf: continue
    for l in open(lf):
        x = json.loads(l)
        if x["status"] != "error": done.add(x["loxo_id"])
log = open(logp, "a")
for r in plan:
    if IDS is not None and r["loxo_id"] not in IDS: continue
    if r["action"] not in ("merge", "create") or r["loxo_id"] in done: continue
    if SHARD and r["loxo_id"] % int(SHARD.split("/")[1]) != int(SHARD.split("/")[0]): continue
    if any((r["loxo_id"], i) not in sums for i in range(len(r["notes"]))):
        continue                                   # wait until every note of this person is summarised
    res = {"loxo_id": r["loxo_id"], "name": r["name"], "action": r["action"], "status": None, "candidate_id": None,
           "contacts_added": [], "cv": None, "notes_added": 0, "pipeline_notes": 0, "fields": 0, "issues": ""}
    try:
        cvs = [os.path.join(L, "cvs", f) for f in r["cv_files"]]
        cvs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        if r["action"] == "merge":
            cid = r["spott_ids"][0]
            if len(r["spott_ids"]) > 1: res["issues"] += f" duplicates in Spott {r['spott_ids']};"
        else:
            cid = None
            for p in cvs[:1]:
                blob = open(p, "rb").read()
                if blob[:4] == b"%PDF" or blob[:2] == b"PK":
                    try:
                        body, ct = multipart("file", os.path.basename(p), blob)
                        cid = call("POST", "/candidates/_from-unsupervised-cv", raw=body, ctype=ct).get("id"); res["cv"] = "parsed"
                    except RuntimeError as e: res["issues"] += f" CV parse failed: {str(e)[:120]};"
            if not cid:
                body = {"firstName": proper(r["first"]) or "Unknown", "lastName": proper(r["last"]) or "Unknown"}
                cid = call("POST", "/candidates", body).get("id")
        res["candidate_id"] = cid
        rec = call("GET", f"/candidates/{cid}") if cid and cid != "DRY" else {"emails": {"emails": []}, "phoneNumbers": {"phoneNumbers": []}, "socialMedia": {"socialMedia": []}, "name": {}, "customAttributes": []}
        # contacts + name + owner
        patch = {}
        have_e = [e["email"].lower() for e in rec["emails"]["emails"]]
        new_e = [e for e in r["emails"] if e.lower() not in have_e]
        if new_e:
            patch["emails"] = [{"email": e["email"], "purpose": e.get("purpose"), "isPrimary": e.get("isPrimary", False)} for e in rec["emails"]["emails"]] + \
                              [{"email": e, "purpose": "personal", "isPrimary": not have_e and i == 0} for i, e in enumerate(new_e)]
        have_p = [re.sub(r"\D", "", p["phoneNumber"])[-9:] for p in rec["phoneNumbers"]["phoneNumbers"]]
        new_p = []
        for p in (e164(x, r.get("country")) for x in r["phones"]):
            if p and re.sub(r"\D", "", p)[-9:] not in have_p + [re.sub(r"\D", "", x)[-9:] for x in new_p]: new_p.append(p)
        if new_p:
            patch["phoneNumbers"] = [{"phoneNumber": p["phoneNumber"], "purpose": p.get("purpose") or "personal", "isPrimary": p.get("isPrimary", False)} for p in rec["phoneNumbers"]["phoneNumbers"]] + \
                                    [{"phoneNumber": p, "purpose": "personal", "isPrimary": not have_p and i == 0} for i, p in enumerate(new_p)]
        if r["linkedin"] and not any(s.get("type") == "LINKEDIN" for s in rec["socialMedia"]["socialMedia"]):
            patch["socialMedia"] = [{"url": s["url"], "type": s["type"]} for s in rec["socialMedia"]["socialMedia"]] + [{"url": r["linkedin"], "type": "LINKEDIN"}]
        if r["action"] == "merge" and rec.get("hasClientContacts") and rec.get("isVisibleIfClientContact") is False:
            patch["visibleIfClientContact"] = True      # candidate + client contact: keep them in the Candidates list (Praveen, 26 Nov)
        if r["action"] == "create":
            patch["mainContact"] = {"userId": NAVIN}
            fn, ln = rec["name"].get("firstName"), rec["name"].get("lastName")
            if fn and (fn.isupper() or fn.islower()): patch["firstName"] = proper(fn)
            if ln and (ln.isupper() or ln.islower()): patch["lastName"] = proper(ln)
        if patch:
            call("PATCH", f"/candidates/{cid}", patch); res["contacts_added"] = sorted(k for k in patch if k != "mainContact")
        # CV for merged records that have none
        if r["action"] == "merge" and cvs:
            att = call("GET", "/attachments?" + urllib.parse.urlencode({"candidateId": cid})).get("items", [])
            if not att:
                body, ct = multipart("files", os.path.basename(cvs[0]), open(cvs[0], "rb").read(), {"type": "CV"})
                up = call("POST", "/attachments/temporary?type=CV", raw=body, ctype=ct)
                aid = (up[0] if isinstance(up, list) else (up.get("items") or up.get("attachments") or [up])[0])
                aid = aid.get("attachmentId") or aid.get("id")
                call("POST", "/attachments/temporary/assign", {"attachments": [{"id": aid, "type": "CV"}], "candidateIds": [cid]}); res["cv"] = "attached"
        # notes: one per conversation + one per pipeline
        existing = call("GET", "/notes?" + urllib.parse.urlencode({"candidateId": cid, "limit": 50})).get("items", []) if cid != "DRY" else []
        titles = {x.get("title") or "" for x in existing}
        learned = {}
        for i, n in enumerate(r["notes"]):
            s = sums.get((r["loxo_id"], i))
            if not s: res["issues"] += f" note {n['date']} not summarised;"; continue
            for k, v in (s.get("fields") or {}).items(): learned.setdefault(k, v)
            if s.get("skip") or not s.get("lines"): continue
            title = f"{n['date']} – {'call' if n['type'] in CALL_TYPES else 'Loxo'}"
            if title in titles: continue
            call("POST", "/notes", {"title": title, "content": "".join(f"<p>{html.escape(x)}</p>" for x in s["lines"][:5]),
                                    "links": [{"entityType": "candidate", "entityId": cid}]})
            titles.add(title); res["notes_added"] += 1
        for h in r["history"]:
            title = f"{h['last'] or h['first'] or r['last_activity']} – Loxo pipeline"
            line = f"{h['client'] or 'Unknown client'} – {h['role']}: reached \"{h['stage_reached']}\""
            if h["first"]: line += f" ({h['first']} to {h['last']})"
            if any(line[:60] in (x.get("content") or "") for x in existing): continue
            call("POST", "/notes", {"title": title, "content": f"<p>{html.escape(line)}.</p><p>Job status in Loxo: {html.escape(str(h['job_status']))}.</p>",
                                    "links": [{"entityType": "candidate", "entityId": cid}]})
            res["pipeline_notes"] += 1
        # field values: Loxo profile first, then what the notes state
        fields = dict(r["fields"])
        for k, v in learned.items(): fields.setdefault(k, v)
        ex = {}
        for a in rec.get("customAttributes") or []:
            v = a.get("value") or {}
            ex[a["attributeDefinitionId"]] = v.get("select") or v.get("multiSelect") or v.get("number") or v.get("date") or v.get("text")
        at, rej = attrs(fields, ex)
        if at: call("PUT", f"/custom-attributes/candidates/{cid}/values/_bulk", {"attributes": at}); res["fields"] = len(at)
        if rej: res["issues"] += " rejected: " + "; ".join(rej)
        res["status"] = "ok"
    except Exception as e:
        res["status"] = "error"; res["issues"] += f" {e}"
    log.write(json.dumps(res) + "\n"); log.flush()
    print(json.dumps(res)[:260])
