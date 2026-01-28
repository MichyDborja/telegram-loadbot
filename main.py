import json, os, re, asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

TOKEN = os.getenv("TOKEN") or "YOUR_BOT_TOKEN_HERE"
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
        [InlineKeyboardButton("⚠️ Unpaid List", callback_data="unpaid_list")]
    ]
    await update.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=InlineKeyboardMarkup(kb))

# ---------------- BUTTON HANDLER ----------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    # ADD BUYER
    if query.data=="add_buyer":
        context.user_data["step"]="add_buyer"
        kb=[[InlineKeyboardButton("Back to Menu", callback_data="back_main")]]
        await query.message.reply_text("Send buyer name:", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data=="back_main":
        await start(update, context)

    # RECORD LOAD
    elif query.data=="record_load":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b, callback_data=f"buyer_{b}")] for b in data["buyers"]]
        await query.message.reply_text("Select buyer:", reply_markup=InlineKeyboardMarkup(kb))

    # SELECT BUYER
    elif query.data.startswith("buyer_"):
        buyer = query.data.replace("buyer_","")
        context.user_data["buyer"]=buyer
        context.user_data["step"]="record_details"
        prices = data.get("prices", {})
        if prices:
            kb = [[InlineKeyboardButton(k.upper(), callback_data=f"price_{k}")] for k in prices.keys()]
            await query.message.reply_text("Select a price keyword or type details & amount manually:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.message.reply_text("Send load details & amount manually:\nExample:\n09123456789 SA99 1,046.64")

    # PRICE SELECTION
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
        await query.message.reply_text(f"📦 RECORDED\nID:{record['id']}\nBuyer:{record['buyer']}\nPrice:{record['price']:,.2f}\nCost:{record['cost']:,.2f}\nNetwork:{network.upper()}")
        context.user_data.clear()

    # WALLET
    elif query.data=="wallet":
        wallets = data.get("wallets",{"smart":0,"globe":0,"tm":0})
        txt = "💰 WALLET BALANCES\n"
        for k,v in wallets.items(): txt+=f"{k.upper()}: {v:,.2f}\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"]="wallet_add"
            await query.message.reply_text("Send amount and network to ADD:\nExample:\nsmart 1000")

    # SUMMARY
    elif query.data=="summary":
        total_sales = sum(r["price"] for r in data["records"])
        total_paid = sum(r["paid_amount"] for r in data["records"])
        total_unpaid = total_sales - total_paid
        total_cost = sum(r.get("cost",0) for r in data["records"])
        total_profit = total_paid - total_cost
        txt = f"📊 SALES SUMMARY\nTotal Sales: {total_sales:,.2f}\nTotal Paid: {total_paid:,.2f}\nTotal Unpaid: {total_unpaid:,.2f}\nTotal Cost: {total_cost:,.2f}\nProfit: {total_profit:,.2f}"
        await query.message.reply_text(txt)

    # HISTORY
    elif query.data=="buyer_history":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b,callback_data=f"history_{b}")] for b in data["buyers"]]
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
            txt+=f"{r['time']} | {r['details']} | {r['price']:,.2f} | {status}\n"
        await query.message.reply_text(txt)

    # PRICELIST
    elif query.data=="pricelist":
        txt="💲 PRICELIST\n"
        for k,v in data.get("prices",{}).items():
            txt+=f"{k.upper()} = {v['price']} (Cost:{v['cost']}, Network:{v['network'].upper()})\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"]="add_price"
            await query.message.reply_text("Send new price: keyword price cost network\nExample: SA99 50 48.5 smart")

    # UNPAID LIST
    elif query.data=="unpaid_list":
        records = [r for r in data["records"] if r["status"]=="UNPAID"]
        if not records:
            await query.message.reply_text("No unpaid records.")
            return
        msg = "⚠️ UNPAID LIST\n"
        totals = {}
        for r in records:
            # delay fee: only 12AM updates
            record_time = datetime.strptime(r['time'], "%Y-%m-%d %H:%M")
            delay = 0
            if datetime.now().date() > record_time.date():
                delay = 5
            price_with_delay = r["price"] + delay
            totals[r["buyer"]] = totals.get(r["buyer"],0) + price_with_delay
            msg += f"{r['time']} | {r['buyer']} | {r['details']} | {price_with_delay:,.2f} | {r['status']}\n"
        msg += "\n--- TOTAL PER BUYER ---\n"
        for b, t in totals.items():
            msg += f"{b}: {t:,.2f}\n"
        await query.message.reply_text(msg)

