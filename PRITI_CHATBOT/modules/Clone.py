import logging
import os
import time
import asyncio
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors.exceptions.bad_request_400 import AccessTokenExpired, AccessTokenInvalid

from config import API_ID, API_HASH, OWNER_ID
from PRITI_CHATBOT import PRITI_CHATBOT as app, save_clonebot_owner, CLONE_OWNERS
from PRITI_CHATBOT import db as mongodb

# DB collections (assumed motor/mongo async)
cloneownerdb = mongodb.cloneownerdb
clonebotdb = mongodb.clonebotdb

# Premium / payment settings
UPI_ID = "the.luckyxrajakumar@fam"   # change if needed
UPI_QR = "https://files.catbox.moe/vx7b94.png"  # change if needed

PENDING_PREMIUM = {}  # in-memory payment windows (user_id -> expiry_timestamp)
PREMIUM_LOG_CHAT = int(os.getenv("CLONE_LOGGER", OWNER_ID))

# In-memory runtime set of started clone bot ids
CLONES = set()

# Helper: mask token for privacy
def _mask_token(token: str) -> str:
    if not token or len(token) < 10:
        return "<hidden>"
    return "••••••" + token[-6:]


# ---------------------------
# /clone (and aliases /host, /deploy)
# - checks premium/limit first (unless OWNER or CLONE_OWNERS)
# - then requires token and attempts to start the cloned bot
# - stores token in DB (masked in messages)
# ---------------------------
@app.on_message(filters.command(["clone", "host", "deploy"]))
async def clone_txt(client, message):
    user_id = message.from_user.id
    user_db = await clonebotdb.find_one({"user_id": user_id}) or {}

    # bypass for owner or configured clone owners
    bypass_premium = (user_id == int(OWNER_ID)) or (user_id in CLONE_OWNERS)

    # If not bypass, require premium (show buy prompt even if token provided)
    if not bypass_premium:
        if not user_db.get("premium", False):
            # friendly english buy prompt
            return await message.reply_text(
                "💎 **Premium required — ₹99 / 30 days**\n"
                "You will be allowed to clone 1 bot per premium cycle.\n\n"
                "Press the button below to buy premium.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_premium")]]
                ),
            )

        expiry = user_db.get("expiry", 0)
        if expiry < time.time():
            await clonebotdb.update_one({"user_id": user_id}, {"$set": {"premium": False}})
            return await message.reply_text("⚠️ Your premium has expired. Please renew to continue.")

        if user_db.get("clones_left", 0) <= 0:
            return await message.reply_text("⚠️ You have used your clone allowance for this cycle.")

    # Now require token argument to proceed
    if len(message.command) <= 1:
        return await message.reply_text(
            "Usage: `/clone <BOT_TOKEN>`\n\nExample:\n`/clone 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`"
        )

    bot_token = message.text.split(maxsplit=1)[1].strip()
    mi = await message.reply_text("🔎 Validating bot token and starting clone...")

    # Validate token and start a client for the new bot
    try:
        ai = Client(bot_token, API_ID, API_HASH, bot_token=bot_token, plugins=dict(root="PRITI_CHATBOT/mplugin"))
        await ai.start()
        bot = await ai.get_me()
        bot_id = bot.id

        # save owner mapping (if your save_clonebot_owner expects something else, adjust)
        try:
            await save_clonebot_owner(bot_id, user_id)
        except Exception:
            # not critical; continue
            logging.exception("save_clonebot_owner failed")

        # set minimal commands for the cloned bot (friendly english)
        try:
            await ai.set_bot_commands([
                BotCommand("start", "Start the bot"),
                BotCommand("help", "Help & commands"),
                BotCommand("ping", "Check bot status"),
                BotCommand("repo", "Get source code"),
            ])
        except Exception:
            # ignore failures setting commands
            pass

    except (AccessTokenExpired, AccessTokenInvalid):
        return await mi.edit_text("❌ Invalid bot token. Please provide a valid token from @BotFather.")
    except Exception as e:
        # If already in DB, inform user; else log
        existing = await clonebotdb.find_one({"token": bot_token})
        if existing:
            return await mi.edit_text("ℹ️ This bot token has already been cloned.")
        logging.exception("Error while validating bot token")
        return await mi.edit_text(f"❌ Error while validating token: `{e}`")

    # Save clone details (token stored in DB; messages never show full token)
    try:
        details = {
            "bot_id": bot.id,
            "is_bot": True,
            "user_id": user_id,
            "name": bot.first_name or "",
            "username": bot.username or "",
            "token": bot_token,
            "created_at": int(time.time()),
            "active": True,
        }

        await clonebotdb.insert_one(details)
        CLONES.add(bot.id)

        # decrement clones_left for paid users (if not bypass)
        if not bypass_premium:
            await clonebotdb.update_one({"user_id": user_id}, {"$inc": {"clones_left": -1}})

        # notify owner with masked token
        try:
            await app.send_message(
                int(OWNER_ID),
                f"✅ New Clone Started\nBot: @{bot.username}\nBot ID: `{bot.id}`\nOwner: `{user_id}`\nToken: `{_mask_token(bot_token)}`"
            )
        except Exception:
            logging.exception("Failed to notify owner about new clone")

        await mi.edit_text(f"🎉 Bot @{bot.username} cloned successfully! Use /delclone to remove it.")

    except Exception as e:
        logging.exception("Error storing clone details")
        await mi.edit_text(f"⚠️ Error while saving clone: `{e}`")


