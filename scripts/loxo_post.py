#!/usr/bin/env python3
"""Post-step for imported Loxo people (state/loxo/import_log.jsonl, status ok). No AI.
1. Contacts from the Loxo CV file (PDF text + link annotations, or DOCX text + hyperlinks): add any LinkedIn, email or
   phone missing in Spott (send full merged lists, keep the primary, never delete).
2. Function / Seniority / Segment from the reviewed title mapping (scripts/title_map.py + state/title_overrides.csv), only
   where empty; Function, Segment and Work rights marked "Unknown" where nothing is known (Nav's standard).
3. Source = "Loxo import" on created records, once that option exists in Spott.
Log: state/loxo/post_log.jsonl (resumable)."""
import json, os, re, io, csv, sys, time, zipfile, urllib.request, html
sys.path.insert(0, os.path.dirname(__file__))
import title_map as TM
from pypdf import PdfReader
S = os.path.join(os.path.dirname(__file__), "..", "state"); L = os.path.join(S, "loxo")
API = "https://api.gospott.com"
def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"})
    for a in range(5):
        try:
            r = urllib.request.urlopen(req, timeout=90).read(); time.sleep(0.3); return json.loads(r) if r else {}
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and a < 4: time.sleep(2 ** a + 1); continue
            raise RuntimeError(f"{method} {path} -> {e.code} {e.read()[:200].decode(errors='ignore')}")
CC = {"France": "33", "Germany": "49", "United Kingdom": "44", "UK": "44", "Netherlands": "31", "Sweden": "46", "Spain": "34",
      "Italy": "39", "Belgium": "32", "Switzerland": "41", "Austria": "43", "Portugal": "351", "Ireland": "353", "Denmark": "45"}
def e164(p, country=None):
    d = re.sub(r"[^\d+]", "", p or "")
    if d.startswith("00"): d = "+" + d[2:]
    if not d.startswith("+") and d.startswith("0") and CC.get(country or ""): d = "+" + CC[country] + d[1:]
    return d if d.startswith("+") and 10 <= len(d) <= 16 else None
LI = re.compile(r"linkedin\.com/in/([A-Za-z0-9\-_%]+)", re.I)
EM = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PH = re.compile(r"(?:\+|00)\d[\d\s().\-]{7,16}\d")
def cv_text(path):
    blob = open(path, "rb").read(); txt, links = "", []
    try:
        if blob[:4] == b"%PDF":
            pdf = PdfReader(io.BytesIO(blob))
            for pg in pdf.pages[:5]:
                try: txt += (pg.extract_text() or "") + "\n"
                except Exception: pass
                for a in (pg.get("/Annots") or []):
                    try:
                        u = a.get_object().get("/A", {}).get("/URI")
                        if u: links.append(str(u))
                    except Exception: pass
        elif blob[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(blob))
            txt = html.unescape(re.sub(r"<[^>]+>", " ", z.read("word/document.xml").decode("utf8", "ignore")))
            if "word/_rels/document.xml.rels" in z.namelist():
                links = re.findall(r'Target="([^"]+)"', z.read("word/_rels/document.xml.rels").decode("utf8", "ignore"))
    except Exception: pass
    return txt, links
defs = {d["label"]: d for d in sorted(json.load(open(os.path.join(S, "custom_fields.json")))["custom_fields_candidate"]["items"], key=lambda d: d.get("createdAt") or "")}
over = {r["title"]: r for r in csv.DictReader(open(os.path.join(S, "title_overrides.csv")))}
def mapt(title):
    if not title: return "Unknown", "Unknown", []
    if title in over: o = over[title]; return o["function"], o["seniority"], [x for x in o["segment"].split("|") if x]
    t = title.lower(); f = TM.fn(t); s = TM.sen(t, f)
    return f, s, (TM.seg(t) if f in ("AE", "Founding AE", "SDR/BDR", "AM/CSM", "Sales Engineer", "Sales Leader") else [])
