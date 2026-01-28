import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = "8521646944:AAHMSVQqXGPr7WcaG6zkiO443DYdUOvADJ4"  # Replace with your bot token
DATA_FILE = "data.json"
ADMIN_IDS = [5955882128]  # Replace with your Telegram ID

# ---------------- STORAGE ----------------
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "buyers": {},
            "records": [],
            "prices": {
                "mb": {"price":6.0,"network":"smart"},
                "gb": {"price":6.0,"network":"smart"},
                "sa99": {"price":50.0,"network":"smart"},
                "patt": {"price":50.0,"network":"smart"},
                "pafb": {"price":50.0,"network":"smart"},
                "goplus99": {"price":93.0,"network":"globe"}
            },
            "wallets": {"smart":0.0,"globe":0.0,"tm":0.0}
        }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ---------------- MAIN MENU ----------------
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Add Buyer", callback_data="add_buyer")],
        [InlineKeyboardButton("Buyers", callback_data="list_buyers")],
        [InlineKeyboardButton("Record Load", callback_data="record_load")],
        [InlineKeyboardButton("View Records", callback_data="view_records")],
        [InlineKeyboardButton("Price List", callback_data="price_list")],
        [InlineKeyboardButton("Wallet", callback_data="wallet")]
    ]
    if is_admin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("Update Wallet", callback_data="update_wallet")])

    if update.message:
        await update.message.reply_text("📋 Main Menu", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.message.edit_text("📋 Main Menu", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------------- BUTTON HANDLER ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    # Main menu
    if query.data == "main_menu":
        await main_menu(update, context)

    # Add buyer
    elif query.data == "add_buyer":
        await query.message.reply_text("Type buyer name:")
        context.user_data["action"] = "adding_buyer"

    # List buyers
    elif query.data == "list_buyers":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        keyboard = [[InlineKeyboardButton(b, callback_data=f"buyer_{b}")] for b in data["buyers"]]
        keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
        await query.message.reply_text("Select Buyer:", reply_markup=InlineKeyboardMarkup(keyboard))

    # Buyer menu
    elif query.data.startswith("buyer_"):
        buyer = query.data.split("_",1)[1]
        context.user_data["current_buyer"] = buyer
        keyboard = [
            [InlineKeyboardButton("Record Load", callback_data="buyer_record_load")],
            [InlineKeyboardButton("View History", callback_data="buyer_history")],
            [InlineKeyboardButton("Back", callback_data="list_buyers")]
        ]
        await query.message.reply_text(f"Buyer: {buyer}", reply_markup=InlineKeyboardMarkup(keyboard))

    # Record load
    elif query.data == "record_load":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet. Add one first!")
            return
        keyboard = [[InlineKeyboardButton(b, callback_data=f"select_buyer_{b}")] for b in data["buyers"]]
        keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
        await query.message.reply_text("Select a buyer to record load:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("select_buyer_"):
        buyer = query.data.split("_",2)[2]
        context.user_data["current_buyer"] = buyer
        context.user_data["action"] = "recording_load"
        await query.message.reply_text(f"Buyer selected: {buyer}\nSend load details (ex: 09123456789 1000mb / sa99)")

    elif query.data == "buyer_record_load":
        buyer = context.user_data.get("current_buyer")
        if not buyer:
            await query.message.reply_text("No buyer selected. Please select a buyer first.")
            return
        context.user_data["action"] = "recording_load"
        await query.message.reply_text(f"Buyer selected: {buyer}\nSend load details (ex: 09123456789 1000mb / sa99)")

    # Buyer history
    elif query.data == "buyer_history":
        buyer = context.user_data.get("current_buyer")
        if not buyer or buyer not in data["buyers"]:
            await query.message.reply_text("Buyer not found.")
            return
        txt = f"History for {buyer}:\n"
        total = 0
        for r in data["buyers"][buyer]:
            txt += f"#{r['id']} | {r['number']} | {r['details']} | {r['price']:.2f}php | {r['status']}\n"
            if r['status'] == "UNPAID":
                total += r['price']
        txt += f"TOTAL UNPAID BALANCE: {total:,.2f}php"
        await query.message.reply_text(txt)

    # View records
    elif query.data == "view_records":
        if not data["records"]:
            await query.message.reply_text("No records yet.")
            return
        keyboard = []
        for r in data["records"]:
            keyboard.append([
                InlineKeyboardButton(f"PAID #{r['id']}", callback_data=f"paid_{r['id']}"),
                InlineKeyboardButton(f"UNPAID #{r['id']}", callback_data=f"unpaid_{r['id']}"),
                InlineKeyboardButton(f"Payment #{r['id']}", callback_data=f"record_{r['id']}")
            ])
        keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
        await query.message.reply_text("Records:", reply_markup=InlineKeyboardMarkup(keyboard))

    # Update status
    elif query.data.startswith("paid_") or query.data.startswith("unpaid_"):
        action, rid = query.data.split("_")
        rid = int(rid)
        for r in data["records"]:
            if r["id"] == rid:
                r["status"] = action.upper()
                save_data(data)
                await query.message.reply_text(f"Updated record #{rid} -> {action.upper()}")
                return

    # Payment tagging
    elif query.data.startswith("record_"):
        rid = int(query.data.split("_")[1])
        context.user_data["payment_rid"] = rid
        keyboard = [
            [InlineKeyboardButton("GCash", callback_data="pay_gcash")],
            [InlineKeyboardButton("Maya", callback_data="pay_maya")],
            [InlineKeyboardButton("Back", callback_data="view_records")]
        ]
        await query.message.reply_text(f"Select payment method for record #{rid}:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("pay_"):
        method = query.data.split("_")[1]
        context.user_data["payment_method"] = method
        context.user_data["action"] = "tag_payment"
        await query.message.reply_text(f"Enter payment amount via {method.upper()} (e.g., 1,046.64):")

    # Price list
    elif query.data == "price_list":
        txt = "PRICELIST:\n"
        for k,v in data["prices"].items():
            txt += f"{k} = {v['price']:.2f}php ({v['network']})\n"
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        await query.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(keyboard))

    # Wallet
    elif query.data == "wallet":
        wallets = data.get("wallets", {"smart":0.0,"globe":0.0,"tm":0.0})
        txt = f"Wallet Balances:\nSMART: {wallets['smart']:,.2f}php\nGLOBE: {wallets['globe']:,.2f}php\nTM: {wallets['tm']:,.2f}php"
        await query.message.reply_text(txt)

    # Update wallet (admin)
    elif query.data == "update_wallet":
        if not is_admin(query.from_user.id):
            await query.message.reply_text("Admin only")
            return
        keyboard = [
            [InlineKeyboardButton("SMART", callback_data="wallet_smart")],
            [InlineKeyboardButton("GLOBE", callback_data="wallet_globe")],
            [InlineKeyboardButton("TM", callback_data="wallet_tm")],
            [InlineKeyboardButton("Back", callback_data="main_menu")]
        ]
        await query.message.reply_text("Select network to update:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("wallet_"):
        net = query.data.split("_")[1]
        context.user_data["action"] = "update_wallet"
        context.user_data["wallet_network"] = net
        await query.message.reply_text(f"Enter amount to ADD to {net.upper()} wallet (e.g., 1,046.64):")

# ---------------- MESSAGE HANDLER ----------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    # Add buyer
    if context.user_data.get("action") == "adding_buyer":
        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("Name cannot be empty.")
            return
        data["buyers"][name] = []
        save_data(data)
        context.user_data.clear()
        await update.message.reply_text(f"Buyer added: {name}")

    # Record load
    elif context.user_data.get("action") == "recording_load":
        buyer = context.user_data.get("current_buyer")
        if not buyer:
            await update.message.reply_text("No buyer selected.")
            return
        text = update.message.text.lower().strip()
        if not text:
            await update.message.reply_text("Load details cannot be empty.")
            return

        number = text.split()[0]
        price = 0.0
        network = "unknown"
        for key, val in data["prices"].items():
            if key in text:
                price = float(val["price"]) if isinstance(val, dict) else float(val)
                network = val["network"] if isinstance(val, dict) else "unknown"
                break

        rec_id = len(data["records"]) + 1
        record = {
            "id": rec_id,
            "buyer": buyer,
            "number": number,
            "details": text,
            "price": price,
            "status": "SOLD",
            "network": network
        }
        data["records"].append(record)
        data["buyers"][buyer].append(record)
        save_data(data)
        context.user_data.clear()
        await update.message.reply_text(f"✅ Recorded load!\nID: {rec_id}\nBuyer: {buyer}\nPrice: {price:,.2f}php\nNetwork: {network}")

    # Update wallet
    elif context.user_data.get("action") == "update_wallet":
        net = context.user_data.get("wallet_network")
        try:
            amt = float(update.message.text.strip().replace(",", ""))
        except:
            await update.message.reply_text("Please enter a valid number (e.g., 1,046.64).")
            return
        data["wallets"][net] += amt
        save_data(data)
        context.user_data.clear()
        await update.message.reply_text(f"✅ {net.upper()} wallet updated! New balance: {data['wallets'][net]:,.2f}php")

    # Tag payment
    elif context.user_data.get("action") == "tag_payment":
        rid = context.user_data.get("payment_rid")
        method = context.user_data.get("payment_method")
        try:
            amt = float(update.message.text.strip().replace(",", ""))
        except:
            await update.message.reply_text("Please enter a valid amount (e.g., 1,046.64).")
            return

        for r in data["records"]:
            if r["id"] == rid:
                r["payment"] = {"method": method.upper(), "amount": amt}
                r["status"] = "PAID"
                save_data(data)
                context.user_data.clear()
                await update.message.reply_text(f"✅ Payment recorded!\nRecord #{rid}\nMethod: {method.upper()}\nAmount: {amt:,.2f}php")
                return

# ---------------- RUN BOT ----------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_handler(MessageHandler(filters.COMMAND, main_menu))  # /start triggers main menu

print("Bot running...")
app.run_polling()