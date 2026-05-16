import os
import asyncio
import random
import time
from datetime import datetime
from typing import Optional
from pyrogram import Client, filters, raw
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from pyrogram.enums import ParseMode, PollType

# ──────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────
API_ID    = int(os.environ.get("API_ID", 0))
API_HASH  = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = Client(
    "IndianQuizBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ──────────────────────────────────────────────
#  IN-MEMORY STORAGE
# ──────────────────────────────────────────────
user_sessions: dict = {}
active_quizzes: dict = {}
user_quizzes: dict = {}

STEPS = {
    "IDLE": 0,
    "WAIT_TITLE": 1,
    "WAIT_DESC": 2,
    "WAIT_QUESTION": 3,
    "WAIT_TIME": 4,
    "WAIT_SHUFFLE": 5,
}

TIME_OPTIONS = {
    "10 sec": 10, "15 sec": 15, "30 sec": 30,
    "45 sec": 45, "1 min": 60,  "2 min": 120,
    "3 min": 180, "4 min": 240, "5 min": 300,
}

SHUFFLE_OPTIONS = ["Shuffle All", "No Shuffle", "Only Questions", "Only Answers"]


# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────
def get_session(user_id: int) -> dict:
    if user_id not in user_sessions:
        user_sessions[user_id] = {"step": STEPS["IDLE"], "quiz": {}, "questions": []}
    return user_sessions[user_id]


def reset_session(user_id: int):
    user_sessions[user_id] = {"step": STEPS["IDLE"], "quiz": {}, "questions": []}


def time_keyboard() -> ReplyKeyboardMarkup:
    keys = list(TIME_OPTIONS.keys())
    rows = [keys[i:i+3] for i in range(0, len(keys), 3)]
    return ReplyKeyboardMarkup(
        [[KeyboardButton(k) for k in row] for row in rows],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def shuffle_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Shuffle All"), KeyboardButton("No Shuffle")],
            [KeyboardButton("Only Questions"), KeyboardButton("Only Answers")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def quiz_action_keyboard(quiz_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Start This Quiz", callback_data=f"start_solo:{quiz_id}")],
        [InlineKeyboardButton("👥 Start in Group",  callback_data=f"start_group:{quiz_id}")],
        [InlineKeyboardButton("📤 Share Quiz",       callback_data=f"share:{quiz_id}")],
        [InlineKeyboardButton("✏️ Edit Quiz",        callback_data=f"edit:{quiz_id}")],
        [InlineKeyboardButton("📊 Quiz Stats",       callback_data=f"stats:{quiz_id}")],
    ])


def generate_quiz_id(user_id: int) -> str:
    return f"{user_id}_{int(time.time())}"


def find_quiz(quiz_id: str) -> Optional[dict]:
    for quizzes in user_quizzes.values():
        for q in quizzes:
            if q["id"] == quiz_id:
                return q
    return None


def apply_shuffle(questions: list, mode: str) -> list:
    qs = [q.copy() for q in questions]
    if mode in ("Shuffle All", "Only Questions"):
        random.shuffle(qs)
    if mode in ("Shuffle All", "Only Answers"):
        for q in qs:
            combined = list(zip(q["options"], range(len(q["options"]))))
            random.shuffle(combined)
            new_options, old_indices = zip(*combined)
            q["options"] = list(new_options)
            q["correct"] = list(old_indices).index(q["correct"])
    return qs


# ──────────────────────────────────────────────
#  /start — Private
# ──────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, message: Message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) > 1 and args[1].startswith("quiz_"):
        quiz_id = args[1][5:]
        await launch_quiz(client, message, quiz_id, user=message.from_user)
        return

    reset_session(user_id)
    await message.reply(
        "🇮🇳 **Welcome to IndianQuizBot!**\n\n"
        "This bot will help you **create a quiz** with a series of **multiple choice questions**.\n\n"
        "You can add extra media or text to questions and set a time limit. "
        "Once your quiz is done, you can share it to groups — or invite users "
        "to answer questions individually in the chat with the bot.\n\n"
        "_If somebody sent you a quiz link and you got here, tap_ **Create New Quiz** _to begin._",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Create New Quiz", callback_data="create_quiz")],
            [InlineKeyboardButton("🌐 Language: English", callback_data="lang_noop")],
        ]),
        parse_mode=ParseMode.MARKDOWN,
    )


