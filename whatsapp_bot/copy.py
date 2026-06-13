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
