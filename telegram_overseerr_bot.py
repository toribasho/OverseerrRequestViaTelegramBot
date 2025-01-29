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
VERSION = "2.6.0"
BUILD = "2025.01.28.131"

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

def get_global_telegram_notifications():
    """
    Retrieves the current global Telegram notification settings from Overseerr.
    Returns a dictionary with the settings or None on error.
    """
    try:
        url = f"{OVERSEERR_API_URL}/settings/notifications/telegram"
        headers = {
            "X-Api-Key": OVERSEERR_API_KEY
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        settings = response.json()
        logger.info(f"Current Global Telegram notification settings: {settings}")
        return settings
    except requests.RequestException as e:
        logger.error(f"Error when retrieving Telegram notification settings: {e}")
        return None

async def set_global_telegram_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Activates the global Telegram notifications in Overseerr.
    Returns True if successful, otherwise False.
    """

    bot_info = await context.bot.get_me()
    chat_id = str(update.effective_chat.id)

    payload = {
        "enabled": True,
        "types": 4063,  # Activate all notification types (except silent)
        "options": {
            "botUsername": bot_info.username,  # Botname
            "botAPI": TELEGRAM_TOKEN,          # Telegram Token
            "chatId": chat_id,                 # Chat-ID - i guess the admin will use the bot first?
            "sendSilently": True
        }
    }
    try:
        url = f"{OVERSEERR_API_URL}/settings/notifications/telegram"
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": OVERSEERR_API_KEY
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Global Telegram notifications have been successfully activated.")
        return True
    except requests.RequestException as e:
        logger.error(f"Error when activating global Telegram notifications: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return False

GLOBAL_TELEGRAM_NOTIFICATION_STATUS = get_global_telegram_notifications()

async def enable_global_telegram_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Activates global Telegram notifications
    """
    if GLOBAL_TELEGRAM_NOTIFICATION_STATUS:
        enabled = GLOBAL_TELEGRAM_NOTIFICATION_STATUS.get("enabled", False)
        if enabled:

            logger.info("Global Telegram notifications are activated.")
        else:
            logger.info("Activate global Telegram notifications...")
            await set_global_telegram_notifications(update, context)
    else:
        logger.error("Could not retrieve Global Telegram notification settings.")


###############################################################################
#                           BOT COMMAND HANDLERS
###############################################################################
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start command. Shows a welcome message.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} executed /start.")

    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} is not authorized. Requesting password.")
        await request_password(update, context)
        return

    await enable_global_telegram_notifications(update, context)

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
        " - 🔍 Search movies & TV shows\n"
        " - 📊 Check availability\n"
        " - 🎫 Request new titles\n"
        " - 🛠 Report issues\n\n"
        "💡 *How to start:* Type `/check <title>`\n"
        "_Example: `/check Venom`_\n\n"
        "You can also select your user with [/settings]."
    )

    await update.message.reply_text(start_message, parse_mode="Markdown")

