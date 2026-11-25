#!/usr/bin/env python3
"""Attach extracted screening/call notes to Spott candidates via the REST API (no AI, no prompts).

Input : state/attach_queue.jsonl  (built by build_attach_queue.py)
        state/spott_candidates.jsonl (fresh pull), state/custom_fields.json
Per item: match (given id -> LinkedIn -> email -> unique full name) -> create if missing and the conversation is
within 24 months (else check_with_navin) -> fill missing contacts -> one dated note (skipped if a note with that
date already exists) -> conversation field values.
Log   : state/attach_log.jsonl (resumable by key).  Usage: attach_notes.py [--dry] [--limit N]
"""
import json, os, re, sys, time, unicodedata, urllib.request, urllib.parse, html

S = os.path.join(os.path.dirname(__file__), "..", "state")
API = "https://api.gospott.com"
NAVIN = "user_3LKSME63LBqHEQAVSj1tyQJCgyf"
CUTOFF = "2024-11-25"          # 24 months before the migration
DRY = "--dry" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None


def call(method, path, body=None):
    if DRY and method != "GET":
        return {}
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"})
    for a in range(5):
        try:
            r = urllib.request.urlopen(req, timeout=60).read()
            time.sleep(0.25)
            if not r: return {}
            try: return json.loads(r)
            except ValueError:   # some endpoints answer with a bare id or several JSON values
                m = re.search(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", r)
                return {"id": m.group(0).decode()} if m else {"_raw": r[:200].decode(errors="ignore")}
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and a < 4:
                time.sleep(2 ** a + 1); continue
            raise RuntimeError(f"{method} {path} -> {e.code} {e.read()[:300].decode(errors='ignore')}")


def norm(s):
    return re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).strip()


def slug(u):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", u or "", re.I)
    return m.group(1).lower().rstrip("/") if m else None


def e164(p):
    d = re.sub(r"[^\d+]", "", p or "")
    if d.startswith("00"): d = "+" + d[2:]
    return d if d.startswith("+") and 9 <= len(d) <= 16 else None


C = [json.loads(l) for l in open(os.path.join(S, "spott_candidates.jsonl"))]
by_li, by_email, by_name = {}, {}, {}
for c in C:
    for u in c["linkedin"]:
        if slug(u): by_li.setdefault(slug(u), set()).add(c["id"])
    for e in c["emails"]: by_email.setdefault(e.lower(), set()).add(c["id"])
    n = norm(f"{c['first']} {c['last']}").split()
    if len(n) >= 2: by_name.setdefault(n[0] + " " + n[-1], set()).add(c["id"])
known_ids = {c["id"] for c in C}

defs = {}
for d in sorted(json.load(open(os.path.join(S, "custom_fields.json")))["custom_fields_candidate"]["items"],
                key=lambda d: d.get("createdAt") or ""):
    defs[d["label"]] = d
FMAP = {"base": "Base", "ote": "OTE", "currency": "Currency", "notice_period": "Notice period", "work_setup": "Work setup",
        "work_rights": "Work rights", "status": "Status", "next_step": "Next step", "languages": "Language",
        "function": "Function", "seniority": "Seniority", "segment": "Segment sold to", "sector": "Sector sold to"}
ALIAS = {"Sales leader": "Sales Leader", "Team lead": "Team Lead", "Swedish": "Nordic (Swedish/Danish/Norwegian)",
         "Danish": "Nordic (Swedish/Danish/Norwegian)", "Norwegian": "Nordic (Swedish/Danish/Norwegian)"}


