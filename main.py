import json, os, re, asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
        [InlineKeyboardButton("📝 History", callback_data="buyer_history")],
        [InlineKeyboardButton("💲 Pricelist", callback_data="pricelist")],
        [InlineKeyboardButton("📄 Unpaid Receipt", callback_data="unpaid_receipt")]
    ]
    if update.message:
        await update.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=InlineKeyboardMarkup(kb))
    elif update.callback_query:
        await update.callback_query.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=InlineKeyboardMarkup(kb))

# ---------------- BUTTON HANDLER ----------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    # ---------- ADD BUYER ----------
    if query.data == "add_buyer":
        context.user_data["step"] = "add_buyer"
        kb = [[InlineKeyboardButton("Cancel / Back", callback_data="main_menu")]]
        await query.message.reply_text("Send buyer name:", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "main_menu":
        await start(update, context)

    # ---------- RECORD LOAD ----------
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
            kb = [[InlineKeyboardButton(k.upper(), callback_data=f"price_{k}")] for k in prices.keys()]
            await query.message.reply_text(
                "Select a price keyword or type details & amount manually:",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await query.message.reply_text("Send load details & amount manually:\nExample:\n09123456789 SA99 1,046.64")

    # ---------- PRICE SELECTION ----------
    elif query.data.startswith("price_"):
        keyword = query.data.replace("price_","")
        price_info = data.get("prices",{}).get(keyword)
        if not price_info:
            await query.message.reply_text("Price not found.")
            return
        network = price_info["network"]
        cost = price_info["cost"]
        if data["wallets"].get(network,0) < cost:
            await query.message.reply_text(f"❌ Not enough in {network.upper()} wallet. Top-up first.")
            return
        data["wallets"][network] -= cost

        record = {
            "id": len(data["records"])+1,
            "buyer": context.user_data["buyer"],
            "details": keyword,
            "price": price_info["price"],
            "cost": cost,
            "network": network,
            "status": "UNPAID",
            "paid_amount": 0,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(record)
        save_data(data)
        await query.message.reply_text(
            f"📦 RECORDED\nID:{record['id']}\nBuyer:{record['buyer']}\nPrice:{record['price']:,.2f}\nCost:{record['cost']:,.2f}\nNetwork:{network.upper()}"
        )
        context.user_data.clear()

    # ---------- WALLET ----------
    elif query.data=="wallet":
        wallets = data.get("wallets",{"smart":0,"globe":0,"tm":0})
        txt = "💰 WALLET BALANCES\n"
        for k,v in wallets.items(): txt+=f"{k.upper()}: {v:,.2f}\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"]="wallet_add"
            await query.message.reply_text("Send amount and network to ADD:\nExample:\nsmart 1000")

    # ---------- SUMMARY ----------
    elif query.data=="summary":
        total = sum(r["price"] for r in data["records"])
        paid = sum(r["paid_amount"] for r in data["records"])
        unpaid = total - paid
        cost = sum(r.get("cost",0) for r in data["records"])
        profit = paid - cost
        txt = f"📊 SALES SUMMARY\nTotal: {total:,.2f}\nPaid: {paid:,.2f}\nUnpaid: {unpaid:,.2f}\nCost: {cost:,.2f}\nProfit: {profit:,.2f}"
        await query.message.reply_text(txt)

    # ---------- BUYER HISTORY ----------
    elif query.data=="buyer_history":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b, callback_data=f"history_{b}")] for b in data["buyers"]]
        await query.message.reply_text("Select buyer:", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("history_"):
        buyer = query.data.replace("history_","")
        records = [r for r in data["records"] if r["buyer"]==buyer]
        if not records:
            await query.message.reply_text("No records for this buyer.")
            return
        txt = f"📝 History for {buyer}:\n"
        for r in records:
            status = f"{r['status']} ({r['paid_amount']:,.2f}/{r['price']:,.2f})"
            txt += f"{r['time']} | {r['details']} | {r['price']:,.2f} | {status}\n"
        await query.message.reply_text(txt)

    # ---------- PRICELIST ----------
    elif query.data=="pricelist":
        txt="💲 PRICELIST\n"
        for k,v in data.get("prices",{}).items():
            txt+=f"{k.upper()} = {v['price']} (Cost:{v['cost']}, Network:{v['network'].upper()})\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"]="add_price"
            await query.message.reply_text(
                "Send new price: keyword price cost network\nExample: SA99 50 48.5 smart"
            )

    # ---------- UNPAID RECEIPT ----------
    elif query.data=="unpaid_receipt":
        records = [r for r in data["records"] if r["status"]=="UNPAID"]
        if not records:
            await query.message.reply_text("No unpaid records.")
            return
        totals = {}
        txt = "⚠️ UNPAID RECEIPTS\n"
        for r in records:
            record_time = datetime.strptime(r["time"], "%Y-%m-%d %H:%M")
            delay = 0
            if datetime.now().date() > record_time.date() and datetime.now().hour == 0:
                delay = 5
                r["price"] += delay
            totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]
            txt += f"{r['time']} | {r['buyer']} | {r['details']} | {r['price']:,.2f} | {r['status']}\n"
        txt += "\n--- TOTAL PER BUYER ---\n"
        for b,t in totals.items():
            txt += f"{b}: {t:,.2f}\n"
        await query.message.reply_text(txt)
        save_data(data)

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
                [InlineKeyboardButton("Add Another", callback_data="add_buyer")],
                [InlineKeyboardButton("Back to Menu", callback_data="main_menu")]
            ]
            await update.message.reply_text(f"✅ Buyer added: {name}", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.clear()

    elif step=="record_details":
        text = update.message.text
        amount = parse_amount(text)
        record = {
            "id":len(data["records"])+1,
            "buyer":context.user_data["buyer"],
            "details":text,
            "price":amount,
            "cost":0,
            "network":"",
            "status":"UNPAID",
            "paid_amount":0,
            "time":datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(record)
        save_data(data)
        await update.message.reply_text(f"📦 RECORDED\nID:{record['id']}\nBuyer:{record['buyer']}\nPrice:{record['price']:,.2f}")
        context.user_data.clear()

    elif step=="wallet_add" and is_admin(update.message.from_user.id):
        parts = update.message.text.split()
        if len(parts)!=2: await update.message.reply_text("Format: network amount"); return
        net, amt = parts[0].lower(), parse_amount(parts[1])
        if net not in ["smart","globe","tm"]: await update.message.reply_text("Invalid network"); return
        data["wallets"][net] = data.get("wallets",{}).get(net,0)+amt
        save_data(data)
        await update.message.reply_text(f"✅ Wallet updated: {net.upper()} {data['wallets'][net]:,.2f}")
        context.user_data.clear()

    elif step=="add_price" and is_admin(update.message.from_user.id):
        parts = update.message.text.split()
        if len(parts)!=4: await update.message.reply_text("Format: keyword price cost network"); return
        k,p,c,n = parts[0].lower(), parse_amount(parts[1]), parse_amount(parts[2]), parts[3].lower()
        if n not in ["smart","globe","tm"]: await update.message.reply_text("Network must be smart/globe/tm"); return
        data.setdefault("prices",{})[k] = {"price":p, "cost":c, "network":n}
        save_data(data)
        await update.message.reply_text(f"✅ Price added/updated: {k.upper()}={p} (Cost:{c}, Network:{n.upper()})")
        context.user_data.clear()

# ---------------- PAYMENT ----------------
async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    _, method, rid = query.data.split("_")
    rid = int(rid)
    for r in data["records"]:
        if r["id"]==rid:
            context.user_data["step"]="pay_record"
            context.user_data["record_id"]=rid
            context.user_data["method"]=method.upper()
            remaining = r["price"] - r["paid_amount"]
            await query.message.reply_text(f"Enter amount paid for record ID:{rid} (Unpaid:{remaining:,.2f}):")
            return

async def pay_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    if step!="pay_record": return
    amt = parse_amount(update.message.text)
    rid = context.user_data["record_id"]
    method = context.user_data["method"]
    data = load_data()
    for r in data["records"]:
        if r["id"]==rid:
            remaining = r["price"] - r["paid_amount"]
            pay = min(amt, remaining)
            r["paid_amount"] += pay
            r["status"] = "PAID" if r["paid_amount"]>=r["price"] else "UNPAID"
            save_data(data)
            await update.message.reply_text(
                f"✅ Payment recorded\nID:{rid}\nPaid:{pay:,.2f}\nTotal Paid:{r['paid_amount']:,.2f}\nRemaining:{r['price']-r['paid_amount']:,.2f}"
            )
            context.user_data.clear()
            return

# ---------------- REMINDER JOB ----------------
async def reminder_job(app):
    data = load_data()
    records = [r for r in data["records"] if r["status"]=="UNPAID"]
    if not records: return
    totals = {}
    msg = "⚠️ UNPAID RECORDS REMINDER:\n"
    for r in records:
        record_time = datetime.strptime(r["time"], "%Y-%m-%d %H:%M")
        if datetime.now().date() > record_time.date() and datetime.now().hour==0:
            r["price"] += 5  # delay fee at 12AM only
        totals[r["buyer"]] = totals.get(r["buyer"],0)+r["price"]
        msg += f"{r['time']} | {r['buyer']} | {r['details']} | {r['price']:,.2f} | {r['status']}\n"
    msg += "\n--- TOTAL PER BUYER ---\n"
    for b,t in totals.items():
        msg += f"{b}: {t:,.2f}\n"
    save_data(data)
    for admin_id in ADMIN_IDS:
        await app.bot.send_message(admin_id,msg)

# ---------------- MAIN ----------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(payment, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, pay_amount))

    # ---------------- APScheduler ----------------
    scheduler = AsyncIOScheduler()
    for hr in [0,8,17,20]:
        scheduler.add_job(reminder_job, "cron", hour=hr, minute=0, args=[app])
    scheduler.start()

    print("Bot running...")
    await app.run_polling()

if __name__=="__main__":
    asyncio.run(main())
