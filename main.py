import json, os, re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

TOKEN = os.getenv("TOKEN") or "8521646944:AAHMSVQqXGPr7WcaG6zkiO443DYdUOvADJ4"
ADMIN_IDS = [5955882128]  # Replace with your Telegram ID
DATA_FILE = "data.json"
WEBHOOK_URL = "https://telegram-loadbot-vmeq-production-0745.up.railway.app/"  # Your Railway URL

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

# ---------------- MAIN MENU ----------------
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Buyer", callback_data="add_buyer")],
        [InlineKeyboardButton("📦 Record Load", callback_data="record_load")],
        [InlineKeyboardButton("💰 Wallet", callback_data="wallet")],
        [InlineKeyboardButton("📊 Summary", callback_data="summary")],
        [InlineKeyboardButton("💲 Pricelist", callback_data="pricelist")],
        [InlineKeyboardButton("📄 Unpaid Receipts", callback_data="unpaid_receipt")],
        [InlineKeyboardButton("📅 Reports", callback_data="reports")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=main_menu_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=main_menu_keyboard())

# ---------------- BUTTON HANDLER ----------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    
    if query.data == "main_menu":
        await start(update, context)

    elif query.data == "add_buyer":
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
        prices = data.get("prices", {})
        if prices:
            kb = [[InlineKeyboardButton(k.upper(), callback_data=f"price_{k}")] for k in prices]
            await query.message.reply_text("Select a keyword OR type manual load & amount:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.message.reply_text("Send details & amount manually:")

    elif query.data.startswith("price_"):
        key = query.data.replace("price_","")
        p = data["prices"].get(key)
        if not p: return
        if data["wallets"][p["network"]] < p["cost"]:
            await query.message.reply_text("❌ Not enough wallet balance")
            return
        data["wallets"][p["network"]] -= p["cost"]

        r = {
            "id": len(data["records"])+1,
            "buyer": context.user_data["buyer"],
            "details": key,
            "price": p["price"],
            "cost": p["cost"],
            "network": p["network"],
            "status": "UNPAID",
            "paid_amount": 0,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(r)
        save_data(data)
        await query.message.reply_text(f"✅ Recorded\nBuyer:{r['buyer']}\nAmount:{r['price']}")
        context.user_data.clear()

    elif query.data == "wallet":
        txt = "💰 WALLET BALANCES\n"
        for k,v in data["wallets"].items():
            txt += f"{k.upper()}: {v}\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"] = "wallet_add"
            await query.message.reply_text("Send: network amount\nExample: smart 1000")

    elif query.data == "summary":
        total = sum(r["price"] for r in data["records"])
        paid = sum(r["paid_amount"] for r in data["records"])
        cost = sum(r["cost"] for r in data["records"])
        profit = paid - cost
        await query.message.reply_text(f"📊 SUMMARY\nTotal Sales:{total}\nPaid:{paid}\nCost:{cost}\nProfit:{profit}")

    elif query.data == "pricelist":
        txt="💲 PRICELIST\n"
        for k,v in data["prices"].items():
            txt+=f"{k.upper()} → {v['price']} | Cost:{v['cost']} | {v['network'].upper()}\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"]="add_price"
            await query.message.reply_text("Send: keyword price cost network\nExample: pa50 50 48.5 smart")

    elif query.data == "unpaid_receipt":
        rec=[r for r in data["records"] if r["status"]=="UNPAID"]
        if not rec:
            await query.message.reply_text("No unpaid records.")
            return
        totals={}
        txt="⚠️ UNPAID RECEIPTS\n"
        for r in rec:
            totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]
            txt+=f"{r['time']} | {r['buyer']} | {r['details']} | {r['price']}\n"
        txt+="\n--- TOTAL PER BUYER ---\n"
        for b,t in totals.items():
            txt+=f"{b}: {t}\n"
        await query.message.reply_text(txt)

    elif query.data == "reports":
        records = data["records"]
        now = datetime.now()
        day_total = sum(r["price"] for r in records if datetime.strptime(r["time"], "%Y-%m-%d %H:%M").date() == now.date())
        week_total = sum(r["price"] for r in records if datetime.strptime(r["time"], "%Y-%m-%d %H:%M").isocalendar()[1] == now.isocalendar()[1])
        month_total = sum(r["price"] for r in records if datetime.strptime(r["time"], "%Y-%m-%d %H:%M").month == now.month)
        await query.message.reply_text(f"📅 REPORTS\nDaily: {day_total}\nWeekly: {week_total}\nMonthly: {month_total}")

# ---------------- MESSAGES ----------------
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    step = context.user_data.get("step")

    if step=="add_buyer":
        name = update.message.text.strip()
        if name not in data["buyers"]:
            data["buyers"].append(name)
            save_data(data)
        kb = [[
            InlineKeyboardButton("➕ Add Another", callback_data="add_buyer"),
            InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")
        ]]
        await update.message.reply_text(f"✅ Buyer added: {name}", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.clear()

    elif step=="record_details":
        amt=parse_amount(update.message.text)
        r={
            "id":len(data["records"])+1,
            "buyer":context.user_data["buyer"],
            "details":update.message.text,
            "price":amt,
            "cost":0,
            "network":"",
            "status":"UNPAID",
            "paid_amount":0,
            "time":datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(r)
        save_data(data)
        await update.message.reply_text(f"✅ Recorded {amt}")
        context.user_data.clear()

    elif step=="wallet_add":
        try:
            net, amt = update.message.text.split()
            amt = parse_amount(amt)
            if net.lower() not in data["wallets"]:
                await update.message.reply_text("Invalid network.")
                return
            data["wallets"][net.lower()] += amt
            save_data(data)
            await update.message.reply_text("✅ Wallet updated")
            context.user_data.clear()
        except:
            await update.message.reply_text("Format: network amount\nExample: smart 1000")

    elif step=="add_price":
        try:
            k,p,c,n = update.message.text.split()
            data["prices"][k.lower()] = {"price":parse_amount(p),"cost":parse_amount(c),"network":n.lower()}
            save_data(data)
            await update.message.reply_text("✅ Pricelist updated")
            context.user_data.clear()
        except:
            await update.message.reply_text("Format: keyword price cost network\nExample: pa50 50 48.5 smart")

# ---------------- MAIN ----------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    # Set webhook
    await app.bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")

    # Start webhook listener on Railway's port
    PORT = int(os.environ.get("PORT", 3000))
    await app.start_webhook(listen="0.0.0.0", port=PORT, webhook_url=WEBHOOK_URL)
    await app.idle()

if __name__=="__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())
