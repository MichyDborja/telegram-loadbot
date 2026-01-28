import json, os, re, asyncio
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", "8080"))
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")

ADMIN_IDS = [5955882128]
DATA_FILE = "data.json"

# ---------------- STORAGE ----------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "buyers": [],
            "records": [],
            "wallets": {"smart":0,"globe":0,"tm":0},
            "prices":{}
        }
    with open(DATA_FILE,"r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f,indent=2)

def parse_amount(text):
    text = text.replace(",","")
    match = re.search(r"\d+(\.\d+)?", text)
    return float(match.group()) if match else 0.0

def is_admin(uid):
    return uid in ADMIN_IDS

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("➕ Add Buyer", callback_data="add_buyer")],
        [InlineKeyboardButton("📦 Record Load", callback_data="record_load")],
        [InlineKeyboardButton("💰 Wallet", callback_data="wallet")],
        [InlineKeyboardButton("📊 Summary", callback_data="summary")],
        [InlineKeyboardButton("📝 History", callback_data="buyer_history")],
        [InlineKeyboardButton("💲 Pricelist", callback_data="pricelist")],
        [InlineKeyboardButton("📄 Unpaid Receipt", callback_data="unpaid_receipt")]
    ]
    await update.message.reply_text(
        "📌 LOAD MANAGEMENT BOT",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ---------------- BUTTON HANDLER ----------------

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    if query.data == "add_buyer":
        context.user_data["step"] = "add_buyer"
        await query.message.reply_text("Send buyer name:")

    elif query.data == "record_load":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b, callback_data=f"buyer_{b}")] for b in data["buyers"]]
        await query.message.reply_text("Select buyer:", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("buyer_"):
        buyer = query.data.replace("buyer_","")
        context.user_data["buyer"] = buyer
        context.user_data["step"] = "record_details"
        await query.message.reply_text("Send load details & amount:\n09123456789 PA50")

    elif query.data == "wallet":
        txt = "💰 WALLET BALANCE\n"
        for k,v in data["wallets"].items():
            txt += f"{k.upper()}: {v:,.2f}\n"
        await query.message.reply_text(txt)

    elif query.data == "summary":
        total = sum(r["price"] for r in data["records"])
        paid = sum(r["paid_amount"] for r in data["records"])
        cost = sum(r["cost"] for r in data["records"])
        profit = paid - cost
        await query.message.reply_text(
            f"📊 SUMMARY\n\n"
            f"Total: {total:,.2f}\n"
            f"Paid: {paid:,.2f}\n"
            f"Unpaid: {total-paid:,.2f}\n"
            f"Cost: {cost:,.2f}\n"
            f"Profit: {profit:,.2f}"
        )

    elif query.data == "unpaid_receipt":
        records = [r for r in data["records"] if r["status"]=="UNPAID"]
        if not records:
            await query.message.reply_text("No unpaid records.")
            return

        txt="⚠️ UNPAID LIST\n\n"
        totals={}
        for r in records:
            totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]
            txt+=f"{r['time']} | {r['buyer']} | {r['details']} | {r['price']:,.2f}\n"

        txt+="\n--- TOTAL PER BUYER ---\n"
        for b,t in totals.items():
            txt+=f"{b}: {t:,.2f}\n"

        await query.message.reply_text(txt)

# ---------------- MESSAGE HANDLER ----------------

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    step = context.user_data.get("step")

    if step == "add_buyer":
        name = update.message.text.strip()
        if name not in data["buyers"]:
            data["buyers"].append(name)
            save_data(data)
        await update.message.reply_text(f"✅ Buyer added: {name}")
        context.user_data.clear()

    elif step == "record_details":
        amount = parse_amount(update.message.text)
        record = {
            "id": len(data["records"])+1,
            "buyer": context.user_data["buyer"],
            "details": update.message.text,
            "price": amount,
            "cost": 0,
            "network": "",
            "status": "UNPAID",
            "paid_amount": 0,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(record)
        save_data(data)
        await update.message.reply_text("📦 Load recorded.")
        context.user_data.clear()

# ---------------- WEBHOOK SERVER ----------------

async def handle(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response()

async def main():
    global app
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    await app.initialize()
    await app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

    web_app = web.Application()
    web_app.router.add_post("/webhook", handle)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("🚀 Bot running via webhook...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
