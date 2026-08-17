"""Generate the optimized CV as a PDF (reportlab platypus) from the canonical
structured model. Same clean-reconstruction principle as docx_writer: nothing
from the uploaded file flows through."""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from .render_common import collect_bold_terms, contact_line, split_segments, term_pattern

_STYLES = {
    'name': ParagraphStyle('name', fontName='Helvetica-Bold', fontSize=18,
                           leading=21, alignment=1, spaceAfter=1),
    'title': ParagraphStyle('title', fontName='Helvetica', fontSize=11,
                            leading=13, alignment=1, spaceAfter=2),
    'contact': ParagraphStyle('contact', fontName='Helvetica', fontSize=8.5,
                              leading=11, alignment=1, textColor=colors.HexColor('#555555'),
                              spaceAfter=4),
    'heading': ParagraphStyle('heading', fontName='Helvetica-Bold', fontSize=10,
                              leading=12, spaceBefore=7, spaceAfter=1),
    'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9.5,
                           leading=12, spaceAfter=2),
    'role': ParagraphStyle('role', fontName='Helvetica', fontSize=9.5,
                           leading=12, spaceBefore=3, spaceAfter=1),
    'bullet': ParagraphStyle('bullet', fontName='Helvetica', fontSize=9.5,
                             leading=12, leftIndent=12, bulletIndent=2, spaceAfter=1),
}


def _markup(text, pattern):
    """Escape, then bold the technology terms (segments split pre-escape so
    offsets stay honest)."""
    return ''.join(f'<b>{escape(seg)}</b>' if bold else escape(seg)
                   for seg, bold in split_segments(text or '', pattern))


def build_pdf(cv):
    pattern = term_pattern(collect_bold_terms(cv))
    story = [Paragraph(escape(cv.get('name', '')), _STYLES['name'])]
    if cv.get('title'):
        story.append(Paragraph(escape(cv['title']), _STYLES['title']))
    contact = contact_line(cv)
    if contact:
        story.append(Paragraph(escape(contact), _STYLES['contact']))

    def heading(text):
        story.append(Paragraph(escape(text.upper()), _STYLES['heading']))
        story.append(HRFlowable(width='100%', thickness=0.6,
                                color=colors.HexColor('#999999'), spaceAfter=3))

    if cv.get('summary'):
        heading('Summary')
        story.append(Paragraph(_markup(cv['summary'], pattern), _STYLES['body']))

    if cv.get('skills_groups'):
        heading('Skills')
        for g in cv['skills_groups']:
            skills = escape(', '.join(g.get('skills') or []))
            story.append(Paragraph(
                f"<b>{escape(g.get('group', ''))}:</b> <b>{skills}</b>", _STYLES['body']))

    if cv.get('experience'):
        heading('Experience')
        for exp in cv['experience']:
            company = f" — {escape(exp['company'])}" if exp.get('company') else ''
            dates = (f" &nbsp;&nbsp;<font size='8.5' color='#555555'>{escape(exp['dates'])}</font>"
                     if exp.get('dates') else '')
            story.append(Paragraph(
                f"<b>{escape(exp.get('title', ''))}</b>{company}{dates}", _STYLES['role']))
            for bullet in exp.get('bullets') or []:
                story.append(Paragraph(_markup(bullet, pattern),
                                       _STYLES['bullet'], bulletText='•'))

    if cv.get('projects'):
        heading('Projects')
        for proj in cv['projects']:
            tech = f" <font size='8.5'>({escape(proj['tech'])})</font>" if proj.get('tech') else ''
            story.append(Paragraph(f"<b>{escape(proj.get('name', ''))}</b>{tech}", _STYLES['role']))
            desc = _markup(proj.get('description', ''), pattern)
            if proj.get('link'):
                desc += f" <font size='8.5' color='#555555'>{escape(proj['link'])}</font>"
            if desc:
                story.append(Paragraph(desc, _STYLES['body']))

    if cv.get('education'):
        heading('Education')
        for edu in cv['education']:
            inst = f" — {escape(edu['institution'])}" if edu.get('institution') else ''
            dates = (f" &nbsp;&nbsp;<font size='8.5' color='#555555'>{escape(edu['dates'])}</font>"
                     if edu.get('dates') else '')
            story.append(Paragraph(
                f"<b>{escape(edu.get('degree', ''))}</b>{inst}{dates}", _STYLES['role']))

    for extra in cv.get('extras') or []:
        if not (extra.get('lines') or []):
            continue
        heading(extra.get('heading') or 'Additional')
        for line in extra['lines']:
            story.append(Paragraph(_markup(line, pattern), _STYLES['body']))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4,
                      topMargin=1.2 * cm, bottomMargin=1.2 * cm,
                      leftMargin=1.4 * cm, rightMargin=1.4 * cm,
                      title=f"{cv.get('name', 'CV')} — CV",
                      author=cv.get('name', '')).build(story)
    return buf.getvalue()
