import json, os, re, asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN") or "8521646944:AAHMSVQqXGPr7WcaG6zkiO443DYdUOvADJ4"
ADMIN_IDS = [5955882128]  # Replace with your Telegram ID
DATA_FILE = "data.json"

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
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    # ---------- MAIN MENU ----------
    if query.data == "main_menu":
        await start(update, context)
        return

    # ---------- ADD BUYER ----------
    if query.data == "add_buyer":
        context.user_data["step"] = "add_buyer"
        kb = [
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
        ]
        await query.message.reply_text("Send buyer name:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ---------- RECORD LOAD ----------
    if query.data == "record_load":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b, callback_data=f"buyer_{b}")] for b in data["buyers"]]
        await query.message.reply_text("Select buyer:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if query.data.startswith("buyer_"):
        buyer = query.data.replace("buyer_","")
        context.user_data["buyer"] = buyer
        context.user_data["step"] = "record_details"
        prices = data.get("prices",{})
        if prices:
            kb = [[InlineKeyboardButton(k.upper(), callback_data=f"price_{k}")] for k in prices]
            kb.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
            await query.message.reply_text("Select keyword OR send details manually:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.message.reply_text("Send load details & amount manually:")

        return

    # ---------- PRICE SELECTION ----------
    if query.data.startswith("price_"):
        key = query.data.replace("price_","")
        p = data["prices"].get(key)
        if not p: return
        if data["wallets"][p["network"]] < p["cost"]:
            await query.message.reply_text(f"❌ Not enough in {p['network'].upper()} wallet")
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

        kb = [
            [InlineKeyboardButton("➕ Add Another Load", callback_data="record_load")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
        ]
        await query.message.reply_text(f"✅ Load recorded\nBuyer: {r['buyer']}\nAmount: {r['price']}", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.clear()
        return

    # ---------- WALLET ----------
    if query.data == "wallet":
        txt = "💰 WALLET BALANCES\n"
        for k,v in data["wallets"].items():
            txt += f"{k.upper()}: {v}\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"] = "wallet_add"
            await query.message.reply_text("Send: network amount\nExample: smart 1000")
        return

    # ---------- SUMMARY ----------
    if query.data == "summary":
        total = sum(r["price"] for r in data["records"])
        paid = sum(r["paid_amount"] for r in data["records"])
        cost = sum(r["cost"] for r in data["records"])
        profit = paid - cost
        await query.message.reply_text(
            f"📊 SUMMARY\nSales: {total}\nPaid: {paid}\nCost: {cost}\nProfit: {profit}"
        )
        return

    # ---------- PRICELIST ----------
    if query.data == "pricelist":
        txt = "💲 PRICELIST\n"
        for k,v in data["prices"].items():
            txt += f"{k.upper()} → {v['price']} | Cost:{v['cost']} | {v['network'].upper()}\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"] = "add_price"
            await query.message.reply_text("Send: keyword price cost network\nExample: pa50 50 48.5 smart")
        return

    # ---------- UNPAID RECEIPT ----------
    if query.data == "unpaid_receipt":
        rec = [r for r in data["records"] if r["status"] == "UNPAID"]
        if not rec:
            await query.message.reply_text("No unpaid records.")
            return
        totals = {}
        txt = "⚠️ UNPAID RECEIPTS\n"
        for r in rec:
            totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]
            txt += f"{r['time']} | {r['buyer']} | {r['details']} | {r['price']}\n"
        txt += "\n--- TOTAL PER BUYER ---\n"
        for b,t in totals.items():
            txt += f"{b}: {t}\n"
        await query.message.reply_text(txt)
        return

    # ---------- REPORTS ----------
    if query.data == "reports":
        kb = [
            [InlineKeyboardButton("📅 Daily", callback_data="report_daily")],
            [InlineKeyboardButton("📆 Weekly", callback_data="report_weekly")],
            [InlineKeyboardButton("🗓️ Monthly", callback_data="report_monthly")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
        ]
        await query.message.reply_text("Select report:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if query.data.startswith("report_"):
        period = query.data.replace("report_","")
        txt = f"📊 {period.capitalize()} Report\n"
        now = datetime.now()
        for r in data["records"]:
            record_time = datetime.strptime(r["time"], "%Y-%m-%d %H:%M")
            include = False
            if period=="daily" and record_time.date() == now.date():
                include = True
            elif period=="weekly" and now - timedelta(days=7) <= record_time <= now:
                include = True
            elif period=="monthly" and record_time.month == now.month and record_time.year == now.year:
                include = True
            if include:
                txt += f"{r['time']} | {r['buyer']} | {r['details']} | {r['price']} | {r['status']}\n"
        await query.message.reply_text(txt)
        return

# ---------------- MESSAGES ----------------
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    step = context.user_data.get("step")

    if step=="add_buyer":
        name = update.message.text.strip()
        if name not in data["buyers"]:
            data["buyers"].append(name)
            save_data(data)
        kb = [
            [InlineKeyboardButton("➕ Add Another", callback_data="add_buyer")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
        ]
        await update.message.reply_text(f"✅ Buyer added: {name}", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.clear()
        return

    if step=="record_details":
        amt = parse_amount(update.message.text)
        r = {
            "id": len(data["records"])+1,
            "buyer": context.user_data["buyer"],
            "details": update.message.text,
            "price": amt,
            "cost": 0,
            "network": "",
            "status": "UNPAID",
            "paid_amount": 0,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(r)
        save_data(data)
        kb = [
            [InlineKeyboardButton("➕ Add Another Load", callback_data="record_load")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
        ]
        await update.message.reply_text(f"✅ Recorded {amt}", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.clear()
        return

    if step=="wallet_add":
        net, amt = update.message.text.split()
        amt = parse_amount(amt)
        data["wallets"][net] += amt
        save_data(data)
        await update.message.reply_text("✅ Wallet updated")
        context.user_data.clear()
        return

    if step=="add_price":
        k,p,c,n = update.message.text.split()
        data["prices"][k.lower()] = {"price":parse_amount(p), "cost":parse_amount(c), "network":n.lower()}
        save_data(data)
        await update.message.reply_text("✅ Pricelist updated")
        context.user_data.clear()
        return

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
        await asyncio.sleep(3600)  # check every hour

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    # Start daily reminder
    asyncio.create_task(daily_reminder_loop(app))

    print("Bot running 24/7...")
    app.run_polling()  # <-- no asyncio.run()

if __name__=="__main__":
    main()
