# drive-to-spott

Migrates candidate data from the Google Drive folders Navin shared ("To import (CVs)", "Migration") into Spott,
following the GTM Talent record standard. Runs inside Claude Code; `.claude/settings.json` pre-approves exactly
the Drive-read and Spott tools the import needs (email, campaigns, deletes and Drive writes are denied).

## Pipeline
1. **Inventory** – list both folders via the Google Drive connector into `state/inv_cv.jsonl`, `state/inv_mig.jsonl`.
2. **Classify** – `python3 classify.py state/inv_cv.jsonl state/inv_mig.jsonl state/run` sorts files (cv, candidate_notes,
   call_notes, client_doc, admin, empty, hold_old) and groups them by person.
3. **Import** – batches of ~30 people, each run by an agent following `WORKER.md`: dedup by LinkedIn → email → name,
   import CV (`upload_cv.sh`) or update the existing record, fill contact gaps, one dated note per conversation,
   stage every field value to `state/profiles_<batch>.jsonl`. Resumable: finished people are skipped.
4. **Bulk fields** – `python3 plan_fields.py` validates staged values against Spott's field options and groups them
   into `spott_set_custom_field` calls of up to 100 records (`state/field_plan.json`); rejects go to a CSV.
5. **Report** – results files summarise created / updated / needs-review.

Candidate data (`state/`, `batches/`, downloaded CVs) is never committed.
