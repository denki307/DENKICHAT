import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand

# --- MAIN BOT LINK ---
MAIN_BOT_USERNAME = "PritiChatBot"  # <-- अपना main bot username डालें
GO_TO_CLONE_URL = f"https://t.me/{MAIN_BOT_USERNAME}?start=clone"

CLONE_IMG = "https://files.catbox.moe/ram63w.jpg"
# ↑ यहाँ जो image चाहिए उसका URL डालें


# --------------------------------------------------
# SET BOT COMMANDS (auto on start)
# --------------------------------------------------
@Client.on_message(filters.command("setcmds") & filters.user(OWNER_ID))
async def set_cmds(_, m):
    try:
        await _.set_bot_commands([
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Help menu"),
            BotCommand("ping", "Check bot status"),
            BotCommand("stats", "Show bot statistics"),
            BotCommand("gcast", "Broadcast (Owner only)")
        ])
        await m.reply_text("✅ Commands have been set successfully.")
    except Exception as e:
        await m.reply_text(f"❌ Failed to set commands:\n`{e}`")


# --------------------------------------------------
# BLOCK ALL CLONE COMMANDS
# --------------------------------------------------
@Client.on_message(filters.command(["clone", "host", "deploy", "idclone", "deploybot", "makebot"]))
async def block_clone(client, message):
    await message.reply_photo(
        photo=CLONE_IMG,
        caption=(
            "**❌ Cloning is not allowed here.**\n\n"
            "**🚀 Tap the button below to clone your bot safely.**"
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