# ---------------------------
# Premium buy flow (UPI QR + confirm)
# ---------------------------
@app.on_callback_query(filters.regex("^buy_premium$"))
async def buy_premium_cb(client, query):
    text = (
        "💎 **Premium: ₹99 / 30 Days**\n\n"
        f"Pay using UPI ID: `{UPI_ID}`\n\n"
        "Scan the QR or pay using your UPI app. After payment, press 'I Have Paid' and upload the screenshot in private chat (10 minutes)."
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✔ I Have Paid", callback_data="confirm_payment")]])
    try:
        await query.message.reply_photo(photo=UPI_QR, caption=text, reply_markup=keyboard)
    except Exception:
        await query.message.reply_text(text, reply_markup=keyboard)
    try:
        await query.message.delete()
    except:
        pass


@app.on_callback_query(filters.regex("^confirm_payment$"))
async def confirm_payment_cb(client, query):
    uid = query.from_user.id
    expires = (datetime.utcnow() + timedelta(minutes=10)).timestamp()
    PENDING_PREMIUM[uid] = expires
    await clonebotdb.update_one({"user_id": uid}, {"$set": {"pending_payment": True, "payment_window_expires": expires}}, upsert=True)
    await query.message.edit("🕒 10 minutes started. Please send the payment screenshot in private chat to me within 10 minutes.")


# Receive payment screenshot (private)
@app.on_message(filters.private & filters.photo)
async def receive_payment_screenshot(client, message):
    uid = message.from_user.id
    user_db = await clonebotdb.find_one({"user_id": uid}) or {}

    if not user_db.get("pending_payment"):
        # The user hasn't started a payment window — ignore silently
        return

    pending_ts = PENDING_PREMIUM.get(uid) or user_db.get("payment_window_expires", 0)
    now = datetime.utcnow().timestamp()
    if not pending_ts or now > pending_ts:
        PENDING_PREMIUM.pop(uid, None)
        await clonebotdb.update_one({"user_id": uid}, {"$set": {"pending_payment": False}}, upsert=True)
        return await message.reply_text("❌ Your payment window has expired. Start again via /clone → Buy Premium.")

    # Forward screenshot to premium log chat
    try:
        await message.forward(PREMIUM_LOG_CHAT)
    except Exception as e:
        return await message.reply_text(f"❌ Failed to forward screenshot: {e}")

    # Send approve/reject buttons to log chat
    try:
        user = message.from_user
        fullname = user.first_name + ((" " + user.last_name) if user.last_name else "")
        uname = f"@{user.username}" if user.username else "No username"
        await app.send_message(
            PREMIUM_LOG_CHAT,
            f"💸 Premium payment screenshot received\nUser: `{uid}`\nName: {fullname}\nUsername: {uname}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}")]
            ])
        )
    except Exception:
        logging.exception("Failed to notify premium log chat")

    # cleanup
    PENDING_PREMIUM.pop(uid, None)
    await clonebotdb.update_one({"user_id": uid}, {"$set": {"pending_payment": False}}, upsert=True)
    await message.reply_text("✅ Screenshot received. Please wait for admin approval.")