def attrs_for(fields, last_contact, existing):
    out, rejects = [], []
    f = dict(fields or {})
    if last_contact: f["last_contact_date"] = last_contact
    for key, raw in f.items():
        label = FMAP.get(key) or ("Last contact date" if key == "last_contact_date" else None)
        if not label or raw in (None, "", [], "unknown", "Unknown"): continue
        d = defs.get(label)
        if not d: rejects.append(f"{key}: no field"); continue
        vt, opts = d["viewType"], (d.get("definition") or {}).get("options") or []
        if vt == "customSelect":
            v = ALIAS.get(raw, raw)
            if isinstance(v, str) and v.lower().startswith("other") and "Other" in opts: v = "Other"
            if v not in opts: rejects.append(f"{key}={raw}"); continue
            out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "select": v}})
        elif vt == "customMultiSelect":
            vals = [ALIAS.get(x, x) for x in (raw if isinstance(raw, list) else [raw])]
            good = [x for x in vals if x in opts]
            bad = [x for x in vals if x not in opts]
            if bad and label == "Language" and "Other" in opts: good.append("Other")
            elif bad: rejects.append(f"{key}={bad}")
            cur = [x for x in existing.get(d["id"], []) if x != "Unknown"]
            merged = cur + [x for x in good if x not in cur]
            if good: out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "multiSelect": merged}})
        elif vt == "customNumber":
            try: out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "number": float(raw)}})
            except (TypeError, ValueError): rejects.append(f"{key}={raw}")
        elif vt == "customDate":
            out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "date": str(raw)[:10]}})
        elif vt == "customText":
            out.append({"attributeDefinitionId": d["id"], "value": {"viewType": vt, "text": str(raw)}})
    return out, rejects


def match(it):
    if it.get("spott_candidate_id") in known_ids: return [it["spott_candidate_id"]], "given id"
    if slug(it.get("linkedin")) in by_li: return sorted(by_li[slug(it["linkedin"])]), "linkedin"
    for e in it.get("emails") or []:
        if e.lower() in by_email: return sorted(by_email[e.lower()]), "email"
    n = norm(f"{it.get('first_name')} {it.get('last_name')}").split()
    if len(n) >= 2 and n[0] + " " + n[-1] in by_name: return sorted(by_name[n[0] + " " + n[-1]]), "name"
    return [], None


logp = os.path.join(S, "attach_log_dry.jsonl" if DRY else "attach_log.jsonl")
done = set()
if os.path.exists(logp):
    for l in open(logp):
        r = json.loads(l)
        if r["status"] not in ("error",): done.add(r["key"])
