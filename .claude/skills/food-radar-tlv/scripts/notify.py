#!/usr/bin/env python3
"""Send the food-radar-tlv report via Brevo. stdlib only (urllib) — ponytail: no sdk dep.

Usage:
  python3 notify.py <report.md|report.html> ["Subject line"]
  python3 notify.py --dry-run <report.md> ["Subject"]   # show what would be sent; don't send
  python3 notify.py --selftest                           # run the md->html self-check

Credentials (read from env, or ~/.env as fallback):
  BREVO_API_KEY      required to actually send (https://app.brevo.com/settings/keys/api)
  FOOD_RADAR_FROM    required — a Brevo *verified* sender address (Senders & IPs → Senders)
  FOOD_RADAR_TO      recipient(s), comma-separated. Default: ofir.lazarov@gmail.com

If creds are missing it prints a notice and exits 0 (no-op) — a radar run never fails on notify.
"""
import os, sys, json, html, re, urllib.request, urllib.error

DEFAULT_TO = "ofir.lazarov@gmail.com"

def load_dotenv(path=None):
    path = path or os.path.expanduser("~/.env")
    if not os.path.exists(path):
        return
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_URL = re.compile(r'(https?://[^\s<>")\]]+)')

def md_to_html(md):
    """Minimal, good-enough Markdown -> email HTML (headers, bold, autolinked URLs, bullets)."""
    out = []
    for raw in md.splitlines():
        line = html.escape(raw)
        m = re.match(r'(#{1,3})\s+(.*)', line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl} style='margin:14px 0 4px'>{m.group(2)}</h{lvl}>")
            continue
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = _URL.sub(r'<a href="\1">\1</a>', line)
        if re.match(r'\s*[-*]\s+', raw):
            out.append("<li>" + re.sub(r'^\s*[-*]\s+', '', line) + "</li>")
        elif raw.strip() == "":
            out.append("<br>")
        else:
            out.append(line + "<br>")
    return ("<div style=\"font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;"
            "font-size:14px;line-height:1.5;color:#1a1a1a;max-width:760px\">"
            + "\n".join(out) + "</div>")

def send(api_key, frm, to, subject, html_body):
    body = {
        "sender": {"email": frm},
        "to": [{"email": e.strip()} for e in to.split(",") if e.strip()],
        "subject": subject,
        "htmlContent": html_body,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(body).encode(),
        headers={"api-key": api_key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status

def selftest():
    h = md_to_html("# Title\n- item **bold**\nsee https://ex.co/p?a=1")
    assert "<h1" in h and ">Title</h1>" in h, "header"
    assert "<strong>bold</strong>" in h, "bold"
    assert '<a href="https://ex.co/p?a=1">' in h, "autolink"
    assert "<li>item" in h, "bullet"
    assert "&lt;script&gt;" in md_to_html("<script>"), "escaping"
    print("selftest OK")

def main(argv):
    if "--selftest" in argv:
        selftest(); return 0
    dry = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__); return 2
    path, subject = args[0], (args[1] if len(args) > 1 else "Food Radar TLV")
    text = open(path, encoding="utf-8").read()
    html_body = text if path.endswith(".html") else md_to_html(text)
    load_dotenv()
    key = os.environ.get("BREVO_API_KEY")
    frm = os.environ.get("FOOD_RADAR_FROM") or os.environ.get("BREVO_FROM")
    to = os.environ.get("FOOD_RADAR_TO", DEFAULT_TO)
    if dry:
        print(f"[dry-run] to={to} | from={frm or '(unset)'} | key={'set' if key else '(unset)'} "
              f"| subject={subject!r} | html_bytes={len(html_body)}")
        return 0
    if not key or not frm:
        print("notify: BREVO_API_KEY / FOOD_RADAR_FROM not set — skipping email "
              "(add them to ~/.env). Report NOT sent.", file=sys.stderr)
        return 0
    try:
        st = send(key, frm, to, subject, html_body)
        print(f"notify: sent to {to} (HTTP {st})")
        return 0
    except urllib.error.HTTPError as e:
        print(f"notify: Brevo error {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
