"""Generate the optimized CV as a brand-new .docx from the canonical
structured model (python-docx). NOTHING from the uploaded file is copied —
no XML parts, styles, relationships, macros, embedded objects or images can
survive into this document because it never touches the original package.
Links appear as plain text (no external relationships at all), which keeps
the final package inspection (docx_inspect.py) trivially clean."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt, RGBColor

from .render_common import collect_bold_terms, contact_line, split_segments, term_pattern

_GREY = RGBColor(0x55, 0x55, 0x55)
_RIGHT_TAB_CM = 18.2  # A4 width minus the two 1.4cm margins


def _add_runs(paragraph, text, pattern, size=None, bold_all=False):
    for segment, is_bold in split_segments(text, pattern):
        run = paragraph.add_run(segment)
        run.bold = bold_all or is_bold
        if size:
            run.font.size = size


def _section_heading(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(10.5)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:space'), '2')
    bottom.set(qn('w:color'), '999999')
    pbdr.append(bottom)
    pPr.append(pbdr)
    return p


def _role_line(doc, left_bold, left_rest, right):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(_RIGHT_TAB_CM), WD_TAB_ALIGNMENT.RIGHT)
    run = p.add_run(left_bold)
    run.bold = True
    if left_rest:
        p.add_run(left_rest)
    if right:
        tab = p.add_run(f'\t{right}')
        tab.font.color.rgb = _GREY
        tab.font.size = Pt(9.5)
    return p


def build_docx(cv):
    """Optimized CV dict → .docx bytes (clean reconstruction)."""
    doc = Document()
    section = doc.sections[0]
    for attr in ('top_margin', 'bottom_margin', 'left_margin', 'right_margin'):
        setattr(section, attr, Cm(1.4))
    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(2)

    pattern = term_pattern(collect_bold_terms(cv))

    name_p = doc.add_paragraph()
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = name_p.add_run(cv.get('name', ''))
    name_run.bold = True
    name_run.font.size = Pt(20)
    name_p.paragraph_format.space_after = Pt(0)

    if cv.get('title'):
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_p.add_run(cv['title'])
        title_run.font.size = Pt(12)
        title_p.paragraph_format.space_after = Pt(1)

    contact = contact_line(cv)
    if contact:
        c_p = doc.add_paragraph()
        c_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        c_run = c_p.add_run(contact)
        c_run.font.size = Pt(9)
        c_run.font.color.rgb = _GREY

    if cv.get('summary'):
        _section_heading(doc, 'Summary')
        p = doc.add_paragraph()
        _add_runs(p, cv['summary'], pattern)

    if cv.get('skills_groups'):
        _section_heading(doc, 'Skills')
        for g in cv['skills_groups']:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(f"{g.get('group', '')}: ")
            run.bold = True
            skills_run = p.add_run(', '.join(g.get('skills') or []))
            skills_run.bold = True

    if cv.get('experience'):
        _section_heading(doc, 'Experience')
        for exp in cv['experience']:
            company = f" — {exp['company']}" if exp.get('company') else ''
            _role_line(doc, exp.get('title', ''), company, exp.get('dates', ''))
            for bullet in exp.get('bullets') or []:
                p = doc.add_paragraph(style='List Bullet')
                p.paragraph_format.space_after = Pt(1)
                _add_runs(p, bullet, pattern)

    if cv.get('projects'):
        _section_heading(doc, 'Projects')
        for proj in cv['projects']:
            tech = f" ({proj['tech']})" if proj.get('tech') else ''
            _role_line(doc, proj.get('name', ''), tech, '')
            desc = proj.get('description') or ''
            link = proj.get('link')
            if desc or link:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(1)
                _add_runs(p, desc, pattern)
                if link:
                    link_run = p.add_run(f'  {link}')
                    link_run.font.color.rgb = _GREY
                    link_run.font.size = Pt(9.5)

    if cv.get('education'):
        _section_heading(doc, 'Education')
        for edu in cv['education']:
            inst = f" — {edu['institution']}" if edu.get('institution') else ''
            _role_line(doc, edu.get('degree', ''), inst, edu.get('dates', ''))

    for extra in cv.get('extras') or []:
        if not (extra.get('lines') or []):
            continue
        _section_heading(doc, extra.get('heading') or 'Additional')
        for line in extra['lines']:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            _add_runs(p, line, pattern)

    buf = io.BytesIO()
    doc.save(buf)
    return _strip_inert_parts(buf.getvalue())


# python-docx's built-in template ships a few Word-native extras we never
# populate (customXml properties, a thumbnail image). The final package must
# contain ONLY parts we intentionally create, so they are stripped — together
# with their relationships and content-type declarations.
_STRIP_PARTS = re.compile(r'^(?:customXml/|docProps/thumbnail\.)')
_RELS_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
_CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'


def _resolve(rels_part, target):
    # OPC: <dir>/_rels/<name>.rels targets resolve relative to <dir>
    # (package root for _rels/.rels).
    base_dir = '/'.join(rels_part.split('/')[:-2])
    parts = (f'{base_dir}/{target}' if base_dir and not target.startswith('/') else target).split('/')
    out = []
    for p in parts:
        if p == '..':
            if out:
                out.pop()
        elif p not in ('', '.'):
            out.append(p)
    return '/'.join(out)


def _filter_rels(xml_bytes, rels_part):
    ET.register_namespace('', _RELS_NS)
    root = ET.fromstring(xml_bytes)
    for rel in list(root):
        target = rel.get('Target', '')
        if rel.get('TargetMode', '') != 'External' and _STRIP_PARTS.match(_resolve(rels_part, target)):
            root.remove(rel)
    return ET.tostring(root, xml_declaration=True, encoding='UTF-8')


def _filter_content_types(xml_bytes):
    ET.register_namespace('', _CT_NS)
    root = ET.fromstring(xml_bytes)
    for node in list(root):
        tag = node.tag.rsplit('}', 1)[-1]
        if tag == 'Override' and _STRIP_PARTS.match(node.get('PartName', '').lstrip('/')):
            root.remove(node)
        elif tag == 'Default' and node.get('Extension', '').lower() in ('jpeg', 'jpg', 'png'):
            root.remove(node)
    return ET.tostring(root, xml_declaration=True, encoding='UTF-8')


def _strip_inert_parts(data):
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            if _STRIP_PARTS.match(name):
                continue
            payload = src.read(name)
            if name == '[Content_Types].xml':
                payload = _filter_content_types(payload)
            elif name.endswith('.rels'):
                payload = _filter_rels(payload, name)
            dst.writestr(name, payload)
    return out.getvalue()
