from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Language map ───────────────────────────────────────────────
LANGUAGES = {
    "Hindi": "hi", "English": "en", "Urdu": "ur", "Bengali": "bn",
    "Punjabi": "pa", "Tamil": "ta", "Telugu": "te", "Marathi": "mr",
    "Gujarati": "gu", "Kannada": "kn", "Malayalam": "ml", "Odia": "or",
    "Arabic": "ar", "Russian": "ru", "French": "fr", "Spanish": "es",
    "German": "de", "Japanese": "ja", "Korean": "ko", "Chinese": "zh-CN",
    "Turkish": "tr", "Persian": "fa", "Indonesian": "id", "Portuguese": "pt",
}

# ── Start message ──────────────────────────────────────────────
START_TEXT = """**Hey {name}! 👋**

Main ek AI-powered chatbot hoon jo aapse bilkul insaanon jaisi baatein karta hai.

╔═══════════════════╗
  ✦ Mujhe group mein add karo
  ✦ Direct baat karo private mein
  ✦ Language set karo apni marzi se
╚═══════════════════╝

**Total Users:** `{users}`
**Total Chats:** `{chats}`
**Uptime:** `{uptime}`"""

# ── Help text ──────────────────────────────────────────────────
HELP_TEXT = """**📋 Commands List**

**Chatbot:**
› /chatbot — Enable / Disable bot in group
› /lang — Chat ki language set karo
› /resetlang — Language default pe reset karo
› /ask [sawaal] — AI se seedha sawaal poocho

**Info:**
› /start — Bot ko wake up karo
› /help — Yeh menu dekho
› /ping — Bot ka response time
› /id — Apna / chat ka ID dekho
› /stats — Bot ke stats dekho

**Owner Only:**
› /broadcast — Sab chats/users ko message
› /addsudo — Sudo user add karo
› /rmsudo — Sudo user hatao
› /sudolist — Sudo users dekho"""

# ── Buttons ────────────────────────────────────────────────────
def start_buttons(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{username}?startgroup=true")],
        [
            InlineKeyboardButton("📋 Help", callback_data="help"),
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ],
        [InlineKeyboardButton("❌ Close", callback_data="close")],
    ])

def help_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="start")],
        [InlineKeyboardButton("❌ Close", callback_data="close")],
    ])

def chatbot_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Enable", callback_data="cb_enable"),
            InlineKeyboardButton("❌ Disable", callback_data="cb_disable"),
        ],
    ])

def language_buttons() -> InlineKeyboardMarkup:
    buttons, row = [], []
    for name, code in LANGUAGES.items():
        row.append(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🚫 No Language (Mix)", callback_data="lang_nolang")])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    return InlineKeyboardMarkup(buttons)
