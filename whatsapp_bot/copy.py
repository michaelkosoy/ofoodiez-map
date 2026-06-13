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
    "Reach us at *hello@ofoodiez.com* or DM us on Instagram *@ofoodiez* 🧡\n"
    "Type *menu* anytime to start over."
)
