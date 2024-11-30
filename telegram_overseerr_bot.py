import logging
import requests
import urllib.parse
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
from config import OVERSEERR_API_URL, OVERSEERR_API_KEY, TELEGRAM_TOKEN

VERSION = "2.2"
BUILD = "2024.11.30.91"  # Build number increased

# Status codes from the Overseerr API
STATUS_UNKNOWN = 1
STATUS_PENDING = 2
STATUS_PROCESSING = 3
STATUS_PARTIALLY_AVAILABLE = 4
STATUS_AVAILABLE = 5

# Issue types as per Overseerr's specifications
ISSUE_TYPES = {
    1: "Video",
    2: "Audio",
    3: "Subtitle",
    4: "Other"
}

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def search_media(media_name: str):
    """Search for media in Overseerr."""
    try:
        # Build the query parameters
        query_params = {'query': media_name}
        # Properly URL-encode the parameters
        encoded_query = urllib.parse.urlencode(query_params, quote_via=urllib.parse.quote)
        # Construct the full URL with encoded parameters
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
    """Process Overseerr search results."""
    processed_results = []
    for result in results:
        media_title = (
            result.get("name")
            or result.get("originalName")
            or result.get("title")
            or "Unknown Title"
        )

        # Use firstAirDate for TV shows and releaseDate for movies
        date_key = "firstAirDate" if result["mediaType"] == "tv" else "releaseDate"
        media_year = result.get(date_key, "")
        media_year = media_year.split("-")[0] if media_year else "Unknown Year"

        media_info = result.get("mediaInfo")
        if media_info:
            media_status = media_info.get("status")
            overseerr_media_id = media_info.get("id")  # Overseerr internal media ID
        else:
            media_status = None
            overseerr_media_id = None

        processed_results.append(
            {
                "title": media_title,
                "year": media_year,
                "id": result["id"],  # TMDb ID
                "mediaType": result["mediaType"],
                "status": media_status,
                "poster": result.get("posterPath"),
                "description": result.get("overview", "No description available"),
                "overseerr_id": overseerr_media_id,  # Added
            }
        )
    return processed_results


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    start_message = (
        f"Welcome to the Overseerr Telegram Bot! v{VERSION} (Build {BUILD})!\n\n"
        "🔍 *To search for a movie or TV show and make a request:*\n"
        "Type `/check <title>`.\n"
        "_Example: /check Venom_\n\n"
        "🎬 *What I do:*\n"
        "- I search for the title you provide.\n"
        "- If it's found, I check if a request already exists.\n"
        "- If it hasn't been requested yet, I'll send a request for you and inform you about the status.\n\n"
        "Try it out and let me handle your requests easily! 😊"
    )
    await update.message.reply_text(start_message, parse_mode="Markdown")


