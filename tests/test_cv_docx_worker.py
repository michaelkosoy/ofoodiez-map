"""Hostile-DOCX defenses (§ DOCX structural validation / security fixtures)."""
import pytest

import cv_evil_docs as evil
from cv_review.docx_worker import DocxRejected, parse_docx_bytes


def _code(data):
    with pytest.raises(DocxRejected) as exc:
        parse_docx_bytes(data)
    return exc.value.code


def test_good_docx_parses():
    out = parse_docx_bytes(evil.good_docx())
    assert out['ok'] and 'Jane Smith' in out['text'] and 'PostgreSQL' in out['text']


def test_headers_and_footers_extracted():
    out = parse_docx_bytes(evil.docx_with_header())
    assert '+972-50-0000000' in out['text']


def test_fake_docx_rejected():
    assert _code(evil.fake_docx()) == 'not_docx'


def test_malformed_zip_rejected():
    assert _code(b'PK\x03\x04 truncated garbage') == 'not_docx'


def test_zip_traversal_rejected():
    assert _code(evil.traversal_docx()) == 'zip_slip'


def test_absolute_path_rejected():
    assert _code(evil.absolute_path_docx()) == 'zip_slip'


def test_encrypted_rejected():
    assert _code(evil.encrypted_docx()) == 'encrypted'


def test_ratio_bomb_rejected():
    assert _code(evil.ratio_bomb_docx()) == 'zip_bomb'


def test_entry_flood_rejected():
    assert _code(evil.entry_flood_docx()) == 'zip_bomb'


def test_macro_enabled_disguised_as_docx_rejected():
    assert _code(evil.macro_content_type_docx()) == 'macros'


def test_vba_project_rejected():
    assert _code(evil.vba_project_docx()) == 'macros'


def test_ole_embedding_rejected():
    assert _code(evil.ole_embedding_docx()) == 'embedded_object'


def test_activex_rejected():
    assert _code(evil.activex_docx()) == 'active_content'


def test_doctype_entity_rejected():
    assert _code(evil.doctype_docx()) == 'xml_attack'


def test_malformed_xml_rejected():
    assert _code(evil.malformed_xml_docx()) == 'bad_xml'


def test_non_word_content_type_rejected():
    assert _code(evil.not_word_content_type_docx()) == 'not_docx'