log = open(logp, "a")
n = 0
for line in open(os.path.join(S, "attach_queue.jsonl")):
    it = json.loads(line)
    if it["key"] in done: continue
    if LIMIT and n >= LIMIT: break
    n += 1
    res = {"key": it["key"], "name": f"{it.get('first_name')} {it.get('last_name')}", "status": None, "candidate_id": None,
           "notes_added": 0, "contacts_added": [], "fields": 0, "issues": it.get("issues") or ""}
    try:
        if it.get("empty") or not it.get("note"):
            res["status"] = "skipped"; res["issues"] += " | empty doc"
        elif not it.get("first_name") or not it.get("last_name"):
            res["status"] = "unidentified"
        else:
            ids, how = match(it)
            date = it.get("conversation_date") or ""
            if it.get("force_uncertain"):
                res["status"] = "match_uncertain"; res["issues"] += f" | low-confidence match, candidates found: {ids}"
            elif len(ids) > 1 and how == "name":
                res["status"] = "match_uncertain"; res["issues"] += f" | {len(ids)} records named alike: {ids}"
            elif not ids and date and date < CUTOFF:
                res["status"] = "check_with_navin"; res["issues"] += f" | last conversation {date}"
            else:
                created = False
                if ids:
                    cid = sorted(ids)[0]
                    if len(ids) > 1: res["issues"] += f" | duplicates in Spott: {ids}"
                else:
                    body = {"firstName": it["first_name"], "lastName": it["last_name"], "mainContact": {"userId": NAVIN}}
                    em = [e for e in (it.get("emails") or []) if "@" in e]
                    if em: body["emails"] = [{"email": e, "purpose": "personal", "isPrimary": i == 0} for i, e in enumerate(em)]
                    ph = [p for p in map(e164, it.get("phones") or []) if p]
                    if ph: body["phoneNumbers"] = [{"phoneNumber": p, "purpose": "personal", "isPrimary": i == 0} for i, p in enumerate(ph)]
                    if slug(it.get("linkedin")): body["socialMedia"] = [{"url": "https://www.linkedin.com/in/" + slug(it["linkedin"]), "type": "LINKEDIN"}]
                    cid = call("POST", "/candidates", body).get("id", "DRY-NEW"); created = True
                res["candidate_id"] = cid
                rec = call("GET", f"/candidates/{cid}") if not cid.startswith("DRY") else {}
                # contacts: add only what's missing (arrays replace, so send the full merged list)
                if rec and not created:
                    patch = {}
                    have_e = [e["email"].lower() for e in rec["emails"]["emails"]]
                    new_e = [e for e in (it.get("emails") or []) if "@" in e and e.lower() not in have_e]
                    if new_e:
                        patch["emails"] = [{"email": e["email"], "purpose": e.get("purpose"), "isPrimary": e.get("isPrimary", False)} for e in rec["emails"]["emails"]] + \
                                          [{"email": e, "purpose": "personal", "isPrimary": not have_e and i == 0} for i, e in enumerate(new_e)]
                    have_p = [re.sub(r"\D", "", p["phoneNumber"])[-9:] for p in rec["phoneNumbers"]["phoneNumbers"]]
                    new_p = [p for p in map(e164, it.get("phones") or []) if p and re.sub(r"\D", "", p)[-9:] not in have_p]
                    if new_p:
                        patch["phoneNumbers"] = [{"phoneNumber": p["phoneNumber"], "purpose": p.get("purpose") or "personal", "isPrimary": p.get("isPrimary", False)} for p in rec["phoneNumbers"]["phoneNumbers"]] + \
                                                [{"phoneNumber": p, "purpose": "personal", "isPrimary": not have_p and i == 0} for i, p in enumerate(new_p)]
                    has_li = any(s.get("type") == "LINKEDIN" for s in rec["socialMedia"]["socialMedia"])
                    if slug(it.get("linkedin")) and not has_li:
                        patch["socialMedia"] = [{"url": s["url"], "type": s["type"]} for s in rec["socialMedia"]["socialMedia"]] + \
                                               [{"url": "https://www.linkedin.com/in/" + slug(it["linkedin"]), "type": "LINKEDIN"}]
                    if patch:
                        call("PATCH", f"/candidates/{cid}", patch); res["contacts_added"] = sorted(patch)
                # note (one per conversation)
                title = f"{date or 'undated'} – {it.get('source_label') or 'Doc'}"
                existing_notes = call("GET", "/notes?" + urllib.parse.urlencode({"candidateId": cid, "limit": 50})).get("items", []) if rec else []
                if any((x.get("title") or "").startswith(date) for x in existing_notes if date):
                    res["issues"] += " | note for this date already present"
                else:
                    content = "".join(f"<p>{html.escape(l)}</p>" for l in it["note"][:5])
                    call("POST", "/notes", {"title": title, "content": content, "links": [{"entityType": "candidate", "entityId": cid}]})
                    res["notes_added"] = 1
                # conversation field values
                existing = {a["attributeDefinitionId"]: (a.get("value") or {}).get("multiSelect") or [] for a in (rec.get("customAttributes") or [])}
                fields = dict(it.get("fields") or {})
                attrs, rej = attrs_for(fields, date or None, existing)
                if created:
                    attrs += [{"attributeDefinitionId": defs["Source"]["id"], "value": {"viewType": "customSelect", "select": "Drive import"}}]
                if attrs:
                    call("PUT", f"/custom-attributes/candidates/{cid}/values/_bulk", {"attributes": attrs}); res["fields"] = len(attrs)
                if rej: res["issues"] += " | rejected: " + "; ".join(rej)
                res["status"] = "created" if created else "updated"
                res["matched_on"] = how
    except Exception as e:
        res["status"] = "error"; res["issues"] += f" | {e}"
    print(json.dumps(res)[:300]) if DRY else None
    log.write(json.dumps(res) + "\n"); log.flush()
print("processed", n)
