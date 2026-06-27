# Search queries — food-radar-tlv

Always run **Hebrew and English**. Do not skip the Hebrew banks — they surface most local signals.
With Tavily, add recency via `topic: "news"` + `days: 1` (or `time_range` / `start_date`+`end_date`
for overrides), and use `include_domains` to focus the `site:` groups.

---

## A. Broad Hebrew discovery

- `מסעדה חדשה תל אביב`
- `בית קפה חדש תל אביב`
- `בר אוכל חדש תל אביב`
- `מאפייה חדשה תל אביב`
- `פופ אפ אוכל תל אביב`
- `אירוע קולינרי תל אביב`
- `ארוחת שף תל אביב`
- `פתיחה בקרוב מסעדה תל אביב`
- `סופט לאנץ מסעדה תל אביב`
- `מסעדה בהרצה תל אביב`
- `פופ-אפ תל אביב`
- `פופ-אפ מסעדה חדשה תל אביב`
- `חדש בתל אביב מסעדה`
- `מסעדה חדשה תל אביב נפתחה`

## B. Broad English discovery

- `new restaurant Tel Aviv`
- `new cafe Tel Aviv`
- `new bakery Tel Aviv`
- `food pop-up Tel Aviv`
- `chef dinner Tel Aviv`
- `soft opening Tel Aviv restaurant`
- `opening soon restaurant Tel Aviv`
- `new food place Tel Aviv`

## C. Hiring / opening

- `דרושים למסעדה חדשה תל אביב`
- `דרושים לבית קפה חדש תל אביב`
- `צוות הקמה מסעדה תל אביב`
- `טבחים מסעדה חדשה תל אביב`
- `ברמנים מסעדה חדשה תל אביב`
- `מגייסים מסעדה חדשה תל אביב`
- `מגייסים צוות למסעדה תל אביב`
- `מגייסים לפופ-אפ תל אביב`
- `hiring new restaurant Tel Aviv`
- `opening team restaurant Tel Aviv`
- `new cafe hiring Tel Aviv`

## D. Source-specific (`site:` / `include_domains`)

- `site:timeout.co.il חדשות האוכל תל אביב`
- `site:timeout.co.il מסעדה חדשה תל אביב`
- `site:mako.co.il מסעדה חדשה תל אביב`
- `site:mako.co.il חדשות מסעדות תל אביב`
- `site:ynet.co.il מסעדה חדשה תל אביב`
- `site:walla.co.il אוכל מסעדה חדשה תל אביב`
- `site:ontopo.com תל אביב מסעדה`
- `site:tabitisrael.co.il תל אביב מסעדה`
- `site:secrettelaviv.com food Tel Aviv event`
- `site:debbestfood.com מסעדות חדשות`

## E. Indexed social (public pages only — no login, no scraping private data)

- `site:instagram.com "פתיחה בקרוב" "תל אביב" מסעדה`
- `site:instagram.com "מסעדה חדשה" "תל אביב"`
- `site:instagram.com "דרושים" "מסעדה חדשה" "תל אביב"`
- `site:instagram.com "פופ אפ" "תל אביב" אוכל`
- `site:instagram.com "סופט לאנץ" "תל אביב"`
- `site:tiktok.com "מסעדה חדשה" "תל אביב"`
- `site:tiktok.com "new restaurant" "Tel Aviv"`
- `site:facebook.com/events "פופ אפ אוכל" "תל אביב"`
- `site:linkedin.com "opening team" "Tel Aviv" restaurant`

**Social is the primary discovery layer — run it heavily and improvise.** Beyond the fixed lines
above, generate fresh TRIGGER × ANGLE × NEIGHBORHOOD combos every run (HE + EN) from the
`combination_bank` in `social-watchlist.yaml`. Rotate them so each run finds new things. Starters:

- `site:instagram.com "פופ אפ" "פלורנטין"` · `site:instagram.com "פופ אפ" "יפו" אוכל`
- `site:instagram.com "ערב חד פעמי" "תל אביב"` · `site:instagram.com "ארוחת שף" "תל אביב" קולאב`
- `site:instagram.com "סופט אופנינג" OR "הרצה" "תל אביב"` · `site:instagram.com "השבוע נפתח" "תל אביב"`
- `site:instagram.com "לזמן מוגבל" OR "סוף שבוע בלבד" אוכל תל אביב`
- `site:instagram.com "guest chef" OR "chef takeover" "Tel Aviv"` · `site:instagram.com "supper club" "Tel Aviv"`
- `site:instagram.com "natural wine" OR "wine bar" "Jaffa" OR "Florentin" "now open"`
- `site:instagram.com "secret" OR "hidden" OR "speakeasy" bar "Tel Aviv"`
- `site:tiktok.com "פופ אפ" "תל אביב"` · `site:tiktok.com "מקום חדש" "תל אביב" אוכל`
- `site:tiktok.com "soft opening" OR "new spot" "Tel Aviv"`
- `<top_chef / restaurant_group / top_restaurant name>` + `"פופ אפ"` / `"ערב חד פעמי"` / `"בקרוב"` / `"דרושים"`
- Hashtag sweeps: `#פופאפתלאביב` · `#מסעדהחדשה` · `#popuptlv` · `#newrestauranttlv` · `#tlvfood`

> **Dating social hits:** if a post has no date in its text, use the **posted/published** date the tool
> returns (platform timestamp / "posted on" / "Video by X on <date>"). That posted-date is the signal
> date for the time-window test — don't drop a dateless-in-body post if a real posted-date exists.

## F. Top chefs / restaurant groups / top restaurants (hiring + new projects — run every time)

Pair each name from `social-watchlist.yaml` with a hiring/new-project term. A leading chef or group
hiring an "opening team" almost always precedes a new venue.

- `<chef name> מסעדה חדשה` · `<chef name> פותח` · `<chef name> פרויקט חדש` · `<chef name> דרושים`
- `<restaurant group> דרושים צוות הקמה` · `<restaurant group> מקום חדש` · `<restaurant group> בקרוב`
- `<top restaurant> דרושים` · `<top restaurant> צוות הקמה` · `<top restaurant> סניף חדש`
- `"דרושים" "צוות הקמה" מסעדה תל אביב` · `"opening team" OR "now hiring" chef Tel Aviv new`
- `site:linkedin.com (<chef/group name>) "Tel Aviv" (hiring OR "opening team")`
- `site:instagram.com (<chef/group handle or name>) ("דרושים" OR "בקרוב" OR "מסעדה חדשה")`
- Also scan each chef/group's **own** public page/site/LinkedIn for "careers"/"דרושים"/"בקרוב".

---

## Keyword glossary

### Hebrew keywords
דרושים · דרוש · דרושה · מגייסים · מגייס · למסעדה חדשה · לבית קפה חדש · חדש · מסעדה חדשה · תל אביב ·
פתיחה בקרוב · לפני פתיחה · בהרצה · הרצה · סופט לאנץ׳ · צוות הקמה · שף מחפש · טבחים · מלצרים · ברמנים ·
מארחים · מסעדת שף חדשה · קפה חדש · פופ אפ · פופ-אפ · פופאף · אירוע קולינרי · ארוחת שף · ערב חד פעמי ·
שיתוף פעולה קולינרי

### English keywords
opening soon · soft opening · new restaurant · new cafe · new bakery · food pop-up · chef dinner ·
collaboration dinner · hiring for new restaurant · opening team · new concept · coming soon ·
Tel Aviv food pop-up · Tel Aviv restaurant opening · Tel Aviv new cafe

---

## Normalization map (apply before dedupe)

| Variants | Canonical |
|----------|-----------|
| Tel Aviv · TLV · תל אביב · ת"א | Tel Aviv |
| Yafo · Jaffa · יפו | Yafo |
| cafe · café · coffee shop · בית קפה | cafe |
| restaurant · מסעדה | restaurant |
| pop-up · popup · פופ אפ · פופ-אפ · פופאף | pop-up |
| soft launch · soft opening · הרצה · סופט לאנץ׳ · בהרצה | soft_opening |

## Secondary-geography terms (include only on strong signal — see geography gate)

רמת גן (Ramat Gan) · גבעתיים (Givatayim) · הרצליה (Herzliya) · רמת השרון (Ramat HaSharon) ·
חולון (Holon) · בת ים (Bat Yam) · בני ברק (Bnei Brak) · פתח תקווה (Petah Tikva) ·
ראשון לציון (Rishon LeZion) · רעננה (Ra'anana) · כפר סבא (Kfar Saba) · הוד השרון (Hod HaSharon)