# ──────────────────────────────────────────────
#  /start — Group
# ──────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.group)
async def cmd_start_group(client: Client, message: Message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("quiz_"):
        quiz_id = args[1][5:]
        await launch_quiz(client, message, quiz_id, user=message.from_user)
    else:
        me = await client.get_me()
        await message.reply(
            f"👋 Hi! I'm **IndianQuizBot**!\n\n"
            f"Create a quiz in my DM first:\n"
            f"👉 [Open IndianQuizBot](https://t.me/{me.username})\n\n"
            f"Then use **'Start in Group'** to bring it here!",
            parse_mode=ParseMode.MARKDOWN,
        )


# ──────────────────────────────────────────────
#  CALLBACKS
# ──────────────────────────────────────────────
@app.on_callback_query(filters.regex("^create_quiz$"))
async def cb_create_quiz(client, cq):
    user_id = cq.from_user.id
    sess = get_session(user_id)
    sess["step"] = STEPS["WAIT_TITLE"]
    sess["quiz"] = {}
    sess["questions"] = []
    await cq.message.reply(
        "📝 Let's create a new quiz!\n\n"
        "First, send me the **title** of your quiz\n"
        "_(e.g. 'Indian GK' or '10 questions about Bollywood')_",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN,
    )
    await cq.answer()


@app.on_callback_query(filters.regex("^lang_noop$"))
async def cb_lang(client, cq):
    await cq.answer("Language: English only", show_alert=False)


@app.on_callback_query(filters.regex(r"^open_quiz:"))
async def cb_open_quiz(client, cq):
    quiz_id = cq.data.split(":", 1)[1]
    quiz = find_quiz(quiz_id)
    if not quiz:
        await cq.answer("Quiz not found!", show_alert=True)
        return
    me = await client.get_me()
    share_link = f"https://t.me/{me.username}?start=quiz_{quiz_id}"
    await cq.message.reply(
        f"**{quiz['title']}**\n_{quiz.get('description', '')}_\n\n"
        f"✏️ {len(quiz['questions'])} question(s)  •  ⏱ {quiz['time_label']}  •  🔀 {quiz['shuffle']}\n\n"
        f"**Sharing link:**\n{share_link}",
        reply_markup=quiz_action_keyboard(quiz_id),
        parse_mode=ParseMode.MARKDOWN,
    )
    await cq.answer()


@app.on_callback_query(filters.regex(r"^start_solo:"))
async def cb_start_solo(client, cq):
    quiz_id = cq.data.split(":", 1)[1]
    await launch_quiz(client, cq.message, quiz_id, user=cq.from_user)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^start_group:"))
async def cb_start_group_cb(client, cq):
    quiz_id = cq.data.split(":", 1)[1]
    quiz = find_quiz(quiz_id)
    if not quiz:
        await cq.answer("Quiz not found!", show_alert=True)
        return
    me = await client.get_me()
    group_link = f"https://t.me/{me.username}?startgroup=quiz_{quiz_id}"
    await cq.message.reply(
        f"👥 **Start quiz in a group:**\n\n"
        f"[Tap here to add me to a group and start **'{quiz['title']}'**]({group_link})",
        parse_mode=ParseMode.MARKDOWN,
    )
    await cq.answer()


@app.on_callback_query(filters.regex(r"^share:"))
async def cb_share(client, cq):
    quiz_id = cq.data.split(":", 1)[1]
    quiz = find_quiz(quiz_id)
    if not quiz:
        await cq.answer("Quiz not found!", show_alert=True)
        return
    me = await client.get_me()
    share_link = f"https://t.me/{me.username}?start=quiz_{quiz_id}"
    await cq.message.reply(
        f"🔗 **Share this quiz:**\n\n[{quiz['title']}]({share_link})\n\nSend this link to your friends or groups!",
        parse_mode=ParseMode.MARKDOWN,
    )
    await cq.answer()


@app.on_callback_query(filters.regex(r"^edit:"))
async def cb_edit(client, cq):
    await cq.message.reply("✏️ Editing not supported yet. Recreate with /newquiz.")
    await cq.answer()


@app.on_callback_query(filters.regex(r"^stats:"))
async def cb_stats(client, cq):
    quiz_id = cq.data.split(":", 1)[1]
    quiz = find_quiz(quiz_id)
    if not quiz:
        await cq.answer("Quiz not found!", show_alert=True)
        return
    await cq.message.reply(
        f"📊 **Stats — '{quiz['title']}'**\n\n"
        f"• Questions: {len(quiz['questions'])}\n"
        f"• Total plays: {quiz.get('plays', 0)}\n"
        f"• Time limit: {quiz.get('time_label', 'N/A')}\n"
        f"• Shuffle: {quiz.get('shuffle', 'N/A')}\n"
        f"• Created: {quiz.get('created_at', 'N/A')}",
        parse_mode=ParseMode.MARKDOWN,
    )
    await cq.answer()


@app.on_callback_query(filters.regex(r"^ready:"))
async def cb_ready(client, cq):
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if chat_id not in active_quizzes:
        await cq.answer("No quiz session found.", show_alert=True)
        return

    aq = active_quizzes[chat_id]
    if user_id not in aq["ready"]:
        aq["ready"].add(user_id)
        aq["scores"][user_id] = {
            "name": cq.from_user.first_name,
            "score": 0,
            "time": 0.0,
        }

    ready_count = len(aq["ready"])
    needed = aq.get("min_players", 1)
    await cq.answer(f"You are ready! ({ready_count}/{needed})")

    try:
        await cq.message.edit_reply_markup(
            InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"✅ I am ready! ({ready_count})",
                    callback_data=f"ready:{aq['quiz_id']}"
                )
            ]])
        )
    except Exception:
        pass

    if ready_count >= needed:
        task = aq.get("timer_task")
        if task and not task.done():
            return
        aq["timer_task"] = asyncio.create_task(run_quiz(client, chat_id))


