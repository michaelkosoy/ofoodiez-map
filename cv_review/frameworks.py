"""Small, versioned role-skill recommendation framework.

Used ONLY when no job description is supplied, to keep the model's
career-development suggestions inside a controlled vocabulary instead of
letting it invent random skill lists. This is a RECOMMENDATION framework —
it is not proof of labor-market demand, and prompts must never present it
as such (no "90% of jobs require X" claims).
"""

FRAMEWORK_VERSION = 'v1-2026-08'

FRAMEWORKS = {
    'Backend Engineer': {
        'language depth': ['Python', 'Java', 'Go', 'Node.js', 'C#'],
        'databases': ['PostgreSQL', 'MySQL', 'MongoDB', 'Redis'],
        'API design': ['REST', 'GraphQL', 'gRPC'],
        'testing': ['unit testing', 'integration testing'],
        'cloud': ['AWS', 'GCP', 'Azure'],
        'containers': ['Docker'],
        'orchestration': ['Kubernetes'],
        'messaging / event systems': ['Kafka', 'RabbitMQ', 'SQS'],
        'observability': ['structured logging', 'metrics', 'tracing'],
        'CI/CD': ['GitHub Actions', 'Jenkins', 'CI/CD pipelines'],
        'system design / distributed systems': ['caching', 'queueing', 'horizontal scaling'],
    },
    'Frontend Engineer': {
        'framework depth': ['React', 'Vue', 'Angular'],
        'language depth': ['TypeScript', 'modern JavaScript'],
        'styling / layout': ['CSS', 'responsive design', 'accessibility'],
        'state & data': ['state management', 'REST/GraphQL consumption'],
        'testing': ['component testing', 'end-to-end testing'],
        'performance': ['bundle optimization', 'Core Web Vitals'],
        'tooling': ['Vite/Webpack', 'CI/CD'],
    },
    'Full Stack Engineer': {
        'frontend': ['React', 'TypeScript'],
        'backend': ['Node.js', 'Python', 'API design'],
        'databases': ['PostgreSQL', 'MongoDB'],
        'cloud & deployment': ['AWS', 'Docker', 'CI/CD'],
        'testing': ['unit testing', 'end-to-end testing'],
    },
    'DevOps / Platform Engineer': {
        'cloud': ['AWS', 'GCP', 'Azure'],
        'infrastructure as code': ['Terraform', 'Pulumi'],
        'containers & orchestration': ['Docker', 'Kubernetes'],
        'CI/CD': ['GitHub Actions', 'ArgoCD', 'Jenkins'],
        'observability': ['Prometheus', 'Grafana', 'alerting'],
        'scripting': ['Bash', 'Python'],
        'networking & security basics': ['DNS', 'TLS', 'IAM'],
    },
    'Data Engineer': {
        'languages': ['Python', 'SQL'],
        'pipelines / orchestration': ['Airflow', 'dbt'],
        'processing': ['Spark', 'Kafka'],
        'warehouses': ['BigQuery', 'Snowflake', 'Redshift'],
        'data modeling': ['dimensional modeling', 'data quality checks'],
        'cloud': ['AWS', 'GCP'],
    },
    'Security Researcher': {
        'fundamentals': ['networking', 'operating systems', 'web security'],
        'tooling': ['Burp Suite', 'IDA/Ghidra', 'scripting in Python'],
        'practice': ['CTF participation', 'vulnerability write-ups'],
        'application security': ['OWASP Top 10', 'secure code review'],
        'certifications / structured learning': ['OSCP-style labs'],
    },
    'Product Manager': {
        'discovery & research': ['user interviews', 'market analysis'],
        'analytics': ['SQL basics', 'product analytics tools', 'A/B testing'],
        'delivery': ['roadmapping', 'agile execution'],
        'communication': ['PRD writing', 'stakeholder alignment'],
        'technical fluency': ['API basics', 'working with engineers'],
    },
    'Product Designer': {
        'craft': ['Figma', 'design systems', 'prototyping'],
        'research': ['usability testing', 'user interviews'],
        'delivery': ['developer handoff', 'accessibility'],
        'communication': ['case studies', 'portfolio storytelling'],
    },
}

_KEYWORDS = {
    'Backend Engineer': ['backend', 'back-end', 'server', 'api'],
    'Frontend Engineer': ['frontend', 'front-end', 'react', 'ui developer'],
    'Full Stack Engineer': ['full stack', 'fullstack', 'full-stack'],
    'DevOps / Platform Engineer': ['devops', 'platform', 'sre', 'infrastructure'],
    'Data Engineer': ['data engineer', 'etl', 'data pipeline'],
    'Security Researcher': ['security', 'cyber', 'pentest', 'appsec'],
    'Product Manager': ['product manager', ' pm ', 'product owner'],
    'Product Designer': ['designer', 'ux', 'ui/ux', 'product design'],
}


def framework_for(role_text):
    """Best-effort match of a free-text role/title to a framework family.
    Falls back to Backend Engineer (the product's main junior audience)."""
    text = f' {(role_text or "").lower()} '
    for family, words in _KEYWORDS.items():
        if any(w in text for w in words):
            return family, FRAMEWORKS[family]
    return 'Backend Engineer', FRAMEWORKS['Backend Engineer']
