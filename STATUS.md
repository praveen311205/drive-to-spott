# Migration status (handoff between sessions — no candidate data here; details live in state/, gitignored)

## Done
- Inventory + classification (classify.py month-regex bug fixed). Batches in batches/.
- 612 CVs from "To import (CVs)" bulk-uploaded by Praveen in the Spott app (3 failed to parse).
- CV batches cv_00–cv_02 and cv_05 finished; cv_03, cv_04, cv_06 partially done, then STOPPED by decision:
  CV-derived fields (Function, Seniority, Segment, Sector) will come from Spott AI fill instead.
- Drive triage of untitled / call-notes docs → state/review_decisions.jsonl. Metaview search → state/metaview_found.jsonl
  (only one Metaview summary exists in Drive; the rest live in the Metaview app).
- Duplicate pairs found so far → state/merge_list.tsv (merge by hand in Spott; the API can't merge).

## In progress
- Screening-note batches screen_00..02 (state/screen_prompt.txt): one note + staged conversation fields per person.
  Older than 24 months and not in Spott → status check_with_navin (create nothing).

## Next
1. Attach the candidate call notes / matched screening docs from state/review_decisions.jsonl (match_confidence high);
   unnamed + low-confidence → review list for Navin. Satispay + Zimpler candidate lists → lookup/create.
2. Metaview: needs an export or the Metaview↔Spott integration (no connector in this environment).
3. Bulk fields: refresh state/custom_fields.json, `python3 plan_fields.py --include-sector`, then apply ONLY the
   conversation fields (Base, OTE, Currency, Notice period, Work setup, Work rights, Status, Source,
   Last contact date, Next step) if Spott AI fill owns Function/Seniority/Segment/Sector.
4. "Check with Navin" list for >24-month people (Sheet preferred over a Spott list), merge list, report.
