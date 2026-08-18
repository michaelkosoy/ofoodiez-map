"""Generate the optimized CV as a PDF (reportlab platypus) from the canonical
structured model — clean reconstruction, nothing from the uploaded file flows
through.

Template: dense single-column resume in the classic Israeli-tech style —
centered name + contact line, ruled section headings ("Experience:"), a
narrow left date column beside each position, tight bullets with bolded
technologies.

One-pager guarantee: the layout is rendered at the LARGEST font scale that
still fits a single page (trying big→small), so a short CV fills the page and
a long one compresses instead of spilling over."""
import io
import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from .render_common import (collect_bold_terms, has_hebrew, script_runs,
                            split_segments, term_pattern)

# ── Hebrew support ──────────────────────────────────────────────────────────
# reportlab's built-in fonts have no Hebrew (a Hebrew name rendered as boxes)
# and no bidi engine. Hebrew runs are therefore drawn with a vendored OFL font
# and reordered to visual order with python-bidi; Latin text keeps Helvetica so
# the approved look is unchanged.
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
HEBREW_FONT = 'NotoSansHebrew'


def _register_hebrew_font():
    try:
        pdfmetrics.registerFont(TTFont(HEBREW_FONT,
                                       os.path.join(_FONT_DIR, 'NotoSansHebrew-Regular.ttf')))
        pdfmetrics.registerFont(TTFont(f'{HEBREW_FONT}-Bold',
                                       os.path.join(_FONT_DIR, 'NotoSansHebrew-Bold.ttf')))
        pdfmetrics.registerFontFamily(HEBREW_FONT, normal=HEBREW_FONT,
                                      bold=f'{HEBREW_FONT}-Bold',
                                      italic=HEBREW_FONT,
                                      boldItalic=f'{HEBREW_FONT}-Bold')
        addMapping(HEBREW_FONT, 0, 0, HEBREW_FONT)
        addMapping(HEBREW_FONT, 1, 0, f'{HEBREW_FONT}-Bold')
        return True
    except Exception as exc:      # missing/corrupt font must not break reviews
        print(f'⚠️ CV review: Hebrew font unavailable ({type(exc).__name__}: {exc})')
        return False


HEBREW_READY = _register_hebrew_font()


def _to_visual(text):
    """Logical → visual order for a line containing Hebrew (reportlab draws
    strictly left to right)."""
    try:
        from bidi.algorithm import get_display
        return get_display(text)
    except Exception:
        # ponytail: naive fallback — reverse the whole line. Correct for a
        # Hebrew-only line (a name), imperfect for mixed punctuation.
        return text[::-1]

_MARGIN = 1.25 * cm
_DATE_COL = 3.0 * cm
_BODY_COL = A4[0] - 2 * _MARGIN - _DATE_COL
_AVAIL_W = A4[0] - 2 * _MARGIN
_AVAIL_H = A4[1] - 2 * _MARGIN
_LINK_COLOR = '#1a4d8f'

# Largest-first: the first scale whose measured height fits one page wins.
_SCALES = (1.5, 1.42, 1.34, 1.26, 1.18, 1.1, 1.04, 1.0, 0.95, 0.9, 0.85, 0.8, 0.75)
_MAX_SECTION_GAP = 40   # pt of extra air per section when content is thin


def _styles(s, extra_gap=0):
    def st(name, size, *, bold=False, leading=1.28, align=0, color='#111111',
           space_after=0, space_before=0, left=0, bullet=0):
        return ParagraphStyle(
            name, fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=size * s, leading=size * s * leading, alignment=align,
            textColor=colors.HexColor(color), spaceAfter=space_after * s,
            spaceBefore=space_before * s, leftIndent=left * s, bulletIndent=bullet * s)
    return {
        'name': st('name', 19, bold=True, align=1, leading=1.1, space_after=1),
        'title': st('title', 11.5, align=1, space_after=2),
        'contact': st('contact', 9, align=1, color='#444444', space_after=4),
        'heading': ParagraphStyle(
            'heading', fontName='Helvetica-Bold', fontSize=10.5 * s,
            leading=10.5 * s * 1.28, textColor=colors.HexColor('#111111'),
            spaceBefore=7 * s + extra_gap, spaceAfter=0),
        'body': st('body', 9.5, space_after=2),
        'role': st('role', 10, space_after=1),
        'dates': st('dates', 8.5, color='#555555', leading=1.2),
        'bullet': st('bullet', 9.5, left=11, bullet=2, space_after=1, leading=1.25),
        'skills': st('skills', 9.5, space_after=1.5),
    }


