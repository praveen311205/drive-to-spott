#!/usr/bin/env python3
"""Classify a Drive inventory (JSONL of Drive file metadata) and group files by person.

Usage: classify.py <inv_cv.jsonl> <inv_mig.jsonl> <out_dir>

Outputs in <out_dir>:
  manifest.csv      one row per file: id, title, mime, folder, category, person_key, action
  people.jsonl      one row per person: {key, name, cv:[...], notes:[...], calls:[...]}
  review.csv        files that need a human / LLM decision (ambiguous)
Categories:
  cv               a resume / CV file (pdf, docx, doc, gdoc)
  candidate_notes  a Google Doc titled with a person's name (screening notes)
  call_notes       Gemini "Notes by Gemini" / meeting notes / recordings (need content check)
  hold_old         inside the "To check - older than 2y" folder (not imported, listed for review)
  empty            near-empty Google Docs (<=1024 bytes)
  admin            invoices, contracts, T&Cs, receipts, forms, JDs, internal docs
  client_doc       docs about a client/company contact ("Name - Company"), not a candidate
  other            anything else (reviewed manually)
"""
import csv, json, os, re, sys, unicodedata
from collections import defaultdict

CV_FOLDER = "1tr11nbhbyUkae5uGzcRzIOoRIrsjClRd"
MIG_FOLDER = "1OEyvB9wtaUDq8X45KTvxemXGPcF5HdAv"
OLD_FOLDER_TITLE = "To check - older than 2y"

