#!/usr/bin/env python3
"""normalize_findings.py — optional helper for the food-radar-tlv skill.

Normalizes Hebrew/English place names, cities, and status values, then fuzzy-deduplicates
findings that refer to the same place. Pure standard library; runs on Python 3.9+.

The skill works without this script — it is a convenience for deterministic normalize + dedupe.
It never invents data: it only reshapes/merges what you pass in.

Usage:
    python3 normalize_findings.py --input findings.json
    cat findings.json | python3 normalize_findings.py
    python3 normalize_findings.py --input findings.json --output normalized.json --threshold 0.86

Input: a JSON list of findings, or {"findings": [...]}. Each finding is a dict with at least a
"name". See ../output-schema.md for the full shape.

Output: {"findings": [...]} with normalized fields and merged duplicates, plus a "normalized_name"
on each. Hebrew is preserved (ensure_ascii=False).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher

# --- vocab maps -------------------------------------------------------------

CITY_VARIANTS = {
    "Tel Aviv-Yafo": ["tel aviv-yafo", "tel aviv yafo", "tel aviv", "tlv",
                       "תל אביב-יפו", "תל אביב", "ת\"א", "תא",
                       "yafo", "jaffa", "יפו"],
    "Ramat Gan": ["ramat gan", "רמת גן"],
    "Givatayim": ["givatayim", "גבעתיים"],
    "Herzliya": ["herzliya", "הרצליה"],
    "Ramat HaSharon": ["ramat hasharon", "רמת השרון"],
    "Holon": ["holon", "חולון"],
    "Bat Yam": ["bat yam", "בת ים"],
    "Bnei Brak": ["bnei brak", "בני ברק"],
    "Petah Tikva": ["petah tikva", "petach tikva", "פתח תקווה", "פתח תקוה"],
    "Rishon LeZion": ["rishon lezion", "rishon le zion", "ראשון לציון"],
    "Ra'anana": ["ra'anana", "raanana", "רעננה"],
    "Kfar Saba": ["kfar saba", "כפר סבא"],
    "Hod HaSharon": ["hod hasharon", "הוד השרון"],
}

STATUS_VARIANTS = {
    "opened": ["opened", "open", "now open", "נפתח", "נפתחה", "כבר פתוח"],
    "opening_soon": ["opening soon", "coming soon", "opening_soon",
                     "פתיחה בקרוב", "לפני פתיחה", "בקרוב"],
    "soft_opening": ["soft opening", "soft launch", "soft_opening",
                     "הרצה", "בהרצה", "סופט לאנץ", "סופט לאנץ׳", "סופט לאנצ'"],
    "pop_up": ["pop-up", "pop up", "popup", "pop_up", "פופ אפ", "פופאפ", "פופ-אפ"],
    "event": ["event", "אירוע", "ערב חד פעמי", "ארוחת שף"],
    "hiring_signal": ["hiring", "hiring signal", "hiring_signal",
                      "דרושים", "דרוש", "דרושה", "צוות הקמה"],
    "rumor": ["rumor", "rumour", "שמועה", "מדובר"],
}

TYPE_VARIANTS = {
    "restaurant": ["restaurant", "מסעדה", "מסעדת שף", "bistro"],
    "cafe": ["cafe", "café", "coffee shop", "coffeeshop", "בית קפה", "קפה"],
    "bakery": ["bakery", "מאפייה", "מאפיה"],
    "bar": ["bar", "wine bar", "cocktail bar", "בר", "בר יין"],
    "pop-up": ["pop-up", "popup", "pop up", "פופ אפ", "פופאפ"],
    "event": ["event", "אירוע"],
}

# generic words removed when building the dedupe "core" of a name
GENERIC_TOKENS = {
    "restaurant", "cafe", "café", "coffee", "shop", "bakery", "bar", "kitchen",
    "bistro", "the", "a", "מסעדה", "מסעדת", "בית", "קפה", "מאפייה", "מאפיה",
    "בר", "של", "שף",
}

_HEB_PUNCT = "׳״־"          # geresh, gershayim, maqaf
_PUNCT_RE = re.compile(r"[^\w֐-׿]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


# --- normalization ----------------------------------------------------------

def normalize_text(value: str) -> str:
    """Lowercase, unicode-normalize, strip Hebrew/Latin punctuation, collapse spaces."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    for ch in _HEB_PUNCT:
        text = text.replace(ch, "")
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_name(name: str) -> str:
    return normalize_text(name)


def name_core(name: str) -> str:
    """Normalized name with generic type tokens dropped, for looser matching."""
    tokens = [t for t in normalize_text(name).split() if t not in GENERIC_TOKENS]
    return " ".join(tokens) if tokens else normalize_text(name)