# ──────────────────────────────────────────────
#  COMMANDS
# ──────────────────────────────────────────────
@app.on_message(filters.command("newquiz") & filters.private)
async def cmd_newquiz(client: Client, message: Message):
    user_id = message.from_user.id
    sess = get_session(user_id)
    sess["step"] = STEPS["WAIT_TITLE"]
    sess["quiz"] = {}
    sess["questions"] = []
    await message.reply(
        "📝 Let's create a new quiz!\n\nFirst, send me the **title** of your quiz\n_(e.g. 'Indian GK')_",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("skip") & filters.private)
async def cmd_skip(client: Client, message: Message):
    user_id = message.from_user.id
    sess = get_session(user_id)
    if sess["step"] != STEPS["WAIT_DESC"]:
        await message.reply("Nothing to skip right now.")
        return
    sess["quiz"]["description"] = ""
    sess["step"] = STEPS["WAIT_QUESTION"]
    await message.reply(
        "✅ Description skipped.\n\nNow send me a **poll** with your first question.\n"
        "Tap 📎 → Poll → choose **Quiz** type → mark correct answer.\n\n"
        "⚠️ _Warning: This bot can't create anonymous polls._",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("undo") & filters.private)
async def cmd_undo(client: Client, message: Message):
    user_id = message.from_user.id
    sess = get_session(user_id)
    if sess["step"] == STEPS["WAIT_QUESTION"] and sess["questions"]:
        sess["questions"].pop()
        count = len(sess["questions"])
        await message.reply(
            f"↩️ Last question removed. Quiz now has **{count}** question(s).\n\nSend next or /done.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await message.reply("Nothing to undo.")


@app.on_message(filters.command("done") & filters.private)
async def cmd_done(client: Client, message: Message):
    user_id = message.from_user.id
    sess = get_session(user_id)
    if sess["step"] != STEPS["WAIT_QUESTION"]:
        await message.reply("You're not creating a quiz. Send /newquiz to start.")
        return
    if not sess["questions"]:
        await message.reply("⚠️ Add at least one question first.")
        return
    sess["step"] = STEPS["WAIT_TIME"]
    await message.reply(
        "⏱ Please set a **time limit** for questions.\n\n"
        "_We recommend 10–30 seconds for trivia._",
        reply_markup=time_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("myquizzes") & filters.private)
async def cmd_myquizzes(client: Client, message: Message):
    user_id = message.from_user.id
    quizzes = user_quizzes.get(user_id, [])
    if not quizzes:
        await message.reply("No quizzes yet. Send /newquiz to create one!")
        return
    text = "📋 **Your Quizzes:**\n\n"
    buttons = []
    for q in quizzes:
        text += f"• **{q['title']}** — {len(q['questions'])} question(s)\n"
        buttons.append([InlineKeyboardButton(f"▶️ {q['title']}", callback_data=f"open_quiz:{q['id']}")])
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("stop"))
async def cmd_stop(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id not in active_quizzes:
        await message.reply("No active quiz here.")
        return
    aq = active_quizzes[chat_id]
    task = aq.get("timer_task")
    if task and not task.done():
        task.cancel()
    await show_final_results(client, chat_id)
    active_quizzes.pop(chat_id, None)


# ──────────────────────────────────────────────
#  MAIN PRIVATE MESSAGE HANDLER
# ──────────────────────────────────────────────
EXCLUDED = ["start", "newquiz", "skip", "undo", "done", "myquizzes", "stop"]

@app.on_message(filters.private & ~filters.command(EXCLUDED))
async def handle_private(client: Client, message: Message):
    user_id = message.from_user.id
    sess = get_session(user_id)
    step = sess["step"]

    if step == STEPS["WAIT_TITLE"]:
        if not message.text:
            await message.reply("Please send the quiz title as text.")
            return
        sess["quiz"]["title"] = message.text.strip()
        sess["step"] = STEPS["WAIT_DESC"]
        await message.reply(
            f"✅ Title: **{sess['quiz']['title']}**\n\n"
            "Good. Now send me a **description** of your quiz. This is optional, you can /skip this step.",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif step == STEPS["WAIT_DESC"]:
        if not message.text:
            await message.reply("Please send text or use /skip.")
            return
        sess["quiz"]["description"] = message.text.strip()
        sess["step"] = STEPS["WAIT_QUESTION"]
        await message.reply(
            "✅ Description saved.\n\n"
            "Good. Now send me a **poll** with your first question.\n"
            "Tap 📎 → Poll → choose **Quiz** type → mark the correct answer.\n\n"
            "⚠️ _Warning: This bot can't create anonymous polls. "
            "Users in groups will see votes from other members._",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN,
        )

    elif step == STEPS["WAIT_QUESTION"]:
        if message.poll:
            poll = message.poll
            options = [opt.text for opt in poll.options]
            correct = poll.correct_option_id if poll.correct_option_id is not None else 0
            sess["questions"].append({
                "question": poll.question,
                "options": options,
                "correct": correct,
                "explanation": poll.explanation or "",
            })
            count = len(sess["questions"])
            option_lines = "\n".join(
                f"{'✅' if i == correct else '○'} {opt}" for i, opt in enumerate(options)
            )
            await message.reply(
                f"✅ Question **{count}** added!\n\n❓ {poll.question}\n{option_lines}\n\n"
                f"Your quiz **'{sess['quiz']['title']}'** now has **{count}** question(s).\n\n"
                f"If you made a mistake, send /undo.\n"
                f"Now send the next question — or some text or media that will be shown before it.\n"
                f"When done, simply send /done to finish creating the quiz.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await message.reply(
                "Please send a **poll** (tap 📎 → Poll → Quiz type) to add a question.\nOr send /done when finished.",
                parse_mode=ParseMode.MARKDOWN,
            )

    elif step == STEPS["WAIT_TIME"]:
        if message.text and message.text in TIME_OPTIONS:
            sess["quiz"]["time_limit"] = TIME_OPTIONS[message.text]
            sess["quiz"]["time_label"] = message.text
            sess["step"] = STEPS["WAIT_SHUFFLE"]
            await message.reply("🔀 Shuffle questions and answer options?", reply_markup=shuffle_keyboard())
        else:
            await message.reply("Please choose a time limit from the keyboard.", reply_markup=time_keyboard())

    elif step == STEPS["WAIT_SHUFFLE"]:
        if message.text and message.text in SHUFFLE_OPTIONS:
            sess["quiz"]["shuffle"] = message.text
            await finalize_quiz(client, message, user_id, sess)
        else:
            await message.reply("Please choose a shuffle option from the keyboard.", reply_markup=shuffle_keyboard())

    else:
        await message.reply("Send /start to begin or /newquiz to create a quiz.")


# ──────────────────────────────────────────────
#  FINALIZE QUIZ
# ──────────────────────────────────────────────
async def finalize_quiz(client: Client, message: Message, user_id: int, sess: dict):
    quiz = sess["quiz"]
    questions = sess["questions"]
    quiz_id = generate_quiz_id(user_id)
    quiz["id"] = quiz_id
    quiz["questions"] = questions
    quiz["created_at"] = datetime.now().strftime("%d-%m-%Y %H:%M")
    quiz["creator_id"] = user_id
    quiz["plays"] = 0

    if user_id not in user_quizzes:
        user_quizzes[user_id] = []
    user_quizzes[user_id].append(quiz)
    reset_session(user_id)

    me = await client.get_me()
    share_link = f"https://t.me/{me.username}?start=quiz_{quiz_id}"

    await message.reply(
        f"👍 **Quiz created!**\n\n"
        f"**{quiz['title']}**\n_{quiz.get('description', '')}_\n\n"
        f"✏️ {len(questions)} question(s)  •  ⏱ {quiz['time_label']}  •  🔀 {quiz['shuffle']}\n\n"
        f"**External sharing link:**\n{share_link}",
        reply_markup=quiz_action_keyboard(quiz_id),
        parse_mode=ParseMode.MARKDOWN,
    )
    await message.reply("Choose an action above ☝️", reply_markup=ReplyKeyboardRemove())


# ──────────────────────────────────────────────
#  LAUNCH QUIZ
# ──────────────────────────────────────────────
async def launch_quiz(client: Client, message: Message, quiz_id: str, user=None):
    quiz = find_quiz(quiz_id)
    if not quiz:
        await message.reply("❌ Quiz not found. Ask the creator to share the link again.")
        return

    chat_id = message.chat.id
    if chat_id in active_quizzes:
        await message.reply("⚠️ A quiz is already running here! Send /stop to end it first.")
        return

    quiz["plays"] = quiz.get("plays", 0) + 1
    questions = apply_shuffle(quiz["questions"], quiz.get("shuffle", "No Shuffle"))
    is_group = message.chat.type.name not in ("PRIVATE", "BOT")
    min_players = 2 if is_group else 1

    active_quizzes[chat_id] = {
        "quiz_id": quiz_id,
        "quiz": quiz,
        "questions": questions,
        "q_index": 0,
        "scores": {},
        "ready": set(),
        "poll_msg_ids": [],
        "current_poll_id": None,
        "min_players": min_players,
        "timer_task": None,
        "is_group": is_group,
        "answered": set(),
        "q_start_time": 0.0,
    }

    lobby_text = (
        f"🎮 Get ready for the quiz **'{quiz['title']}'**\n\n"
        f"_{quiz.get('description', '')}_\n\n"
        f"✏️ {len(questions)} question(s)\n"
        f"⏱ {quiz['time_label']} per question\n"
        f"👁 Votes are **visible** to "
        f"{'group members and the quiz owner' if is_group else 'the quiz owner'}\n\n"
        f"{'🏁 The quiz will begin when at least 2 people are ready to play.' if is_group else '🏁 Press the button below when you are ready.'}\n"
        f"Send /stop to stop it."
    )

    await message.reply(
        lobby_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ I am ready!", callback_data=f"ready:{quiz_id}")
        ]]),
        parse_mode=ParseMode.MARKDOWN,
    )

    if not is_group and user:
        aq = active_quizzes[chat_id]
        aq["ready"].add(user.id)
        aq["scores"][user.id] = {"name": user.first_name, "score": 0, "time": 0.0}
        aq["timer_task"] = asyncio.create_task(run_quiz(client, chat_id))


