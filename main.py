import json, os, re, asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, Webhook

TOKEN = os.getenv("TOKEN") or "8521646944:AAHMSVQqXGPr7WcaG6zkiO443DYdUOvADJ4"
ADMIN_IDS = [5955882128]
DATA_FILE = "data.json"

RAILWAY_URL = os.getenv("RAILWAY_STATIC_URL")  # your Railway URL
PORT = int(os.getenv("PORT", 8000))

# ---------------- STORAGE ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"buyers": [], "records": [], "wallets": {"smart":0,"globe":0,"tm":0}, "prices":{}}
    with open(DATA_FILE,"r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f,indent=2)

def is_admin(uid):
    return uid in ADMIN_IDS

def parse_amount(text):
    text = text.replace(",","")
    match = re.search(r"\d+(\.\d+)?", text)
    return float(match.group()) if match else 0.0

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("➕ Add Buyer", callback_data="add_buyer")],
        [InlineKeyboardButton("📦 Record Load", callback_data="record_load")],
        [InlineKeyboardButton("💰 Wallet", callback_data="wallet")],
        [InlineKeyboardButton("📊 Summary", callback_data="summary")],
        [InlineKeyboardButton("💲 Pricelist", callback_data="pricelist")],
        [InlineKeyboardButton("📄 Unpaid Receipt", callback_data="unpaid_receipt")],
        [InlineKeyboardButton("📅 Reports", callback_data="reports")]
    ]
    if update.message:
        await update.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=InlineKeyboardMarkup(kb))

# ---------------- BUTTON HANDLER ----------------
# (Use the same buttons() code from polling version)
# ---------------- MESSAGES ----------------
# (Use the same messages() code from polling version)
# ---------------- DAILY REMINDER ----------------
async def daily_reminder_loop(app):
    while True:
        data = load_data()
        rec = [r for r in data["records"] if r["status"]=="UNPAID"]
        if rec:
            totals = {}
            msg = "⚠️ UNPAID RECORDS REMINDER\n"
            for r in rec:
                totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]
                msg += f"{r['time']} | {r['buyer']} | {r['details']} | {r['price']}\n"
            msg += "\n--- TOTAL PER BUYER ---\n"
            for b,t in totals.items():
                msg += f"{b}: {t}\n"
            save_data(data)
            for admin_id in ADMIN_IDS:
                await app.bot.send_message(admin_id,msg)
        await asyncio.sleep(3600)

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    # Daily Reminder
    asyncio.create_task(daily_reminder_loop(app))

    # Start Webhook
    print(f"Bot running with webhook on {RAILWAY_URL}/webhook/{TOKEN}")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=f"/webhook/{TOKEN}",
        webhook_url=f"{RAILWAY_URL}/webhook/{TOKEN}"
    )

if __name__=="__main__":
    main()