def _hebrew_aware(text, bold=False):
    """Escape `text`, switching to the Hebrew font (and visual order) for its
    Hebrew runs. Latin runs keep the document font."""
    if not has_hebrew(text) or not HEBREW_READY:
        return escape(text or '')
    out = []
    for chunk, is_hebrew in script_runs(_to_visual(text)):
        safe = escape(chunk)
        if is_hebrew:
            name = f'{HEBREW_FONT}-Bold' if bold else HEBREW_FONT
            out.append(f'<font name="{name}">{safe}</font>')
        else:
            out.append(safe)
    return ''.join(out)


def _markup(text, pattern):
    return ''.join(
        f'<b>{_hebrew_aware(seg, bold=True)}</b>' if bold else _hebrew_aware(seg)
        for seg, bold in split_segments(text or '', pattern))


def _contact_markup(cv):
    bits = []
    for value in (cv.get('phone'), cv.get('email')):
        if value:
            bits.append(_hebrew_aware(value))
    if cv.get('location'):
        bits.append(_hebrew_aware(cv['location']))
    for link in cv.get('links') or []:
        url = (link.get('url') or '').strip()
        if not url:
            continue
        href = url if url.startswith(('http://', 'https://')) else f'https://{url}'
        label = _hebrew_aware(link.get('label') or url)
        bits.append(f'<link href="{escape(href)}" color="{_LINK_COLOR}"><u>{label}</u></link>')
    return ' &nbsp;|&nbsp; '.join(bits)


def _entry_table(date_text, right_flowables, styles, s):
    left = Paragraph(_hebrew_aware(date_text or ''), styles['dates'])
    table = Table([[left, right_flowables]], colWidths=[_DATE_COL, _BODY_COL])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 6),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5 * s),
    ]))
    return table


def _story(cv, s, extra_gap=0):
    styles = _styles(s, extra_gap)
    pattern = term_pattern(collect_bold_terms(cv))
    story = [Paragraph(_hebrew_aware(cv.get('name', ''), bold=True), styles['name'])]
    if cv.get('title'):
        story.append(Paragraph(_hebrew_aware(cv['title']), styles['title']))
    contact = _contact_markup(cv)
    if contact:
        story.append(Paragraph(contact, styles['contact']))

    def heading(text):
        story.append(Paragraph(_hebrew_aware(text, bold=True) + ':', styles['heading']))
        story.append(HRFlowable(width='100%', thickness=0.8, color=colors.HexColor('#333333'),
                                spaceBefore=1 * s, spaceAfter=3 * s))

    if cv.get('summary'):
        heading('Summary')
        story.append(Paragraph(_markup(cv['summary'], pattern), styles['body']))

    if cv.get('experience'):
        heading('Experience')
        for exp in cv['experience']:
            company = f" — {_hebrew_aware(exp['company'])}" if exp.get('company') else ''
            right = [Paragraph(f"<b>{_hebrew_aware(exp.get('title', ''), bold=True)}</b>{company}", styles['role'])]
            right += [Paragraph(_markup(b, pattern), styles['bullet'], bulletText='•')
                      for b in exp.get('bullets') or []]
            story.append(_entry_table(exp.get('dates'), right, styles, s))

    if cv.get('projects'):
        heading('Projects')
        for proj in cv['projects']:
            tech = f" <font color='#555555'>({_hebrew_aware(proj['tech'])})</font>" if proj.get('tech') else ''
            right = [Paragraph(f"<b>{_hebrew_aware(proj.get('name', ''), bold=True)}</b>{tech}", styles['role'])]
            desc = _markup(proj.get('description', ''), pattern)
            if proj.get('link'):
                url = proj['link'].strip()
                href = url if url.startswith(('http://', 'https://')) else f'https://{url}'
                desc += (f' <link href="{escape(href)}" color="{_LINK_COLOR}">'
                         f'<u>{escape(url)}</u></link>')
            if desc:
                right.append(Paragraph(desc, styles['bullet'], bulletText='•'))
            story.append(_entry_table('', right, styles, s))

    if cv.get('education'):
        heading('Education')
        for edu in cv['education']:
            inst = f" — {_hebrew_aware(edu['institution'])}" if edu.get('institution') else ''
            right = [Paragraph(f"<b>{_hebrew_aware(edu.get('degree', ''), bold=True)}</b>{inst}", styles['role'])]
            story.append(_entry_table(edu.get('dates'), right, styles, s))

    for extra in cv.get('extras') or []:
        if not (extra.get('lines') or []):
            continue
        heading(extra.get('heading') or 'Additional')
        for line in extra['lines']:
            story.append(Paragraph(_markup(line, pattern), styles['bullet'], bulletText='•'))

    # Skills close the CV: group label bold, the list itself plain — the
    # technologies are already emphasized where they carry weight (bullets).
    if cv.get('skills_groups'):
        heading('Skills')
        for g in cv['skills_groups']:
            skills = _hebrew_aware(', '.join(g.get('skills') or []))
            story.append(Paragraph(
                f"<b>{_hebrew_aware(g.get('group', ''), bold=True)}:</b> {skills}", styles['skills']))

    return story