########################################################################
#                 UNIFIED SETTINGS MENU FUNCTION
########################################################################
async def show_settings_menu(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """
    Displays the settings menu (both for /settings command and 'Back to Settings').
    Checks if it's a callback query or a normal message, then edits or sends a new message.
    """

    user_id = None
    if isinstance(update_or_query, Update) and update_or_query.message:
        # Called via /settings command
        user_id = update_or_query.effective_user.id
        logger.info(f"User {user_id} called /settings.")
        is_callback = False
    elif isinstance(update_or_query, CallbackQuery):
        # Called via inline button
        user_id = update_or_query.from_user.id
        logger.info(f"User {user_id} requested 'Back to Settings'.")
        is_callback = True
    else:
        return  # Should not happen in normal flows

    # OPTIONAL: check authorization
    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} not authorized.")
        await request_password(update_or_query, context)
        return

    # Example: read user_data from context
    current_uid = context.user_data.get("overseerr_user_id")
    current_name = context.user_data.get("overseerr_user_name")

    # Construct your heading text
    if current_uid and current_name:
        heading_text = (
            f"⚙️ *Settings* - Current User:\n"
            f" {current_name} (ID: {current_uid}) ✅\n\n"
            "Select an option below to manage your settings:"
        )
    else:
        heading_text = (
            "⚙️ *Settings* - No User Selected\n\n"
            "❗️ *Please select a user to continue.*\n\n"
            "Tap the *Change User* button below to pick an existing user or create a new one. It's quick and easy!"
        )

    # Define buttons
    keyboard = [
        [
            InlineKeyboardButton("🔄 Change User", callback_data="change_user"),
            InlineKeyboardButton("➕ Create New User", callback_data="create_user")
        ],
        [
            InlineKeyboardButton("🔔 Manage Notifications", callback_data="manage_notifications")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="cancel_settings")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Decide if we edit or send a new message
    if is_callback:
        # We have a CallbackQuery => edit the existing message
        query = update_or_query
        await query.edit_message_text(
            heading_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        # Normal /settings command => send a new message
        update = update_or_query
        await update.message.reply_text(
            heading_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

########################################################################
#                    /settings COMMAND
########################################################################
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /settings command. Calls the unified show_settings_menu function.
    """
    await show_settings_menu(update, context)

async def show_manage_notifications_menu(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """
    Displays a menu letting the user toggle:
      - Telegram notifications on/off (interpreted from notificationTypes.telegram)
      - Silent mode on/off (from telegramSendSilently)
    for their selected Overseerr user, using partial updates.
    """
    # Check if it's a callback or normal command
    if isinstance(update_or_query, Update) and update_or_query.message:
        query = None
        user_id = update_or_query.effective_user.id
        chat_id = update_or_query.effective_chat.id
    elif isinstance(update_or_query, CallbackQuery):
        query = update_or_query
        user_id = query.from_user.id
        chat_id = query.message.chat_id
    else:
        return

    # Which Overseerr user is selected?
    overseerr_user_id = context.user_data.get("overseerr_user_id")
    overseerr_user_name = context.user_data.get("overseerr_user_name", "Unknown User")

    if not overseerr_user_id:
        msg = "No Overseerr user selected. Use /settings to pick a user first."
        if query:
            await query.edit_message_text(msg)
        else:
            await update_or_query.message.reply_text(msg)
        return

    # Fetch from Overseerr to show real-time status
    current_settings = get_user_notification_settings(overseerr_user_id)
    if not current_settings:
        error_text = f"Failed to retrieve notification settings for Overseerr user {overseerr_user_id}."
        if query:
            await query.edit_message_text(error_text)
        else:
            await update_or_query.message.reply_text(error_text)
        return

    # Extract relevant fields
    # If notificationTypes or telegram is missing, default to 0
    notification_types = current_settings.get("notificationTypes", {})
    telegram_bitmask = notification_types.get("telegram", 0)
    telegram_silent = current_settings.get("telegramSendSilently", False)

    # We interpret telegram_bitmask > 0 to mean "enabled"
    telegram_is_enabled = (telegram_bitmask != 0)

    # Build the display text
    heading_text = (
        "🔔 *Notification Settings*\n"
        "Manage how Overseerr sends you updates via Telegram.\n\n"
        f"👤 *User Information:*\n"
        f"   - Name: *{overseerr_user_name}* (ID: `{overseerr_user_id}`)\n\n"
        "⚙️ *Current Telegram Settings:*\n"
        f"   - Notifications: {'*Enabled* ✅' if telegram_is_enabled else '*Disabled* ❌'}\n"
        f"   - Silent Mode: {'*On* 🤫' if telegram_silent else '*Off* 🔊'}\n\n"
        "🔄 *Actions:*\n"
        "Use the buttons below to toggle notifications or silent mode. "
        "Your preferences will be updated immediately."
    )

    # Build inline keyboard
    # "Disable Telegram" if currently enabled, or "Enable Telegram" if it's disabled
    toggle_telegram_label = "Disable Telegram" if telegram_is_enabled else "Enable Telegram"
    toggle_silent_label = "Turn Silent Off" if telegram_silent else "Turn Silent On"

    keyboard = [
        [
            InlineKeyboardButton(toggle_telegram_label, callback_data="toggle_user_notifications")
        ],
        [
            InlineKeyboardButton(toggle_silent_label, callback_data="toggle_user_silent")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Settings", callback_data="back_to_settings")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit or send message
    if query:
        await query.edit_message_text(
            text=heading_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update_or_query.message.reply_text(
            text=heading_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

def get_user_notification_settings(overseerr_user_id: int) -> dict:
    """
    (Optional) Fetch the user's notification settings from Overseerr:
    GET /api/v1/user/<OverseerrUserID>/settings/notifications
    Returns a dict or an empty dict on error.
    """
    try:
        url = f"{OVERSEERR_API_URL}/user/{overseerr_user_id}/settings/notifications"
        headers = {
            "X-Api-Key": OVERSEERR_API_KEY,
            "Content-Type": "application/json"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Fetched notification settings for Overseerr user {overseerr_user_id}: {data}")
        return data
    except requests.RequestException as e:
        logger.error(f"Failed to fetch settings for user {overseerr_user_id}: {e}")
        return {}

def update_telegram_settings_for_user(
    overseerr_user_id: int,
    telegram_bitmask: int,       # either 3657 or 0
    chat_id: str,
    send_silently: bool
) -> bool:
    """
    Sends a partial update to /user/<OverseerrUserID>/settings/notifications.
    - telegram_bitmask=3657: enable all telegram notifications
    - telegram_bitmask=0: disable all telegram notifications
    - We set telegramEnabled=true because Overseerr apparently keeps it that way.
    - telegramChatId is necessary so Overseerr knows which chat to use.
    """
    payload = {
        "notificationTypes": {
            "telegram": telegram_bitmask
        },
        "telegramEnabled": True,         # Always true in Overseerr DB
        "telegramChatId": chat_id,       # Must provide the chat ID
        "telegramSendSilently": send_silently
    }

    url = f"{OVERSEERR_API_URL}/user/{overseerr_user_id}/settings/notifications"
    headers = {
        "X-Api-Key": OVERSEERR_API_KEY,
        "Content-Type": "application/json"
    }
    logger.info(f"Updating user {overseerr_user_id} with payload: {payload}")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Successfully updated telegram bitmask for user {overseerr_user_id}.")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to update telegram bitmask for user {overseerr_user_id}: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return False

async def toggle_user_notifications(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """
    If the user currently has 0 => switch to 3657.
    If the user currently has 3657 => switch to 0.
    """
    overseerr_user_id = context.user_data.get("overseerr_user_id")
    if not overseerr_user_id:
        await query.edit_message_text("No Overseerr user selected.")
        return

    # GET the current settings to see if it's 0 or not
    settings = get_user_notification_settings(overseerr_user_id)
    if not settings:
        await query.edit_message_text(f"Failed to get settings for user {overseerr_user_id}.")
        return
    
    # If "notificationTypes" or "notificationTypes.telegram" is missing, default to 0
    notif_types = settings.get("notificationTypes", {})
    current_value = notif_types.get("telegram", 0)

    # Flip between 0 and 3657
    new_value = 3657 if current_value == 0 else 0

    telegram_silent = settings.get("telegramSendSilently", False)
    chat_id = str(query.message.chat_id)

    success = update_telegram_settings_for_user(
        overseerr_user_id=overseerr_user_id,
        telegram_bitmask=new_value,
        chat_id=chat_id,
        send_silently=telegram_silent
    )

    if not success:
        await query.edit_message_text("❌ Failed to update Telegram bitmask in Overseerr.")
        return

    # Optionally re-fetch or trust your new data
    await show_manage_notifications_menu(query, context)

async def toggle_user_silent(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """
    Toggles the 'telegramSendSilently' flag for the currently selected Overseerr user.
    This only changes whether notifications (if enabled) are sent silently or not.
    If notifications are disabled (bitmask=0), silent mode won't matter in practice,
    but we still update the 'telegramSendSilently' field in Overseerr.
    """
    user_id = query.from_user.id

    overseerr_user_id = context.user_data.get("overseerr_user_id")
    if not overseerr_user_id:
        await query.edit_message_text("No Overseerr user selected.")
        return

    current_settings = get_user_notification_settings(overseerr_user_id)
    if not current_settings:
        await query.edit_message_text(
            f"Failed to fetch notification settings for user {overseerr_user_id}."
        )
        return

    # Instead of relying on telegramEnabled (which Overseerr keeps 'true'),
    # we read the actual bitmask from notificationTypes['telegram'].
    notification_types = current_settings.get("notificationTypes", {})
    current_bitmask = notification_types.get("telegram", 0)

    # Flip the silent mode
    current_silent = current_settings.get("telegramSendSilently", False)
    new_silent = not current_silent

    # If current_bitmask == 0, the user effectively has Telegram disabled.
    # Toggling silent won't enable them, but we can still store the preference.
    chat_id = str(query.message.chat_id)

    success = update_telegram_settings_for_user(
        overseerr_user_id=overseerr_user_id,
        telegram_bitmask=current_bitmask,  # keep the same bitmask (0 = off, 3657 = on, etc.)
        chat_id=chat_id,
        send_silently=new_silent
    )

    if not success:
        await query.edit_message_text("❌ Failed to update silent mode in Overseerr.")
        return

    # Refresh the menu to display the new silent mode
    await show_manage_notifications_menu(query, context)

########################################################################
#                    /check COMMAND
########################################################################
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
        await show_settings_menu(update, context)
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
            chat_id=update_or_query.message.chat_id,
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
            chat_id=update_or_query.message.chat_id,
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
        await query.edit_message_text(
            "⚙️ Use /start or /settings to return anytime 😊",
            parse_mode="Markdown")
        return
    
    elif data == "change_user":
        await handle_change_user(query, context)
        return
    
    elif data == "manage_notifications":
        await show_manage_notifications_menu(query, context)
        return

    elif data == "toggle_user_notifications":
        await toggle_user_notifications(query, context)
        return
    
    elif data == "toggle_user_silent":
        await toggle_user_silent(query, context)
        return

    elif data == "cancel_user_creation":
        logger.info(f"User {user_id} canceled user creation.")
        context.user_data.pop("creating_new_user", None)
        context.user_data.pop("new_user_data", None)

        old_msg_id = context.user_data.pop("create_user_message_id", None)
        if old_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=old_msg_id,
                    text="❌ User creation canceled."
                )
            except Exception as e:
                logger.warning(f"Failed to edit creation message to 'canceled': {e}")

        # Optionally go back to settings
        await show_settings_menu(query, context)
        return

    elif data == "back_to_settings":
        # Handle the 'Back to Settings' button
        await show_settings_menu(query, context)
        return
    
    elif data == "create_user":
        logger.info(f"User {user_id} clicked on 'Create New User' button.")
        context.user_data["creating_new_user"] = True
        context.user_data["new_user_data"] = {}  # store partial info here

        # Keep track of this message ID so we can delete it later
        context.user_data["create_user_message_id"] = query.message.message_id

        # Show a prompt for email with a Cancel Creation button
        keyboard = [[InlineKeyboardButton("🔙 Cancel Creation", callback_data="cancel_user_creation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Ask for the email
        await query.edit_message_text(
            "➕ *Create New User*\n\n"
            "📝 *Step 1:* Please enter the user's email address.\n"
            "_(Make sure it’s valid, as Overseerr might use it for notifications)_",
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

        # Fetch notification settings for the selected user
        current_settings = get_user_notification_settings(int(selected_user_id_str))
        
        # Check if Telegram notifications are enabled
        notification_types = current_settings.get("notificationTypes", {})
        telegram_bitmask = notification_types.get("telegram", 0)
        if telegram_bitmask == 0:  # Notifications are disabled
            chat_id = str(query.message.chat_id)
            success = update_telegram_settings_for_user(
                overseerr_user_id=int(selected_user_id_str),
                chat_id=chat_id,
                send_silently=current_settings.get("telegramSendSilently", False),
                telegram_bitmask=3657  # Enable all notifications
            )

        # Persist in JSON so it survives bot restarts
        save_user_selection(user_id, int(selected_user_id_str), display_name)

        await show_settings_menu(query, context)
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
#                HANDLE CHANGE USER FUNCTION
###############################################################################
async def handle_change_user(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the 'Change User' button click. Presents a list of Overseerr users to select from.
    """
    user_id = query.from_user.id
    logger.info(f"User {user_id} is attempting to change Overseerr user.")

    user_list = get_overseerr_users()
    if not user_list:
        await query.edit_message_text("❌ Could not fetch user list from Overseerr. Please try again later.")
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

    # Add a 'Back to Settings' button
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🔄 *Select an Overseerr User:*\n",
        parse_mode="Markdown",
        reply_markup=reply_markup
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
            await show_settings_menu(update, context)
            update_whitelist_in_config(user_id)
        else:
            logger.info(f"User {user_id} provided a wrong password.")
            await update.message.reply_text("❌ Wrong password. Please try again.")
        return

    # 2) Check if we are in 'creating_new_user' flow
    if context.user_data.get("creating_new_user"):
        new_user_data = context.user_data.setdefault("new_user_data", {})

        # STEP 1: Email
        if "email" not in new_user_data:
            new_user_data["email"] = text.strip()
            logger.info(f"Got new user email: {new_user_data['email']}")

            # Edit the SAME message (Step 1 -> Step 2)
            old_msg_id = context.user_data.get("create_user_message_id")
            if old_msg_id:
                keyboard = [[InlineKeyboardButton("🔙 Cancel Creation", callback_data="cancel_user_creation")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=old_msg_id,
                        text=(
                            "➕ *Create New User*\n\n"
                            "👤 *Step 2:* Great! Now, what should the *username* be?"
                        ),
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit 'Step 1' message -> Step 2: {e}")

            return

        # STEP 2: Username
        if "username" not in new_user_data:
            new_user_data["username"] = text.strip()
            logger.info(f"Got new user username: {new_user_data['username']}")

            # (Optional) change the same message to a "creating user" or "please wait" note
            old_msg_id = context.user_data.get("create_user_message_id")
            if old_msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=old_msg_id,
                        text="⏳ Creating the user in Overseerr..."
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit message to 'please wait': {e}")

            # Now create the user
            success = create_overseerr_user(
                email=new_user_data["email"],
                username=new_user_data["username"],
                permissions=12650656
            )

            if success:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=old_msg_id,
                    text=(
                        f"✅ *Success!* The new user `{new_user_data['username']}` "
                        f"(email `{new_user_data['email']}`) was created."
                    ),
                    parse_mode="Markdown"
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=old_msg_id,
                    text="❌ Failed to create the new user. Check logs."
                )

            # Cleanup
            context.user_data.pop("creating_new_user", None)
            context.user_data.pop("new_user_data", None)
            context.user_data.pop("create_user_message_id", None)

            # Redirect to settings
            await show_settings_menu(update, context)
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
                    chat_id=update.message.chat_id,
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

    # user_data_loader runs FIRST for every incoming update (group=-999).
    # Ensures the user's Overseerr selection is loaded from JSON if not present.
    app.add_handler(MessageHandler(filters.ALL, user_data_loader), group=-999)
    app.add_handler(CallbackQueryHandler(user_data_loader), group=-999)

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("check", check_media))

    # Register callback query handler (for inline buttons)
    app.add_handler(CallbackQueryHandler(button_handler))

    # Register a message handler for non-command text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot is starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()