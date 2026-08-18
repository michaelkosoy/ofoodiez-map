"""Shared helpers for rendering the canonical optimized CV to text/DOCX/PDF.
All renderers consume ONLY the structured optimized_cv — nothing from the
uploaded document is ever copied through."""
import re


HEBREW_RE = re.compile(r'[֐-׿יִ-ﭏ]')


def has_hebrew(text):
    return bool(HEBREW_RE.search(text or ''))


def script_runs(text):
    """Split text into [(chunk, is_hebrew), ...] so each renderer can pick the
    right font per chunk. Neutral characters (spaces, punctuation, digits) join
    the run they touch, keeping the chunk count small."""
    if not text:
        return []
    if not has_hebrew(text):
        return [(text, False)]
    runs, current, current_heb = [], [], None
    for char in text:
        if HEBREW_RE.match(char):
            kind = True
        elif char.isalpha():          # Latin letter
            kind = False
        else:
            kind = current_heb        # neutral: stay in the current run
        if current and kind is not current_heb and kind is not None:
            runs.append((''.join(current), bool(current_heb)))
            current = []
        current.append(char)
        if kind is not None:
            current_heb = kind
    if current:
        runs.append((''.join(current), bool(current_heb)))
    return runs


_LINK_LABELS = {
    'linkedin': 'LinkedIn', 'github': 'GitHub', 'gitlab': 'GitLab',
    'website': 'Portfolio', 'site': 'Portfolio', 'portfolio': 'Portfolio',
    'homepage': 'Portfolio', 'blog': 'Blog', 'medium': 'Medium',
    'stackoverflow': 'Stack Overflow', 'stack overflow': 'Stack Overflow',
    'kaggle': 'Kaggle', 'behance': 'Behance', 'dribbble': 'Dribbble',
    'twitter': 'X', 'x': 'X', 'email': 'Email', 'phone': 'Phone',
}
_SMALL_WORDS = {'and', 'of', 'the', 'in', 'on', 'for', 'to', 'a', 'an', '&'}


def _title_case(text):
    """MILITARY SERVICE → Military Service, while keeping acronyms (IDF, IT)."""
    parts = re.split(r'(\s+)', (text or '').strip())
    out = []
    for part in parts:
        if not part or part.isspace():
            out.append(part)
            continue
        low = part.lower()
        if len(part) <= 3 and part.isupper() and part.isalpha() and low not in _SMALL_WORDS:
            out.append(part)                       # acronym
        elif out and low in _SMALL_WORDS:
            out.append(low)
        else:
            out.append(part if any(c.islower() for c in part) else low.capitalize())
    return ''.join(out).rstrip(':')


def _merge_extra_lines(lines):
    """A model often emits one entry's attributes as separate lines
    ("Artillery Corps" / "Sergeant" / "2020-2022" / "<description>"), which
    renders as a pile of one-word bullets. Join the fragments into a single
    lead line — but only in sections that actually have a descriptive line, so
    genuine per-line lists (languages, certifications) stay untouched."""
    lines = [l.strip() for l in lines if l and l.strip()]
    if len(lines) < 2 or not any(len(l) > 80 for l in lines):
        return lines
    out, buf = [], []
    for line in lines:
        self_contained = (len(line) > 80 or re.search(r'[.!?]$', line)
                          or ' — ' in line or ' - ' in line or ':' in line)
        if self_contained:
            if buf:
                out.append(' — '.join(buf))
                buf = []
            out.append(line)
        else:
            buf.append(line)
    if buf:
        out.append(' — '.join(buf))
    return out


_GPA_RE = re.compile(r'(?i)\bGPA\b[^\d]{0,12}(\d{1,3}(?:\.\d+)?)')


def _short_degree(degree):
    """CV convention is a one-line degree. "Software Development Course:
    Graduated with a GPA of 96 in an intensive full stack program." becomes
    "Software Development Course — GPA 96" (the GPA is kept, the prose isn't)."""
    degree = (degree or '').strip()
    if len(degree) <= 70 or ':' not in degree:
        return degree
    head = degree.split(':', 1)[0].strip(' .,;—-')
    if not (3 <= len(head) <= 70):
        return degree
    gpa = _GPA_RE.search(degree)
    return f'{head} — GPA {gpa.group(1)}' if gpa else head


MAX_SUMMARY_WORDS = 42   # ~2–3 rendered lines; the prompt targets 40

# Characters the PDF's standard fonts (WinAnsi) cannot draw — they come out as
# a black box (e.g. U+2011 NON-BREAKING HYPHEN in "self‑checkout"). Mapped to
# their plain equivalents before rendering. Anything else (Hebrew, etc.) is
# left untouched on purpose.
_GLYPH_FIXES = {
    '‐': '-', '‑': '-', '‒': '-', '−': '-', '­': '',
    ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ',
    ' ': ' ', ' ': ' ', '​': '', '‌': '', '‍': '',
    '﻿': '', '‘': "'", '’': "'", '‚': "'", '‛': "'",
    '“': '"', '”': '"', '„': '"', '′': "'", '″': '"',
    '•': '-', '‣': '-', '●': '-', '·': '-', '…': '...',
    'ﬁ': 'fi', 'ﬂ': 'fl', '⁄': '/', '∕': '/',
}
_GLYPH_TABLE = str.maketrans(_GLYPH_FIXES)


def _fix_glyphs(obj):
    if isinstance(obj, str):
        return obj.translate(_GLYPH_TABLE)
    if isinstance(obj, list):
        return [_fix_glyphs(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _fix_glyphs(v) for k, v in obj.items()}
    return obj


def _trim_summary(text):
    """Keep the summary to a tight 2–3 lines. Cuts at sentence boundaries only,
    so a trimmed summary never ends mid-thought."""
    text = (text or '').strip()
    if len(text.split()) <= MAX_SUMMARY_WORDS:
        return text
    kept, count = [], 0
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        words = len(sentence.split())
        if kept and count + words > MAX_SUMMARY_WORDS:
            break
        kept.append(sentence)
        count += words
    return ' '.join(kept)


def polish_cv(cv):
    """Presentation normalization applied once, before every renderer: tidy
    link labels, section headings and list fragments. Never changes facts."""
    cv.update(_fix_glyphs({k: v for k, v in cv.items()}))
    cv['summary'] = _trim_summary(cv.get('summary'))
    for edu in cv.get('education') or []:
        edu['degree'] = _short_degree(edu.get('degree'))
    for link in cv.get('links') or []:
        label = (link.get('label') or '').strip()
        link['label'] = _LINK_LABELS.get(label.lower(), _title_case(label) if label else '')
    for extra in cv.get('extras') or []:
        extra['heading'] = _title_case(extra.get('heading') or 'Additional')
        extra['lines'] = _merge_extra_lines(extra.get('lines') or [])
    for group in cv.get('skills_groups') or []:
        group['group'] = _title_case(group.get('group') or '')
    return cv


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
    # Skills last: a screener reads the story first, the keyword list closes it.
    if cv.get('skills_groups'):
        lines += ['', 'SKILLS']
        for g in cv['skills_groups']:
            lines.append(f"{g.get('group', '')}: {', '.join(g.get('skills') or [])}")
    return '\n'.join(lines).strip() + '\n'