def _map_value(value: str, table: dict) -> str:
    """Return the canonical key whose variant matches `value` (normalized), else `value`.

    Matching is whole-word (regex \\b) so e.g. the `opened` variant "open" does NOT match
    inside "opening", which would otherwise mis-map "soft opening" -> "opened".
    """
    if not value:
        return value
    norm = normalize_text(value)
    for canonical, variants in table.items():
        if norm == normalize_text(canonical):
            return canonical
        for variant in variants:
            v = normalize_text(variant)
            if not v:
                continue
            if norm == v or re.search(r"\b%s\b" % re.escape(v), norm):
                return canonical
    return value


def normalize_city(value: str) -> str:
    return _map_value(value, CITY_VARIANTS)


def normalize_status(value: str) -> str:
    return _map_value(value, STATUS_VARIANTS)


def normalize_type(value: str) -> str:
    mapped = _map_value(value, TYPE_VARIANTS)
    return mapped if mapped != value else (value or "unknown")


# --- dedupe / merge ---------------------------------------------------------

def similar(a: str, b: str, threshold: float) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if (a in b or b in a) and min(len(a), len(b)) >= 4:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _uniq(seq):
    seen, out = set(), []
    for item in seq:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else item
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def merge_findings(group: list) -> dict:
    """Merge a cluster of findings about the same place into one record."""
    base = dict(group[0])
    names, proofs, sources, signals = [], [], [], []
    confidences, first_seen, last_seen = [], [], []
    for f in group:
        if f.get("name"):
            names.append(f["name"])
        names.extend(f.get("original_names", []) or [])
        proofs.extend(f.get("proof", []) or [])
        sources.extend(f.get("source_names", []) or [])
        signals.extend(f.get("signal_types", []) or [])
        if isinstance(f.get("confidence"), int):
            confidences.append(f["confidence"])
        if f.get("first_seen_at"):
            first_seen.append(f["first_seen_at"])
        if f.get("last_seen_at"):
            last_seen.append(f["last_seen_at"])
    # proofs carry their own source_name; also collect bare source names
    sources.extend([p.get("source_name") for p in proofs if isinstance(p, dict) and p.get("source_name")])

    base["normalized_name"] = normalize_name(base.get("name", ""))
    base["original_names"] = _uniq([n for n in names if n])
    base["type"] = normalize_type(base.get("type", ""))
    base["city"] = normalize_city(base.get("city", base.get("area", "")))
    base["status"] = normalize_status(base.get("status", ""))
    base["proof"] = _uniq(proofs)
    base["source_names"] = _uniq([s for s in sources if s])
    base["signal_types"] = _uniq([s for s in signals if s])
    if confidences:
        base["confidence"] = max(confidences)
    if first_seen:
        base["first_seen_at"] = min(first_seen)
    if last_seen:
        base["last_seen_at"] = max(last_seen)
    return base


def _finding_urls(f: dict) -> set:
    urls = set(f.get("proof_urls", []) or [])
    for p in f.get("proof", []) or []:
        if isinstance(p, dict) and p.get("url"):
            urls.add(p["url"])
    return urls


def dedupe(findings: list, threshold: float) -> list:
    """Cluster findings about the same place, then merge each cluster.

    A finding joins a cluster if it shares a proof URL with it (a strong cross-language signal)
    or its normalized name is similar. NOTE: pure-stdlib matching cannot transliterate Hebrew<->
    English (e.g. "Bua Bakery" vs "מאפיית בועה"); rely on a shared proof URL for those, or merge
    them in the model's reasoning during the run.
    """
    clusters: list = []
    for f in findings:
        core = name_core(f.get("name", ""))
        norm = normalize_name(f.get("name", ""))
        urls = _finding_urls(f)
        placed = False
        for cluster in clusters:
            if ((urls and urls & cluster["urls"])
                    or similar(norm, cluster["norm"], threshold)
                    or similar(core, cluster["core"], threshold)):
                cluster["items"].append(f)
                cluster["urls"] |= urls
                placed = True
                break
        if not placed:
            clusters.append({"norm": norm, "core": core, "urls": urls, "items": [f]})
    return [merge_findings(c["items"]) for c in clusters]


# --- io ---------------------------------------------------------------------

def load_findings(path: str) -> list:
    raw = sys.stdin.read() if path in (None, "-") else open(path, "r", encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("findings", [])
    if not isinstance(data, list):
        raise ValueError("input must be a JSON list of findings or {\"findings\": [...]}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize + dedupe food-radar-tlv findings.")
    ap.add_argument("--input", "-i", default="-", help="findings JSON file (default: stdin)")
    ap.add_argument("--output", "-o", default="-", help="output JSON file (default: stdout)")
    ap.add_argument("--threshold", "-t", type=float, default=0.86,
                    help="fuzzy match ratio for dedupe (0-1, default 0.86)")
    args = ap.parse_args()

    findings = load_findings(args.input)
    result = {"findings": dedupe(findings, args.threshold)}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output in (None, "-"):
        print(text)
    else:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    sys.stderr.write("normalized %d finding(s) into %d record(s)\n"
                     % (len(findings), len(result["findings"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
