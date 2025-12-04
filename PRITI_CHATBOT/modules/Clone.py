import logging
import os
import sys
import shutil
import asyncio
import time
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.errors.exceptions.bad_request_400 import AccessTokenExpired, AccessTokenInvalid
import config
from pyrogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_HASH, API_ID, OWNER_ID
from PRITI_CHATBOT import CLONE_OWNERS
from PRITI_CHATBOT import PRITI_CHATBOT as app, save_clonebot_owner
from PRITI_CHATBOT import db as mongodb

# --- New imports / constants for premium system ---
from datetime import datetime, timedelta

UPI_ID = "the.luckyxrajakumar@fam"  # <-- change to your UPI ID if needed
UPI_QR = "https://files.catbox.moe/vx7b94.png"  # <-- change to your QR link if needed

# In-memory pending payments window (user_id -> expiry_timestamp)
PENDING_PREMIUM = {}

# where screenshots and expiry notifications will be sent (use OWNER_ID or a logger chat)
PREMIUM_LOG_CHAT = int(os.getenv("CLONE_LOGGER", OWNER_ID))

# --- existing globals from your code ---
CLONES = set()
cloneownerdb = mongodb.cloneownerdb
clonebotdb = mongodb.clonebotdb

# ---------------------------
# Helper: mask token for privacy (show only last 6 chars)
# ---------------------------
def _mask_token(token: str) -> str:
    if not token or len(token) < 10:
        return "<hidden>"
    # show only last 6 chars, rest masked
    return "••••••" + token[-6:]


# ---------------------------
# Modified /clone handler with premium + limit enforcement
# ---------------------------
@app.on_message(filters.command(["clone", "host", "deploy"]))
async def clone_txt(client, message):
    if len(message.command) <= 1:
        await message.reply_text("**Provide Bot Token after /clone Command from @Botfather.**\n\n**Example:** `/clone bot token paste here`")
        return

    bot_token = message.text.split("/clone", 1)[1].strip()
    user_id = message.from_user.id

    # fetch user's premium record (async)
    user_data = await clonebotdb.find_one({"user_id": user_id}) or {}

    # owners or configured clone owners bypass premium/limits
    bypass_premium = (user_id == int(OWNER_ID)) or (user_id in CLONE_OWNERS)

    # if not bypass, require premium
    if not bypass_premium:
        if not user_data.get("premium", False):
            # prompt to buy
            await message.reply_text(
                "💎 **Premium Required**\n"
                "Price: ₹99 / 30 Days\n"
                "Limit: 1 Bot Clone\n\n",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_premium")]]
                ),
            )
            return

        # check expiry
        expiry = user_data.get("expiry", 0)
        if expiry < time.time():
            # expire premium in DB
            await clonebotdb.update_one({"user_id": user_id}, {"$set": {"premium": False}})
            await message.reply_text("⚠️ Your premium expired! Buy again for ₹99.")
            return

        # check clones left
        if user_data.get("clones_left", 0) <= 0:
            await message.reply_text("⚠️ You already used your 1 clone limit.")
            return

    # proceed cloning attempt
    mi = await message.reply_text("Please wait while I check the bot token.")
    try:
        ai = Client(bot_token, API_ID, API_HASH, bot_token=bot_token, plugins=dict(root="PRITI_CHATBOT/mplugin"))
        await ai.start()
        bot = await ai.get_me()
        bot_id = bot.id
        # save clone owner mapping
        await save_clonebot_owner(bot_id, user_id)

        # set commands (no token leaks here)
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
        await mi.edit_text("**Invalid bot token. Please provide a valid one.**")
        return
    except Exception as e:
        # if bot token already cloned, inform user (keep token private)
        cloned_bot = await clonebotdb.find_one({"token": bot_token})
        if cloned_bot:
            await mi.edit_text("**🤖 Your bot is already cloned ✅**")
            return
        logging.exception("Error while validating bot token")
        await mi.edit_text(f"**Error while validating bot token:**\n`{e}`")
        return

    # store details but DO NOT leak token in messages/logs
    try:
        details = {
            "bot_id": bot.id,
            "is_bot": True,
            "user_id": user_id,
            "name": bot.first_name,
            "token": bot_token,  # stored securely in DB, we will not print it
            "username": bot.username,
            "created_at": int(time.time()),
            "active": True,
        }

        # insert to db
        await clonebotdb.insert_one(details)
        CLONES.add(bot.id)

        # decrement clones_left for paid users
        if not bypass_premium:
            await clonebotdb.update_one({"user_id": user_id}, {"$inc": {"clones_left": -1}})

        # notify owner but mask the token for privacy
        try:
            await app.send_message(
                int(OWNER_ID),
                f"**#New_Clone**\n\n**Bot:- @{bot.username}**\n\n**Details:-**\n"
                f"Bot ID: `{bot.id}`\n"
                f"Name: `{bot.first_name}`\n"
                f"Owner ID: `{user_id}`\n"
                f"Token: `{_mask_token(bot_token)}`\n"
            )
        except Exception:
            logging.exception("Couldn't send new clone notification to owner")

        await mi.edit_text(
            f"**Bot @{bot.username} has been successfully cloned and started ✅.**\n"
            f"**Remove clone by :- /delclone**\n"
            f"**Check all cloned bot list by:- /cloned**"
        )

    except BaseException as e:
        logging.exception("Error while cloning bot.")
        await mi.edit_text(
            f"⚠️ <b>Error:</b>\n\n<code>{e}</code>\n\n**Contact owner for assistance**"
        )


