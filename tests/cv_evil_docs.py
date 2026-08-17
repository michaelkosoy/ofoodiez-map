"""Synthetic hostile-DOCX builders for the security fixtures (§ tests).
All fixtures are generated in-memory — no binary blobs in the repo."""
import io
import zipfile

CT_GOOD = (b'<?xml version="1.0"?>'
           b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
           b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
           b'<Default Extension="xml" ContentType="application/xml"/>'
           b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
           b'</Types>')

CT_MACRO = CT_GOOD.replace(
    b'wordprocessingml.document.main+xml',
    b'ms-word.document.macroEnabled.main+xml')

CT_NOT_WORD = CT_GOOD.replace(
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml',
    b'application/vnd.oasis.opendocument.text')

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def doc_xml(*paragraphs):
    body = ''.join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    return f'<?xml version="1.0"?><w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'.encode()


def build(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def good_docx(*paragraphs):
    paragraphs = paragraphs or ('Jane Smith', 'Backend Engineer', 'Python, PostgreSQL')
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml(*paragraphs))])


def docx_with_header():
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml('Jane Smith', 'Engineer')),
                  ('word/header1.xml', doc_xml('+972-50-0000000'))])


def fake_docx():
    return b'MZ this is definitely not a zip archive'


def traversal_docx():
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml('x')),
                  ('../../../etc/evil.txt', b'x')])


def absolute_path_docx():
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml('x')),
                  ('/etc/passwd', b'x')])


def encrypted_docx():
    """zipfile can't write encrypted entries — patch the encryption flag bit
    directly into the local + central-directory headers of one entry."""
    data = bytearray(build([('[Content_Types].xml', CT_GOOD),
                            ('word/document.xml', doc_xml('x'))]))
    marker = b'word/document.xml'
    for sig, flag_off in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
        pos = 0
        while True:
            pos = data.find(sig, pos)
            if pos == -1:
                break
            name_off = pos + (30 if sig == b'PK\x03\x04' else 46)
            if data[name_off:name_off + len(marker)] == marker:
                data[pos + flag_off] |= 0x1
            pos += 4
    return bytes(data)


def ratio_bomb_docx():
    # 30 MB of zeros — compresses to ~30 KB, expands past the per-part ceiling.
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml('x')),
                  ('word/media/zeros.xml', b'\x00' * (30 * 1024 * 1024))])


def entry_flood_docx():
    entries = [('[Content_Types].xml', CT_GOOD), ('word/document.xml', doc_xml('x'))]
    entries += [(f'junk/part{i}.xml', b'<x/>') for i in range(3000)]
    return build(entries)


def macro_content_type_docx():
    """resume.docx that is really a macro-enabled document (.docm disguised)."""
    return build([('[Content_Types].xml', CT_MACRO),
                  ('word/document.xml', doc_xml('x'))])


def vba_project_docx():
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml('x')),
                  ('word/vbaProject.bin', b'\xd0\xcf\x11\xe0 fake vba')])


def ole_embedding_docx():
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml('x')),
                  ('word/embeddings/oleObject1.bin', b'\xd0\xcf\x11\xe0 fake ole')])


def activex_docx():
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', doc_xml('x')),
                  ('word/activeX/activeX1.xml', b'<ax/>')])


def doctype_docx():
    evil = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa">]>'
            b'<w:document xmlns:w="' + W_NS.encode() + b'"><w:body/></w:document>')
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', evil)])


def malformed_xml_docx():
    return build([('[Content_Types].xml', CT_GOOD),
                  ('word/document.xml', b'<w:document><unclosed')])


def not_word_content_type_docx():
    return build([('[Content_Types].xml', CT_NOT_WORD),
                  ('word/document.xml', doc_xml('x'))])
