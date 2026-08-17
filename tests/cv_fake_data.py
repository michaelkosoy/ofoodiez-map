"""Scripted model outputs for pipeline tests — a FakeModel stands in for
Gemini so every enforcement path is tested deterministically and offline."""
from cv_review.schemas import RULES


class FakeModel:
    """Callable matching gemini.generate_json's signature. Responses keyed by
    purpose prefix ('extract', 'critic', 'optimize', 'repair'); values are
    dicts or callables(parts)->dict."""

    def __init__(self, responses):
        self.responses = responses
        self.purposes = []

    def __call__(self, parts, schema, *, purpose, usage, key, **kw):
        self.purposes.append(purpose)
        usage.add(purpose, 'fake-model',
                  {'promptTokenCount': 100, 'candidatesTokenCount': 200}, 0.01)
        for prefix in ('repair', 'critic_optimized', 'critic', 'optimize', 'extract'):
            if purpose.startswith(prefix) and prefix in self.responses:
                r = self.responses[prefix]
                out = r(parts) if callable(r) else r
                import copy
                return copy.deepcopy(out)
        raise AssertionError(f'no fake response for purpose {purpose}')


def make_extraction(name='Jane Smith', confidence=0.98,
                    location_raw='12 Dizengoff Street, Apt 3, Tel Aviv 6433212',
                    city='Tel Aviv', country='Israel',
                    skills=('Python', 'PostgreSQL', 'Kafka'),
                    bullets=('Built REST APIs in Python serving 6,000 users',
                             'Designed PostgreSQL schemas and Kafka pipelines'),
                    is_cv=True):
    return {
        'is_cv': is_cv,
        'candidate_name': {'full_name': name, 'confidence': confidence,
                           'source_text': name or ''},
        'contact': {'email': 'jane@example.com', 'phone': '+972-50-0000000',
                    'location_raw': location_raw, 'city': city, 'country': country,
                    'links': [{'label': 'GitHub', 'url': 'github.com/janesmith'}]},
        'title': 'Backend Software Engineer',
        'summary': 'Backend engineer working with Python, PostgreSQL and Kafka.',
        'skills': [{'name': s, 'source_text': f'Skills: {s}'} for s in skills],
        'experience': [{'company': 'Acme', 'title': 'Backend Engineer',
                        'dates': '2023-2025', 'bullets': list(bullets)}],
        'projects': [{'name': 'TinyURL clone', 'description': 'URL shortener in Python',
                      'link': 'github.com/janesmith/tinyurl'}],
        'education': [{'institution': 'TAU', 'degree': 'B.Sc. Computer Science',
                       'dates': '2020-2023'}],
        'extras': [],
        'flags': {'has_photo': False, 'language': 'en', 'self_ratings': False,
                  'emphasized_technologies': False, 'page_count_estimate': 2},
    }


def make_critic(quality=68, jd_match=61):
    return {
        'rules_checklist': [{'rule': r, 'status': 'partial', 'note': 'הערה'}
                            for r in RULES],
        'quality_score': quality,
        'jd_match': jd_match,
        'verdict': 'קורות חיים סבירים עם מקום לשיפור.',
        'strengths': ['פרויקטים עם קישורים', 'טכנולוגיות רלוונטיות', 'ניסיון אמיתי'],
        'improvements': [{'area': 'פתיחה', 'issue': 'אין פסקת פתיחה',
                          'fix': 'הוסיפו פסקת פתיחה', 'before': '',
                          'rewrite': 'Backend engineer with Python experience.'}],
        'action_items': ['הוסיפו פסקת פתיחה', 'קצרו לעמוד אחד',
                         'הדגישו טכנולוגיות', 'הוסיפו מספרים'],
    }


def make_optimizer(name='Jane Smith', summary='Backend engineer skilled in Python, PostgreSQL and Kafka.',
                   skills=('Python', 'PostgreSQL', 'Kafka'),
                   bullets=('Built REST APIs in Python serving 6,000 users',
                            'Designed PostgreSQL schemas and Kafka pipelines'),
                   location='Tel Aviv', not_evidenced=(), recs=(), extra_changes=()):
    return {
        'optimized_cv': {
            'name': name, 'title': 'Backend Software Engineer',
            'location': location, 'email': 'jane@example.com', 'phone': '+972-50-0000000',
            'links': [{'label': 'GitHub', 'url': 'github.com/janesmith'}],
            'summary': summary,
            'skills_groups': [{'group': 'Backend', 'skills': list(skills)}],
            'experience': [{'company': 'Acme', 'title': 'Backend Engineer',
                            'dates': '2023-2025', 'bullets': list(bullets)}],
            'projects': [{'name': 'TinyURL clone', 'tech': 'Python',
                          'description': 'URL shortener in Python',
                          'link': 'github.com/janesmith/tinyurl'}],
            'education': [{'institution': 'TAU', 'degree': 'B.Sc. Computer Science',
                           'dates': '2020-2023'}],
            'extras': [],
        },
        'changes': [{'change_type': 'rewrite', 'section': 'experience',
                     'before': 'Responsible for APIs', 'after': bullets[0],
                     'reason': 'ניסוח תוצאה במקום אחריות', 'evidence_refs': ['claim_001']},
                    {'change_type': 'keep', 'section': 'education',
                     'before': 'B.Sc.', 'after': 'B.Sc.',
                     'reason': 'רלוונטי כמו שהוא', 'evidence_refs': []}]
                   + list(extra_changes),
        'jd_analysis': {'strong_matches': ['Python', 'PostgreSQL'],
                        'surfaced': ['Kafka'],
                        'not_evidenced': list(not_evidenced)},
        'career_recommendations': list(recs),
    }


K8S_REC = {'skill': 'Kubernetes', 'priority': 'high', 'reason_type': 'target_job_gap',
           'reason': 'המשרה דורשת במפורש Kubernetes, וזה לא נראה בקורות החיים שהעלית.',
           'cv_evidence': 'not_found',
           'recommendation': 'פרסו שירות מבוסס קונטיינרים ל-Kubernetes ולמדו Deployments ו-Services.',
           'cv_instruction': 'לא להוסיף לקורות החיים עד שיש ניסיון אמיתי.'}

JOB = {'job_title': 'Senior Backend Engineer',
       'job_description': 'We need Python, PostgreSQL, Kafka and Kubernetes. AWS is a plus.',
       'instructions': '', 'removed_urls': []}

NO_JOB = {'job_title': '', 'job_description': '', 'instructions': '', 'removed_urls': []}