# ---------------------------
# Buy premium flow: send UPI details + QR
# ---------------------------
@app.on_callback_query(filters.regex("^buy_premium$"))
async def buy_premium_cb(client, query):
    uid = query.from_user.id

    text = (
        "💎 *Premium: ₹99 / 30 Days*\n\n"
        "📌 *Pay Using UPI ID:*\n"
        f"`{UPI_ID}`\n\n"
        "📥 Scan the QR below to pay instantly.\n\n"
        "After payment, click the button below to start your 10-minute window to upload the screenshot."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✔ I Have Paid", callback_data="confirm_payment")]
        ]
    )

    # send QR with caption
    try:
        await query.message.reply_photo(
            photo=UPI_QR,
            caption=text,
            reply_markup=keyboard
        )
    except Exception:
        # fallback to sending text only
        await query.message.reply_text(text, reply_markup=keyboard)

    # remove the previous buy premium message for cleanliness
    try:
        await query.message.delete()
    except:
        pass


# start payment window
@app.on_callback_query(filters.regex("^confirm_payment$"))
async def confirm_payment_cb(client, query):
    uid = query.from_user.id
    expires = (datetime.utcnow() + timedelta(minutes=10)).timestamp()
    PENDING_PREMIUM[uid] = expires
    # mark pending_payment in DB (upsert)
    await clonebotdb.update_one({"user_id": uid}, {"$set": {"pending_payment": True, "payment_window_expires": expires}}, upsert=True)
    await query.message.edit("🕒 *10 minutes started.* Please send payment screenshot in private chat within 10 minutes.")


# receive screenshot in private
@app.on_message(filters.private & filters.photo)
async def receive_payment_screenshot(client, message):
    uid = message.from_user.id

    # Fetch user data
    user_db = await clonebotdb.find_one({"user_id": uid}) or {}

    pending_payment = user_db.get("pending_payment", False)
    pending_ts = PENDING_PREMIUM.get(uid) or user_db.get("payment_window_expires", 0)
    now = datetime.utcnow().timestamp()

    # If user didn't start flow, ignore silently
    if not pending_payment:
        return

    # If window expired
    if not pending_ts or now > pending_ts:
        PENDING_PREMIUM.pop(uid, None)
        await clonebotdb.update_one({"user_id": uid}, {"$set": {"pending_payment": False}}, upsert=True)
        await message.reply_text(
            "❌ Your payment window has expired.\n"
            "Please start again via /clone → Buy Premium."
        )
        return

    # Forward screenshot to PREMIUM_LOG_CHAT for manual review
    try:
        fwd = await message.forward(PREMIUM_LOG_CHAT)
    except Exception as e:
        return await message.reply_text(f"Error forwarding screenshot: {e}")

    user = message.from_user
    fullname = user.first_name + (" " + user.last_name if user.last_name else "")
    username = f"@{user.username}" if user.username else "None"

    # send a message in premium log chat with approve/reject buttons
    try:
        await app.send_message(
            PREMIUM_LOG_CHAT,
            f"👤 **Premium Payment Screenshot Received**\n"
            f"━━━━━━━━━━━━━━\n"
            f"🆔 **User ID:** `{uid}`\n"
            f"👤 **Name:** {fullname}\n"
            f"🔗 **Username:** {username}\n"
            f"👉 **Mention:** {user.mention}\n"
            f"━━━━━━━━━━━━━━\n"
            f"Approve or Reject:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}")
                ]
            ])
        )
    except Exception:
        logging.exception("Failed to notify PREMIUM_LOG_CHAT")

    # Clear pending after screenshot is received
    PENDING_PREMIUM.pop(uid, None)
    await clonebotdb.update_one({"user_id": uid}, {"$set": {"pending_payment": False}}, upsert=True)
    await message.reply_text("📨 Your screenshot has been received. Please wait for approval.")


