import logging
import requests
import urllib.parse
import json
import os

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

###############################################################################
#                              BOT VERSION & BUILD
###############################################################################
VERSION = "2.5.0"
BUILD = "2025.01.19.110"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.info(f"Bot Version: {VERSION} BUILD: {BUILD}")

###############################################################################
#                    LOAD CONFIG OR ENVIRONMENT VARIABLES
###############################################################################
try:
    logger.info("Importing environment/config variables...")
    OVERSEERR_API_URL = (
        os.environ.get("OVERSEERR_API_URL")
        or getattr(__import__("config"), "OVERSEERR_API_URL", None)
    )
    OVERSEERR_API_KEY = (
        os.environ.get("OVERSEERR_API_KEY")
        or getattr(__import__("config"), "OVERSEERR_API_KEY", None)
    )
    TELEGRAM_TOKEN = (
        os.environ.get("TELEGRAM_TOKEN")
        or getattr(__import__("config"), "TELEGRAM_TOKEN", None)
    )
    PASSWORD = (
        os.environ.get("PASSWORD")
        or getattr(__import__("config"), "PASSWORD", "")
    )
    logger.info("Variables loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load config: {e}")

###############################################################################
#                          OVERSEERR CONSTANTS
###############################################################################
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

os.makedirs("data", exist_ok=True)  # Ensure 'data/' folder exists

###############################################################################
#                              FILE PATHS
###############################################################################
WHITELIST_FILE = "data/whitelist.json"
USER_SELECTION_FILE = "data/user_selection.json"

###############################################################################
#                     WHITELIST (PASSWORD-PROTECTED BOT)
###############################################################################
def load_whitelist():
    """
    Load the whitelist from JSON or migrate from config.py if needed.
    Returns a set of Telegram user IDs that are authorized to use the bot.
    """
    try:
        with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Whitelist file not found or invalid. Attempting config.py migration...")
        try:
            from config import WHITELIST
            if WHITELIST and isinstance(WHITELIST, list):
                whitelist_set = set(WHITELIST)
                save_whitelist(whitelist_set)
                logger.info("Whitelist migrated from config.py.")
                clear_whitelist_in_config()
                return whitelist_set
            else:
                logger.warning("No valid WHITELIST found in config.py. Creating a new file.")
                save_whitelist(set())
                return set()
        except (ImportError, AttributeError):
            logger.warning("config.py or WHITELIST not found. Creating a new whitelist file.")
            save_whitelist(set())
            return set()

def save_whitelist(whitelist):
    """
    Save the whitelist set to the JSON file.
    """
    try:
        with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
            json.dump(list(whitelist), f, indent=4)
        logger.info("Whitelist saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save whitelist: {e}")