async def check_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /check command."""
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

    # Display the first 5 results with buttons
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
    """Display a paginated list of results using InlineKeyboardButtons."""
    keyboard = []

    # Generate the current results (max. 5 per page)
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
        # First page: Cancel on the left, More on the right (if more results)
        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")
        if total_results > 5:
            more_button = InlineKeyboardButton("➡️ More", callback_data=f"page_{offset + 5}")
            navigation_buttons = [cancel_button, more_button]
        else:
            navigation_buttons = [cancel_button]
    elif is_last_page:
        # Last page: Back on the left, Cancel on the right
        back_button = InlineKeyboardButton("⬅️ Back", callback_data=f"page_{offset - 5}")
        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")
        navigation_buttons = [back_button, cancel_button]
    else:
        # Middle pages: Back on the left, ❌ in the middle, More on the right
        back_button = InlineKeyboardButton("⬅️ Back", callback_data=f"page_{offset - 5}")
        x_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")
        more_button = InlineKeyboardButton("➡️ More", callback_data=f"page_{offset + 5}")
        navigation_buttons = [back_button, x_button, more_button]

    if navigation_buttons:
        keyboard.append(navigation_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    if new_message:
        # Send a new message
        sent_message = await context.bot.send_message(
            chat_id=update_or_query.message.chat_id,
            text="Please select a result:",
            reply_markup=reply_markup,
        )
        return sent_message  # Return the message object
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
        # Fallback in case message is None
        sent_message = await context.bot.send_message(
            chat_id=update_or_query.effective_chat.id,
            text="Please select a result:",
            reply_markup=reply_markup
        )
        return sent_message


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()

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
            # Check if media is already available
            media_status = selected_result.get("status")
            if media_status in [STATUS_AVAILABLE, STATUS_PROCESSING, STATUS_PARTIALLY_AVAILABLE]:
                # Inform the user that the media is already available or processing
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
                    # Edit the caption of the photo message
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
                    # Edit the text of the message
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
        # Delete the media preview message
        await query.message.delete()
        # Send a new message with the search results
        sent_message = await display_results_with_buttons(
            query, context, results, offset=0, new_message=True
        )
        # Store the new message ID
        context.user_data["results_message_id"] = sent_message.message_id
    elif data == "cancel_search":
        # Cancel the search
        await cancel_search(query, context)
    elif data.startswith("report_"):
        overseerr_media_id = int(data.split("_")[1])
        selected_result = next((r for r in results if r.get("overseerr_id") == overseerr_media_id), None)
        if selected_result:
            # Store the selected result in context.user_data
            context.user_data['selected_result'] = selected_result

            # Show issue type selection buttons
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
        # Store issue type in context.user_data
        context.user_data['reporting_issue'] = {
            'issue_type': issue_type_id,
            'issue_type_name': issue_type_name,
        }

        # Prompt the user for issue description
        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_issue")
        reply_markup = InlineKeyboardMarkup([[cancel_button]])

        prompt_message = (
            f"🛠 *Report an Issue*\n\n"
            f"You selected: *{issue_type_name}*\n\n"
            f"📋 *Please describe the issue with {context.user_data['selected_result']['title']}.*\n"
            "Type your message below. Provide as much detail as possible to help us resolve it:"
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
        # User canceled the issue reporting
        # Clear the reporting_issue state
        context.user_data.pop('reporting_issue', None)

        # Restore the original media message
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
    """Process the user's selected result."""
    # Determine if update_or_query is Update or CallbackQuery
    if isinstance(update_or_query, Update):
        query = update_or_query.callback_query
    else:
        query = update_or_query  # It's already a CallbackQuery

    media_title = result["title"]
    media_year = result["year"]
    media_id = result["id"]  # TMDb ID
    media_type = result["mediaType"]
    overseerr_media_id = result.get("overseerr_id")  # Overseerr ID
    poster = result["poster"]
    description = result["description"]
    media_status = result.get("status")

    # Store the selected result for later use (e.g., when canceling issue reporting)
    context.user_data['selected_result'] = result

    # Build the back and other buttons
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

        # Include the Report Issue button only if Overseerr media ID is available
        if overseerr_media_id:
            report_button = InlineKeyboardButton("🛠 Report Issue", callback_data=f"report_{overseerr_media_id}")
            keyboard = [[back_button, report_button]]
        else:
            keyboard = [[back_button]]
        footer_message = f"ℹ️ *{media_title}* is {status_message}."
    else:
        # Media not available or processing, include request button
        request_button = InlineKeyboardButton(
            "📥 Request", callback_data=f"confirm_{media_id}"
        )
        keyboard = [[back_button, request_button]]
        footer_message = ""

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Delete the previous "Please select a result:" message
    results_message_id = context.user_data.get("results_message_id")
    if results_message_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, message_id=results_message_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")
        # Remove the message ID from user_data
        context.user_data.pop("results_message_id", None)

    # Send or edit media preview
    media_message = f"*{media_title} ({media_year})*\n\n{description}"

    if footer_message:
        media_message += f"\n\n{footer_message}"

    media_preview_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None

    if media_preview_url:
        if edit_message:
            # Edit the existing message
            await query.edit_message_caption(
                caption=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            # Store the message ID
            context.user_data['media_message_id'] = query.message.message_id
        else:
            # Send a new message with the media preview
            sent_message = await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=media_preview_url,
                caption=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            # Store the message ID
            context.user_data['media_message_id'] = sent_message.message_id
    else:
        if edit_message:
            await query.edit_message_text(
                text=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            # Store the message ID
            context.user_data['media_message_id'] = query.message.message_id
        else:
            # Send a new message without an image
            sent_message = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=media_message,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            # Store the message ID
            context.user_data['media_message_id'] = sent_message.message_id


async def cancel_search(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Handle the cancel action to abort the current search."""
    # Delete the current message
    await query.message.delete()
    # Delete any stored message IDs
    results_message_id = context.user_data.get("results_message_id")
    if results_message_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, message_id=results_message_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")
        context.user_data.pop("results_message_id", None)
    # Clear user data related to the search
    context.user_data.pop("search_results", None)
    # Send a confirmation message
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔴 Search cancelled.",
    )


def request_media(media_id: int, media_type: str, is_tv: bool):
    """Send a request to add the media to Overseerr."""
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
    """Send an issue report to Overseerr."""
    payload = {
        "mediaId": media_id,  # Overseerr media ID
        "mediaType": media_type,
        "issueType": issue_type,  # Issue type selected by the user
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
    """Handle text messages from the user."""
    if 'reporting_issue' in context.user_data:
        # User is in the process of reporting an issue
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

        # Send the issue to the Overseerr API
        success = create_issue(media_id, media_type, issue_description, issue_type)

        if success:
            # Updated confirmation message
            await update.message.reply_text(
                f"✅ Thank you! Your issue with *{media_title}* has been successfully reported. We will address it as soon as possible. You will receive a notification once the issue is resolved.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to report the issue with *{media_title}*. Please try again later.",
                parse_mode="Markdown",
            )

        # Clear the reporting_issue state
        context.user_data.pop('reporting_issue', None)

        # Delete the media message
        media_message_id = context.user_data.get('media_message_id')
        if media_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=media_message_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")
            context.user_data.pop('media_message_id', None)

        # Remove selected_result
        context.user_data.pop('selected_result', None)
    else:
        # Handle other messages or ignore
        await update.message.reply_text(
            "I didn't understand that. Please use /start to see the available commands."
        )


def main():
    """Start the Telegram bot."""
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("check", check_media))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
