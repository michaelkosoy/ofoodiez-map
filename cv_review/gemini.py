"""Thin REST client for Gemini generateContent with structured output.

Deliberate configuration (checked against Google's current docs, 2026-08):
  * generateContent + generationConfig.responseMimeType/responseSchema is the
    current, GA structured-output surface (the newer Interactions API exists,
    but generateContent is not deprecated; we stay on the surface the rest of
    the codebase already uses).
  * NO `tools` are ever sent: no Google Search grounding, no URL Context, no
    code execution, no browsing. Rewriting one CV needs no internet.
  * Thinking tokens are billed as output tokens; we record them separately
    when the API reports them.
  * Prompts are NEVER logged (CVs are personal data) — only status codes,
    sizes and token counts.

Operational requirement (documented, not enforceable from code): production
must run this against a PAID-tier Google AI project so CV content is handled
under the paid service data terms — never free-tier for real users.
"""
import json
import os
import time

import requests

DEFAULT_MODEL = 'gemini-3.5-flash-lite'

# USD per 1M tokens (input, output) — Google AI pricing as of 2026-08.
# Thinking tokens bill at the output rate. Update alongside model changes.
PRICES_PER_1M = {
    'gemini-3.5-flash-lite': (0.30, 2.50),
    'gemini-3.1-flash-lite': (0.25, 1.50),
    'gemini-2.5-flash-lite': (0.10, 0.40),
    'gemini-3.7-flash': (0.75, 3.75),
    'gemini-3.6-flash': (0.75, 3.75),
    'gemini-3.5-flash': (1.50, 9.00),
    'gemini-3.1-pro-preview': (2.00, 12.00),
}


def model_name(purpose=None):
    """Model for one pipeline step. A step can be pointed at a stronger model
    without touching code — GEMINI_CV_MODEL_OPTIMIZE=gemini-3.7-flash spends
    the extra money only on the rewrite, which is the step where writing
    quality actually shows. Falls back to GEMINI_CV_MODEL, then the default.
    (Benchmark before switching: scripts/cv_eval.py is the judge.)"""
    if purpose:
        step = purpose.split('_')[0].upper()        # repair_1 → REPAIR
        override = os.environ.get(f'GEMINI_CV_MODEL_{step}')
        if override:
            return override
    return os.environ.get('GEMINI_CV_MODEL', DEFAULT_MODEL)


def api_key():
    key = os.environ.get('GEMINI_API_KEY')
    if not key or key == 'your_gemini_api_key_here':
        return None
    return key


class GeminiError(Exception):
    """Upstream model failure with a client-safe message."""

    def __init__(self, message, user_message=None):
        super().__init__(message)
        self.user_message = user_message or (
            'The AI reviewer had a temporary problem. Please try again in a minute.')


class UsageTracker:
    """Per-review operational metadata: calls, tokens, cost, duration.
    No prompt contents are ever stored here."""

    def __init__(self):
        self.calls = []

    def add(self, purpose, model, usage_metadata, seconds):
        um = usage_metadata or {}
        self.calls.append({
            'purpose': purpose,
            'model': model,
            'input_tokens': um.get('promptTokenCount', 0),
            'output_tokens': um.get('candidatesTokenCount', 0),
            'thoughts_tokens': um.get('thoughtsTokenCount', 0),
            'seconds': round(seconds, 2),
        })

    def totals(self):
        inp = sum(c['input_tokens'] for c in self.calls)
        out = sum(c['output_tokens'] + c['thoughts_tokens'] for c in self.calls)
        # Price per call, since steps may run on different models.
        cost, priced = 0.0, True
        for call in self.calls:
            prices = PRICES_PER_1M.get(call['model'])
            if not prices:
                priced = False
                continue
            cost += (call['input_tokens'] * prices[0]
                     + (call['output_tokens'] + call['thoughts_tokens']) * prices[1]) / 1e6
        models = sorted({c['model'] for c in self.calls})
        return {
            'model': ' + '.join(models) if models else model_name(),
            'calls': len(self.calls),
            'input_tokens': inp,
            'output_tokens': out,
            'estimated_cost_usd': round(cost, 6) if priced else None,
            'seconds': round(sum(c['seconds'] for c in self.calls), 2),
            'per_call': self.calls,
        }


def _strip_code_fences(text):
    text = text.strip()
    if text.startswith('```'):
        newline = text.find('\n')
        text = text[newline + 1:] if newline != -1 else text[3:]
        text = text.strip()
        if text.endswith('```'):
            text = text[:-3].strip()
    return text


def generate_json(parts, schema, *, purpose, usage, key,
                  max_output_tokens=16384, temperature=0.2, timeout=90):
    """One structured-output call. Returns the parsed JSON dict.
    Raises GeminiError with a client-safe message on any failure."""
    model = model_name(purpose)
    url = (f'https://generativelanguage.googleapis.com/v1beta/'
           f'models/{model}:generateContent')
    payload = {
        'contents': [{'parts': parts}],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema': schema,
            'temperature': temperature,
            'maxOutputTokens': max_output_tokens,
        },
        # No 'tools' key — grounding/URL-context/code-execution stay OFF.
    }

    last_err = None
    for attempt in (1, 2):
        start = time.monotonic()
        try:
            resp = requests.post(url, json=payload, timeout=timeout,
                                 headers={'x-goog-api-key': key})
        except requests.RequestException as exc:
            last_err = f'request failed: {type(exc).__name__}'
            print(f'❌ CV gemini [{purpose}] attempt {attempt}: {last_err}')
            time.sleep(2.0)
            continue
        elapsed = time.monotonic() - start

        if resp.status_code != 200:
            print(f'❌ CV gemini [{purpose}] attempt {attempt}: HTTP {resp.status_code}: '
                  f'{resp.text[:300]}')
            if resp.status_code == 429:
                last_err = 'rate limited'
                if attempt == 1:
                    time.sleep(3.0)
                    continue
                raise GeminiError('gemini 429', 'The AI reviewer is at capacity right now. '
                                                'Please try again in a few minutes.')
            if resp.status_code >= 500 and attempt == 1:
                last_err = f'HTTP {resp.status_code}'
                time.sleep(2.0)
                continue
            raise GeminiError(f'gemini HTTP {resp.status_code}')

        try:
            body = resp.json()
            candidate = body['candidates'][0]
            raw = ''.join(p.get('text', '') for p in candidate['content']['parts']
                          if isinstance(p, dict))
            usage.add(purpose, model, body.get('usageMetadata'), elapsed)
            data = json.loads(_strip_code_fences(raw))
            if not isinstance(data, dict):
                raise ValueError('non-object JSON')
            return data
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            finish = ''
            try:
                finish = body.get('candidates', [{}])[0].get('finishReason', '')
            except Exception:
                pass
            print(f'❌ CV gemini [{purpose}] attempt {attempt}: bad response shape/JSON '
                  f'({type(exc).__name__}, finishReason={finish})')
            last_err = 'unparseable response'
            if attempt == 1:
                continue
    raise GeminiError(f'gemini [{purpose}]: {last_err}')
