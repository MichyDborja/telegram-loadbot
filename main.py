import json, os, re, asyncio
from datetime import datetime, timedelta, time as dt_time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN") or "PUT_YOUR_BOT_TOKEN_HERE"
ADMIN_IDS = [5955882128]
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

# ---------------- DAILY REMINDER ----------------
async def daily_reminder_loop(app):
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), dt_time(9,0))
        if now > target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        data = load_data()
        unpaid = [r for r in data["records"] if r["status"] == "UNPAID"]
        if unpaid:
            totals = {}
            for r in unpaid:
                totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]

            msg = "⚠️ DAILY UNPAID REMINDER\n\n"
            for b,t in totals.items():
                msg += f"{b}: ₱{t}\n"

            for admin in ADMIN_IDS:
                try:
                    await app.bot.send_message(admin, msg)
                except:
                    pass

# ---------------- REPORT GENERATOR ----------------
def generate_report(days):
    data = load_data()
    now = datetime.now()

    if days == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0)
    else:
        start = now - timedelta(days=days)

    rec = [
        r for r in data["records"]
        if datetime.strptime(r["time"], "%Y-%m-%d %H:%M") >= start
    ]

    if not rec:
        return "No data available."

    sales = sum(r["price"] for r in rec)
    paid = sum(r["paid_amount"] for r in rec)
    cost = sum(r["cost"] for r in rec)
    profit = paid - cost
    unpaid = sum(r["price"] for r in rec if r["status"] == "UNPAID")

    return (
        f"📊 REPORT\n\n"
        f"Sales: ₱{sales}\n"
        f"Paid: ₱{paid}\n"
        f"Cost: ₱{cost}\n"
        f"Profit: ₱{profit}\n"
        f"Unpaid: ₱{unpaid}"
    )

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("➕ Add Buyer", callback_data="add_buyer")],
        [InlineKeyboardButton("📦 Record Load", callback_data="record_load")],
        [InlineKeyboardButton("💰 Wallet Manager", callback_data="wallet")],
        [InlineKeyboardButton("💲 Price List", callback_data="pricelist")],
        [InlineKeyboardButton("📊 Summary", callback_data="summary")],
        [InlineKeyboardButton("📄 Unpaid Accounts", callback_data="unpaid_receipt")],
        [InlineKeyboardButton("📆 Daily Report", callback_data="report_day")],
        [InlineKeyboardButton("📅 Weekly Report", callback_data="report_week")],
        [InlineKeyboardButton("🗓 Monthly Report", callback_data="report_month")]
    ]
    text = "📌 LOAD MANAGEMENT BOT"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ---------------- BUTTON HANDLER ----------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    if query.data == "main_menu":
        await start(update, context)

    elif query.data == "report_day":
        await query.message.reply_text(generate_report(1))

    elif query.data == "report_week":
        await query.message.reply_text(generate_report(7))

    elif query.data == "report_month":
        await query.message.reply_text(generate_report("month"))

    elif query.data == "add_buyer":
        context.user_data["step"] = "add_buyer"
        await query.message.reply_text("Enter buyer name:")

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
        prices = data.get("prices",{})
        if prices:
            kb = [[InlineKeyboardButton(k.upper(), callback_data=f"price_{k}")] for k in prices]
            await query.message.reply_text("Select load:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.message.reply_text("Send details & amount:")

    elif query.data.startswith("price_"):
        key = query.data.replace("price_","")
        p = data["prices"].get(key)
        if not p: return

        if data["wallets"][p["network"]] < p["cost"]:
            await query.message.reply_text("❌ Insufficient wallet balance")
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

        await query.message.reply_text(f"✅ Load Recorded\nBuyer: {r['buyer']}\nAmount: ₱{r['price']}")
        context.user_data.clear()

    elif query.data == "wallet":
        txt = "💰 WALLET BALANCES\n\n"
        for k,v in data["wallets"].items():
            txt += f"{k.upper()}: ₱{v}\n"
        await query.message.reply_text(txt)

        if is_admin(query.from_user.id):
            context.user_data["step"] = "wallet_add"
            await query.message.reply_text("Send: network amount\nExample: smart 1000")

    elif query.data == "summary":
        total = sum(r["price"] for r in data["records"])
        paid = sum(r["paid_amount"] for r in data["records"])
        cost = sum(r["cost"] for r in data["records"])
        profit = paid - cost
        await query.message.reply_text(
            f"📊 SUMMARY\n\nSales: ₱{total}\nPaid: ₱{paid}\nCost: ₱{cost}\nProfit: ₱{profit}"
        )

    elif query.data == "pricelist":
        txt="💲 PRICE LIST\n\n"
        for k,v in data["prices"].items():
            txt+=f"{k.upper()} → ₱{v['price']} | Cost:{v['cost']} | {v['network'].upper()}\n"
        await query.message.reply_text(txt)

        if is_admin(query.from_user.id):
            context.user_data["step"]="add_price"
            await query.message.reply_text("Send: keyword price cost network\nExample: pa50 50 48.5 smart")

    elif query.data == "unpaid_receipt":
        rec=[r for r in data["records"] if r["status"]=="UNPAID"]
        if not rec:
            await query.message.reply_text("No unpaid accounts.")
            return
        totals={}
        txt="📄 UNPAID ACCOUNTS\n\n"
        for r in rec:
            totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]
        for b,t in totals.items():
            txt+=f"{b}: ₱{t}\n"
        await query.message.reply_text(txt)

# ---------------- MESSAGES ----------------
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data=load_data()
    step=context.user_data.get("step")

    if step=="add_buyer":
        name=update.message.text.strip()
        if name not in data["buyers"]:
            data["buyers"].append(name)
            save_data(data)

        kb=[
            [InlineKeyboardButton("➕ Add Another Buyer", callback_data="add_buyer")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ]

        await update.message.reply_text(f"✅ Buyer Added: {name}", reply_markup=InlineKeyboardMarkup(kb))
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
        await update.message.reply_text(f"✅ Load Recorded: ₱{amt}")
        context.user_data.clear()

    elif step=="wallet_add":
        net,amt=update.message.text.split()
        data["wallets"][net.lower()] += parse_amount(amt)
        save_data(data)
        await update.message.reply_text("✅ Wallet Updated")
        context.user_data.clear()

    elif step=="add_price":
        k,p,c,n=update.message.text.split()
        data["prices"][k.lower()]={"price":parse_amount(p),"cost":parse_amount(c),"network":n.lower()}
        save_data(data)
        await update.message.reply_text("✅ Price Added")
        context.user_data.clear()

# ---------------- MAIN ----------------
async def main():
    app=ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    asyncio.create_task(daily_reminder_loop(app))

    print("Bot running 24/7...")
    await app.run_polling()

if __name__=="__main__":
    asyncio.run(main())