# ---------------- MESSAGES ----------------
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    step = context.user_data.get("step")

    if step=="add_buyer":
        name=update.message.text.strip()
        if name not in data["buyers"]:
            data["buyers"].append(name)
            save_data(data)
            kb=[[InlineKeyboardButton("Add Another", callback_data="add_buyer")],
                [InlineKeyboardButton("Back to Menu", callback_data="back_main")]]
            await update.message.reply_text(f"✅ Buyer added: {name}", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.clear()

    elif step=="record_details":
        text=update.message.text
        amount=parse_amount(text)
        record={
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
        await update.message.reply_text(f"📦 RECORDED\nID:{record['id']}\nBuyer:{record['buyer']}\nPrice:{amount:,.2f}")
        context.user_data.clear()

    elif step=="wallet_add" and is_admin(update.message.from_user.id):
        parts=update.message.text.split()
        if len(parts)!=2: await update.message.reply_text("Format: network amount"); return
        net, amt = parts[0].lower(), parse_amount(parts[1])
        if net not in ["smart","globe","tm"]: await update.message.reply_text("Invalid network"); return
        data["wallets"][net] = data.get("wallets",{}).get(net,0)+amt
        save_data(data)
        await update.message.reply_text(f"✅ Wallet updated: {net.upper()} {data['wallets'][net]:,.2f}")
        context.user_data.clear()

    elif step=="add_price" and is_admin(update.message.from_user.id):
        parts=update.message.text.split()
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
            await query.message.reply_text(f"Enter amount paid for record ID:{rid} (Unpaid:{r['price']-r['paid_amount']:,.2f}):")
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
            if r["paid_amount"]>=r["price"]: r["status"]="PAID"
            save_data(data)
            await update.message.reply_text(f"✅ Payment recorded\nID:{rid}\nPaid:{pay:,.2f}\nTotal Paid:{r['paid_amount']:,.2f}\nRemaining:{r['price']-r['paid_amount']:,.2f}")
            context.user_data.clear()
            return

# ---------------- UNPAID REMINDER ----------------
async def unpaid_reminder(app):
    data = load_data()
    records = [r for r in data["records"] if r["status"]=="UNPAID"]
    if not records:
        return
    msg = "⚠️ UNPAID RECORDS REMINDER:\n"
    totals = {}
    for r in records:
        record_time = datetime.strptime(r['time'], "%Y-%m-%d %H:%M")
        delay = 0
        if datetime.now().date() > record_time.date():
            delay = 5
        price_with_delay = r["price"] + delay
        totals[r["buyer"]] = totals.get(r["buyer"],0) + price_with_delay
        msg += f"{r['time']} | {r['buyer']} | {r['details']} | {price_with_delay:,.2f} | {r['status']}\n"
    msg += "\n--- TOTAL PER BUYER ---\n"
    for b,t in totals.items():
        msg += f"{b}: {t:,.2f}\n"
    for admin_id in ADMIN_IDS:
        await app.bot.send_message(admin_id,msg)

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(payment, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, pay_amount))

    # Scheduler
    scheduler = AsyncIOScheduler()
    # Delay fee updates at 12AM
    scheduler.add_job(lambda: asyncio.create_task(unpaid_reminder(app)), CronTrigger(hour=0, minute=0))
    # Unpaid reminders at 12AM, 8AM, 5PM, 8PM
    for hour in [0,8,17,20]:
        scheduler.add_job(lambda: asyncio.create_task(unpaid_reminder(app)), CronTrigger(hour=hour, minute=0))
    scheduler.start()

    print("Bot running...")
    app.run_polling(close_loop=False)

if __name__=="__main__":
    main()
