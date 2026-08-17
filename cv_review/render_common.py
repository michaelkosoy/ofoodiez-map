"""Shared helpers for rendering the canonical optimized CV to text/DOCX/PDF.
All renderers consume ONLY the structured optimized_cv — nothing from the
uploaded document is ever copied through."""
import re


def collect_bold_terms(cv):
    """Technologies to visually emphasize (guide rule 6): the skills list plus
    project tech — longest first so overlapping terms bold correctly."""
    terms = []
    for group in cv.get('skills_groups') or []:
        terms += group.get('skills') or []
    for proj in cv.get('projects') or []:
        if proj.get('tech'):
            terms += [t.strip() for t in re.split(r'[,;/]', proj['tech']) if t.strip()]
    seen, out = set(), []
    for t in terms:
        key = t.lower()
        if len(t) >= 2 and key not in seen:
            seen.add(key)
            out.append(t)
    out.sort(key=len, reverse=True)
    return out[:60]


def term_pattern(terms):
    if not terms:
        return None
    alt = '|'.join(re.escape(t) for t in terms)
    return re.compile(r'(?i)(?<!\w)(?:' + alt + r')(?!\w)')


def split_segments(text, pattern):
    """[(segment, is_bold), ...] — bold segments are term matches."""
    if not pattern or not text:
        return [(text, False)]
    out, pos = [], 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def contact_line(cv):
    bits = [b for b in (cv.get('email'), cv.get('phone'), cv.get('location')) if b]
    for link in cv.get('links') or []:
        url = (link.get('url') or '').strip()
        if url:
            bits.append(url)
    return '  |  '.join(bits)


def cv_to_text(cv):
    """Plain-text rendering — the 'Copy text' payload and the final artifact
    the validators sweep."""
    lines = [cv.get('name', ''), cv.get('title', '')]
    contact = contact_line(cv)
    if contact:
        lines.append(contact)
    if cv.get('summary'):
        lines += ['', 'SUMMARY', cv['summary']]
    if cv.get('skills_groups'):
        lines += ['', 'SKILLS']
        for g in cv['skills_groups']:
            lines.append(f"{g.get('group', '')}: {', '.join(g.get('skills') or [])}")
    if cv.get('experience'):
        lines += ['', 'EXPERIENCE']
        for exp in cv['experience']:
            dates = f"  ({exp.get('dates')})" if exp.get('dates') else ''
            lines.append(f"{exp.get('title', '')} — {exp.get('company', '')}{dates}")
            lines += [f"• {b}" for b in exp.get('bullets') or []]
    if cv.get('projects'):
        lines += ['', 'PROJECTS']
        for p in cv['projects']:
            tech = f" ({p['tech']})" if p.get('tech') else ''
            link = f" — {p['link']}" if p.get('link') else ''
            lines.append(f"{p.get('name', '')}{tech}: {p.get('description', '')}{link}")
    if cv.get('education'):
        lines += ['', 'EDUCATION']
        for e in cv['education']:
            dates = f"  ({e.get('dates')})" if e.get('dates') else ''
            lines.append(f"{e.get('degree', '')} — {e.get('institution', '')}{dates}")
    for ex in cv.get('extras') or []:
        lines += ['', (ex.get('heading') or '').upper()]
        lines += ex.get('lines') or []
    return '\n'.join(lines).strip() + '\n'