plan = {json.loads(l)["loxo_id"]: json.loads(l) for l in open(os.path.join(L, "plan.jsonl"))}
logp = os.path.join(L, "post_log.jsonl")
done = {json.loads(l)["loxo_id"] for l in open(logp) if json.loads(l)["status"] == "ok"} if os.path.exists(logp) else set()
log = open(logp, "a")
src_ok = "Loxo import" in ((defs.get("Source") or {}).get("definition") or {}).get("options", [])
import glob as _g
for l in [x for lf in sorted(_g.glob(os.path.join(L, "import_log*.jsonl"))) if "dry" not in lf for x in open(lf)]:
    imp = json.loads(l)
    if imp["status"] != "ok" or imp["loxo_id"] in done: continue
    r = plan[imp["loxo_id"]]; cid = imp["candidate_id"]
    res = {"loxo_id": r["loxo_id"], "candidate_id": cid, "status": None, "cv_contacts": [], "fields": [], "issues": ""}
    try:
        rec = call("GET", f"/candidates/{cid}")
        # 1. CV contacts
        li, ems, phs = set(), set(), set()
        for f in r["cv_files"]:
            txt, links = cv_text(os.path.join(L, "cvs", f)); hay = txt + "\n" + "\n".join(links)
            li |= {m.group(1).lower().rstrip("/") for m in LI.finditer(hay)}
            ems |= {m.group(0).lower().rstrip(".") for m in EM.finditer(hay.replace("mailto:", " "))}
            phs |= {p for p in (e164(m.group(0), r.get("country")) for m in PH.finditer(txt + "\n" + "\n".join(x[4:] for x in links if x.startswith("tel:")))) if p}
        li = {x for x in li if not x.endswith("-") and not any(o != x and o.startswith(x) for o in li)}   # drop line-wrapped fragments
        patch = {}
        have_e = [e["email"].lower() for e in rec["emails"]["emails"]]
        new_e = sorted(e for e in ems if e not in have_e)[:2]
        if new_e:
            patch["emails"] = [{"email": e["email"], "purpose": e.get("purpose"), "isPrimary": e.get("isPrimary", False)} for e in rec["emails"]["emails"]] + \
                              [{"email": e, "purpose": "personal", "isPrimary": not have_e and i == 0} for i, e in enumerate(new_e)]
        have_p = [re.sub(r"\D", "", p["phoneNumber"])[-9:] for p in rec["phoneNumbers"]["phoneNumbers"]]
        new_p = sorted(p for p in phs if re.sub(r"\D", "", p)[-9:] not in have_p)[:2]
        if new_p:
            patch["phoneNumbers"] = [{"phoneNumber": p["phoneNumber"], "purpose": p.get("purpose") or "personal", "isPrimary": p.get("isPrimary", False)} for p in rec["phoneNumbers"]["phoneNumbers"]] + \
                                    [{"phoneNumber": p, "purpose": "personal", "isPrimary": not have_p and i == 0} for i, p in enumerate(new_p)]
        if len(li) == 1 and not any(s.get("type") == "LINKEDIN" for s in rec["socialMedia"]["socialMedia"]):
            patch["socialMedia"] = [{"url": s["url"], "type": s["type"]} for s in rec["socialMedia"]["socialMedia"]] + [{"url": "https://www.linkedin.com/in/" + li.pop(), "type": "LINKEDIN"}]
        elif len(li) > 1: res["issues"] += f" several LinkedIn URLs in CV {sorted(li)};"
        if patch:
            try: call("PATCH", f"/candidates/{cid}", patch); res["cv_contacts"] = sorted(patch)
            except RuntimeError as e: res["issues"] += f" contacts not added: {str(e)[:120]};"
        # 2. Function / Seniority / Segment / Unknowns
        ex = {a["label"]: a.get("value") or {} for a in rec.get("customAttributes") or []}
        def empty(lab): v = ex.get(lab) or {}; return not (v.get("select") or v.get("multiSelect"))
        f, s, g = mapt((rec.get("latestWorkExperience") or {}).get("title"))
        at = []
        if empty("Function"): at.append({"attributeDefinitionId": defs["Function"]["id"], "value": {"viewType": "customSelect", "select": f}})
        if empty("Seniority") and s in defs["Seniority"]["definition"]["options"]: at.append({"attributeDefinitionId": defs["Seniority"]["id"], "value": {"viewType": "customSelect", "select": s}})
        if empty("Segment sold to"): at.append({"attributeDefinitionId": defs["Segment sold to"]["id"], "value": {"viewType": "customMultiSelect", "multiSelect": g or ["Unknown"]}})
        if empty("Work rights"): at.append({"attributeDefinitionId": defs["Work rights"]["id"], "value": {"viewType": "customSelect", "select": "Unknown"}})
        if src_ok and imp["action"] == "create" and empty("Source"):
            at.append({"attributeDefinitionId": defs["Source"]["id"], "value": {"viewType": "customSelect", "select": "Loxo import"}})
        if at:
            call("PUT", f"/custom-attributes/candidates/{cid}/values/_bulk", {"attributes": at})
            res["fields"] = [a["value"].get("select") or a["value"].get("multiSelect") for a in at]
        res["status"] = "ok"
    except Exception as e:
        res["status"] = "error"; res["issues"] += f" {e}"
    log.write(json.dumps(res) + "\n"); log.flush()
print("post-step done; Source written:", src_ok)
