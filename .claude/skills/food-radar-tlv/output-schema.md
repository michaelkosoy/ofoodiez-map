# Output schema — food-radar-tlv

Two shapes: a **finding** (produced during a run) and a **seen-record** (persisted in
`seen-records.json`). Both are JSON. Dates use ISO-8601 where available; `null` when unknown.

---

## finding

```yaml
finding:
  name: string                      # as displayed
  normalized_name: string           # lowercased/transliterated key used for dedupe
  type: restaurant | cafe | bakery | bar | pop-up | event | unknown
  area: string                      # Tel Aviv neighborhood or city name
  city: string                      # Tel Aviv-Yafo | Ramat Gan | Givatayim | ... (see geography gate)
  status: opened | opening_soon | soft_opening | pop_up | event | hiring_signal | rumor
  why_found: string                 # one short reason
  proof:                            # >= 1 required; no proof => do not output
    - source_name: string
      url: string                   # must come from a real tool result — never invented
      date: string | null
      proof_sentence: string | null
  confidence: 1 | 2 | 3 | 4 | 5
  signal_types:
    - official_announcement
    - chef_hint
    - creator_mention
    - hiring_signal
    - tagged_location
    - pop_up_announcement
    - supplier_or_designer_hint
    - reservation_link_shared
    - event_page_shared
  notes: string                     # one short sentence only
  first_seen_at: string             # ISO datetime
  last_seen_at: string              # ISO datetime
```

---

## seen-record (persisted in `seen-records.json`)

```yaml
seen_record:
  normalized_name: string           # primary key
  original_names: [string]          # all surface forms seen (HE + EN + variants)
  type: string                      # same enum as finding.type
  area: string
  city: string
  status: string                    # same enum as finding.status
  first_seen_at: string             # ISO datetime — set once
  last_seen_at: string              # ISO datetime — updated each time the entity reappears
  proof_urls: [string]              # accumulated unique proof URLs
  source_names: [string]            # accumulated unique source names
  confidence: 1 | 2 | 3 | 4 | 5     # latest/best confidence
  signal_types: [string]            # accumulated unique signal types
  notes: string
  last_output_at: string | null     # ISO datetime the entity was last included in a printed report
```

File shape:

```json
{ "version": 1, "records": [ { /* seen_record */ } ] }
```

---

## Meaningful update (re-output an already-seen record only if one of these)

- official opening date found
- new reservation page found
- new event date added
- new media coverage
- new official social post
- new hiring signal that changes confidence
- location/address confirmed
- status changed (e.g. rumor / opening_soon → opened)