# ---------------------------
# Approve / Reject handlers (only OWNER_ID or CLONE_OWNERS can approve)
# ---------------------------
@app.on_callback_query(filters.regex("^approve_"))
async def approve_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Only owner or clone owners can approve.", show_alert=True)

    try:
        uid = int(query.data.split("_",1)[1])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    # Count how many bots user already cloned
    total_clones = await clonebotdb.count_documents({"user_id": uid}) + 1

    # set premium and expiry and clones_left = 1
    expiry = (datetime.utcnow() + timedelta(days=30)).timestamp()
    await clonebotdb.update_one(
        {"user_id": uid},
        {"$set": {"premium": True, "expiry": expiry, "clones_left": 1}},
        upsert=True
    )

    # notify in log message (edit)
    approved_text = (
        "✅ **Premium Successfully Approved!**\n\n"
        f"👤 **User ID:** `{uid}`\n"
        f"🤖 **Total Bots Cloned (After Approval):** **Bot #{total_clones}**\n"
        f"⏳ **Validity:** 30 Days\n"
    )

    try:
        await query.message.edit(approved_text)
    except:
        pass

    # notify user privately
    try:
        await app.send_message(
            uid,
            f"🎉 **Premium Approved!**\n"
            f"Now you can clone **1 bot** (valid for 30 days).\n\n"
            f"Use /clone to start cloning."
        )
    except:
        pass


@app.on_callback_query(filters.regex("^reject_"))
async def reject_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Only owner or clone owners can reject.", show_alert=True)
    try:
        uid = int(query.data.split("_",1)[1])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    await clonebotdb.update_one({"user_id": uid}, {"$set": {"premium": False, "pending_payment": False}}, upsert=True)
    try:
        await query.message.edit(f"❌ Premium rejected for `{uid}`")
    except:
        pass
    try:
        await app.send_message(uid, "❌ Your premium request was rejected. Please try again with a valid screenshot.")
    except:
        pass


# ---------------------------
# Expiry watcher: notifies PREMIUM_LOG_CHAT when premium expires with Stop / Extend buttons
# ---------------------------
async def expiry_watcher():
    while True:
        try:
            now = datetime.utcnow().timestamp()
            expired_cursor = clonebotdb.find({"premium": True, "expiry": {"$lte": now}})
            expired = [doc async for doc in expired_cursor]
            for doc in expired:
                uid = doc.get("user_id")
                # notify admin log chat with options
                try:
                    await app.send_message(
                        PREMIUM_LOG_CHAT,
                        f"⏳ Premium expired for user `{uid}`\nTake action:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 Stop Cloned Bot", callback_data=f"stop_clone_{uid}"),
                             InlineKeyboardButton("▶️ Continue (extend 30d)", callback_data=f"extend_clone_{uid}")]
                        ])
                    )
                except:
                    logging.exception("Couldn't send expiry notification")

                # mark premium false to prevent duplicate notifications
                await clonebotdb.update_one({"user_id": uid}, {"$set": {"premium": False}})
            # check every 60 seconds
            await asyncio.sleep(60)
        except Exception:
            logging.exception("expiry_watcher error")
            await asyncio.sleep(60)

# handlers for stop / extend actions (owner or CLONE_OWNERS allowed)
@app.on_callback_query(filters.regex("^stop_clone_"))
async def stop_clone_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Only owner or clone owners can perform this.", show_alert=True)
    try:
        uid = int(query.data.split("_")[2])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    # deactivate user's cloned bots
    await clonebotdb.update_many({"user_id": uid}, {"$set": {"active": False}})
    docs_cursor = clonebotdb.find({"user_id": uid})
    docs = [d async for d in docs_cursor]
    for d in docs:
        try:
            CLONES.discard(d.get("bot_id"))
        except:
            pass

    try:
        await query.message.edit(f"🛑 Stopped cloned bots for `{uid}`")
    except:
        pass
    try:
        await app.send_message(uid, "🛑 Your cloned bots were stopped by admin due to premium expiry.")
    except:
        pass


