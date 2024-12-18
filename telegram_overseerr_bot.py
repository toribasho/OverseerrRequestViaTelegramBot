import logging
import requests
import urllib.parse
import ast

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Attempt to import all variables from config.py, including PASSWORD and WHITELIST.
# If PASSWORD and WHITELIST are not defined (older config version), an ImportError will occur.
try:
    from config import OVERSEERR_API_URL, OVERSEERR_API_KEY, TELEGRAM_TOKEN, PASSWORD, WHITELIST
except ImportError:
    # If the user is using an older config.py without PASSWORD and WHITELIST,
    # we define them here with default values. This ensures backward compatibility
    # and prevents the bot from crashing when these variables are missing.
    from config import OVERSEERR_API_URL, OVERSEERR_API_KEY, TELEGRAM_TOKEN
    PASSWORD = ""     # No password set by default
    WHITELIST = []     # Empty whitelist by default

VERSION = "2.3.0"
BUILD = "2024.12.18.101"  # Incremented build number

# Status codes
STATUS_UNKNOWN = 1
STATUS_PENDING = 2
STATUS_PROCESSING = 3
STATUS_PARTIALLY_AVAILABLE = 4
STATUS_AVAILABLE = 5

ISSUE_TYPES = {
    1: "Video",
    2: "Audio",
    3: "Subtitle",
    4: "Other"
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

in_memory_whitelist = set(WHITELIST)

def user_is_authorized(user_id: int) -> bool:
    if not PASSWORD:
        return True
    return user_id in in_memory_whitelist

async def request_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 *Access Restricted*\n\n"
        "Please enter the password to use this bot:",
        parse_mode="Markdown"
    )
    context.user_data['awaiting_password'] = True

def check_password(user_input: str) -> bool:
    return user_input.strip() == PASSWORD.strip()

