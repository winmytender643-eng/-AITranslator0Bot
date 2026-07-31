"""
AITranslator0Bot - AI image generation Telegram bot (DALL-E powered).

Commands:
  /start    - welcome message + starting credits
  /balance  - check your credit balance
  /generate <prompt> - generate an image (also works: just send plain text)
  /grant <user_id> <amount> - (admin only) add credits to a user
  /help     - usage help
"""

import logging
import os

from openai import OpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")  # your Telegram numeric user id, as a string
COST_PER_IMAGE = int(os.getenv("COST_PER_IMAGE", "1"))
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "dall-e-3")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1024x1024")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")

openai_client = OpenAI(api_key=OPENAI_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    balance = database.get_or_create_user(user.id, user.username)
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm AITranslator0Bot 🎨\n\n"
        f"Send me any text prompt (or use /generate <prompt>) and I'll turn it "
        f"into an AI-generated image.\n\n"
        f"You have {balance} free credit(s) to start "
        f"({COST_PER_IMAGE} credit per image).\n"
        f"Use /balance any time to check your credits, /help for more info."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How to use me:\n"
        "• /generate a red fox in the snow, digital art\n"
        "• or just type a prompt directly, no command needed\n"
        "• /balance - check your remaining credits\n"
        f"Each image costs {COST_PER_IMAGE} credit(s)."
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bal = database.get_or_create_user(user.id, user.username)
    await update.message.reply_text(f"💳 You have {bal} credit(s) remaining.")


async def grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not ADMIN_ID or str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("You're not authorized to do that.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /grant <user_id> <amount>")
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Both user_id and amount must be numbers.")
        return

    database.get_or_create_user(target_id, None)
    new_balance = database.add_credits(target_id, amount)
    await update.message.reply_text(
        f"Granted {amount} credit(s) to {target_id}. New balance: {new_balance}."
    )


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    database.get_or_create_user(user.id, user.username)

    prompt = " ".join(context.args) if context.args else update.message.text
    if not prompt or not prompt.strip():
        await update.message.reply_text(
            "Send me a text prompt to generate an image, e.g.\n"
            "/generate a cyberpunk city at night"
        )
        return

    if not database.try_spend_credit(user.id, COST_PER_IMAGE):
        await update.message.reply_text(
            "🚫 You're out of credits. Contact the bot admin to top up."
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO
    )
    status_msg = await update.message.reply_text("🎨 Generating your image...")

    try:
        response = openai_client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size=IMAGE_SIZE,
            n=1,
        )
        image_url = response.data[0].url
        remaining = database.get_balance(user.id)
        await update.message.reply_photo(
            photo=image_url,
            caption=f"✅ Done! Credits remaining: {remaining}",
        )
    except Exception as exc:  # noqa: BLE001 - report and refund on any failure
        logger.exception("Image generation failed")
        database.add_credits(user.id, COST_PER_IMAGE)  # refund since it failed
        await update.message.reply_text(
            f"⚠️ Something went wrong generating that image, so your credit "
            f"was refunded. Error: {exc}"
        )
    finally:
        await status_msg.delete()


def main():
    database.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("grant", grant))
    app.add_handler(CommandHandler("generate", generate_image))
    # Any plain text message (that isn't a command) is treated as a prompt
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
