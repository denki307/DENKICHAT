import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- MAIN BOT LINK ---
MAIN_BOT_USERNAME = "PritiChatBot"  # <-- सिर्फ अपना main bot username डालें

GO_TO_CLONE_URL = f"https://t.me/{MAIN_BOT_USERNAME}?start=clone"

CLONE_IMG = "https://files.catbox.moe/ram63w.jpg" 
# ↑ यहाँ जो image चाहिए उसका URL डालें


# -------------- BLOCK CLONE SYSTEM --------------
@Client.on_message(filters.command(["clone", "host", "deploy"]))
async def clone_block(client, message):
    await message.reply_photo(
        photo=CLONE_IMG,
        caption=(
            "**❌ Cloning is not allowed here.**\n\n"
            "**👉 Tap the button below to clone your bot safely.**"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🚀 Go To Clone", url=GO_TO_CLONE_URL
                    )
                ]
            ]
        )
    )
# --------------------------------------------------


# -------------- NORMAL FEATURES (SAFE FOR USER) --------------
@Client.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text(
        "✨ **Welcome! I am active and ready.**\n"
        "Use /help to see commands."
    )


@Client.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "**📜 Available Commands:**\n\n"
        "• /start – Start the bot\n"
        "• /help – Help menu\n"
        "• /ping – Check bot status\n"
        "• /stats – Bot statistics\n"
        "• /gcast – Broadcast (Owner only)\n\n"
        "⚠️ **Clone commands are disabled here. Use main bot.**"
    )


@Client.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    await message.reply_text("🏓 Pong! Bot is alive.")


@Client.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    await message.reply_text("📊 **Bot statistics are currently active.**")


@Client.on_message(filters.command("gcast"))
async def gcast_cmd(client, message):
    if message.from_user.id != int(client.me.id):
        return await message.reply_text("❌ Owner only.")
    
    await message.reply_text("✔ Global broadcast feature active.")
# ---------------------------------------------------------------