FOLDER = "application/vnd.google-apps.folder"
GDOC = "application/vnd.google-apps.document"
CV_MIMES = {"application/pdf", GDOC, "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

ADMIN_RX = re.compile(r"(invoice|factuur|receipt|terms ?& ?conditions|t&cs|agreement|contract|rsvp|"
                      r"loonheffing|speaker guide|\bjd\b|job description|segmentation|landing page|"
                      r"project proposal|territory planning|90-day plan|goals|resources|outbound|"
                      r"case study|technical exercise|pulling money|priorities|kick ?off|software inventory|"
                      r"internship|compensation|\bicp\b|offer|tracker|hive pod|b2venture)", re.I)
CV_WORD_RX = re.compile(r"\b(cv|resume|résumé|curriculum vitae)\b", re.I)
CALL_RX = re.compile(r"(notes by gemini|^notes\b|meeting|intro:|catch up|follow-up|call\b|\.mp4$)", re.I)

STRIP_RX = [
    r"\.(pdf|docx?|txt)$", r"\.(pdf|docx?)", r"\(\d+\)", r"\b(cv|resume|résumé|curriculum vitae)\b",
    r"\b(docx?|pdf|final|updated|newest version|new|english|eng|one page|full|v\d+|full skills)\b",
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", r"\b(19|20)\d{2}\b", r"\b\d{3,}\b",
    r"\d+(st|nd|rd|th)\b", r"[_\-–,\[\]().']", r"\s+",
]


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def name_from_title(title):
    t = re.sub(r"[_.]", " ", re.sub(r"\.(pdf|docx?|txt)$", "", title, flags=re.I))
    t = re.sub(r"\s-\s.*$", "", t) if re.search(r"\s-\s(cv|resume)", t, re.I) else t
    for rx in STRIP_RX:
        t = re.sub(rx, " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def person_key(name):
    toks = [w for w in norm(name).split() if len(w) > 1]
    if len(toks) < 2:
        return None
    return toks[0] + " " + toks[-1]


def main(cv_path, mig_path, out):
    os.makedirs(out, exist_ok=True)
    files = {}
    for path, root in ((cv_path, CV_FOLDER), (mig_path, MIG_FOLDER)):
        for line in open(path):
            f = json.loads(line)
            f["_root"] = root
            files.setdefault(f["id"], f)
    old_folder_ids = {"1JAfDfhUjmyVVe1_rRA-G5i82wH5PmOuU"} | {f["id"] for f in files.values() if f["mimeType"] == FOLDER and f["title"] == OLD_FOLDER_TITLE}

    rows, people, review = [], defaultdict(lambda: {"cv": [], "notes": [], "calls": [], "names": set()}), []
    for f in files.values():
        mime, title = f["mimeType"], f["title"].strip()
        size = int(f.get("fileSize") or 0)
        cat, key = "other", None
        if mime == FOLDER:
            continue
        if f.get("parentId") in old_folder_ids:
            cat = "hold_old"
        elif mime.startswith("video/") or "notes by gemini" in title.lower() or CALL_RX.search(title) and mime == GDOC:
            cat = "call_notes"
        elif mime == GDOC and size <= 1024:
            cat = "empty"
        elif ADMIN_RX.search(title) and not CV_WORD_RX.search(title):
            cat = "admin"
        elif mime in CV_MIMES and (f["_root"] == CV_FOLDER or CV_WORD_RX.search(title) or mime != GDOC):
            cat = "cv"
        elif mime == GDOC and title.lower().startswith("untitled"):
            cat = "other"  # untitled with content: content check needed
        elif mime == GDOC and re.search(r"\s[-–]\s|\(", title):
            cat = "client_doc"  # "Alex Kiely - Choco", "Dave (CRO) - Choco"
        elif mime == GDOC and 2 <= len(title.split()) <= 4 and not re.search(r"[:,]|^(reference|senior|to the)\b|\b(s\.l\.|ltd|gmbh|bv)\b", title, re.I):
            cat = "candidate_notes"
        if cat in ("cv", "candidate_notes", "hold_old"):
            nm = name_from_title(title) if cat != "candidate_notes" else title
            key = person_key(nm)
            if key:
                p = people[key]
                p["names"].add(nm)
                (p["cv"] if cat in ("cv", "hold_old") else p["notes"]).append(
                    {"id": f["id"], "title": title, "mime": mime, "size": size,
                     "modified": f.get("modifiedTime"), "hold": cat == "hold_old"})
            else:
                review.append([f["id"], title, mime, cat, "could not derive a person name from title"])
        if cat in ("other", "call_notes", "client_doc"):
            review.append([f["id"], title, mime, cat, "needs content check"])
        rows.append([f["id"], title, mime, "cv_folder" if f["_root"] == CV_FOLDER else "migration", cat, key or ""])

    with open(os.path.join(out, "manifest.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["file_id", "title", "mime", "folder", "category", "person_key"]); w.writerows(rows)
    with open(os.path.join(out, "review.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["file_id", "title", "mime", "category", "reason"]); w.writerows(review)
    with open(os.path.join(out, "people.jsonl"), "w") as fh:
        for k, p in sorted(people.items()):
            live = [c for c in p["cv"] if not c["hold"]]
            # primary CV: newest modified, then largest; PDFs/DOCX preferred over GDocs
            live.sort(key=lambda c: (c["mime"] != GDOC, c["modified"] or "", c["size"]), reverse=True)
            rec = {"key": k, "name": max(p["names"], key=len), "primary_cv": live[0] if live else None,
                   "other_cvs": live[1:], "held_cvs": [c for c in p["cv"] if c["hold"]], "notes": p["notes"]}
            fh.write(json.dumps(rec) + "\n")

    from collections import Counter
    print("files:", len(rows)); print(Counter(r[4] for r in rows))
    print("people:", len(people), "| with live CV:",
          sum(1 for p in people.values() if any(not c["hold"] for c in p["cv"])),
          "| notes-only:", sum(1 for p in people.values() if not p["cv"] and p["notes"]),
          "| hold-only:", sum(1 for p in people.values() if p["cv"] and all(c["hold"] for c in p["cv"])))
    print("review:", len(review))


if __name__ == "__main__":
    main(*sys.argv[1:4])
