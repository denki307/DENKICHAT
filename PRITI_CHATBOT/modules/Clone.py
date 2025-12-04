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

        # --- User Clone Limit (Owner unlimited) ---
        user_id = message.from_user.id

        if user_id != int(OWNER_ID):
            existing_clone = await clonebotdb.find_one({"user_id": user_id})
            if existing_clone:
                await mi.edit_text(
                    f"**⚠️ You can clone only 1 bot!**\n"
                    f"**You already cloned:** @{existing_clone['username']}\n\n"
                    f"🗑 Remove clone → `/delclone {existing_clone['token']}`"
                )
                return

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

            user_id = message.from_user.id
            await save_clonebot_owner(bot_id, user_id)

            await ai.set_bot_commands(
                [
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
                ]
            )

        except (AccessTokenExpired, AccessTokenInvalid):
            await mi.edit_text("**Invalid bot token. Please provide a valid one.**")
            return

        except Exception as e:
            cloned_bot = await clonebotdb.find_one({"token": bot_token})
            if cloned_bot:
                await mi.edit_text("**🤖 Your bot is already cloned ✅**")
                return

        await mi.edit_text("**Cloning process started. Please wait for the bot to start.**")

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

# ----- USER FULL DETAILS MESSAGE -----
user_details = (
    "✨ **Clone Successful!**\n\n"
    "**👤 User Details:**\n"
    f"• Name: {mention}\n"
    f"• User ID:** `{user_id}`\n"
    f"• Username:** @{message.from_user.username}\n\n"
    
    "**🤖 Bot Details:**\n"
    f"• Bot Name:** {bot.first_name}\n"
    f"• Bot Username:** @{bot.username}\n"
    f"• Bot ID:** `{bot.id}`\n"
    "• Status:** `Running Successfully ✓`\n\n"
    
    "**🔐 Bot Token (Hidden):**\n"
    f"`{bot_token[:10]}*************************`\n\n"

    f"Thanks {mention} ❤️\n"
    "See your clone: `/cloned`\n"
    f"Delete clone: `/delclone {bot_token}`"
)

# ----- SEND TO USER -----
await message.reply_text(user_details, parse_mode="Markdown")

# ===============================
#  SEND LOG TO OWNER (MAIN BOT OWNER)
# ===============================
owner_log = (
    "🆕 **New Clone Created**\n\n"
    f"👤 **User:** {mention} (`{user_id}`)\n"
    f"🤖 **Bot:** @{bot.username}\n"
    f"📛 **Bot ID:** `{bot.id}`\n"
    f"🔢 **Token:** `{bot_token}`\n"
)

await app.send_message(int(OWNER_ID), owner_log, parse_mode="Markdown")

# ===============================
#  SEND LOG TO LOGGER GROUP
# ===============================
try:
    logger_msg = (
        "📢 **New Clone Log**\n\n"
        f"👤 User: {mention} (`{user_id}`)\n"
        f"🤖 Bot: @{bot.username}\n"
        f"🆔 Bot ID: `{bot.id}`\n"
        f"🔑 Token: `{bot_token}`\n\n"
        "🔥 Clone Completed Successfully!"
    )

    await app.send_message(config.LOGGER_GROUP, logger_msg, parse_mode="Markdown")

except Exception as e:
    print("Logger send error:", e)


@app.on_message(filters.command("cloned"))
async def list_cloned_bots(client, message):
    try:
        user_id = message.from_user.id

        # ------------ OWNER: See All Clones ------------
        if user_id == int(OWNER_ID):
            cloned_bots = await clonebotdb.find().to_list(length=None)
            if not cloned_bots:
                return await message.reply_text("No bots have been cloned yet.")

            total_clones = len(cloned_bots)
            text = f"**👑 Total Cloned Bots:** {total_clones}\n\n"

            for bot in cloned_bots:
                text += (
                    f"**🤖 Bot Username:** @{bot['username']}\n"
                    f"**Bot Name:** {bot['name']}\n"
                    f"**Bot ID:** `{bot['bot_id']}`\n"
                    f"**Owner ID:** `{bot['user_id']}`\n\n"
                )

            return await message.reply_text(text)

        # ------------ USER: See Only Own Clone ------------
        my_clone = await clonebotdb.find_one({"user_id": user_id})

        if not my_clone:
            return await message.reply_text("**❌ You have not cloned any bot yet.**")

        # User sees ONLY his bot
        text = (
            "**🤖 Your Cloned Bot:**\n\n"
            f"**Bot Username:** @{my_clone['username']}\n"
            f"**Bot Name:** {my_clone['name']}\n"
            f"**Bot ID:** `{my_clone['bot_id']}`\n"
        )

        return await message.reply_text(text)

    except Exception as e:
        logging.exception(e)
        await message.reply_text("**An error occurred while listing cloned bots.**")



@app.on_message(
    filters.command(["deletecloned", "delcloned", "delclone", "deleteclone", "removeclone", "cancelclone"])
)
async def delete_cloned_bot(client, message):

    try:
        if len(message.command) < 2:
            await message.reply_text("**⚠️ Please provide the bot token after the command.**")
            return

        bot_token = " ".join(message.command[1:])
        ok = await message.reply_text("**Checking the bot token...**")

        cloned_bot = await clonebotdb.find_one({"token": bot_token})

        if cloned_bot:
            await clonebotdb.delete_one({"token": bot_token})

            try:
                CLONES.remove(cloned_bot["bot_id"])
            except:
                pass

            await ok.edit_text(
                f"**🤖 your cloned bot has been removed from my database ✅**\n"
                f"**🔄 Kindly revoke your bot token from @botfather otherwise your bot will stop when @{app.username} will restart ☠️**"
            )

        else:
            await message.reply_text(
                "**Provide Bot Token after /delclone Command from @Botfather.**\n\n"
                "**Example:** `/delclone bot token paste here`"
            )

    except Exception as e:
        await message.reply_text(f"**An error occurred while deleting the cloned bot:** {e}")
        logging.exception(e)



async def restart_bots():

    global CLONES

    try:
        logging.info("Restarting all cloned bots...")
        bots = [bot async for bot in clonebotdb.find()]

        async def restart_bot(bot):
            bot_token = bot["token"]
            ai = Client(
                bot_token,
                API_ID,
                API_HASH,
                bot_token=bot_token,
                plugins=dict(root="PRITI_CHATBOT/mplugin")
            )

            try:
                await ai.start()
                bot_info = await ai.get_me()

                await ai.set_bot_commands(
                    [
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
                    ]
                )

                if bot_info.id not in CLONES:
                    CLONES.add(bot_info.id)

            except (AccessTokenExpired, AccessTokenInvalid):
                await clonebotdb.delete_one({"token": bot_token})
                logging.info(f"Removed expired or invalid token for bot ID: {bot['bot_id']}")

            except Exception as e:
                logging.exception(f"Error while restarting bot with token {bot_token}: {e}")

        await asyncio.gather(*(restart_bot(bot) for bot in bots))

    except Exception as e:
        logging.exception("Error while restarting bots.")



@app.on_message(filters.command("delallclone") & filters.user(int(OWNER_ID)))
async def delete_all_cloned_bots(client, message):

    try:
        a = await message.reply_text("**Deleting all cloned bots...**")
        await clonebotdb.delete_many({})
        CLONES.clear()

        await a.edit_text("**All cloned bots have been deleted successfully ✅**")
        os.system(f"kill -9 {os.getpid()} && bash start")

    except Exception as e:
        await a.edit_text(f"**An error occurred while deleting all cloned bots.** {e}")
        logging.exception(e)