def clear_whitelist_in_config():
    """
    Clears the WHITELIST in config.py (if present),
    to ensure no duplication between file-based and config-based whitelists.
    """
    config_file_path = "config.py"
    try:
        with open(config_file_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            f.seek(0)
            f.truncate()
            for line in lines:
                if line.strip().startswith("WHITELIST"):
                    f.write("WHITELIST = []\n")
                else:
                    f.write(line)
        logger.info("WHITELIST in config.py cleared.")
    except FileNotFoundError:
        logger.info("config.py not found. Nothing to clear.")
    except Exception as e:
        logger.error(f"Failed to clear WHITELIST in config.py: {e}")

in_memory_whitelist = load_whitelist()

def user_is_authorized(user_id: int) -> bool:
    """
    Check if the user is in the whitelist.
    If no PASSWORD is set, everyone is authorized.
    """
    if not PASSWORD:
        return True
    return user_id in in_memory_whitelist

def update_whitelist_in_config(new_user_id: int):
    """
    Add the new user to the local in-memory whitelist (and save to file).
    """
    if new_user_id not in in_memory_whitelist:
        in_memory_whitelist.add(new_user_id)
        save_whitelist(in_memory_whitelist)
        logger.info(f"Updated whitelist with user {new_user_id}.")

async def request_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ask the user to enter a password if they're not in the whitelist.
    """
    await update.message.reply_text(
        "🔒 *Access Restricted*\n\n"
        "Please enter the password to use this bot:",
        parse_mode="Markdown"
    )
    context.user_data['awaiting_password'] = True
    logger.info(f"User {update.effective_user.id} is prompted for a password.")

def check_password(user_input: str) -> bool:
    """
    Compare user input with the global PASSWORD.
    """
    return user_input.strip() == PASSWORD.strip()

###############################################################################
#                PERSISTENT USER SELECTION LOGIC (Overseerr user)
###############################################################################
def load_user_selections() -> dict:
    """
    Load a dict from user_selection.json:
    {
      "<telegram_user_id>": {
        "userId": 10,
        "userName": "Some Name"
      },
      ...
    }
    """
    if not os.path.exists(USER_SELECTION_FILE):
        logger.info("No user_selection.json found. Returning empty dictionary.")
        return {}
    try:
        with open(USER_SELECTION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Loaded user selections from {USER_SELECTION_FILE}: {data}")
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("user_selection.json not found or invalid. Returning empty dictionary.")
        return {}

def save_user_selection(telegram_user_id: int, user_id: int, user_name: str):
    """
    Store the user's Overseerr selection in user_selection.json:
    {
      "<telegram_user_id>": {
        "userId": 10,
        "userName": "DisplayName"
      }
    }
    """
    data = load_user_selections()
    data[str(telegram_user_id)] = {
        "userId": user_id,
        "userName": user_name
    }
    try:
        with open(USER_SELECTION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info(f"Saved user selection for Telegram user {telegram_user_id}: (Overseerr user {user_id})")
    except Exception as e:
        logger.error(f"Failed to save user selection: {e}")

def get_saved_user_for_telegram_id(telegram_user_id: int):
    """
    Return (userId, userName) or (None, None) if not found.
    """
    data = load_user_selections()
    entry = data.get(str(telegram_user_id))
    if entry:
        logger.info(f"Found saved user for Telegram user {telegram_user_id}: {entry}")
        return entry["userId"], entry["userName"]
    logger.info(f"No saved user found for Telegram user {telegram_user_id}.")
    return None, None

###############################################################################
#                      OVERSEERR API: FETCH USERS
###############################################################################
def get_overseerr_users():
    """
    Fetch all Overseerr users via /api/v1/user.
    Returns a list of users or an empty list on error.
    """
    try:
        url = f"{OVERSEERR_API_URL}/user"
        logger.info(f"Fetching Overseerr users from: {url}")
        response = requests.get(
            url,
            headers={"X-Api-Key": OVERSEERR_API_KEY},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        logger.info(f"Fetched {len(results)} Overseerr users.")
        return results
    except requests.RequestException as e:
        logger.error(f"Error fetching Overseerr users: {e}")
        return []

###############################################################################
#                     OVERSEERR API: SEARCH
###############################################################################
def search_media(media_name: str):
    """
    Search for media by title in Overseerr.
    Returns the JSON result or None on error.
    """
    try:
        logger.info(f"Searching for media: {media_name}")
        query_params = {'query': media_name}
        encoded_query = urllib.parse.urlencode(query_params, quote_via=urllib.parse.quote)
        url = f"{OVERSEERR_API_URL}/search?{encoded_query}"
        response = requests.get(
            url,
            headers={"X-Api-Key": OVERSEERR_API_KEY},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error during media search: {e}")
        return None

def process_search_results(results: list):
    """
    Process Overseerr search results into a simplified list of dicts:
    [
      {
        "title": "...",
        "year": "...",
        "id": ...,
        "mediaType": "...",
        "status": ...,
        "poster": "...",
        "description": "...",
        "overseerr_id": ...
      },
      ...
    ]
    """
    processed_results = []
    for result in results:
        media_title = (
            result.get("name")
            or result.get("originalName")
            or result.get("title")
            or "Unknown Title"
        )

        date_key = "firstAirDate" if result["mediaType"] == "tv" else "releaseDate"
        media_year = result.get(date_key, "") or "Unknown Year"
        if media_year and "-" in media_year:
            media_year = media_year.split("-")[0]

        media_info = result.get("mediaInfo", {})
        media_status = media_info.get("status")
        overseerr_media_id = media_info.get("id")

        processed_results.append({
            "title": media_title,
            "year": media_year,
            "id": result["id"],  # often the TMDb ID
            "mediaType": result["mediaType"],
            "status": media_status,
            "poster": result.get("posterPath"),
            "description": result.get("overview", "No description available"),
            "overseerr_id": overseerr_media_id
        })

    logger.info(f"Processed {len(results)} search results.")
    return processed_results

###############################################################################
#              OVERSEERR API: REQUEST & ISSUE CREATION
###############################################################################
def request_media(media_id: int, media_type: str, is_tv: bool, requested_by: int = None) -> bool:
    """
    Create a request on Overseerr for the specified media.
    In Overseerr v1, the field is "userId" for the requesting user.
    """
    payload = {
        "mediaId": media_id,
        "mediaType": media_type,
    }
    if is_tv:
        payload["seasons"] = "all"

    if requested_by is not None:
        payload["userId"] = requested_by

    logger.info(f"Sending request payload to Overseerr: {payload}")
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
        logger.info(f"Request successful for mediaId {media_id}.")
        return True
    except requests.RequestException as e:
        logger.error(f"Error during media request: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return False

def create_issue(media_id: int, media_type: str, issue_description: str, issue_type: int, user_id: int = None):
    """
    Create an issue on Overseerr. In Overseerr v1, we can also attach a "userId".
    """
    payload = {
        "mediaId": media_id,
        "mediaType": media_type,
        "issueType": issue_type,
        "message": issue_description,
    }
    if user_id is not None:
        payload["userId"] = user_id

    logger.info(f"Sending issue payload to Overseerr: {payload}")
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
        logger.info(f"Issue creation successful for mediaId {media_id}.")
        return True
    except requests.RequestException as e:
        logger.error(f"Error during issue creation: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return False

###############################################################################
#          get_latest_version_from_github: CHECK FOR UPDATES (OPTIONAL)
###############################################################################
def get_latest_version_from_github():
    """
    Check GitHub releases to find the latest version name (if any).
    Returns a string like 'v2.4.0' or an empty string on error.
    """
    try:
        response = requests.get(
            "https://api.github.com/repos/LetsGoDude/OverseerrRequestViaTelegramBot/releases/latest",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        latest_version = data.get("name", "")
        return latest_version
    except requests.RequestException as e:
        logger.warning(f"Failed to check latest version on GitHub: {e}")
        return ""

###############################################################################
#            user_data_loader: RUNS BEFORE OTHER HANDLERS (group=-999)
###############################################################################
async def user_data_loader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    This handler runs BEFORE any other handlers (group=-999).
    It checks if the user has an Overseerr user in memory; if not,
    it loads from user_selection.json (persistent storage).
    Ensures user data is available even if they haven't run /start yet.
    """
    if not update.effective_user:
        # In rare cases, no user data is available (e.g. channel posts).
        return

    telegram_user_id = update.effective_user.id
    if "overseerr_user_id" not in context.user_data:
        saved_user_id, saved_user_name = get_saved_user_for_telegram_id(telegram_user_id)
        if saved_user_id is not None:
            context.user_data["overseerr_user_id"] = saved_user_id
            context.user_data["overseerr_user_name"] = saved_user_name
            logger.info(
                f"[user_data_loader] Restored user {saved_user_name} (ID {saved_user_id}) "
                f"for Telegram user {telegram_user_id}."
            )
        else:
            logger.info(
                f"[user_data_loader] No saved user found for Telegram user {telegram_user_id}. "
                "Nothing to load."
            )

###############################################################################
#                           BOT COMMAND HANDLERS
###############################################################################
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start command. Shows a welcome message.
    Previously, we restored user data here, but now it's done in user_data_loader.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} executed /start.")

    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} is not authorized. Requesting password.")
        await request_password(update, context)
        return

    latest_version = get_latest_version_from_github()
    newer_version_text = ""
    if latest_version:
        latest_stripped = latest_version.strip().lstrip("v")
        if latest_stripped > VERSION:
            newer_version_text = f"\n🔔 A new version (v{latest_stripped}) is available!"

    start_message = (
        f"👋 Welcome to the Overseerr Telegram Bot! v{VERSION}"
        f"{newer_version_text}"
        "\n\n🎬 *What I can do:*\n"
        "- Search movies & TV shows\n"
        "- Check availability\n"
        "- Request new titles\n"
        "- Report issues\n\n"
        "💡 *How to start:* Type `/check <title>`\n"
        "_Example: `/check Venom`_\n\n"
        "You can also select your user with [/settings]."
    )

    await update.message.reply_text(start_message, parse_mode="Markdown")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /settings command. Lists all Overseerr users so the user can pick one.
    Saves that choice to user_selection.json.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} executed /settings.")

    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} is not authorized for /settings. Requesting password.")
        await request_password(update, context)
        return

    current_uid = context.user_data.get("overseerr_user_id")
    current_name = context.user_data.get("overseerr_user_name")
    if current_uid and current_name:
        heading_text = (
            f"⚙️ *Settings - Current User:* {current_name} (ID: {current_uid})\n\n"
            "Select a user from the list below to change your selection:"
        )
    else:
        heading_text = (
            "⚙️ *Settings - No User Selected*\n\n"
            "Select a user from the list below:"
        )

    user_list = get_overseerr_users()
    if not user_list:
        await update.message.reply_text(
            "Could not fetch user list from Overseerr. Please try again later."
        )
        return

    keyboard = []
    for overseerr_user in user_list:
        uid = overseerr_user["id"]
        display_name = (
            overseerr_user.get("displayName")
            or overseerr_user.get("username")
            or f"User {uid}"
        )
        callback_data = f"select_user_{uid}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])

    create_user_button = [InlineKeyboardButton("➕ Create New User", callback_data="create_user")]
    keyboard.append(create_user_button)

    # Add a separate row with a Cancel button
    cancel_button_row = [InlineKeyboardButton("🔴 Cancel", callback_data="cancel_settings")]
    keyboard.append(cancel_button_row)


    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        heading_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def check_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /check <title> command. Searches for media on Overseerr
    and displays the results with inline buttons.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} executed /check with args: {context.args}.")

    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} is not authorized. Requesting password.")
        await request_password(update, context)
        return

    if "overseerr_user_id" not in context.user_data:
        logger.info(f"User {user_id} has no selected user yet.")
        await update.message.reply_text(
            "You haven't selected a user yet. Please use /settings first."
        )
        return

    if not context.args:
        await update.message.reply_text("Please provide a title. Example: `/check Venom`")
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

    sent_message = await display_results_with_buttons(update, context, processed_results, offset=0)
    context.user_data["results_message_id"] = sent_message.message_id

