"""Hostile-DOCX parser. Runs as a one-shot script inside the sandbox
(cv_review/sandbox.py): scrubbed environment, rlimits, hard timeout.

STDLIB ONLY — this file must import nothing from the application (it executes
with no secrets, no PYTHONPATH and no network use). The uploaded document is
DATA, never commands: it is opened as a ZIP in memory, structurally validated,
and only plain text is extracted. Nothing is ever executed, rendered by Word,
or copied into the final optimized document.

Usage:  python docx_worker.py <input_file> <output_json>
Always exits 0 with a structured JSON verdict for expected rejections;
non-zero exit = unexpected crash (parent maps it to a generic safe error).

Defenses (OOXML/ZIP):
  zip bombs (per-entry + total decompressed ceilings, compression-ratio guard,
  capped reads that don't trust ZIP headers), entry-count flood, ZIP-slip /
  absolute paths, encrypted archives, macro-enabled documents (vbaProject.bin
  or macroEnabled content types — .docm disguised as .docx), ActiveX parts,
  embedded OLE/executable objects, malformed XML, and XML DTD/entity attacks
  (any DOCTYPE/ENTITY declaration is rejected outright — legitimate OOXML
  parts never contain them).
"""
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

MAX_INPUT_BYTES = 6 * 1024 * 1024          # upload cap is 5 MB; small slack
MAX_ENTRIES = 2048
MAX_PART_BYTES = 20 * 1024 * 1024          # per-part decompressed ceiling
MAX_TOTAL_UNCOMPRESSED = 50 * 1024 * 1024  # whole-archive decompressed ceiling
MAX_RATIO = 200                            # compression-ratio bomb guard...
RATIO_MIN_SIZE = 64 * 1024                 # ...applied above this size
MAX_TEXT_CHARS = 200_000                   # extracted-text cap sent onward

_W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_DOCUMENT_MAIN_CT = b'wordprocessingml.document.main+xml'


