import json, os, re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import pandas as pd
from reportlab.pdfgen import canvas

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
        [InlineKeyboardButton("💲 Pricelist", callback_data="pricelist")]
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
        await query.message.reply_text("Send buyer name:")

    # RECORD LOAD
    elif query.data=="record_load":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b, callback_data=f"buyer_{b}")] for b in data["buyers"]]
        await query.message.reply_text("Select buyer:", reply_markup=InlineKeyboardMarkup(kb))

    # SELECT BUYER
    elif query.data.startswith("buyer_"):
        buyer=query.data.replace("buyer_","")
        context.user_data["buyer"]=buyer
        context.user_data["step"]="record_details"
        prices = data.get("prices", {})
        if prices:
            kb = [[InlineKeyboardButton(k.upper(), callback_data=f"price_{k}")] for k in prices.keys()]
            await query.message.reply_text("Select a price keyword or type details & amount manually:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.message.reply_text("Send load details & amount:\nExample:\n09123456789 SA99 1,046.64")

    # PRICE SELECTION
    elif query.data.startswith("price_"):
        keyword = query.data.replace("price_","")
        price_info = data.get("prices",{}).get(keyword)
        if not price_info:
            await query.message.reply_text("Price not found.")
            return
        record = {
            "id": len(data["records"])+1,
            "buyer": context.user_data["buyer"],
            "details": f"{keyword} {price_info['price']}",
            "price": price_info["price"],
            "status": "UNPAID",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(record)
        save_data(data)
        kb = [[InlineKeyboardButton("💳 GCash",callback_data=f"pay_gcash_{record['id']}"),
               InlineKeyboardButton("💳 Maya",callback_data=f"pay_maya_{record['id']}")]]
        await query.message.reply_text(f"📦 RECORDED\nID:{record['id']}\nBuyer:{record['buyer']}\nAmount:{record['price']:,.2f}", reply_markup=InlineKeyboardMarkup(kb))
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
        total = sum(r["price"] for r in data["records"])
        unpaid = sum(r["price"] for r in data["records"] if r["status"]=="UNPAID")
        paid = sum(r["price"] for r in data["records"] if r["status"]=="PAID")
        txt = f"📊 SALES SUMMARY\nTotal: {total:,.2f}\nPaid: {paid:,.2f}\nUnpaid: {unpaid:,.2f}"
        await query.message.reply_text(txt)

    # HISTORY
    elif query.data=="buyer_history":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b,callback_data=f"history_{b}")] for b in data["buyers"]]
        await query.message.reply_text("Select buyer:", reply_markup=InlineKeyboardMarkup(kb))

    # PRICELIST
    elif query.data=="pricelist":
        txt="💲 PRICELIST\n"
        for k,v in data.get("prices",{}).items():
            txt+=f"{k.upper()} = {v['price']} ({v['network'].upper()})\n"
        await query.message.reply_text(txt)
        if is_admin(query.from_user.id):
            context.user_data["step"]="add_price"
            await query.message.reply_text("Send new price: keyword price network\nExample: SA99 50 smart")

# ---------------- MESSAGES ----------------
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    step = context.user_data.get("step")

    if step=="add_buyer":
        name=update.message.text.strip()
        if name not in data["buyers"]:
            data["buyers"].append(name)
            save_data(data)
            await update.message.reply_text(f"✅ Buyer added: {name}")
        context.user_data.clear()

    elif step=="record_details":
        text=update.message.text
        amount=parse_amount(text)
        record={
            "id":len(data["records"])+1,
            "buyer":context.user_data["buyer"],
            "details":text,
            "price":amount,
            "status":"UNPAID",
            "time":datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        data["records"].append(record)
        save_data(data)
        kb=[[InlineKeyboardButton("💳 GCash",callback_data=f"pay_gcash_{record['id']}"),
             InlineKeyboardButton("💳 Maya",callback_data=f"pay_maya_{record['id']}")]]
        await update.message.reply_text(f"📦 RECORDED\nID:{record['id']}\nBuyer:{record['buyer']}\nAmount:{amount:,.2f}",reply_markup=InlineKeyboardMarkup(kb))
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
        if len(parts)!=3: await update.message.reply_text("Format: keyword price network"); return
        k,p,n=parts[0].lower(),parse_amount(parts[1]),parts[2].lower()
        if n not in ["smart","globe","tm"]: await update.message.reply_text("Network must be smart/globe/tm"); return
        data.setdefault("prices",{})[k]={"price":p,"network":n}
        save_data(data)
        await update.message.reply_text(f"✅ Price added/updated: {k.upper()}={p} ({n.upper()})")
        context.user_data.clear()

# ---------------- PAYMENT ----------------
async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query=update.callback_query
    await query.answer()
    data=load_data()
    _, method, rid = query.data.split("_")
    rid=int(rid)
    for r in data["records"]:
        if r["id"]==rid:
            r["status"]="PAID"
            r["payment"]=method.upper()
            save_data(data)
            await query.message.reply_text(f"✅ Payment recorded\nID:{rid}\nMethod:{method.upper()}")
            return

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CallbackQueryHandler(payment,pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,messages))
    print("Bot running...")
    app.run_polling(close_loop=False)

if __name__=="__main__":
    main()
