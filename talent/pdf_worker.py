"""One-shot PDF text extractor, run INSIDE cv_review.sandbox (scrubbed env,
rlimits, kill timeout) because email attachments are untrusted input — same
isolation model as the DOCX worker.

Usage: python pdf_worker.py <input.pdf> <verdict.json>
Verdict: {'ok': True, 'text': str, 'pages': int} or {'ok': False, 'error': str}
"""
import json
import sys


def main():
    in_path, out_path = sys.argv[1], sys.argv[2]
    try:
        from pypdf import PdfReader
        reader = PdfReader(in_path)
        if reader.is_encrypted:
            try:
                reader.decrypt('')
            except Exception:
                raise ValueError('encrypted')
        pages = reader.pages[:15]  # a CV is 1-3 pages; cap hostile page counts
        text = '\n'.join((p.extract_text() or '') for p in pages)
        verdict = {'ok': True, 'text': text, 'pages': len(reader.pages)}
    except Exception as exc:
        verdict = {'ok': False, 'error': type(exc).__name__}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(verdict, f, ensure_ascii=False)


if __name__ == '__main__':
    main()