###############################################################################
#              DISPLAY RESULTS WITH BUTTONS (SEARCH PAGINATION)
###############################################################################
async def display_results_with_buttons(
    update_or_query,
    context: ContextTypes.DEFAULT_TYPE,
    results: list,
    offset: int,
    new_message: bool = False,
):
    """
    Creates inline buttons for up to 5 titles per page. Allows
    navigation with Back/More. Returns the message object (if any).
    """
    keyboard = []
    for idx, result in enumerate(results[offset : offset + 5]):
        year = result.get("year", "Unknown Year")
        button_text = f"{result['title']} ({year})"
        callback_data = f"select_{offset + idx}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    total_results = len(results)
    is_first_page = (offset == 0)
    is_last_page = (offset + 5 >= total_results)

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

    # Decide how to send/edit the message
    if new_message:
        sent_message = await context.bot.send_message(
            chat_id=update_or_query.effective_chat.id,
            text="Please select a result:",
            reply_markup=reply_markup
        )
        return sent_message
    elif isinstance(update_or_query, Update) and update_or_query.message:
        sent_message = await update_or_query.message.reply_text(
            text="Please select a result:",
            reply_markup=reply_markup
        )
        return sent_message
    elif isinstance(update_or_query, CallbackQuery):
        await update_or_query.edit_message_text(
            text="Please select a result:",
            reply_markup=reply_markup
        )
        return
    else:
        sent_message = await context.bot.send_message(
            chat_id=update_or_query.effective_chat.id,
            text="Please select a result:",
            reply_markup=reply_markup
        )
        return sent_message

