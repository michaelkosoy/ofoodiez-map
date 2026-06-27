#!/usr/bin/env python3
"""update_seen_records.py — optional helper for the food-radar-tlv skill.

Merges a batch of new findings into seen-records.json: marks brand-new entries, detects meaningful
updates to already-seen ones, accumulates proof URLs / sources / signal types, and updates timestamps.
Pure standard library; runs on Python 3.9+. The skill works without it.

It reuses the normalization helpers from normalize_findings.py (same folder).

Usage:
    python3 update_seen_records.py --seen seen-records.json --findings new_findings.json
    python3 update_seen_records.py --seen seen-records.json --findings new.json --output seen-records.json
    python3 update_seen_records.py --findings new.json            # seen file created if missing

Findings JSON: a list of findings (or {"findings": [...]}) in the shape from ../output-schema.md.
Prints a JSON report to stdout: {"new": [...], "updated": [...], "to_report": [...]} (the records
that should be printed this run). Writes the merged seen-records to --output (default = --seen).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from normalize_findings import (  # noqa: E402
    dedupe, name_core, normalize_city, normalize_name, normalize_status,
    normalize_type, similar, _uniq,
)


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def load_json(path: str, default):
    if not path or not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def proof_urls_of(finding: dict) -> list:
    urls = list(finding.get("proof_urls", []) or [])
    for p in finding.get("proof", []) or []:
        if isinstance(p, dict) and p.get("url"):
            urls.append(p["url"])
    return _uniq([u for u in urls if u])


def source_names_of(finding: dict) -> list:
    names = list(finding.get("source_names", []) or [])
    for p in finding.get("proof", []) or []:
        if isinstance(p, dict) and p.get("source_name"):
            names.append(p["source_name"])
    return _uniq([n for n in names if n])


def find_match(records: list, finding: dict, threshold: float):
    norm = normalize_name(finding.get("name", "")) or finding.get("normalized_name", "")
    core = name_core(finding.get("name", "") or norm)
    for rec in records:
        rnorm = rec.get("normalized_name", "")
        if similar(norm, rnorm, threshold) or similar(core, name_core(rnorm), threshold):
            return rec
    return None


def new_record(finding: dict, now: str) -> dict:
    norm = normalize_name(finding.get("name", "")) or finding.get("normalized_name", "")
    return {
        "normalized_name": norm,
        "original_names": _uniq([finding.get("name")] + list(finding.get("original_names", []) or [])),
        "type": normalize_type(finding.get("type", "")),
        "area": finding.get("area", ""),
        "city": normalize_city(finding.get("city", finding.get("area", ""))),
        "status": normalize_status(finding.get("status", "")),
        "first_seen_at": finding.get("first_seen_at") or now,
        "last_seen_at": now,
        "proof_urls": proof_urls_of(finding),
        "source_names": source_names_of(finding),
        "confidence": finding.get("confidence") if isinstance(finding.get("confidence"), int) else 1,
        "signal_types": _uniq(finding.get("signal_types", []) or []),
        "notes": finding.get("notes", ""),
        "last_output_at": None,
    }


def merge_into(rec: dict, finding: dict, now: str):
    """Update an existing record; return list of reasons it is a meaningful update (empty = none)."""
    reasons = []

    new_urls = [u for u in proof_urls_of(finding) if u not in rec.get("proof_urls", [])]
    if new_urls:
        reasons.append("new_proof_url")
        rec["proof_urls"] = _uniq(list(rec.get("proof_urls", [])) + new_urls)

    new_sources = [s for s in source_names_of(finding) if s not in rec.get("source_names", [])]
    if new_sources:
        reasons.append("new_source")
        rec["source_names"] = _uniq(list(rec.get("source_names", [])) + new_sources)

    new_status = normalize_status(finding.get("status", "")) if finding.get("status") else ""
    if new_status and new_status != rec.get("status"):
        reasons.append("status_changed")
        rec["status"] = new_status

    fc = finding.get("confidence")
    if isinstance(fc, int) and fc != rec.get("confidence"):
        reasons.append("confidence_changed")
        rec["confidence"] = max(fc, rec.get("confidence", 1))

    # accumulate the rest regardless of "meaningful"
    rec["signal_types"] = _uniq(list(rec.get("signal_types", [])) + list(finding.get("signal_types", []) or []))
    if finding.get("name"):
        rec["original_names"] = _uniq(list(rec.get("original_names", [])) + [finding["name"]]
                                      + list(finding.get("original_names", []) or []))
    if finding.get("notes"):
        rec["notes"] = finding["notes"]
    rec["last_seen_at"] = now
    return reasons


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge new findings into seen-records.json.")
    ap.add_argument("--seen", "-s", default="seen-records.json", help="path to seen-records.json")
    ap.add_argument("--findings", "-f", required=True, help="path to new findings JSON")
    ap.add_argument("--output", "-o", default=None, help="output path (default: overwrite --seen)")
    ap.add_argument("--threshold", "-t", type=float, default=0.86, help="fuzzy match ratio")
    ap.add_argument("--now", default=None, help="ISO timestamp override (default: now)")
    args = ap.parse_args()

    now = args.now or now_iso()
    store = load_json(args.seen, {"version": 1, "records": []})
    records = store.setdefault("records", [])

    raw = load_json(args.findings, [])
    if isinstance(raw, dict):
        raw = raw.get("findings", [])
    findings = dedupe(raw, args.threshold)  # normalize + dedupe the incoming batch first

    report = {"new": [], "updated": [], "to_report": []}
    for finding in findings:
        match = find_match(records, finding, args.threshold)
        if match is None:
            rec = new_record(finding, now)
            rec["last_output_at"] = now
            records.append(rec)
            report["new"].append(rec["normalized_name"])
            report["to_report"].append(rec)
        else:
            reasons = merge_into(match, finding, now)
            if reasons:
                match["last_output_at"] = now
                report["updated"].append({"normalized_name": match["normalized_name"], "reasons": reasons})
                report["to_report"].append(match)

    out_path = args.output or args.seen
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(store, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.stderr.write("seen-records: %d new, %d meaningfully updated, %d total records -> %s\n"
                     % (len(report["new"]), len(report["updated"]), len(records), out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
