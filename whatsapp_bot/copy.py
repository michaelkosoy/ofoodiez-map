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

# Personalised greeting sent right before the Welcome menu buttons. {name} is
# already formatted as ", Michael" (or "" if we don't know it yet).
WELCOME_GREETING = "Welcome to Ofoodiez{name}! 🧡🚀"

# ---- Phase B: registration (English v1; young & upbeat) ----
REG_FIRST_NAME = (
    "Welcome to Ofoodiez Referrals! 🧡🚀\n"
    "Let's get you set up — what's your *first name*? 🙌"
)
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
EMP_METHOD_PROMPT = (
    "How would you like to refer candidates at *{company}*? 🤝\n\n"
    "*1* 📧 *Email me* — I'll get a candidate's CV by email and refer them myself.\n"
    "*2* 🔗 *Share my referral link* — candidates get my link automatically, "
    "no work for me.\n\n"
    "Reply *1* or *2*."
)
EMP_LINK_PROMPT = (
    "Awesome — paste your *referral link* for *{company}* 🔗\n"
    "(the personal link your company gives you to refer people)."
)
EMP_LINK_INVALID = (
    "That doesn't look like a valid link 🤔\n"
    "Please paste the full *https://…* referral link."
)
ADVOCATE_LINK_DONE = (
    "Done! 🎉🔗 Your referral link for *{company}* is saved.\n"
    "Anyone who asks for a referral there will get it automatically — no work "
    "for you. 🙌\n{link}\n\n"
    "Type *menu* anytime if you'd like to do more."
)
EMP_EMAIL = (
    "Awesome — *{company}*! 💼\n"
    "Which *work email(s)* should we send candidate referrals to?\n"
    "Add a few if you like — just separate them with commas. 📧"
)
EMP_EMAIL_INVALID = (
    "Hmm, I couldn't spot a valid email there 🤔\n"
    "Mind sending it again? (e.g. you@company.com — separate a few with commas)"
)
EMP_EMAIL_PERSONAL = (
    "Looks like a personal email 🙃\n"
    "Please use your *work email at {company}* (not Gmail/Yahoo/Outlook, etc.) so "
    "we route referrals to the right inbox. 📧"
)
EMP_EMAILS_CONFIRM = (
    "Got it! 🙌 I'll send candidate referrals for *{company}* to:\n"
    "📧 {emails}\n\n"
    "Reply *yes* to confirm — or just send the right email(s) again to change them."
)
EMP_SAVE_FAILED = (
    "Hmm, I couldn't save that just now 😅 — let's try once more.\n"
    "What's your *work email* at {company}? (you can list a few, comma-separated)"
)
ADVOCATE_DONE = (
    "You're officially an Ofoodiez advocate for *{company}*! 🎉🙏\n"
    "We'll send candidate referrals to: *{emails}* ✨\n"
    "Type *menu* anytime if you'd like to do more."
)

# ---- Phase C: candidate company search ----
CAND_COMPANY = (
    "You're all set — welcome aboard! 🎉🚀\n"
    "Which company are you aiming for?"
)
CAND_WELCOME_BACK = (
    "Hey {first}, welcome back! 👋🧡\n"
    "Which company are you aiming for?"
)
CAND_REFERRAL_LINK = (
    "Great news — *{advocate}* from *{company}* shared a referral link with you! 🔗🎉\n"
    "This is a referral link by *{advocate}* from *{company}* — tap it and fill in "
    "your details:\n{link}\n\n"
    "Good luck! 🤞 Type *menu* anytime to explore more."
)
CAND_ROLE = (
    "Amazing — I found *{advocate}* at *{company}*! 🎉\n"
    "They can refer you in. What role are you aiming for? "
    "(e.g. Product Manager, Software Engineer, Analyst)"
)
CAND_JOB_LINK = "Nice — *{company}* it is! 🎯\nPaste the link to the exact job posting you want in for."
CAND_JOB_LINK_INVALID = (
    "That doesn't look like a valid link 🤔\n"
    "Please paste the full *https://* URL of the job posting."
)
CAND_JOB_DESC_PROMPT = (
    "No link? No worries 🙂\n"
    "Just *describe the role* you're after — title, team, anything that helps — "
    "and I'll pass it along."
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
    "Last step! 📄 Send your *CV as a PDF or Word doc* and I'll forward it to the advocate.\n"
    "Make it shine — tailor it to the role if you can. ✨"
)
CAND_RESUME_BAD_TYPE = (
    "I need your CV as a *PDF or Word* file (.pdf, .doc, .docx) 🙏 — attach it and send again."
)
CAND_RESUME_FAILED = "Hmm, I couldn't read that file 😕 — please try sending it again."
CAND_SUBMITTED = (
    "Done! ✅ I've forwarded your application to *{advocate}* at *{company}* — "
    "fingers crossed! 🤞🎉\n"
    "Type *menu* anytime if you'd like to do more."
)
CAND_FINISHED = "Thanks for using Ofoodiez Referrals — we're rooting for you! 🤞🧡"
