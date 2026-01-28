import json, os, re, asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN") or "8521646944:AAHMSVQqXGPr7WcaG6zkiO443DYdUOvADJ4"
ADMIN_IDS = [5955882128]  # replace with your telegram id
DATA_FILE = "data.json"

# ---------------- STORAGE ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "buyers": [],
            "records": [],
            "wallets": {"smart":0, "globe":0, "tm":0},
            "prices": {}
        }
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
        [InlineKeyboardButton("📊 Summary", callback_data="summary")],
        [InlineKeyboardButton("💲 Pricelist", callback_data="pricelist")],
        [InlineKeyboardButton("📄 Unpaid Receipt", callback_data="unpaid_receipt")],
        [InlineKeyboardButton("📅 Reports", callback_data="reports")]
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

    if query.data == "main_menu":
        await start(update, context)

    # ---------- ADD BUYER ----------
    elif query.data == "add_buyer":
        context.user_data["step"] = "add_buyer"
        kb = [
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
        ]
        await query.message.reply_text("Send buyer name:", reply_markup=InlineKeyboardMarkup(kb))

    # ---------- RECORD LOAD ----------
    elif query.data == "record_load":
        if not data["buyers"]:
            await query.message.reply_text("No buyers yet.")
            return
        kb = [[InlineKeyboardButton(b, callback_data=f"buyer_{b}")] for b in data["buyers"]]
        kb.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
        await query.message.reply_text("Select buyer:", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("buyer_"):
        buyer = query.data.replace("buyer_","")
        context.user_data["buyer"] = buyer
        context.user_data["step"] = "record_details"
        prices = data.get("prices",{})
        if prices:
            kb = [[InlineKeyboardButton(k.upper(), callback_data=f"price_{k}")] for k in prices]
            kb.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
            await query.message.reply_text(
                "Select keyword OR send manual:",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            kb = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
            await query.message.reply_text("Send load details & amount manually:", reply_markup=InlineKeyboardMarkup(kb))