# Approve / Reject handlers (owner or CLONE_OWNERS)
@app.on_callback_query(filters.regex("^approve_"))
async def approve_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Only owner or authorized approvers can approve.", show_alert=True)
    try:
        uid = int(query.data.split("_", 1)[1])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    expiry = (datetime.utcnow() + timedelta(days=30)).timestamp()
    await clonebotdb.update_one({"user_id": uid}, {"$set": {"premium": True, "expiry": expiry, "clones_left": 1}}, upsert=True)
    try:
        await query.message.edit(f"✅ Premium approved for `{uid}` (30 days)")
    except:
        pass
    try:
        await app.send_message(uid, "🎉 Your premium has been approved! You can now clone 1 bot for 30 days.")
    except:
        pass


@app.on_callback_query(filters.regex("^reject_"))
async def reject_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Only owner or authorized approvers can reject.", show_alert=True)
    try:
        uid = int(query.data.split("_", 1)[1])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    await clonebotdb.update_one({"user_id": uid}, {"$set": {"premium": False, "pending_payment": False}}, upsert=True)
    try:
        await query.message.edit(f"❌ Premium rejected for `{uid}`")
    except:
        pass
    try:
        await app.send_message(uid, "❌ Your premium payment was rejected. Please try again with a valid screenshot.")
    except:
        pass


# Expiry watcher — notifies admins and marks premium false
async def expiry_watcher():
    while True:
        try:
            now = datetime.utcnow().timestamp()
            cursor = clonebotdb.find({"premium": True, "expiry": {"$lte": now}})
            expired = [d async for d in cursor]
            for doc in expired:
                uid = doc.get("user_id")
                try:
                    await app.send_message(
                        PREMIUM_LOG_CHAT,
                        f"⏳ Premium expired for user `{uid}`",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 Stop Cloned Bot", callback_data=f"stop_clone_{uid}"),
                             InlineKeyboardButton("▶️ Extend 30d", callback_data=f"extend_clone_{uid}")]
                        ])
                    )
                except:
                    logging.exception("Failed to notify premium expiry")

                await clonebotdb.update_one({"user_id": uid}, {"$set": {"premium": False}})
            await asyncio.sleep(60)
        except Exception:
            logging.exception("expiry_watcher error")
            await asyncio.sleep(60)

# Stop / Extend callbacks (owner or CLONE_OWNERS)
@app.on_callback_query(filters.regex("^stop_clone_"))
async def stop_clone_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Not allowed.", show_alert=True)
    try:
        uid = int(query.data.split("_", 2)[2])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    await clonebotdb.update_many({"user_id": uid}, {"$set": {"active": False}})
    docs = [d async for d in clonebotdb.find({"user_id": uid})]
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
        await app.send_message(uid, "🛑 Your cloned bots were stopped by admin.")
    except:
        pass


@app.on_callback_query(filters.regex("^extend_clone_"))
async def extend_clone_cb(client, query):
    actor = query.from_user.id
    if actor != int(OWNER_ID) and actor not in CLONE_OWNERS:
        return await query.answer("Not allowed.", show_alert=True)
    try:
        uid = int(query.data.split("_", 2)[2])
    except:
        return await query.answer("Invalid data.", show_alert=True)

    new_expiry = (datetime.utcnow() + timedelta(days=30)).timestamp()
    await clonebotdb.update_one({"user_id": uid}, {"$set": {"premium": True, "expiry": new_expiry, "clones_left": 1}}, upsert=True)
    try:
        await query.message.edit(f"▶️ Extended premium for `{uid}` by 30 days")
    except:
        pass
    try:
        await app.send_message(uid, "▶️ Your premium was extended. You may clone again.")
    except:
        pass

# Start expiry watcher (try-catch for event loop)
try:
    asyncio.get_event_loop().create_task(expiry_watcher())
except RuntimeError:
    pass


# ---------------------------
# /mybots - user sees only their own clones
# ---------------------------
@app.on_message(filters.command(["mybot", "mybots"]))
async def my_cloned_bots(client, message):
    try:
        user_id = message.from_user.id
        bots = [b async for b in clonebotdb.find({"user_id": user_id})]
        if not bots:
            return await message.reply_text("You have not cloned any bots yet.")
        text = f"🤖 Your Cloned Bots ({len(bots)}):\n\n"
        for bot in bots:
            text += f"• {bot.get('name','Unknown')} — @{bot.get('username','unknown')}\n"
        await message.reply_text(text)
    except Exception:
        logging.exception("mybots error")
        await message.reply_text("⚠️ Failed to load your bots.")