# ──────────────────────────────────────────────
#  RUN QUIZ
# ──────────────────────────────────────────────
async def run_quiz(client: Client, chat_id: int):
    aq = active_quizzes.get(chat_id)
    if not aq:
        return

    questions = aq["questions"]
    quiz = aq["quiz"]
    time_limit = quiz["time_limit"]

    for idx, q in enumerate(questions):
        if chat_id not in active_quizzes:
            return

        aq = active_quizzes[chat_id]
        aq["q_index"] = idx
        aq["answered"] = set()

        try:
            poll_msg = await client.send_poll(
                chat_id=chat_id,
                question=f"[{idx+1}/{len(questions)}] {q['question']}",
                options=q["options"],
                type=PollType.QUIZ,
                correct_option_id=q["correct"],
                explanation=q.get("explanation") or None,
                is_anonymous=False,
                open_period=time_limit,
            )
            aq["current_poll_id"] = poll_msg.poll.id
            aq["poll_msg_ids"].append(poll_msg.id)
            aq["q_start_time"] = time.time()
        except Exception as e:
            print(f"[IndianQuizBot] Poll error: {e}")
            continue

        await asyncio.sleep(time_limit + 1)

        if chat_id not in active_quizzes:
            return

    await show_final_results(client, chat_id)
    active_quizzes.pop(chat_id, None)