class DocxRejected(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _reject(code, message):
    raise DocxRejected(code, message)


def _check_entry_names(infos):
    for zi in infos:
        name = zi.filename
        if '\\' in name or name.startswith('/') or re.match(r'^[A-Za-z]:', name):
            _reject('zip_slip', 'This document contains unsafe file paths.')
        if any(part == '..' for part in name.split('/')):
            _reject('zip_slip', 'This document contains unsafe file paths.')
        if zi.flag_bits & 0x1:
            _reject('encrypted', 'Encrypted documents are not supported.')


def _check_bomb(infos):
    if len(infos) > MAX_ENTRIES:
        _reject('zip_bomb', 'This document contains too many internal files.')
    total = 0
    for zi in infos:
        if zi.file_size > MAX_PART_BYTES:
            _reject('zip_bomb', 'This document expands to an unreasonable size.')
        total += zi.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            _reject('zip_bomb', 'This document expands to an unreasonable size.')
        if zi.file_size > RATIO_MIN_SIZE and zi.file_size / max(zi.compress_size, 1) > MAX_RATIO:
            _reject('zip_bomb', 'This document expands to an unreasonable size.')


def _check_dangerous_parts(names_lower):
    for name in names_lower:
        base = name.rsplit('/', 1)[-1]
        if base == 'vbaproject.bin' or base.endswith('.dotm') or base.endswith('.docm'):
            _reject('macros', 'Macro-enabled documents are not supported. Please upload a plain .docx.')
        if 'activex' in name:
            _reject('active_content', 'This document contains active content and cannot be processed.')
        if '/embeddings/' in name or name.startswith('embeddings/'):
            _reject('embedded_object', 'This document contains embedded objects and cannot be processed. Please upload a plain .docx.')
        if base.endswith(('.exe', '.dll', '.js', '.vbs', '.ps1', '.bat', '.cmd', '.jar', '.scr')):
            _reject('embedded_object', 'This document contains embedded executable content.')


def _read_part(zf, name):
    """Read one part with a hard cap — never trusting the ZIP header sizes."""
    with zf.open(name) as fh:
        data = fh.read(MAX_PART_BYTES + 1)
        if len(data) > MAX_PART_BYTES:
            _reject('zip_bomb', 'This document expands to an unreasonable size.')
    return data


def _check_content_types(data):
    lower = data.lower()
    if b'macroenabled' in lower:
        _reject('macros', 'Macro-enabled documents are not supported. Please upload a plain .docx.')
    if b'oleobject' in lower or b'activex' in lower:
        _reject('embedded_object', 'This document contains embedded objects and cannot be processed.')
    if _DOCUMENT_MAIN_CT not in data:
        _reject('not_docx', 'This file is not a valid Word (.docx) document.')


def _parse_xml_part(data, name):
    if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        _reject('xml_attack', 'This document contains unsupported XML and cannot be processed.')
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        _reject('bad_xml', f'This document contains malformed content ({name}).')


def _text_of(root):
    """Linearize a WordprocessingML part into plain text, paragraph per line.

    Tables come out linearized in document order — plenty for CV-content
    extraction (the AI extraction step re-structures it)."""
    lines = []
    for p in root.iter(f'{{{_W_NS}}}p'):
        chunks = []
        for node in p.iter():
            tag = node.tag.rsplit('}', 1)[-1]
            if tag == 't' and node.text:
                chunks.append(node.text)
            elif tag == 'tab':
                chunks.append('\t')
            elif tag in ('br', 'cr'):
                chunks.append('\n')
        line = ''.join(chunks).strip()
        if line:
            lines.append(line)
    return '\n'.join(lines)


def parse_docx_bytes(data):
    """Validate + extract text from untrusted .docx bytes.

    Returns {'ok': True, 'text': ..., 'meta': {...}}.
    Raises DocxRejected for every recognized-dangerous/invalid case.
    """
    if len(data) > MAX_INPUT_BYTES:
        _reject('too_big', 'This file is too large.')
    if len(data) < 4 or data[:2] != b'PK':
        _reject('not_docx', 'This file is not a valid Word (.docx) document.')
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, Exception) as exc:
        if isinstance(exc, DocxRejected):
            raise
        _reject('not_docx', 'This file is not a valid Word (.docx) document.')

    _check_entry_names(infos)
    _check_bomb(infos)
    names = [zi.filename for zi in infos]
    _check_dangerous_parts([n.lower() for n in names])

    if '[Content_Types].xml' not in names:
        _reject('not_docx', 'This file is not a valid Word (.docx) document.')
    _check_content_types(_read_part(zf, '[Content_Types].xml'))

    if 'word/document.xml' not in names:
        _reject('not_docx', 'This file is not a valid Word (.docx) document.')

    body = _text_of(_parse_xml_part(_read_part(zf, 'word/document.xml'), 'word/document.xml'))

    # Contact details often live in headers/footers — extract those too.
    hf_texts = []
    for name in sorted(names):
        if re.fullmatch(r'word/(?:header|footer)\d*\.xml', name):
            hf_texts.append(_text_of(_parse_xml_part(_read_part(zf, name), name)))

    text = body
    hf = '\n'.join(t for t in hf_texts if t)
    if hf:
        text = f'{text}\n[Header/Footer]\n{hf}'
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + '\n[TRUNCATED]'
    if not text.strip():
        _reject('empty', 'No readable text was found in this document.')

    return {'ok': True, 'text': text,
            'meta': {'entries': len(infos), 'chars': len(text),
                     'headers_footers': len(hf_texts)}}


def main(argv):
    in_path, out_path = argv[1], argv[2]
    try:
        with open(in_path, 'rb') as f:
            data = f.read(MAX_INPUT_BYTES + 1)
        result = parse_docx_bytes(data)
    except DocxRejected as exc:
        result = {'ok': False, 'error_code': exc.code, 'message': exc.message}
    except Exception as exc:  # unexpected — still a structured, safe verdict
        print(f'docx_worker unexpected: {type(exc).__name__}: {exc}', file=sys.stderr)
        result = {'ok': False, 'error_code': 'parse_failed',
                  'message': 'Could not read this document. Please try a different file.'}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
