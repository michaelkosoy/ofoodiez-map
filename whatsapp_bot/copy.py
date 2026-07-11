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

# Sent right before the Welcome menu buttons. WELCOME_INTRO greets a brand-new
# user, explains in ~2 sentences what the bot does, and notes they can switch
# routes / type menu anytime; WELCOME_BACK is the shorter returning-user version.
# {name} is already formatted as ", Michael" (or "" if we don't know it yet).
WELCOME_INTRO = (
    "👋 *Welcome to Ofoodiez Referrals!*\n"
    "I connect you with real people inside companies — find someone who can "
    "refer *you* for a job, or, if you're already working, refer great people in. 🧡\n"
    "You can switch routes or type *menu* anytime.\n\n"
    "What brings you here today? 👇"
)
WELCOME_BACK = (
    "Welcome back{name}! 🧡\n"
    "What would you like to do? (type *menu* anytime) 👇"
)
# Short by-name hello sent right before the shared WA_CT_WELCOME template (which
# says welcome again itself — intentional, per Ofir). Unused once the
# WA_CT_WELCOME_BACK template (name inside the template) is configured.
WELCOME_HI = "Welcome back, {name}! 🧡"

# ---- Phase B: registration (English v1; young & upbeat) ----
REG_FIRST_NAME = (
    "Awesome — let's get to know each other first! 🙌\n"
    "What's your *first name*?"
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
    "Reach us at *info@ofoodiez.com* or DM us on Instagram *@ofoodiez* 🧡\n"
    "Type *menu* anytime to start over."
)
# ---- Signed-in user: edit your own details ----
PROFILE_MENU = (
    "Your details 👤\n"
    "• Name: {name}\n"
    "• Email: {email}\n\n"
    "Reply *name* or *email* to update one · *menu* to go back."
)
PROFILE_NAME_PROMPT = "What should I set your *name* to? (first + last)"
PROFILE_EMAIL_PROMPT = "What's your *email*?"
PROFILE_EMAIL_INVALID = (
    "Hmm, that doesn't look like an email 🤔\n"
    "Try again — e.g. *you@example.com*."
)