# ---------------------------
# /cloned - OWNER only: list all cloned bots
# ---------------------------
@app.on_message(filters.command("cloned"))
async def list_cloned_bots(client, message):
    if message.from_user.id != int(OWNER_ID):
        return await message.reply_text("❌ Only owner can view all cloned bots.")
    try:
        bots = [b async for b in clonebotdb.find({})]
        if not bots:
            return await message.reply_text("No cloned bots found.")
        text = f"🤖 All Cloned Bots ({len(bots)}):\n\n"
        for bot in bots:
            # safe fetch of fields to avoid KeyError
            name = bot.get("name", "Unknown")
            username = bot.get("username", "unknown")
            owner = bot.get("user_id", "unknown")
            text += f"• {name} — @{username} (Owner: `{owner}`)\n"
        await message.reply_text(text)
    except Exception as e:
        logging.exception("Error listing cloned bots")
        await message.reply_text("⚠️ Error while listing cloned bots. Check logs.")


# /totalbots - OWNER only
@app.on_message(filters.command("totalbots"))
async def total_bots(client, message):
    if message.from_user.id != int(OWNER_ID):
        return await message.reply_text("❌ Only owner can view total bots.")
    try:
        count = await clonebotdb.count_documents({})
        await message.reply_text(f"🤖 Total cloned bots: `{count}`")
    except Exception:
        logging.exception("totalbots error")
        await message.reply_text("⚠️ Failed to fetch total bots.")


# ---------------------------
# Delete handler
# - user can delete only their bot
# - owner can delete any bot
# ---------------------------
@app.on_message(filters.command(["delclone", "deleteclone", "delbot", "removeclone", "cancelclone", "delcloned"]))
async def delete_cloned_bot(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/delclone <token_or_username>`")

    query = " ".join(message.command[1:]).strip().replace("@", "")

    try:
        bot = await clonebotdb.find_one({"$or": [{"token": query}, {"username": query}]})
        if not bot:
            return await message.reply_text("❌ No cloned bot found with that token or username.")

        real_owner = int(bot.get("user_id"))
        caller = message.from_user.id

        if caller != real_owner and caller != int(OWNER_ID):
            return await message.reply_text("❌ You are not authorized to delete this bot.")

        await clonebotdb.delete_one({"_id": bot["_id"]})
        CLONES.discard(bot.get("bot_id"))
        return await message.reply_text(f"✅ Bot @{bot.get('username','unknown')} deleted successfully.")
    except Exception as e:
        logging.exception("delete_cloned_bot error")
        return await message.reply_text(f"⚠️ Error while deleting bot: {e}")


# ---------------------------
# /delallclone - OWNER only (delete all cloned bots)
# ---------------------------
@app.on_message(filters.command("delallclone"))
async def delete_all_cloned_bots(client, message):
    if message.from_user.id != int(OWNER_ID):
        return await message.reply_text("❌ Only owner can run this command.")
    msg = await message.reply_text("⚠️ Deleting all cloned bots... please wait.")
    try:
        await clonebotdb.delete_many({})
        CLONES.clear()
        await msg.edit("✅ All cloned bots deleted successfully.")
    except Exception as e:
        logging.exception("delallclone error")
        await msg.edit(f"⚠️ Error while deleting all clones: {e}")


# ---------------------------
# Restart helper (used by your start logic elsewhere)
# ---------------------------
async def restart_bots():
    try:
        logging.info("Restarting all cloned bots...")
        bots = [b async for b in clonebotdb.find({})]
        for bot in bots:
            token = bot.get("token")
            if not token:
                await clonebotdb.delete_one({"_id": bot["_id"]})
                continue
            try:
                ai = Client(token, API_ID, API_HASH, bot_token=token, plugins=dict(root="PRITI_CHATBOT/mplugin"))
                await ai.start()
                b = await ai.get_me()
                CLONES.add(b.id)
                await asyncio.sleep(1)
            except (AccessTokenExpired, AccessTokenInvalid):
                await clonebotdb.delete_one({"token": token})
            except Exception:
                logging.exception("Error restarting a clone bot")
        try:
            await app.send_message(int(OWNER_ID), "✅ All cloned bots started (restart task complete).")
        except:
            pass
    except Exception:
        logging.exception("restart_bots error")


# End of file