# ──────────────────────────────────────────────
#  POLL ANSWER HANDLER — via raw update
# ──────────────────────────────────────────────
@app.on_raw_update()
async def handle_raw_update(client: Client, update, users, chats):
    # UpdateMessagePollVote is fired when a user votes in a quiz/poll
    if not isinstance(update, raw.types.UpdateMessagePollVote):
        return

    poll_id = str(update.poll_id)
    option_ids = [opt for opt in update.options]  # list of bytes
    user_id = update.user_id

    # Get user's first name
    user_name = "Unknown"
    if user_id in users:
        u = users[user_id]
        user_name = u.first_name or "Unknown"

    for chat_id, aq in list(active_quizzes.items()):
        if str(aq.get("current_poll_id", "")) != poll_id:
            continue
        if user_id in aq["answered"]:
            return
        aq["answered"].add(user_id)

        q = aq["questions"][aq["q_index"]]
        if user_id not in aq["scores"]:
            aq["scores"][user_id] = {
                "name": user_name,
                "score": 0,
                "time": 0.0,
            }

        # option_ids is a list of bytes; each byte encodes the chosen option index
        if option_ids:
            chosen = option_ids[0]
            # Pyrogram raw: option is bytes b'\x00', b'\x01', etc.
            chosen_index = chosen[0] if isinstance(chosen, (bytes, bytearray)) else int(chosen)
            if chosen_index == q["correct"]:
                elapsed = round(time.time() - aq.get("q_start_time", time.time()), 1)
                aq["scores"][user_id]["score"] += 1
                aq["scores"][user_id]["time"] += elapsed
        break


# ──────────────────────────────────────────────
#  FINAL RESULTS
# ──────────────────────────────────────────────
async def show_final_results(client: Client, chat_id: int):
    aq = active_quizzes.get(chat_id)
    if not aq:
        return

    scores = aq["scores"]
    quiz = aq["quiz"]
    total_q = len(aq["questions"])

    sorted_scores = sorted(scores.items(), key=lambda x: (-x[1]["score"], x[1]["time"]))
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, data) in enumerate(sorted_scores):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} **{data['name']}** — {data['score']}/{total_q} ({data['time']}s)")

    await client.send_message(
        chat_id,
        f"🏁 The quiz **'{quiz['title']}'** has finished!\n\n"
        f"_{total_q} question(s) answered_\n\n"
        + ("\n".join(lines) if lines else "_No answers recorded._")
        + "\n\n🏆 Congratulations to the winners!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📤 Share Quiz", callback_data=f"share:{aq['quiz_id']}")
        ]]),
        parse_mode=ParseMode.MARKDOWN,
    )


# ──────────────────────────────────────────────
#  START
# ──────────────────────────────────────────────
print("🇮🇳 IndianQuizBot starting...")
app.run()