###############################################################################
#        process_user_selection: SHOW MEDIA DETAILS + REQUEST/ISSUE BUTTON
###############################################################################
async def process_user_selection(
    update_or_query,
    context: ContextTypes.DEFAULT_TYPE,
    result: dict,
    edit_message: bool = False
):
    """
    Displays details about the selected media (poster, description, status).
    Offers a request or issue-report button if applicable.
    """
    if isinstance(update_or_query, Update):
        query = update_or_query.callback_query
    else:
        query = update_or_query

    media_title = result["title"]
    media_year = result["year"]
    media_id = result["id"]  # Usually the TMDb ID
    media_type = result["mediaType"]
    poster = result.get("poster")
    description = result.get("description", "No description available")
    media_status = result.get("status")
    overseerr_media_id = result.get("overseerr_id")

    context.user_data['selected_result'] = result

    back_button = InlineKeyboardButton("⬅️ Back", callback_data="back_to_results")

    # Decide how to display request/issue options based on status
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
        # If not available, let them request it
        request_button = InlineKeyboardButton("📥 Request", callback_data=f"confirm_{media_id}")
        keyboard = [[back_button, request_button]]
        footer_message = ""

    reply_markup = InlineKeyboardMarkup(keyboard)

    # If we previously stored a results_message_id, remove it to avoid confusion
    results_message_id = context.user_data.get("results_message_id")
    if results_message_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=results_message_id
            )
            logger.info(f"Deleted previous results message {results_message_id}.")
        except Exception as e:
            logger.warning(f"Failed to delete message {results_message_id}: {e}")
        context.user_data.pop("results_message_id", None)

    media_message = f"*{media_title} ({media_year})*\n\n{description}"
    if footer_message:
        media_message += f"\n\n{footer_message}"

    media_preview_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None

    # Depending on your design, send a new message or edit the existing one
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

