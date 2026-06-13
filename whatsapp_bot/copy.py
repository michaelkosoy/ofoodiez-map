"""Bilingual (en/he) message strings for the WhatsApp bot.

Pure data, no logic — so adjusting wording never touches business logic.
Keys are language codes ('en', 'he'); see plan §5.
"""

HELP = {
    "en": (
        "Ofoodiez Referrals 💼\n"
        "• Send a company name to find referral links (e.g. Google)\n"
        "• Reply with a number to get a link\n"
        "• Add a link: add <company> <url> [role]"
    ),
    "he": (
        "הפניות Ofoodiez 💼\n"
        "• שלח/י שם חברה כדי למצוא קישורי הפניה (למשל Google)\n"
        "• השב/י עם מספר כדי לקבל קישור\n"
        "• הוספת קישור: הוסף <חברה> <כתובת> [תפקיד]"
    ),
}

# Friendly fallback shown when the handler hits an unexpected error (DB down,
# etc.). Mirrors the home() graceful-degradation pattern.
ERROR = {
    "en": "We're having a hiccup, please try again in a moment 🙏",
    "he": "יש לנו תקלה קטנה, נסה/י שוב בעוד רגע 🙏",
}

# ---- Phase B: registration (English v1; young & upbeat) ----
REG_FIRST_NAME = "Awesome — let's get you set up! 🙌\nWhat's your *first name*?"
REG_LAST_NAME = "Nice to meet you, {first}! 😄\nAnd your *last name*?"
REG_EMAIL = "Almost there, {first}! 📧\nWhat's the best *email* to reach you at?"
REG_EMAIL_INVALID = (
    "Hmm, that doesn't look like an email 🤔\n"
    "Mind trying again? (e.g. you@example.com)"
)
REG_EDIT = "No worries — let's redo it ✏️\nWhat's your *first name*?"
REGISTERED_CANDIDATE = (
    "You're all set — welcome aboard! 🎉🚀\n"
    "Next we'll help you find your dream company and the right person inside — "
    "that part's landing very soon. 🔜"
)
REGISTERED_EMPLOYEE = (
    "You're in — thanks for being an advocate! 🙏✨\n"
    "Setting you up to refer awesome candidates is coming very soon. 🔜"
)
MAIN_COMING_SOON = (
    "That part of the journey is coming very soon! 🔜\n"
    "Type *menu* to head back to the start."
)
CONTACT_INFO = (
    "We'd love to hear from you! 💬\n"
    "Reach us at *contact@ofoodiez.com* or DM us on Instagram *@ofoodiez* 🧡\n"
    "Type *menu* anytime to start over."
)

# ---- Employee / advocate registration ----
EMP_FIRST_NAME = "Awesome — let's set you up as an advocate! 🙌\nWhat's your *first name*?"
EMP_LAST_NAME = "Nice to meet you, {first}! 😄\nAnd your *last name*?"
EMP_COMPANY = "Which company do you work at (and can refer candidates into)? 🏢"
EMP_EMAIL = (
    "Great — *{company}*! 💼\n"
    "What's the best *email at {company}* to receive candidate applications?"
)
EMP_EMAIL_INVALID = "Hmm, that doesn't look like an email 🤔\nMind trying again? (e.g. you@company.com)"
ADVOCATE_DONE = (
    "You're officially an Ofoodiez advocate for *{company}*! 🎉🙏\n"
    "We'll send candidate applications straight to *{email}*. ✨"
)

# ---- Phase C: candidate company search ----
CAND_COMPANY = (
    "You're all set — welcome aboard! 🎉🚀\n"
    "Which company are you aiming for?"
)
CAND_ROLE = (
    "Great news — we've got advocates at *{company}*! 🎉\n"
    "What role are you aiming for? (e.g. Product Manager, Software Engineer, Analyst)"
)
CAND_JOB_LINK = "Nice — *{company}* it is! 🎯\nPaste the link to the exact job posting you want in for."
CAND_JOB_LINK_INVALID = (
    "That doesn't look like a valid link 🤔\n"
    "Please paste the full *https://* URL of the job posting."
)
CAND_NO_ADVOCATES = (
    "We know *{company}*, but there are no advocates there *yet* 😕\n"
    "We've put it on our radar — check back soon, or try another company. 🔜"
)
CAND_NOT_FOUND = (
    "Hmm, couldn't find *{company}* yet 🤔\n"
    "Double-check the spelling (English works best), or type another company — "
    "we've flagged it for our team to add! 🔜"
)
CAND_RESUME_SOON = (
    "Awesome — you're almost there! 🙌\n"
    "The final step (sending your résumé to the advocates) is landing very soon. 🔜"
)
CAND_RESUME_PROMPT = (
    "Last step! 📄 Send your résumé as a *PDF* and we'll get it to the advocates.\n"
    "Make it shine — tailor it to the role if you can. ✨"
)
CAND_RESUME_NOT_PDF = "I need your résumé as a *PDF file* 🙏 — attach the PDF and send again."
CAND_RESUME_FAILED = "Hmm, I couldn't read that file 😕 — please try sending the PDF again."
CAND_SUBMITTED = (
    "Sent to *{n}* advocate(s) — fingers crossed! 🤞🎉\n"
    "Type another company to line up more, or *menu* to finish."
)
CAND_FINISHED = "Thanks for using Ofoodiez Referrals — we're rooting for you! 🤞🧡"