def _story_height(story):
    """Platypus-equivalent height of a story in one frame (no page breaks):
    each flowable's wrapped height plus max(prev spaceAfter, own spaceBefore)."""
    total = 0.0
    prev_after = 0.0
    for flowable in story:
        _w, h = flowable.wrap(_AVAIL_W, _AVAIL_H)
        before = flowable.getSpaceBefore() if hasattr(flowable, 'getSpaceBefore') else 0
        after = flowable.getSpaceAfter() if hasattr(flowable, 'getSpaceAfter') else 0
        total += max(prev_after, before) + h
        prev_after = after
    return total


def _section_gaps(cv):
    """How many section headings the story will have (gap distribution units)."""
    n = sum(1 for present in (cv.get('summary'), cv.get('skills_groups'),
                              cv.get('experience'), cv.get('projects'),
                              cv.get('education')) if present)
    n += sum(1 for x in cv.get('extras') or [] if x.get('lines'))
    return max(1, n)


def _render(cv, scale, gap):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=_MARGIN, bottomMargin=_MARGIN,
                            leftMargin=_MARGIN, rightMargin=_MARGIN,
                            title=f"{cv.get('name', 'CV')} — CV",
                            author=cv.get('name', ''))
    doc.build(_story(cv, scale, gap))
    return buf.getvalue(), doc.page


def build_pdf(cv):
    """Render at the largest type scale that fits one page, then spread any
    leftover vertical space across the section gaps so the page reads as a
    deliberately FULL one-pager rather than a half-empty sheet."""
    chosen, height = _SCALES[-1], None
    for scale in _SCALES:
        h = _story_height(_story(cv, scale))
        if h <= _AVAIL_H:
            chosen, height = scale, h
            break

    gap = 0
    if height is not None:
        leftover = _AVAIL_H - height
        gap = max(0, min(leftover / _section_gaps(cv), _MAX_SECTION_GAP))
        if gap < 1.5:      # not worth the reflow risk
            gap = 0

    pdf, pages = _render(cv, chosen, gap)
    if pages == 1:
        return pdf
    if gap:                                  # gap pushed it over — drop the air
        pdf, pages = _render(cv, chosen, 0)
        if pages == 1:
            return pdf
    for scale in _SCALES[_SCALES.index(chosen) + 1:]:   # measurement drift
        pdf, pages = _render(cv, scale, 0)
        if pages == 1:
            return pdf
    return pdf   # extreme volume: smallest scale (may exceed one page)
