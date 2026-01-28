import json
import os
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

TOKEN = os.getenv("TOKEN") or "PUT_YOUR_BOT_TOKEN_HERE"
ADMIN_IDS = [5955882128]  # CHANGE TO YOUR TELEGRAM ID
DATA_FILE = "data.json"

# ---------------- STORAGE ----------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"buyers": [], "records": [], "wallet": 0}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_admin(uid):
    return uid in ADMIN_IDS

def parse_amount(text):
    text = text.replace(",", "")
    match = re.search(r"\d+(\.\d+)?", text)
    return float(match.group()) if match else 0.0

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("➕ Add Buyer", callback_data="add_buyer")],
        [InlineKeyboardButton("📦 Record Load", callback_data="record_load")],
        [InlineKeyboardButton("💰 Wallet", callback_data="wallet")],
        [InlineKeyboardButton("📊 Summary", callback_data="summary")]
    ]
    await update.message.reply_text("📌 LOAD MANAGEMENT BOT", reply_markup=InlineKeyboardMarkup(kb))

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
        buyer = query.data.replace("buyer_", "")
        context.user_data["buyer"] = buyer
        context.user_data["step"] = "record_details"
        await query.message.reply_text("Send load details & amount:\nExample:\n09123456789 SA99 1,046.64")

    elif query.data == "wallet":
        bal = data.get("wallet", 0)
        await query.message.reply_text(f"💰 Wallet Balance: {bal:,.2f}")
        if is_admin(query.from_user.id):
            await query.message.reply_text("Send amount to ADD:")

            context.user_data["step"] = "wallet_add"

    elif query.data == "summary":
        total = sum(r["price"] for r in data["records"])
        unpaid = sum(r["price"] for r in data["records"] if r["status"] == "UNPAID")
        paid = total - unpaid

        txt = (
            f"📊 SALES SUMMARY\n\n"
            f"Total: {total:,.2f}\n"
            f"Paid: {paid:,.2f}\n"
            f"Unpaid: {unpaid:,.2f}\n"
        )
        await query.message.reply_text(txt)

# ---------------- MESSAGE HANDLER ----------------

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    step = context.user_data.get("step")

    if step == "add_buyer":
        name = update.message.text.strip()
        data["buyers"].append(name)
        save_data(data)
        context.user_data.clear()
        await update.message.reply_text(f"✅ Buyer added: {name}")

    elif step == "record_details":
        text = update.message.text
        amount = parse_amount(text)

        record = {
            "id": len(data["records"]) + 1,
            "buyer": context.user_data["buyer"],
            "details": text,
            "price": amount,
            "status": "UNPAID",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        data["records"].append(record)
        save_data(data)
        context.user_data.clear()

        kb = [[
            InlineKeyboardButton("💳 GCash", callback_data=f"pay_gcash_{record['id']}"),
            InlineKeyboardButton("💳 Maya", callback_data=f"pay_maya_{record['id']}")
        ]]

        await update.message.reply_text(
            f"📦 RECORDED\nID: {record['id']}\nAmount: {amount:,.2f}",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif step == "wallet_add":
        amt = parse_amount(update.message.text)
        data["wallet"] = data.get("wallet", 0) + amt
        save_data(data)
        context.user_data.clear()
        await update.message.reply_text(f"✅ Wallet updated: {data['wallet']:,.2f}")

# ---------------- PAYMENT ----------------

async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    _, method, rid = query.data.split("_")
    rid = int(rid)

    for r in data["records"]:
        if r["id"] == rid:
            r["status"] = "PAID"
            r["payment"] = method.upper()
            save_data(data)

            await query.message.reply_text(
                f"✅ Payment recorded\nID: {rid}\nMethod: {method.upper()}"
            )
            return

# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(payment, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