###############################################################################
#            cancel_search: CANCEL CURRENT SEARCH & CLEANUP
###############################################################################
async def cancel_search(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels the current search and removes related messages or states.
    """
    logger.info(f"Search canceled by user {query.from_user.id}.")
    # Delete the current message
    await query.message.delete()

    # If we have a results_message_id, delete it as well
    results_message_id = context.user_data.get("results_message_id")
    if results_message_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=results_message_id
            )
            logger.info(f"Deleted search results message {results_message_id}.")
        except Exception as e:
            logger.warning(f"Failed to delete results message {results_message_id}: {e}")
        context.user_data.pop("results_message_id", None)

    # Clear any saved search results from context
    context.user_data.pop("search_results", None)

    # Notify user
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔴 Search cancelled.",
    )

###############################################################################
#   button_handler: PROCESSES ALL INLINE BUTTON CLICKS (search, confirm, etc.)
###############################################################################
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main callback handler for inline button clicks (search selection, pagination,
    confirm request, report issue, etc.)
    """
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    logger.info(f"User {user_id} pressed a button with callback data: {data}")
    await query.answer()

    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} is not authorized. Editing message to show an error.")
        await query.edit_message_text(
            text="You need to be authorized. Please use /start and enter the password first."
        )
        return
    
    if data == "cancel_settings":
        # Simply edit the current message to say "Settings canceled" (or delete it).
        logger.info(f"User {user_id} canceled settings.")
        await query.edit_message_text("🔴 Settings canceled. Use /start or /settings again any time.")
        return
    
    elif data == "cancel_user_creation":
        # If user wants to cancel in mid-conversation
        logger.info(f"User {user_id} canceled user creation.")
        context.user_data.pop("creating_new_user", None)
        context.user_data.pop("new_user_data", None)

        # Edit message or send a new one
        await query.edit_message_text(
            "🔴 User creation canceled. Use /settings again to start over."
        )
        return
    
    if data == "create_user":
        logger.info(f"User {user_id} clicked on 'Create New User' button.")
        context.user_data["creating_new_user"] = True
        context.user_data["new_user_data"] = {}  # store partial info here

        # Keep track of this message ID so we can delete it later
        context.user_data["create_user_message_id"] = query.message.message_id

        # Show a prompt for email with a Cancel Creation button
        keyboard = [[InlineKeyboardButton("🔴 Cancel Creation", callback_data="cancel_user_creation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Ask for the email
        await query.edit_message_text(
            "Please enter the *email* for the new user:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    results = context.user_data.get("search_results", [])

    # Handle user selection from /settings
    if data.startswith("select_user_"):
        selected_user_id_str = data.replace("select_user_", "")
        all_users = get_overseerr_users()
        selected_user = next((u for u in all_users if str(u["id"]) == selected_user_id_str), None)
        if not selected_user:
            logger.info(f"User ID {selected_user_id_str} not found in Overseerr user list.")
            await query.edit_message_text("User not found. Please try again.")
            return

        display_name = (
            selected_user.get("displayName")
            or selected_user.get("username")
            or f"User {selected_user_id_str}"
        )

        context.user_data["overseerr_user_id"] = int(selected_user_id_str)
        context.user_data["overseerr_user_name"] = display_name

        # Persist in JSON so it survives bot restarts
        save_user_selection(user_id, int(selected_user_id_str), display_name)

        await query.edit_message_text(
            f"✅ You have selected: {display_name} (ID: {selected_user_id_str})"
        )
        return

    # User clicked a search result
    if data.startswith("select_"):
        result_index = int(data.split("_")[1])
        if result_index < len(results):
            selected_result = results[result_index]
            logger.info(f"User {user_id} selected result index {result_index}: {selected_result['title']}")
            await process_user_selection(update, context, selected_result)
        else:
            logger.warning(f"Invalid result index {result_index}.")
        return

    # Page navigation
    if data.startswith("page_"):
        offset = int(data.split("_")[1])
        logger.info(f"User {user_id} requested page offset {offset}.")
        await display_results_with_buttons(query, context, results, offset)
        return

    # Confirm a request
    if data.startswith("confirm_"):
        media_id = int(data.split("_")[1])
        selected_result = next((r for r in results if r["id"] == media_id), None)
        if selected_result:
            is_tv = (selected_result["mediaType"] == "tv")
            media_status = selected_result.get("status")
            overseerr_user_id = context.user_data.get("overseerr_user_id")
            logger.info(
                f"User {user_id} confirmed request for mediaId {media_id}, "
                f"Overseerr user {overseerr_user_id}."
            )

            if media_status in [STATUS_AVAILABLE, STATUS_PROCESSING, STATUS_PARTIALLY_AVAILABLE]:
                # Already available or in progress
                if media_status == STATUS_AVAILABLE:
                    message = f"ℹ️ *{selected_result['title']}* is already available."
                elif media_status == STATUS_PROCESSING:
                    message = f"⏳ *{selected_result['title']}* is currently being processed."
                elif media_status == STATUS_PARTIALLY_AVAILABLE:
                    message = f"⏳ *{selected_result['title']}* is partially available."
                else:
                    message = f"ℹ️ *{selected_result['title']}* cannot be requested at this time."

                if query.message.photo:
                    await query.edit_message_caption(caption=message, parse_mode="Markdown")
                else:
                    await query.edit_message_text(text=message, parse_mode="Markdown")

            else:
                # Make a request if we have an Overseerr user
                if overseerr_user_id:
                    success = request_media(
                        media_id,
                        selected_result["mediaType"],
                        is_tv,
                        requested_by=overseerr_user_id
                    )
                    if success:
                        message = f"✅ *{selected_result['title']}* has been successfully requested!"
                    else:
                        message = f"❌ Failed to request *{selected_result['title']}*. Please try again later."
                else:
                    message = "No user selected. Use /settings first."

                if query.message.photo:
                    await query.edit_message_caption(caption=message, parse_mode="Markdown")
                else:
                    await query.edit_message_text(text=message, parse_mode="Markdown")
        else:
            logger.warning(f"Selected mediaId {media_id} not found in search results.")
            await query.edit_message_text(
                text="Selected media not found. Please try again.", parse_mode="Markdown"
            )
        return

    # Back to results listing
    if data == "back_to_results":
        logger.info(f"User {user_id} going back to results.")
        await query.message.delete()
        sent_message = await display_results_with_buttons(query, context, results, offset=0, new_message=True)
        context.user_data["results_message_id"] = sent_message.message_id
        return

    # Cancel the search
    if data == "cancel_search":
        await cancel_search(query, context)
        return

    # Report an issue
    if data.startswith("report_"):
        overseerr_media_id = int(data.split("_")[1])
        selected_result = next((r for r in results if r.get("overseerr_id") == overseerr_media_id), None)
        if selected_result:
            context.user_data['selected_result'] = selected_result
            logger.info(
                f"User {user_id} wants to report an issue for {selected_result['title']}, "
                f"Overseerr ID {overseerr_media_id}."
            )
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
            logger.warning(f"Overseerr media ID {overseerr_media_id} not found in search results.")
            await query.message.reply_text(
                "Selected media not found. Please try again.",
                parse_mode="Markdown",
            )
        return

    # Choosing the issue type
    if data.startswith("issue_type_"):
        issue_type_id = int(data.split("_")[2])
        issue_type_name = ISSUE_TYPES.get(issue_type_id, "Other")
        context.user_data['reporting_issue'] = {
            'issue_type': issue_type_id,
            'issue_type_name': issue_type_name,
        }
        logger.info(f"User {user_id} selected issue type {issue_type_id} ({issue_type_name}).")

        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_issue")
        reply_markup = InlineKeyboardMarkup([[cancel_button]])

        selected_result = context.user_data.get('selected_result')
        prompt_message = (
            f"🛠 *Report an Issue*\n\n"
            f"You selected: *{issue_type_name}*\n\n"
            f"📋 *Please describe the issue with {selected_result['title']}.*\n"
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
        return

    # Cancel the issue report
    if data == "cancel_issue":
        context.user_data.pop('reporting_issue', None)
        selected_result = context.user_data.get('selected_result')
        logger.info(f"User {user_id} canceled issue reporting.")
        if selected_result:
            await process_user_selection(query, context, selected_result, edit_message=True)
        else:
            await query.message.reply_text("Issue reporting canceled.")
        return

    # Fallback for unknown callback data
    logger.warning(f"User {user_id} triggered unknown callback data: {data}")
    await query.edit_message_text(
        text="Invalid action. Please try again.", parse_mode="Markdown"
    )

###############################################################################
#                 MESSAGE HANDLER: PASSWORD, NEW USER & ISSUE DESCRIPTION
###############################################################################
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for normal text messages (without slash commands).
    Used for password input and issue descriptions.
    """
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Message handler triggered by user {user_id}: {text}")

    # 1) Password input
    if 'awaiting_password' in context.user_data and context.user_data['awaiting_password']:
        if check_password(text):
            logger.info(f"User {user_id} provided the correct password. Authorizing...")
            in_memory_whitelist.add(user_id)
            save_whitelist(in_memory_whitelist)
            context.user_data['awaiting_password'] = False

            await update.message.reply_text("✅ Password correct! You are now authorized to use the bot.")
            await start_command(update, context)  # Show the main menu again
            update_whitelist_in_config(user_id)
        else:
            logger.info(f"User {user_id} provided a wrong password.")
            await update.message.reply_text("❌ Wrong password. Please try again.")
        return

    # 2) Check if we are in 'creating_new_user' flow
    if context.user_data.get("creating_new_user"):
        new_user_data = context.user_data.setdefault("new_user_data", {})

        if "email" not in new_user_data:
            # The user just typed the email
            new_user_data["email"] = text.strip()
            logger.info(f"New user email: {new_user_data['email']}")

            # 1) Delete the old message that had the initial prompt/buttons
            old_msg_id = context.user_data.get("create_user_message_id")
            if old_msg_id:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=old_msg_id
                    )
                    logger.info(f"Deleted old create-user message {old_msg_id}.")
                except Exception as e:
                    logger.warning(f"Failed to delete old create-user message {old_msg_id}: {e}")

                # Clear that ID so we don't delete it again
                context.user_data.pop("create_user_message_id", None)

            # 2) Now ask for the username in a brand-new message
            #    (still including a 'Cancel Creation' button if you like)
            keyboard = [[InlineKeyboardButton("🔙 Cancel Creation", callback_data="cancel_user_creation")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Got it! Now please enter a *username* for the new user:",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return

        if "username" not in new_user_data:
            # Now we store the username
            new_user_data["username"] = text.strip()
            logger.info(f"New user username: {new_user_data['username']}")

            # 1) Tell the user "please wait" 
            await update.message.reply_text("Please wait... creating user in Overseerr...")      

            # We have both email & username => create user
            success = create_overseerr_user(
                email=new_user_data["email"],
                username=new_user_data["username"],
                permissions=12650656  # or some default
            )

            if success:
                await update.message.reply_text(
                    f"✅ New Overseerr user *{new_user_data['username']}* created successfully!"
                )
            else:
                await update.message.reply_text(
                    "❌ Failed to create new user. Please check logs."
                )

            # Cleanup: end the conversation
            context.user_data.pop("creating_new_user", None)
            context.user_data.pop("new_user_data", None)
            return

    # 3) Issue reporting input
    if 'reporting_issue' in context.user_data:
        issue_description = text
        reporting_issue = context.user_data['reporting_issue']
        issue_type_id = reporting_issue['issue_type']
        issue_type_name = reporting_issue['issue_type_name']

        selected_result = context.user_data.get('selected_result')
        if not selected_result:
            logger.error("No selected_result found while reporting an issue.")
            await update.message.reply_text(
                "An error occurred. Please try reporting the issue again.",
                parse_mode="Markdown",
            )
            return

        media_id = selected_result.get('overseerr_id')
        media_title = selected_result['title']
        media_type = selected_result['mediaType']

        user_id_for_issue = context.user_data.get("overseerr_user_id")
        user_display_name = context.user_data.get("overseerr_user_name", "Unknown User")
        logger.info(
            f"User {user_id} is reporting an issue on mediaId {media_id} "
            f"as Overseerr user {user_id_for_issue}."
        )

        # Prepend the user's display name to the issue description
        final_issue_description = f"(Reported by {user_display_name})\n\n{issue_description}"

        success = create_issue(
            media_id=media_id,
            media_type=media_type,
            issue_description=final_issue_description,
            issue_type=issue_type_id,
            user_id=user_id_for_issue
        )

        if success:
            await update.message.reply_text(
                f"✅ Thank you! Your issue with *{media_title}* has been successfully reported.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to report the issue with *{media_title}*. Please try again later.",
                parse_mode="Markdown",
            )

        # Cleanup
        context.user_data.pop('reporting_issue', None)
        media_message_id = context.user_data.get('media_message_id')
        if media_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=media_message_id
                )
                logger.info(f"Deleted media message {media_message_id} after issue reporting.")
            except Exception as e:
                logger.warning(f"Failed to delete media message {media_message_id}: {e}")
            context.user_data.pop('media_message_id', None)

        context.user_data.pop('selected_result', None)

    else:
        # Generic fallback if the user types something we don't handle
        logger.info(f"User {user_id} typed something unrecognized: {text}")
        await update.message.reply_text(
            "I didn't understand that. Please use /start to see the available commands."
        )

###############################################################################
#                               CREATE NEW USER
###############################################################################
def create_overseerr_user(email: str, username: str, permissions: int = 12650656) -> bool:
    """
    Create a new Overseerr user via POST /api/v1/user
    using admin or privileged API key. Returns True if successful, else False.
    """
    payload = {
        "email": email,
        "username": username,
        "permissions": permissions
    }
    url = f"{OVERSEERR_API_URL}/user"

    logger.info(f"Attempting to create new Overseerr user: {payload}")
    try:
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": OVERSEERR_API_KEY,
            },
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Successfully created Overseerr user {username} at {url}.")
        return True
    except requests.RequestException as e:
        logger.error(f"Error while creating Overseerr user: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return False


###############################################################################
#                               MAIN ENTRY POINT
###############################################################################
def main():
    """
    Main entry point for the Telegram bot.
    """
    logger.info("Starting the Overseerr Telegram Bot...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # 1) user_data_loader runs FIRST for every incoming update (group=-999).
    #    Ensures the user's Overseerr selection is loaded from JSON if not present.
    app.add_handler(MessageHandler(filters.ALL, user_data_loader), group=-999)
    app.add_handler(CallbackQueryHandler(user_data_loader), group=-999)

    # 2) Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("check", check_media))

    # 3) Register callback query handler (for inline buttons)
    app.add_handler(CallbackQueryHandler(button_handler))

    # 4) Register a message handler for non-command text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot is starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
