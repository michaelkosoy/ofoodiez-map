"""Final security inspection of the GENERATED optimized .docx before it is
stored or served. The writer builds only clean parts, so a non-empty problem
list here means a bug or a compromised generation path — the pipeline fails
closed and never ships the artifact.

Checks: valid ZIP/DOCX package, expected parts only, no VBA/macros, no
ActiveX, no OLE/embedded objects or executables, no media, no external
relationship targets (links are rendered as plain text on purpose), no path
traversal, sane decompressed size."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

MAX_TOTAL_UNCOMPRESSED = 20 * 1024 * 1024

# Everything python-docx's default template may legitimately emit.
_ALLOWED_PARTS = [
    re.compile(r'^\[Content_Types\]\.xml$'),
    re.compile(r'^_rels/\.rels$'),
    re.compile(r'^docProps/(?:core|app|custom)\.xml$'),
    re.compile(r'^word/(?:document|styles|stylesWithEffects|settings|fontTable|numbering|webSettings)\.xml$'),
    re.compile(r'^word/theme/theme\d+\.xml$'),
    re.compile(r'^word/_rels/document\.xml\.rels$'),
]
_FORBIDDEN_HINTS = ('vbaproject', 'activex', 'embeddings/', 'oleobject',
                    'macro', '.exe', '.dll', '.bin', 'word/media/')

_REL_NS = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def inspect_docx(data):
    """Returns a list of problems; empty list == artifact approved."""
    problems = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except Exception:
        return ['not a valid ZIP/DOCX package']

    total = 0
    names = []
    for zi in infos:
        name = zi.filename
        names.append(name)
        total += zi.file_size
        if '\\' in name or name.startswith('/') or '..' in name.split('/'):
            problems.append(f'path traversal in part name: {name}')
        low = name.lower()
        for hint in _FORBIDDEN_HINTS:
            if hint in low:
                problems.append(f'forbidden part: {name}')
                break
        if not any(p.match(name) for p in _ALLOWED_PARTS):
            problems.append(f'unexpected part: {name}')
    if total > MAX_TOTAL_UNCOMPRESSED:
        problems.append(f'decompressed size {total} exceeds ceiling')

    if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
        problems.append('missing required DOCX parts')
    else:
        ct = zf.read('[Content_Types].xml').lower()
        for marker in (b'macroenabled', b'oleobject', b'activex', b'vnd.ms-office'):
            if marker in ct:
                problems.append(f'forbidden content type: {marker.decode()}')
        if b'wordprocessingml.document.main+xml' not in ct:
            problems.append('main document content type missing')

    # Relationship audit: no external targets at all (links are plain text).
    for name in names:
        if not name.endswith('.rels'):
            continue
        try:
            root = ET.fromstring(zf.read(name))
        except ET.ParseError:
            problems.append(f'malformed relationships part: {name}')
            continue
        for rel in root.iter(f'{_REL_NS}Relationship'):
            if rel.get('TargetMode', '').lower() == 'external':
                problems.append(
                    f'external relationship in {name}: {rel.get("Target", "?")}')

    # Document must parse as XML (sanity that we produced a valid main part).
    if 'word/document.xml' in names:
        try:
            ET.fromstring(zf.read('word/document.xml'))
        except ET.ParseError:
            problems.append('word/document.xml is not valid XML')

    return problems