# ---- Employee / advocate registration ----
EMP_FIRST_NAME = "Awesome — let's set you up as an advocate! 🙌\nWhat's your *first name*?"
EMP_LAST_NAME = "Nice to meet you, {first}! 😄\nAnd your *last name*?"
EMP_COMPANY = "Which company do you work at (and can refer candidates into)? 🏢"
EMP_TITLE = (
    "Got it — *{company}*! 💼\n"
    "What's your *role/title* there? This lets me match you to candidates looking "
    "for that role (e.g. DevOps, Data Scientist, Product Manager).\n"
    "No title? Reply *skip*."
)
# One combined question (name + family name + title) so advocates skip several
# steps. The work email is asked separately, in the email method.
EMP_DETAILS = (
    "Great — *{company}*! 💼\n"
    "In *one message*, tell me your *full name* and your *title*:\n"
    "e.g. *Gil Zohar, DevOps Manager*"
)
EMP_DETAILS_CONFIRM = (
    "Got it 👇\n"
    "• Name: {name}\n"
    "• Title: {title}\n\n"
    "Looks right? Reply *yes* — or just *resend* to fix it."
)
# ---- Employee: edit an existing submission ----
EMP_EDIT_MENU = (
    "You're set up to refer for *{company}* 💼\n"
    "{details}\n\n"
    "Reply *title*, *link*, or *email* to change one · *remove* to remove this "
    "referral · *add* for another company · *menu* to exit."
)
EMP_EDIT_LIST = (
    "You're an advocate for a few companies 💼\n"
    "{companies}\n\n"
    "Reply the *number* to edit one, *add* for a new company, or *menu*."
)
EMP_EDIT_TITLE = (
    "What's your *role/title* at *{company}* now? "
    "(or *skip* to clear it)"
)
EMP_EDIT_REMOVE_CONFIRM = (
    "Remove your *{company}* referral? Candidates will no longer be sent to you for it.\n"
    "Reply *yes* to confirm, or *menu* to keep it."
)
EMP_EDIT_REMOVED = (
    "Done — your *{company}* referral is removed. 🙌\n"
    "Thanks for being an advocate! Type *menu* anytime."
)
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
# Appended wherever we ask for a company name — the live list of companies
# with advocates, for candidates who don't have a specific one in mind.
_COMPANIES_LIST_LINE = (
    "Not sure which?\n"
    "Browse the companies we have advocates in:\n"
    "https://ofoodiez.com/hitech/referrals-bot"
)
CAND_COMPANY = (
    "You're all set — welcome aboard! 🎉🚀\n"
    "Which company are you aiming for?\n"
    + _COMPANIES_LIST_LINE
)
CAND_WELCOME_BACK = (
    "Hey {first}, welcome back! 👋🧡\n"
    "Which company are you aiming for?\n"
    + _COMPANIES_LIST_LINE
)
CAND_REFERRAL_LINK = (
    "Great news — *{advocate}* from *{company}* shared a referral link with you! 🔗🎉\n"
    "This is a referral link by *{advocate}* from *{company}* — tap it and fill in "
    "your details:\n{link}\n\n"
    "Aiming for a *different role* at *{company}*? Tell me the role and I'll take your "
    "CV and pass it to the team too. All set? Type *menu* anytime. 🤞"
)
CAND_REFERRAL_LINK_NONAME = (
    "Great news — here's a referral link for *{company}*! 🔗🎉\n"
    "Tap it and fill in your details:\n{link}\n\n"
    "Aiming for a *different role* at *{company}*? Tell me the role and I'll take your "
    "CV and pass it to the team too. All set? Type *menu* anytime. 🤞"
)
CAND_REFERRAL_LINK_TITLED = (
    "Great news — I found a *{title}* referral at *{company}*! 🔗🎉\n"
    "Tap it and fill in your details:\n{link}\n\n"
    "Aiming for a *different role* at *{company}*? Tell me the role and I'll take your "
    "CV and pass it to the team too. All set? Type *menu* anytime. 🤞"
)
CAND_REFERRAL_LINK_TITLED_NAMED = (
    "Great news — *{name}*, a *{title}* at *{company}*, can refer you! 🔗🎉\n"
    "Tap their referral link and fill in your details:\n{link}\n\n"
    "Aiming for a *different role* at *{company}*? Tell me the role and I'll take your "
    "CV and pass it to the team too. All set? Type *menu* anytime. 🤞"
)
CAND_ROLE_MATCH = (
    "Great — *{company}*! 🎯\n"
    "What *role* are you aiming for? I'll match you to the right person there "
    "(e.g. DevOps, Data Scientist, Product Manager)."
)
CAND_AFTER_LINK_ROLE = (
    "Sure! Which *role* are you aiming for? "
    "Tell me and I'll grab your CV next. 🎯"
)
CAND_ROLE = (
    "Amazing — I found *{advocate}* at *{company}*! 🎉\n"
    "They can refer you in. What role are you aiming for? "
    "(e.g. Product Manager, Software Engineer, Analyst)"
)
CAND_JOB_LINK = (
    "Nice — *{company}* it is! 🎯\n"
    "Paste the *link to the exact job posting* you want — from *{company}*'s careers "
    "page or its *LinkedIn* listing. This is required so your advocate refers you to "
    "the right role. 🔗"
)
CAND_JOB_LINK_REQUIRED = (
    "I need the *actual link* to the job posting to continue 🙏\n"
    "Paste the URL from the company's careers page or LinkedIn — it should start "
    "with *http*."
)
CAND_DID_YOU_MEAN_ONE = (
    "Hmm, I couldn't find an exact match 🤔\n"
    "Did you mean *{company}*? Reply *yes* to pick it, or type another company name."
)
CAND_DID_YOU_MEAN_MANY = (
    "Hmm, I couldn't find an exact match 🤔\n"
    "Did you mean one of these?\n{options}\n\n"
    "Reply with the *number*, or type another company name."
)
CAND_NO_ADVOCATES = (
    "We know *{company}*, but there's no advocate there *yet* 😕\n"
    "I've logged your request — we'll *message you the moment we have someone* "
    "who can refer you there. 🙌\n"
    "Meanwhile, want to try another company?"
)
CAND_NOT_FOUND = (
    "Hmm, I couldn't find *{company}* yet 🤔\n"
    "I've flagged it for our team — we'll *let you know the moment we've got "
    "someone there* who can refer you. 🙌\n"
    "Double-check the spelling (English works best), or try another company."
)
CAND_COMPANY_VAGUE = (
    "I connect you to a real person *inside a specific company*, so I need the "
    "company's *exact name* — not a role, a field, or something like 'high tech', "
    "'startups' or 'all'. 🙏\n"
    "Which company would you like a referral to? (e.g. *Google*, *Wix*, *Elbit*)\n"
    + _COMPANIES_LIST_LINE + "\n"
    "Type *menu* to go back."
)
CAND_RESUME_SOON = (
    "Awesome — you're almost there! 🙌\n"
    "The final step (sending your résumé to the advocates) is landing very soon. 🔜"
)
CAND_RESUME_PROMPT = (
    "Last step! 📄 Send your *CV as a PDF* and I'll forward it to the advocate.\n"
    "Make it shine — tailor it to the role if you can. ✨\n"
    "Not sure about your CV? We've got a guide for you:\n"
    "https://ofoodiez.com/hitech/cv-guide"
)
CAND_RESUME_BAD_TYPE = (
    "I need your CV as a *PDF* file 🙏 — attach it and send again."
)
CAND_RESUME_FAILED = "Hmm, I couldn't read that file 😕 — please try sending it again."
CAND_SUBMITTED = (
    "Done! ✅ I've forwarded your application to *{advocate}* at *{company}* — "
    "fingers crossed! 🤞🎉\n"
    "Type *menu* anytime if you'd like to do more."
)
CAND_FINISHED = "Thanks for using Ofoodiez Referrals — we're rooting for you! 🤞🧡"
ADVOCATE_PING = (
    "Hey {advocate}! 🎉 *{candidate}* just asked you to refer them for "
    "*{role}* at *{company}*.\n"
    "We've emailed the full application with their CV to {email} — "
    "take a look when you get a chance. Thanks for being an advocate! 🙏"
)
