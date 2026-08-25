import random
import string
import sqlite3
import re
import asyncio
import json
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================= TOKEN =================
TOKEN = "8895185587:AAFf-4_gczmpqH7oH_KAj886Kj5dfbda5xI"

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    action TEXT,
    raw TEXT,
    staff TEXT,
    time TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reply_map (
    chat_id INTEGER,
    message_id INTEGER,
    username TEXT,
    PRIMARY KEY(chat_id, message_id)
)
""")
conn.commit()

# ================= MEMORY =================
user_cache = {}

# ================= ALO SYSTEM =================
pending_alerts = {}

# ===== LOAD AFTER RESTART =====
def load_pending():
    global pending_alerts
    try:
        with open("pending.json", "r", encoding="utf-8") as f:
            pending_alerts = {int(k): v for k, v in json.load(f).items()}
    except:
        pending_alerts = {}

load_pending()

def save_pending():
    try:
        with open("pending.json", "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in pending_alerts.items()}, f, ensure_ascii=False)
    except:
        pass


# ================= SQLITE REPLY MAP =================
def save_reply(chat_id, message_id, username):
    cursor.execute("""
        INSERT OR REPLACE INTO reply_map(chat_id, message_id, username)
        VALUES (?, ?, ?)
    """, (chat_id, message_id, username))
    conn.commit()


def get_reply(chat_id, message_id):
    cursor.execute("""
        SELECT username FROM reply_map
        WHERE chat_id=? AND message_id=?
    """, (chat_id, message_id))
    row = cursor.fetchone()
    return row[0] if row else None


# ================= AUTO ALO =================
def gen_login():
    letters = "abcdefghijkmnpqrstuvwxyz"
    numbers = "123456789"

    return (
        random.choice(numbers) +  # 1
        random.choice(numbers) +  # 2
        random.choice(numbers) +  # 3
        random.choice(letters) +  # 4
        random.choice(numbers) +  # 5
        random.choice(numbers) +  # 6
        random.choice(numbers) +  # 7
        random.choice(letters)    # 8
    )

def gen_withdraw():
    numbers = random.sample("0123456789", 4)
    return ''.join(numbers)

# ================= TEXT =================
def get_text(update):
    m = update.message
    return (m.text or m.caption or "") if m else ""


# ================= USERNAME (FIXED) =================
def extract_username(text, update=None):
    text = text or ""
    chat_id = update.effective_chat.id if update else None

    account = None

    # 1. Ưu tiên bắt STK nếu có chữ "stk"
    stk_match = re.search(
        r'stk\s*[:：]?\s*(\d+)',
        text,
        flags=re.IGNORECASE
    )

    if stk_match:
        account = stk_match.group(1)
        text = text.replace(stk_match.group(0), "")

    ignore = {"mkn", "mkdn", "mkrt", "mkr", "dn", "2mk", "mk2"}

    tokens = re.findall(r'\b[^\s]+\b', text)

    tokens = [
        t for t in tokens
        if t.lower() not in ignore and not t.startswith("/")
    ]

    phone = None
    username = None

    numeric = []
    others = []

    for t in tokens:
        # SĐT
        if re.fullmatch(r'0\d{9}', t):
            if phone is None:
                phone = t
            continue

        # Chỉ toàn số
        if t.isdigit():
            numeric.append(t)
            continue

        # Username hợp lệ
        if re.fullmatch(r'[A-Za-z0-9_]{4,}', t):
            others.append(t)

    # Có username => các dãy số (không bắt đầu bằng 0) sẽ là STK
    if others:
        username = others[0]

        if account is None:
            for n in numeric:
                if not n.startswith("0") and len(n) >= 6:
                    account = n
                    break

    # Không có username nhưng có SĐT
    elif phone:
        # Nếu có thêm một dãy số (>=4 số) đi cùng SĐT thì coi dãy số đó là username
        if numeric:
            for n in numeric:
                if n != phone and len(n) >= 4:
                    username = n
                    break

        # Nếu không có thì vẫn giữ logic cũ
        if username is None:
            username = phone

    # Chỉ có số => coi là username, KHÔNG phải STK
    elif numeric:
        username = numeric[0]

    if username:
        if chat_id:
            user_cache[chat_id] = username
        return username, phone, account

    if update and update.message and update.message.reply_to_message:
        mid = update.message.reply_to_message.message_id
        saved = get_reply(chat_id, mid)
        if saved:
            return saved, None, account

    return "Không có", None, account

# ================= TIME =================
def now_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ================= LOG =================
def save_log(username, action, raw, staff):
    cursor.execute("""
        INSERT INTO logs(username, action, raw, staff, time)
        VALUES (?, ?, ?, ?, ?)
    """, (username, action, raw, staff, now_time()))
    conn.commit()


# ================= UI =================
def build_msg(
    user,
    login_pw=None,
    withdraw_pw=None,
    mode="login",
    phone=None,
    account=None
):
    lines = []

    if phone and phone != user:
        lines.append(f"<b>电话</b>：<code>{phone}</code>")
    elif account:
        lines.append(f"<b>卡号</b>：<code>{account}</code>")

    if user and user != "Không có":
        lines.append(f"<b>会员名</b>：<code>{user}</code>")

    if mode == "login":
        lines.append(f"<b>登录密码</b>：<code>{login_pw}</code>")
    elif mode == "withdraw":
        lines.append(f"<b>提现密码</b>：<code>{withdraw_pw}</code>")
    else:
        lines.append(f"<b>登录</b>：<code>{login_pw}</code>")
        lines.append(f"<b>提现</b>：<code>{withdraw_pw}</code>")

    return "\n\n".join(lines)

def kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅", callback_data="ok"),
        InlineKeyboardButton("❌", callback_data="no")
    ]])


# ================= SEND =================
async def send(update, msg, context, username):
    sent = await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=kb()
    )

    pending_alerts[sent.message_id] = {
        "alo_id": None,
        "root_id": sent.message_id,
        "text": msg,
        "done": False
    }

    save_reply(sent.chat_id, sent.message_id, username)
    save_pending()

# ================= BUTTON =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    # ✅ FIX: callback timeout / invalid query
    try:
        await q.answer()
    except:
        return

    if not q.message:
        return

    msg_id = q.message.message_id
    staff = q.from_user.full_name

    root_id = None

    if msg_id in pending_alerts:
        root_id = msg_id
    else:
        for k, v in pending_alerts.items():
            if v.get("alo_id") == msg_id:
                root_id = k
                break

    if root_id is None:
        return

    data = pending_alerts.get(root_id)
    if not data:
        return

    alo_id = data.get("alo_id")
    is_ok = q.data in ["ok", "alo_ok_" + str(root_id)]

    if q.data in ["ok", "no"]:
        try:
            data["done"] = True

            if alo_id:
                await context.bot.delete_message(
                    chat_id=q.message.chat_id,
                    message_id=alo_id
                )
                data["alo_id"] = None

            base_text = data.get("text", "")
            new_text = base_text + f"\n\n<b>{'❌' if not is_ok else '✅'}{staff}</b>"

            await q.message.edit_text(new_text, parse_mode="HTML")
            save_pending()
        except:
            pass
        return

    elif q.data.startswith("alo_"):
        try:
            if not data:
                for k, v in pending_alerts.items():
                    if v.get("alo_id") == msg_id:
                        data = v
                        root_id = k
                        break

            if not data:
                return

            is_ok = q.data.startswith("alo_ok")

            status = "已通过" if is_ok else "已拒绝"
            popup_text = f"{'❌' if not is_ok else '✅'}{staff} {status}"

            await q.message.edit_text(popup_text)
        except:
            pass

        if alo_id:
            try:
                await asyncio.sleep(1.5)
                await context.bot.delete_message(
                    chat_id=q.message.chat_id,
                    message_id=msg_id
                )
            except:
                pass

        try:
            base_text = data.get("text", "")
            new_root = base_text + f"\n\n<b>{'❌' if not is_ok else '✅'}{staff}</b>"

            await context.bot.edit_message_text(
                chat_id=q.message.chat_id,
                message_id=root_id,
                text=new_root,
                parse_mode="HTML"
            )

            data["done"] = True
            pending_alerts.pop(root_id, None)
            save_pending()
        except:
            pass
        return

# ================= LOGIN =================
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, phone, account = extract_username(get_text(update), update)

    save_reply(update.effective_chat.id, update.message.message_id, user)

    pw = gen_login()

    save_log(user, "mkdn", get_text(update), update.effective_user.full_name)

    await send(
        update,
        build_msg(
            user,
            login_pw=pw,
            mode="login",
            phone=phone,
            account=account
        ),
        context,
        user
    )

# ================= WITHDRAW =================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, phone, account = extract_username(get_text(update), update)

    save_reply(update.effective_chat.id, update.message.message_id, user)

    pw = gen_withdraw()

    save_log(user, "mkrt", get_text(update), update.effective_user.full_name)

    await send(
        update,
        build_msg(
            user,
            withdraw_pw=pw,
            mode="withdraw",
            phone=phone,
            account=account
        ),
        context,
        user
    )

# ================= BOTH =================
async def both(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, phone, account = extract_username(get_text(update), update)

    save_reply(update.effective_chat.id, update.message.message_id, user)

    lp = gen_login()
    wp = gen_withdraw()

    save_log(user, "mkdn", get_text(update), update.effective_user.full_name)
    save_log(user, "mkrt", get_text(update), update.effective_user.full_name)

    await send(
        update,
        build_msg(
            user,
            login_pw=lp,
            withdraw_pw=wp,
            mode="both",
            phone=phone,
            account=account
        ),
        context,
        user
    )

# ================= ROUTER =================
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = get_text(update).lower().strip()
    words = text.split()

    if any(k in words for k in ["mkdn", "mkn", "dn"]):
        await login(update, context)
        return

    if any(k in words for k in ["mkrt", "mkr"]):
        await withdraw(update, context)
        return

    if any(k in words for k in ["mk2", "2mk"]):
        await both(update, context)
        return


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⛔ VUI LÒNG LIÊN HỆ VỚI QUẢN TRỊ VIÊN ĐỂ ĐĂNG KÍ TRƯỚC"
    )

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ALL, router))
app.add_handler(CallbackQueryHandler(button))

print("BOT RUNNING...")
app.run_polling()