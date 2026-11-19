# ==========================================
# TELEGRAM RESELLER BOT - PYDROID 3
# ==========================================

import sqlite3
import logging
from io import BytesIO
from datetime import datetime

import qrcode
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# -------- अपनी सेटिंग यहाँ भरें --------

BOT_TOKEN = '8893611238:AAG6887sxNELEC1RH756p-yaOK4hJGBqKag'
ADMIN_ID = 7317837367       # अपना Telegram numeric ID डालें
UPI_ID ='7355398119@fam'  # अपना UPI ID डालें
PAYEE_NAME = "Reseller Store"

# ---------------------------------------
	
DB = "reseller.sqlite3"

logging.basicConfig(level=logging.INFO)


def connect():
    return sqlite3.connect(DB)


def setup():
    con = connect()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        uid INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS deposits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER,
        amount REAL,
        utr TEXT,
        status TEXT DEFAULT 'PENDING',
        created TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS services(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER,
        service TEXT,
        quantity INTEGER,
        amount REAL,
        status TEXT DEFAULT 'PENDING'
    )
    """)

    con.commit()
    con.close()


def add_user(uid):
    con = connect()
    con.execute(
        "INSERT OR IGNORE INTO users(uid,balance) VALUES(?,0)",
        (uid,)
    )
    con.commit()
    con.close()


def get_balance(uid):
    con = connect()
    row = con.execute(
        "SELECT balance FROM users WHERE uid=?", (uid,)
    ).fetchone()
    con.close()
    return row[0] if row else 0


def menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 बैलेंस", callback_data="balance"),
            InlineKeyboardButton("➕ पैसे जमा करें", callback_data="deposit")
        ],
        [
            InlineKeyboardButton("🛒 सर्विस", callback_data="services"),
            InlineKeyboardButton("📜 ऑर्डर", callback_data="orders")
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    add_user(uid)

    await update.message.reply_text(
        "नमस्ते! Reseller Bot में आपका स्वागत है।\n"
        "नीचे से अपना विकल्प चुनें।",
        reply_markup=menu()
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("यह कमांड केवल Admin के लिए है।")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Pending Deposits", callback_data="pending")],
        [InlineKeyboardButton("सर्विस जोड़ें", callback_data="help_service")]
    ])

    await update.message.reply_text(
        "👑 ADMIN PANEL",
        reply_markup=keyboard
    )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    add_user(uid)
    data = q.data

    if data == "balance":
        await q.message.reply_text(
            f"आपका बैलेंस: ₹{get_balance(uid):.2f}"
        )

    elif data == "deposit":
        context.user_data["state"] = "deposit_amount"
        await q.message.reply_text(
            "कितने रुपये जमा करने हैं? रकम भेजें।"
        )

    elif data == "services":
        con = connect()
        rows = con.execute(
            "SELECT id,name,price FROM services"
        ).fetchall()
        con.close()

        if not rows:
            await q.message.reply_text("अभी कोई सर्विस उपलब्ध नहीं है।")
            return

        keyboard = []
        for sid, name, price in rows:
            keyboard.append([
                InlineKeyboardButton(
                    f"{name} - ₹{price}",
                    callback_data=f"service_{sid}"
                )
            ])

        await q.message.reply_text(
            "अपनी सर्विस चुनें:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("service_"):
        sid = int(data.split("_")[1])
        con = connect()
        row = con.execute(
            "SELECT name,price FROM services WHERE id=?",
            (sid,)
        ).fetchone()
        con.close()

        if not row:
            await q.message.reply_text("सर्विस नहीं मिली।")
            return

        context.user_data["service"] = row[0]
        context.user_data["price"] = row[1]
        context.user_data["state"] = "quantity"

        await q.message.reply_text(
            f"{row[0]} चुनी गई।\n"
            f"कीमत: ₹{row[1]} प्रति यूनिट\n"
            "कितनी Quantity चाहिए?"
        )

    elif data == "orders":
        con = connect()
        rows = con.execute(
            "SELECT id,service,quantity,amount,status "
            "FROM orders WHERE uid=? ORDER BY id DESC LIMIT 10",
            (uid,)
        ).fetchall()
        con.close()

        if not rows:
            await q.message.reply_text("अभी कोई ऑर्डर नहीं है।")
            return

        text = "📜 आपके ऑर्डर:\n\n"
        for row in rows:
            text += (
                f"#{row[0]} | {row[1]} | Qty: {row[2]} "
                f"| ₹{row[3]:.2f} | {row[4]}\n"
            )

        await q.message.reply_text(text)

    elif data == "pending":
        if uid != ADMIN_ID:
            return

        con = connect()
        rows = con.execute(
            "SELECT id,uid,amount,utr FROM deposits "
            "WHERE status='PENDING'"
        ).fetchall()
        con.close()

        if not rows:
            await q.message.reply_text("कोई Pending Deposit नहीं है।")
            return

        for dep_id, user_id, amount, utr in rows:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_{dep_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_{dep_id}"
                )
            ]])

            await q.message.reply_text(
                f"Deposit #{dep_id}\n"
                f"User: {user_id}\n"
                f"Amount: ₹{amount}\n"
                f"UTR: {utr}",
                reply_markup=keyboard
            )

    elif data.startswith("approve_") or data.startswith("reject_"):
        if uid != ADMIN_ID:
            return

        action, dep_id = data.split("_")
        dep_id = int(dep_id)

        con = connect()
        cur = con.cursor()
        cur.execute("BEGIN IMMEDIATE")

        row = cur.execute(
            "SELECT uid,amount FROM deposits "
            "WHERE id=? AND status='PENDING'",
            (dep_id,)
        ).fetchone()

        if row:
            user_id, amount = row

            if action == "approve":
                cur.execute(
                    "UPDATE users SET balance=balance+? WHERE uid=?",
                    (amount, user_id)
                )
                status = "APPROVED"
            else:
                status = "REJECTED"

            cur.execute(
                "UPDATE deposits SET status=? WHERE id=?",
                (status, dep_id)
            )
            con.commit()

            await q.message.reply_text(
                f"Deposit #{dep_id}: {status}"
            )

            try:
                await context.bot.send_message(
                    user_id,
                    f"आपका Deposit #{dep_id} {status} हुआ।"
                )
            except Exception:
                pass
        else:
            con.rollback()
            await q.message.reply_text(
                "यह Deposit पहले ही process हो चुका है।"
            )

        con.close()

    elif data == "help_service":
        if uid == ADMIN_ID:
            await q.message.reply_text(
                "सर्विस जोड़ने के लिए लिखें:\n"
                "/addservice ServiceName | Price\n"
                "उदाहरण:\n"
                "/addservice Instagram Likes | 2"
            )


async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    add_user(uid)
    text = update.message.text.strip()
    state = context.user_data.get("state")

    if state == "deposit_amount":
        try:
            amount = float(text)
            if not 1 <= amount <= 100000:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "₹1 से ₹100000 तक सही रकम भेजें।"
            )
            return

        upi_link = (
            f"upi://pay?pa={UPI_ID}"
            f"&pn={PAYEE_NAME.replace(' ', '%20')}"
            f"&am={amount:.2f}&cu=INR"
        )

        qr = qrcode.make(upi_link)
        image = BytesIO()
        image.name = "payment_qr.png"
        qr.save(image, format="PNG")
        image.seek(0)

        context.user_data["deposit_amount"] = amount
        context.user_data["state"] = "deposit_utr"

        await update.message.reply_photo(
            photo=image,
            caption=(
                f"₹{amount:.2f} का पेमेंट QR कोड।\n"
                "पेमेंट करने के बाद अपना UTR नंबर भेजें।"
            )
        )
        return

    elif state == "deposit_utr":
        utr = text.upper()

        if not 6 <= len(utr) <= 30 or not utr.isalnum():
            await update.message.reply_text(
                "कृपया सही UTR नंबर भेजें।"
            )
            return

        amount = context.user_data.get("deposit_amount")
        if amount is None:
            context.user_data["state"] = None
            await update.message.reply_text(
                "Deposit प्रक्रिया दोबारा शुरू करें।"
            )
            return

        con = connect()
        try:
            old = con.execute(
                "SELECT id FROM deposits WHERE utr=?",
                (utr,)
            ).fetchone()

            if old:
                await update.message.reply_text(
                    "यह UTR पहले जमा किया जा चुका है।"
                )
                return

            con.execute(
                "INSERT INTO deposits(uid,amount,utr,status,created) "
                "VALUES(?,?,?,?,?)",
                (
                    uid,
                    amount,
                    utr,
                    "PENDING",
                    datetime.now().isoformat(timespec="seconds")
                )
            )
            con.commit()
        finally:
            con.close()

        context.user_data["state"] = None
        context.user_data.pop("deposit_amount", None)

        await update.message.reply_text(
            "आपका Deposit अनुरोध Pending है। "
            "Admin पेमेंट सत्यापित करने के बाद बैलेंस अपडेट करेगा।"
        )
        return

    elif state == "quantity":
        try:
            quantity = int(text)
            if not 1 <= quantity <= 100000:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "Quantity 1 से 100000 के बीच पूरी संख्या में भेजें।"
            )
            return

        service = context.user_data.get("service")
        price = context.user_data.get("price")

        if not service or price is None:
            context.user_data["state"] = None
            await update.message.reply_text(
                "सर्विस दोबारा चुनें।"
            )
            return

        total = round(float(price) * quantity, 2)

        con = connect()
        try:
            cur = con.cursor()
            cur.execute("BEGIN IMMEDIATE")

            row = cur.execute(
                "SELECT balance FROM users WHERE uid=?",
                (uid,)
            ).fetchone()

            if not row or row[0] < total:
                con.rollback()
                await update.message.reply_text(
                    f"आपका बैलेंस कम है। ऑर्डर के लिए ₹{total:.2f} "
                    "चाहिए। पहले बैलेंस जमा करें।"
                )
                return

            cur.execute(
                "UPDATE users SET balance=balance-? "
                "WHERE uid=? AND balance>=?",
                (total, uid, total)
            )

            if cur.rowcount != 1:
                con.rollback()
                await update.message.reply_text(
                    "बैलेंस अपडेट नहीं हुआ। कृपया दोबारा कोशिश करें।"
                )
                return

            cur.execute(
                "INSERT INTO orders(uid,service,quantity,amount,status) "
                "VALUES(?,?,?,?,?)",
                (uid, service, quantity, total, "PENDING")
            )

            con.commit()
        finally:
            con.close()

        context.user_data["state"] = None
        context.user_data.pop("service", None)
        context.user_data.pop("price", None)

        await update.message.reply_text(
            f"ऑर्डर सेव हो गया!\n"
            f"सर्विस: {service}\n"
            f"Quantity: {quantity}\n"
            f"कुल रकम: ₹{total:.2f}\n"
            "स्थिति: Pending"
        )
        return

setup()
application = ApplicationBuilder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("admin", admin))
application.add_handler(CallbackQueryHandler(callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
application.run_polling()