def update_whitelist_in_config(new_user_id: int):
    """
    Updates the WHITELIST in config.py by adding the new user_id if it's not already present.
    This approach reads the file line-by-line, finds the WHITELIST line, parses it, updates it, and rewrites it.
    Assumes WHITELIST is defined in a single line in config.py.
    """
    config_file_path = "config.py"
    try:
        with open(config_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        whitelist_line_index = None
        for i, line in enumerate(lines):
            if line.strip().startswith("WHITELIST"):
                whitelist_line_index = i
                break

        if whitelist_line_index is not None:
            # Parse the current WHITELIST line
            # We expect something like WHITELIST = [123456, ...]
            line = lines[whitelist_line_index]
            # Split on '=', take the right side
            right_side = line.split("=", 1)[1].strip()
            # Safely evaluate the Python list
            current_whitelist = ast.literal_eval(right_side)

            if new_user_id not in current_whitelist:
                current_whitelist.append(new_user_id)
                # Rewrite the line
                new_line = f"WHITELIST = {current_whitelist}\n"
                lines[whitelist_line_index] = new_line

                # Write back the file
                with open(config_file_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                logger.info(f"Successfully updated WHITELIST in config.py with user_id {new_user_id}")
    except Exception as e:
        logger.error(f"Failed to update WHITELIST in config.py: {e}")

def search_media(media_name: str):
    try:
        query_params = {'query': media_name}
        encoded_query = urllib.parse.urlencode(query_params, quote_via=urllib.parse.quote)
        url = f"{OVERSEERR_API_URL}/search?{encoded_query}"
        response = requests.get(
            url,
            headers={
                "X-Api-Key": OVERSEERR_API_KEY,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error during media search: {e}")
        return None

def process_search_results(results: list):
    processed_results = []
    for result in results:
        media_title = (
            result.get("name")
            or result.get("originalName")
            or result.get("title")
            or "Unknown Title"
        )

        date_key = "firstAirDate" if result["mediaType"] == "tv" else "releaseDate"
        media_year = result.get(date_key, "")
        media_year = media_year.split("-")[0] if media_year else "Unknown Year"

        media_info = result.get("mediaInfo")
        if media_info:
            media_status = media_info.get("status")
            overseerr_media_id = media_info.get("id")
        else:
            media_status = None
            overseerr_media_id = None

        processed_results.append(
            {
                "title": media_title,
                "year": media_year,
                "id": result["id"],
                "mediaType": result["mediaType"],
                "status": media_status,
                "poster": result.get("posterPath"),
                "description": result.get("overview", "No description available"),
                "overseerr_id": overseerr_media_id,
            }
        )
    return processed_results

def get_latest_version_from_github():
    """Check GitHub releases to find the latest version name."""
    try:
        response = requests.get(
            "https://api.github.com/repos/LetsGoDude/OverseerrRequestViaTelegramBot/releases/latest",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        latest_version = data.get("name", "")  # Use 'name' field
        return latest_version
    except requests.RequestException as e:
        logger.warning(f"Failed to check latest version: {e}")
        return ""

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if PASSWORD and not user_is_authorized(user_id):
        await request_password(update, context)
        return

    latest_version = get_latest_version_from_github()
    is_newer_available = False
    newer_version_text = ""
    if latest_version:
        # Strip the 'v' from the start if present
        latest_version_stripped = latest_version.strip().lstrip("v")
        if latest_version_stripped > VERSION:
            is_newer_available = True
            newer_version_text = f"\n🔔 A new version (v{latest_version_stripped}) is available!"

    start_message = (
         f"👋 Welcome to the Overseerr Telegram Bot! v{VERSION}"
        f"{newer_version_text}"  # This line will be empty if no new version is found
        "\n\n🎬 *What I can do:*\n"
        "- Search movies & TV shows\n"
        "- Check availability\n"
        "- Request new titles\n"
        "- Report issues\n\n"
        "💡 *How to start:* Type `/check <title>`\n"
        "_Example: `/check Venom`_"
    )

    await update.message.reply_text(start_message, parse_mode="Markdown")


async def check_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if PASSWORD and not user_is_authorized(user_id):
        await request_password(update, context)
        return

    if not context.args:
        await update.message.reply_text("Please provide a title for me to check.")
        return

    media_name = " ".join(context.args)
    search_data = search_media(media_name)
    if not search_data:
        await update.message.reply_text(
            "An error occurred during the search. Please try again later."
        )
        return

    results = search_data.get("results", [])
    if not results:
        await update.message.reply_text(
            "No results found. Please try a different title."
        )
        return

    processed_results = process_search_results(results)
    context.user_data["search_results"] = processed_results

    sent_message = await display_results_with_buttons(
        update, context, processed_results, offset=0
    )
    context.user_data["results_message_id"] = sent_message.message_id

async def display_results_with_buttons(
    update_or_query,
    context: ContextTypes.DEFAULT_TYPE,
    results: list,
    offset: int,
    new_message: bool = False,
):
    keyboard = []
    for idx, result in enumerate(results[offset : offset + 5]):
        year = result.get("year", "Unknown Year")
        button_text = f"{result['title']} ({year})"
        callback_data = f"select_{offset + idx}"
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=callback_data)]
        )

    total_results = len(results)
    is_first_page = offset == 0
    is_last_page = offset + 5 >= total_results

    navigation_buttons = []
    if is_first_page:
        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")
        if total_results > 5:
            more_button = InlineKeyboardButton("➡️ More", callback_data=f"page_{offset + 5}")
            navigation_buttons = [cancel_button, more_button]
        else:
            navigation_buttons = [cancel_button]
    elif is_last_page:
        back_button = InlineKeyboardButton("⬅️ Back", callback_data=f"page_{offset - 5}")
        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")
        navigation_buttons = [back_button, cancel_button]
    else:
        back_button = InlineKeyboardButton("⬅️ Back", callback_data=f"page_{offset - 5}")
        x_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")
        more_button = InlineKeyboardButton("➡️ More", callback_data=f"page_{offset + 5}")
        navigation_buttons = [back_button, x_button, more_button]

    if navigation_buttons:
        keyboard.append(navigation_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    if new_message:
        sent_message = await context.bot.send_message(
            chat_id=update_or_query.message.chat_id,
            text="Please select a result:",
            reply_markup=reply_markup,
        )
        return sent_message
    elif isinstance(update_or_query, Update) and update_or_query.message:
        sent_message = await update_or_query.message.reply_text(
            "Please select a result:", reply_markup=reply_markup
        )
        return sent_message
    elif isinstance(update_or_query, CallbackQuery):
        await update_or_query.edit_message_text(
            text="Please select a result:", reply_markup=reply_markup
        )
        return
    else:
        sent_message = await context.bot.send_message(
            chat_id=update_or_query.effective_chat.id,
            text="Please select a result:",
            reply_markup=reply_markup
        )
        return sent_message

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if PASSWORD and not user_is_authorized(user_id):
        await query.edit_message_text(
            text="You need to be authorized. Please use /start and enter the password first."
        )
        return

    data = query.data
    results = context.user_data.get("search_results", [])

    if data.startswith("select_"):
        result_index = int(data.split("_")[1])
        if result_index < len(results):
            selected_result = results[result_index]
            await process_user_selection(update, context, selected_result)
    elif data.startswith("page_"):
        offset = int(data.split("_")[1])
        await display_results_with_buttons(query, context, results, offset)
    elif data.startswith("confirm_"):
        media_id = int(data.split("_")[1])
        selected_result = next((r for r in results if r["id"] == media_id), None)

        if selected_result:
            is_tv = selected_result["mediaType"] == "tv"
            media_status = selected_result.get("status")
            if media_status in [STATUS_AVAILABLE, STATUS_PROCESSING, STATUS_PARTIALLY_AVAILABLE]:
                if media_status == STATUS_AVAILABLE:
                    message = f"ℹ️ *{selected_result['title']}* is already available."
                elif media_status == STATUS_PROCESSING:
                    message = f"⏳ *{selected_result['title']}* is currently being processed."
                elif media_status == STATUS_PARTIALLY_AVAILABLE:
                    message = f"⏳ *{selected_result['title']}* is partially available."
                else:
                    message = f"ℹ️ *{selected_result['title']}* cannot be requested at this time."

                if query.message.photo:
                    await query.edit_message_caption(
                        caption=message, parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(
                        text=message, parse_mode="Markdown"
                    )
            else:
                success = request_media(media_id, selected_result["mediaType"], is_tv)

                if query.message.photo:
                    if success:
                        await query.edit_message_caption(
                            caption=f"✅ *{selected_result['title']}* has been successfully requested!",
                            parse_mode="Markdown",
                        )
                    else:
                        await query.edit_message_caption(
                            caption=f"❌ Failed to request *{selected_result['title']}*. Please try again later.",
                            parse_mode="Markdown",
                        )
                else:
                    if success:
                        await query.edit_message_text(
                            text=f"✅ *{selected_result['title']}* has been successfully requested!",
                            parse_mode="Markdown",
                        )
                    else:
                        await query.edit_message_text(
                            text=f"❌ Failed to request *{selected_result['title']}*. Please try again later.",
                            parse_mode="Markdown",
                        )
        else:
            await query.edit_message_text(
                text="Selected media not found. Please try again.", parse_mode="Markdown"
            )
    elif data == "back_to_results":
        await query.message.delete()
        sent_message = await display_results_with_buttons(
            query, context, results, offset=0, new_message=True
        )
        context.user_data["results_message_id"] = sent_message.message_id
    elif data == "cancel_search":
        await cancel_search(query, context)
    elif data.startswith("report_"):
        overseerr_media_id = int(data.split("_")[1])
        selected_result = next((r for r in results if r.get("overseerr_id") == overseerr_media_id), None)
        if selected_result:
            context.user_data['selected_result'] = selected_result
            issue_type_buttons = [
                [InlineKeyboardButton(text=ISSUE_TYPES[1], callback_data=f"issue_type_1")],
                [InlineKeyboardButton(text=ISSUE_TYPES[2], callback_data=f"issue_type_2")],
                [InlineKeyboardButton(text=ISSUE_TYPES[3], callback_data=f"issue_type_3")],
                [InlineKeyboardButton(text=ISSUE_TYPES[4], callback_data=f"issue_type_4")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_issue")]
            ]
            reply_markup = InlineKeyboardMarkup(issue_type_buttons)

            prompt_message = (
                f"🛠 *Report an Issue*\n\n"
                f"Please select the issue type for *{selected_result['title']}*:"
            )

            if query.message.photo:
                await query.edit_message_caption(
                    caption=prompt_message,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
            else:
                await query.edit_message_text(
                    text=prompt_message,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
        else:
            await query.message.reply_text(
                "Selected media not found. Please try again.",
                parse_mode="Markdown",
            )
    elif data.startswith("issue_type_"):
        issue_type_id = int(data.split("_")[2])
        issue_type_name = ISSUE_TYPES.get(issue_type_id, "Other")
        context.user_data['reporting_issue'] = {
            'issue_type': issue_type_id,
            'issue_type_name': issue_type_name,
        }

        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_issue")
        reply_markup = InlineKeyboardMarkup([[cancel_button]])

        prompt_message = (
            f"🛠 *Report an Issue*\n\n"
            f"You selected: *{issue_type_name}*\n\n"
            f"📋 *Please describe the issue with {context.user_data['selected_result']['title']}.*\n"
            "Type your message below. Provide as much detail as possible:"
        )

        if query.message.photo:
            await query.edit_message_caption(
                caption=prompt_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(
                text=prompt_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
    elif data == "cancel_issue":
        context.user_data.pop('reporting_issue', None)
        selected_result = context.user_data.get('selected_result')
        if selected_result:
            await process_user_selection(query, context, selected_result, edit_message=True)
        else:
            await query.message.reply_text(
                "Issue reporting canceled.",
            )
    else:
        await query.edit_message_text(
            text="Invalid action. Please try again.", parse_mode="Markdown"
        )

async def process_user_selection(update_or_query, context, result, edit_message=False):
    if isinstance(update_or_query, Update):
        query = update_or_query.callback_query
    else:
        query = update_or_query

    media_title = result["title"]
    media_year = result["year"]
    media_id = result["id"]
    media_type = result["mediaType"]
    overseerr_media_id = result.get("overseerr_id")
    poster = result["poster"]
    description = result["description"]
    media_status = result.get("status")

    context.user_data['selected_result'] = result

    back_button = InlineKeyboardButton("⬅️ Back", callback_data="back_to_results")

    if media_status in [STATUS_AVAILABLE, STATUS_PROCESSING, STATUS_PARTIALLY_AVAILABLE]:
        if media_status == STATUS_AVAILABLE:
            status_message = "already available ✅"
        elif media_status == STATUS_PROCESSING:
            status_message = "being processed ⏳"
        elif media_status == STATUS_PARTIALLY_AVAILABLE:
            status_message = "partially available ⏳"
        else:
            status_message = "not available"

        if overseerr_media_id:
            report_button = InlineKeyboardButton("🛠 Report Issue", callback_data=f"report_{overseerr_media_id}")
            keyboard = [[back_button, report_button]]
        else:
            keyboard = [[back_button]]
        footer_message = f"ℹ️ *{media_title}* is {status_message}."
    else:
        request_button = InlineKeyboardButton(
            "📥 Request", callback_data=f"confirm_{media_id}"
        )
        keyboard = [[back_button, request_button]]
        footer_message = ""

    reply_markup = InlineKeyboardMarkup(keyboard)

    results_message_id = context.user_data.get("results_message_id")
    if results_message_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, message_id=results_message_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")
        context.user_data.pop("results_message_id", None)

    media_message = f"*{media_title} ({media_year})*\n\n{description}"
    if footer_message:
        media_message += f"\n\n{footer_message}"

    media_preview_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None

    if media_preview_url:
        if edit_message:
            await query.edit_message_caption(
                caption=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            context.user_data['media_message_id'] = query.message.message_id
        else:
            sent_message = await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=media_preview_url,
                caption=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            context.user_data['media_message_id'] = sent_message.message_id
    else:
        if edit_message:
            await query.edit_message_text(
                text=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            context.user_data['media_message_id'] = query.message.message_id
        else:
            sent_message = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            context.user_data['media_message_id'] = sent_message.message_id

async def cancel_search(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    await query.message.delete()
    results_message_id = context.user_data.get("results_message_id")
    if results_message_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, message_id=results_message_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")
        context.user_data.pop("results_message_id", None)
    context.user_data.pop("search_results", None)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔴 Search cancelled.",
    )

def request_media(media_id: int, media_type: str, is_tv: bool):
    payload = {"mediaId": media_id, "mediaType": media_type}
    if is_tv:
        payload["seasons"] = "all"

    try:
        response = requests.post(
            f"{OVERSEERR_API_URL}/request",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": OVERSEERR_API_KEY,
            },
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error(f"Error during media request: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return False

def create_issue(media_id: int, media_type: str, issue_description: str, issue_type: int):
    payload = {
        "mediaId": media_id,
        "mediaType": media_type,
        "issueType": issue_type,
        "message": issue_description,
    }

    try:
        response = requests.post(
            f"{OVERSEERR_API_URL}/issue",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": OVERSEERR_API_KEY,
            },
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error(f"Error during issue creation: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return False

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if 'awaiting_password' in context.user_data and context.user_data['awaiting_password']:
        user_input = update.message.text
        if check_password(user_input):
            in_memory_whitelist.add(user_id)
            context.user_data['awaiting_password'] = False
            await update.message.reply_text("✅ Password correct! You are now authorized to use the bot.")            
            # Now call the start_command function to display the start_message
            await start_command(update, context)            
            # Update the config.py whitelist
            update_whitelist_in_config(user_id)
        else:
            await update.message.reply_text(
                "❌ Wrong password. Please try again."
            )
        return

    if 'reporting_issue' in context.user_data:
        issue_description = update.message.text
        reporting_issue = context.user_data['reporting_issue']
        issue_type = reporting_issue['issue_type']
        issue_type_name = reporting_issue['issue_type_name']

        selected_result = context.user_data.get('selected_result')
        if not selected_result:
            await update.message.reply_text(
                "An error occurred. Please try reporting the issue again.",
                parse_mode="Markdown",
            )
            return

        media_id = selected_result.get('overseerr_id')
        media_title = selected_result['title']
        media_type = selected_result['mediaType']

        success = create_issue(media_id, media_type, issue_description, issue_type)

        if success:
            await update.message.reply_text(
                f"✅ Thank you! Your issue with *{media_title}* has been successfully reported. We will address it as soon as possible.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to report the issue with *{media_title}*. Please try again later.",
                parse_mode="Markdown",
            )

        context.user_data.pop('reporting_issue', None)

        media_message_id = context.user_data.get('media_message_id')
        if media_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=media_message_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")
            context.user_data.pop('media_message_id', None)

        context.user_data.pop('selected_result', None)
    else:
        await update.message.reply_text(
            "I didn't understand that. Please use /start to see the available commands."
        )

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("check", check_media))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