@app.on_callback_query(filters.regex("^extend_clone_"))
async def extend_clone_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Only owner or clone owners can perform this.", show_alert=True)
    try:
        uid = int(query.data.split("_")[2])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    new_expiry = (datetime.utcnow() + timedelta(days=30)).timestamp()
    await clonebotdb.update_one({"user_id": uid}, {"$set": {"premium": True, "expiry": new_expiry, "clones_left": 1}}, upsert=True)
    try:
        await query.message.edit(f"▶️ Extended premium for `{uid}` by 30 days")
    except:
        pass
    try:
        await app.send_message(uid, "▶️ Your premium was extended by admin. You can continue using your cloned bot.")
    except:
        pass


# try to start expiry watcher if loop is ready
try:
    asyncio.get_event_loop().create_task(expiry_watcher())
except RuntimeError:
    # event loop not ready; it will be started when bot starts elsewhere
    pass


# ======================================================
# Existing handlers (list, delete, restart etc.) — kept largely unchanged but updated to use async db calls and token privacy
# ======================================================

@app.on_message(filters.command("cloned"))
async def list_cloned_bots(client, message):
    try:
        cloned_bots_cursor = clonebotdb.find()
        cloned_bots_list = [b async for b in cloned_bots_cursor]
        if not cloned_bots_list:
            await message.reply_text("No bots have been cloned yet.")
            return
        total_clones = len(cloned_bots_list)
        text = f"**Total Cloned Bots:** {total_clones}\n\n"
        for bot in cloned_bots_list:
            text += f"**Bot ID:** `{bot['bot_id']}`\n"
            text += f"**Bot Name:** {bot.get('name','Unknown')}\n"
            text += f"**Bot Username:** @{bot.get('username','Unknown')}\n\n"
        await message.reply_text(text)
    except Exception as e:
        logging.exception(e)
        await message.reply_text("**An error occurred while listing cloned bots.**")


@app.on_message(
    filters.command(
        ["deletecloned", "delcloned", "delclone", "deleteclone", "removeclone", "cancelclone"]
    )
)
async def delete_cloned_bot(client, message):
    try:
        if len(message.command) < 2:
            await message.reply_text("**⚠️ Please provide the bot token or username after the command.**")
            return

        bot_token_or_username = " ".join(message.command[1:]).strip()
        ok = await message.reply_text("**Checking...**")

        # attempt search by token or username
        cloned_bot = await clonebotdb.find_one({"$or": [{"token": bot_token_or_username}, {"username": bot_token_or_username}]})
        if cloned_bot:
            bot_info = f"**BOT ID**: `{cloned_bot['bot_id']}`\n" \
               f"**BOT NAME**: {cloned_bot.get('name','Unknown')}\n" \
               f"**USERNAME**: @{cloned_bot.get('username','Unknown')}\n" \
               f"**OWNER**: `{cloned_bot.get('user_id')}`\n"

            # check ownership
            c_owner = await cloneownerdb.find_one({"bot_id": cloned_bot['bot_id']})
            c_owner_id = c_owner.get("owner_id") if c_owner else None
            OWNERS = [int(OWNER_ID)]
            if c_owner_id:
                try:
                    OWNERS.append(int(c_owner_id))
                except:
                    pass

            if message.from_user.id not in OWNERS:
                await ok.edit_text("You are not authorized to delete this cloned bot.")
                return

            # delete and cleanup
            await clonebotdb.delete_one({"_id": cloned_bot["_id"]})
            CLONES.discard(cloned_bot["bot_id"])

            await ok.edit_text("✅ Your cloned bot has been removed from the database.")
            # send sanitized info to owner/logger
            try:
                await app.send_message(PREMIUM_LOG_CHAT, bot_info)
            except:
                pass
        else:
            await ok.edit_text("**No cloned bot found with that token/username.**")
    except Exception as e:
        await message.reply_text(f"**An error occurred while deleting the cloned bot:** {e}")
        logging.exception(e)


async def restart_bots():
    global CLONES
    try:
        logging.info("Restarting all cloned bots...")
        bots_cursor = clonebotdb.find()
        bots = [b async for b in bots_cursor]
        
        async def restart_bot(bot):
            bot_token = bot["token"]
            ai = Client(bot_token, API_ID, API_HASH, bot_token=bot_token, plugins=dict(root="PRITI_CHATBOT/mplugin"))
            try:
                await ai.start()
                bot_info = await ai.get_me()
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

                if bot_info.id not in CLONES:
                    CLONES.add(bot_info.id)
                    
            except (AccessTokenExpired, AccessTokenInvalid):
                await clonebotdb.delete_one({"token": bot_token})
                logging.info(f"Removed expired or invalid token for bot ID: {bot.get('bot_id')}")
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

# End of file