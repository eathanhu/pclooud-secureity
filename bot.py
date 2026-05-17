import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
)
from config import BOT_TOKEN, ADMIN_CHAT_ID
from models import approve_user, deny_user, update_user_login


async def send_registration_alert(email, ip, browser, os_name, device, location):
    from telegram import Bot
    bot = Bot(token=BOT_TOKEN)

    text = (
        f"New Registration Request\n\n"
        f"Email: {email}\n"
        f"IP: {ip}\n"
        f"Location: {location}\n"
        f"Browser: {browser}\n"
        f"OS: {os_name}\n"
        f"Device: {device}\n\n"
        f"Do you want to accept this user?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Accept", callback_data=f"accept:{email}"),
            InlineKeyboardButton("Deny", callback_data=f"deny:{email}"),
        ]
    ])

    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, reply_markup=keyboard)
    await bot.close()


async def send_login_alert(email, ip, browser, os_name, device, location, reason):
    from telegram import Bot
    bot = Bot(token=BOT_TOKEN)

    text = (
        f"Login Blocked\n\n"
        f"Email: {email}\n"
        f"IP: {ip}\n"
        f"Location: {location}\n"
        f"Browser: {browser}\n"
        f"OS: {os_name}\n"
        f"Device: {device}\n\n"
        f"Reason: {reason}\n\n"
        f"Do you want to allow this login?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Allow", callback_data=f"allow:{email}"),
            InlineKeyboardButton("Block", callback_data=f"block:{email}"),
        ]
    ])

    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, reply_markup=keyboard)
    await bot.close()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    action, email = data.split(":", 1)

    if action == "accept":
        approve_user(email)
        await query.edit_message_text(f"User {email} has been APPROVED.")
    elif action == "deny":
        deny_user(email)
        await query.edit_message_text(f"User {email} has been DENIED.")
    elif action == "allow":
        approve_user(email)
        await query.edit_message_text(f"Login for {email} ALLOWED. IP/device updated.")
    elif action == "block":
        deny_user(email)
        await query.edit_message_text(f"Login for {email} has been BLOCKED.")


def run_bot_background():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(handle_callback))

    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling(drop_pending_updates=True))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(app.updater.stop())
        loop.run_until_complete(app.stop())
        loop.run_until_complete(app.shutdown())
        loop.close()
