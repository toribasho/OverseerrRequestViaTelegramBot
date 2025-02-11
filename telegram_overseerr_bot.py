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
VERSION = "2.7.0"
BUILD = "2025.02.11.160"

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

# Contains the authorisation bit for 4K
PERMISSION_4K_MOVIE = 2048
PERMISSION_4K_TV = 4096

DEFAULT_POSTER_URL = "https://raw.githubusercontent.com/sct/overseerr/refs/heads/develop/public/images/overseerr_poster_not_found.png"

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
    Load the whitelist from JSON or create a new empty one if not found.
    """
    try:
        with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Whitelist file not found or invalid. Creating a new empty file.")
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
    Process Overseerr search results into a simplified list of dicts.
    Each dict contains relevant fields (title, year, mediaType, etc.).
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
        full_date_str = result.get(date_key, "")  # e.g. "2024-05-12"

        # Extract just the year from the date (if it exists)
        media_year = full_date_str.split("-")[0] if "-" in full_date_str else "Unknown Year"

        media_info = result.get("mediaInfo", {})
        overseerr_media_id = media_info.get("id")
        hd_status = media_info.get("status", 1)
        uhd_status = media_info.get("status4k", 1)

        processed_results.append({
            "title": media_title,
            "year": media_year,
            "id": result["id"],  # usually the TMDb ID
            "mediaType": result["mediaType"],
            "poster": result.get("posterPath"),
            "description": result.get("overview", "No description available"),
            "overseerr_id": overseerr_media_id,
            "release_date_full": full_date_str,
            "status_hd": hd_status,
            "status_4k": uhd_status
        })

    logger.info(f"Processed {len(results)} search results.")
    return processed_results

###############################################################################
#              OVERSEERR API: REQUEST & ISSUE CREATION
###############################################################################
def request_media(
    media_id: int,
    media_type: str,
    requested_by: int,
    is4k: bool
) -> tuple[bool, str]:
    """
    Sends a request to Overseerr for a media item.
        media_id (int): The media's ID
        media_type (str): "movie" or "tv".
        requested_by (int): Overseerr user ID making the request.
        is4k (bool): True to request the 4K version, False for 1080p.
    Returns:
        tuple[bool, str]: (True, "") if the request succeeded, otherwise (False, error_message).
    """

    payload = {
        "mediaId": media_id,
        "mediaType": media_type,
        "userId": requested_by,
        "is4k": is4k # True => 4K, False => 1080p
    }
    
    if media_type == "tv":
        payload["seasons"] = "all"

    try:
        response = requests.post(
            f"{OVERSEERR_API_URL}/request",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": OVERSEERR_API_KEY,
            },
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return True, ""
    except requests.RequestException as e:
        if e.response is not None:
            try:
                error_data = e.response.json()
                error_message = error_data.get("message", e.response.text)
            except Exception:
                error_message = e.response.text
        else:
            error_message = str(e)
        logger.error(f"Request for media {media_id} (4K={is4k}) failed: {error_message}")
        return False, error_message

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
        "types": 1,  # Disable all notification types (except silent)
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

    # check authorization
    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} not authorized.")
        await request_password(update_or_query, context)
        return

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
    # "Disable notifications" if currently enabled, or "Enable notifications" if it's disabled
    toggle_telegram_label = "Disable notifications" if telegram_is_enabled else "Enable notifications"
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
    Shows buttons for 1080p, 4K, or both—depending on user permissions.
    """
    REQUESTED_STATUSES = [STATUS_PENDING, STATUS_PROCESSING, STATUS_PARTIALLY_AVAILABLE, STATUS_AVAILABLE]
    # Determine whether this was triggered by a CallbackQuery
    if isinstance(update_or_query, Update):
        query = update_or_query.callback_query
    else:
        query = update_or_query

    # Basic media info
    media_title = result.get("title", "Unknown Title")
    media_year = result.get("year", "????")
    poster = result.get("poster")
    description = result.get("description", "No description available")

    status_hd = result.get("status_hd", STATUS_UNKNOWN)
    status_4k = result.get("status_4k", STATUS_UNKNOWN)
    overseerr_media_id = result.get("overseerr_id")

    # Save the result for potential future actions (report issue, etc.)
    context.user_data["selected_result"] = result

    overseerr_user_id = context.user_data.get("overseerr_user_id")

    # Decide if the user can request 4K for this media_type
    user_has_4k_permission = False
    if overseerr_user_id:
        user_has_4k_permission = user_can_request_4k(overseerr_user_id, result.get("mediaType", ""))

    # Inline function to interpret the numeric status codes
    def interpret_status(code: int) -> str:
        if code == STATUS_AVAILABLE:
            return "Available ✅"
        elif code == STATUS_PROCESSING:
            return "Processing ⏳"
        elif code == STATUS_PARTIALLY_AVAILABLE:
            return "Partially available ⏳"
        elif code == STATUS_PENDING:
            return "Pending ⏳"
        else:
            # If not requested (STATUS_UNKNOWN), return an empty string.
            return ""

    # Helper to see if we can request a given resolution
    def can_request_resolution(code: int) -> bool:
        return code not in REQUESTED_STATUSES

    # Build the inline keyboard
    keyboard = []
    back_button = InlineKeyboardButton("⬅️ Back", callback_data="back_to_results")

    # Build request_buttons list
    request_buttons = []
    if can_request_resolution(status_hd):
        btn_1080p = InlineKeyboardButton("📥 1080p", callback_data=f"confirm_1080p_{result['id']}")
        request_buttons.append(btn_1080p)

    if user_has_4k_permission and can_request_resolution(status_4k):
        btn_4k = InlineKeyboardButton("📥 4K", callback_data=f"confirm_4k_{result['id']}")
        request_buttons.append(btn_4k)

    if user_has_4k_permission and can_request_resolution(status_hd) and can_request_resolution(status_4k):
        btn_both = InlineKeyboardButton("📥 Both", callback_data=f"confirm_both_{result['id']}")
        request_buttons.append(btn_both)

    # Adjust labels if exactly two buttons are present
    if len(request_buttons) == 1:
        new_buttons = []
        for btn in request_buttons:
            if "Request" not in btn.text:
                new_text = "📥 Request " + btn.text.lstrip("📥 ").strip()
            else:
                new_text = btn.text
            new_buttons.append(InlineKeyboardButton(new_text, callback_data=btn.callback_data))
        request_buttons = new_buttons

    if request_buttons:
        keyboard.append(request_buttons)


    # Show Report Issue if any resolution is pending/processing/partial/available
    def is_reportable(code: int) -> bool:
        return code in [STATUS_PENDING, STATUS_PROCESSING, STATUS_PARTIALLY_AVAILABLE, STATUS_AVAILABLE]

    if (is_reportable(status_hd) or is_reportable(status_4k)) and overseerr_media_id:
        report_button = InlineKeyboardButton("🛠 Report Issue", callback_data=f"report_{overseerr_media_id}")
        keyboard.append([report_button])

    keyboard.append([back_button])

    # Construct the main message text (with inline status interpretation)
    status_hd_str = interpret_status(status_hd)
    status_4k_str = interpret_status(status_4k)

    status_lines = []
    if status_hd_str:
        status_lines.append(f"• 1080p: {status_hd_str}")
    if status_4k_str:
        status_lines.append(f"• 4K: {status_4k_str}")

    if status_lines:
        status_block = "*Current status*:\n" + "\n".join(status_lines)
    else:
        status_block = ""

    media_heading = f"*{media_title} ({media_year})*"
    message_text = f"{media_heading}\n\n{description}\n\n{status_block}"

    # If we have an old results_message_id, delete it
    results_message_id = context.user_data.get("results_message_id")
    if results_message_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=results_message_id
            )
            logger.info(f"Deleted previous results message {results_message_id}.")
        except Exception as e:
            logger.debug(f"Could not delete previous results message {results_message_id}: {e}")
        context.user_data.pop("results_message_id", None)

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Finally send or edit the message (photo or text)
    # Use provided poster or default poster if none available
    media_preview_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else DEFAULT_POSTER_URL

    if edit_message:
        # If the original message is a photo, edit its caption, otherwise edit the text.
        if query.message.photo:
            await query.edit_message_caption(
                caption=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            context.user_data["media_message_id"] = query.message.message_id
        else:
            await query.edit_message_text(
                text=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            context.user_data["media_message_id"] = query.message.message_id
    else:
        sent_msg = await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=media_preview_url,
            caption=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        context.user_data["media_message_id"] = sent_msg.message_id

def user_can_request_4k(overseerr_user_id: int, media_type: str) -> bool:
    """
    Returns True if this user can request 4K for the specified media_type.
    """
    all_users = get_overseerr_users()
    user_info = next((u for u in all_users if u["id"] == overseerr_user_id), None)
    if not user_info:
        logger.warning(f"No user found with Overseerr ID {overseerr_user_id}")
        return False

    user_permissions = user_info.get("permissions", 0)

    # Grant all 4K permissions to admin users (permission value 2)
    if user_permissions == 2:
        return True

    # PERMISSION_4K_MOVIE: 2048 bit
    # PERMISSION_4K_TV = 4096 bit
    if media_type == "movie":
        return (user_permissions & PERMISSION_4K_MOVIE) == PERMISSION_4K_MOVIE
    elif media_type == "tv":
        return (user_permissions & PERMISSION_4K_TV) == PERMISSION_4K_TV
    else:
        return False

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
            # Not critical - sometimes the message is already deleted.
            logger.debug(f"Could not delete search results message {results_message_id}: {e}")
        context.user_data.pop("results_message_id", None)

    # Clear any saved search results from context
    context.user_data.pop("search_results", None)

    # Notify user
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"🔍 Search canceled. \n"
        f"💡 Type `/check <title>` for a new search\n",
        parse_mode="Markdown"
    )

ISSUE_TYPES = {
    1: "Video",
    2: "Audio",
    3: "Subtitle",
    4: "Other"
}

###############################################################################
#   button_handler: PROCESSES ALL INLINE BUTTON CLICKS (search, confirm, etc.)
###############################################################################
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main callback handler for inline button clicks.
    Handles pagination, selection, confirming requests
    (1080p, 4K, or Both), issue reporting, user management, etc.
    """
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    logger.info(f"User {user_id} pressed a button with callback data: {data}")
    await query.answer()  # Acknowledge the button press immediately

    # 1) Authorization check (if your bot is password-protected)
    if PASSWORD and not user_is_authorized(user_id):
        logger.info(f"User {user_id} is not authorized. Showing an error.")
        await query.edit_message_text(
            text="You need to be authorized. Please use /start and enter the password first."
        )
        return

    # 2) Handle various callback_data cases

    # ---------------------------------------------------------
    # A) Settings / User management / Notifications
    # ---------------------------------------------------------
    if data == "cancel_settings":
        logger.info(f"User {user_id} canceled settings.")
        await query.edit_message_text(
            "⚙️ Settings closed. Use /start or /settings to return."
        )
        return

    elif data == "change_user":
        logger.info(f"User {user_id} wants to change Overseerr user.")
        await handle_change_user(query, context)
        return

    elif data == "manage_notifications":
        logger.info(f"User {user_id} wants to manage notifications.")
        await show_manage_notifications_menu(query, context)
        return

    elif data == "toggle_user_notifications":
        logger.info(f"User {user_id} toggling their Telegram notifications.")
        await toggle_user_notifications(query, context)
        return

    elif data == "toggle_user_silent":
        logger.info(f"User {user_id} toggling silent mode.")
        await toggle_user_silent(query, context)
        return

    elif data == "create_user":
        logger.info(f"User {user_id} clicked 'Create New User'.")
        context.user_data["creating_new_user"] = True
        context.user_data["new_user_data"] = {}
        context.user_data["create_user_message_id"] = query.message.message_id

        keyboard = [[InlineKeyboardButton("🔙 Cancel Creation", callback_data="cancel_user_creation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=(
                "➕ *Create New User*\n\n"
                "Step 1: Please enter the user's email address."
            ),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    elif data == "cancel_user_creation":
        logger.info(f"User {user_id} canceled user creation.")
        context.user_data.pop("creating_new_user", None)
        context.user_data.pop("new_user_data", None)
        # Return to settings
        await show_settings_menu(query, context)
        return

    elif data == "back_to_settings":
        logger.info(f"User {user_id} going back to settings.")
        await show_settings_menu(query, context)
        return

    # ---------------------------------------------------------
    # B) Search pagination / selection
    # ---------------------------------------------------------
    # Assume "search_results" are in context.user_data from /check command
    results = context.user_data.get("search_results", [])

    if data.startswith("page_"):
        offset = int(data.split("_")[1])
        logger.info(f"User {user_id} requested page offset {offset}.")
        await display_results_with_buttons(query, context, results, offset)
        return

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

    if data.startswith("select_"):
        # e.g. "select_3" -> index = 3
        result_index = int(data.split("_")[1])
        if 0 <= result_index < len(results):
            selected_result = results[result_index]
            logger.info(f"User {user_id} selected index {result_index}: {selected_result['title']}")
            await process_user_selection(query, context, selected_result)
        else:
            logger.warning(f"Invalid search result index: {result_index}")
            await query.edit_message_text("Invalid selection. Please try again.")
        return

    if data == "back_to_results":
        logger.info(f"User {user_id} going back to search results.")
        # Delete the current media message
        await query.message.delete()
        sent_message = await display_results_with_buttons(
            query, context, results, offset=0, new_message=True
        )
        context.user_data["results_message_id"] = sent_message.message_id
        return

    if data == "cancel_search":
        logger.info(f"User {user_id} canceled the search.")
        await cancel_search(query, context)
        return

    # ---------------------------------------------------------
    # C) Handling requests for 1080p, 4K, or Both
    # ---------------------------------------------------------
    elif data.startswith("confirm_1080p_"):
        media_id = int(data.split("_")[2])
        selected_result = next((r for r in results if r["id"] == media_id), None)
        if not selected_result:
            logger.warning(f"Media ID {media_id} not found in search results.")
            await query.edit_message_text("Unable to find this media. Please try again.")
            return

        overseerr_user_id = context.user_data.get("overseerr_user_id")
        if not overseerr_user_id:
            await query.edit_message_text("No user selected. Use /settings first.")
            return

        success_1080p, message_1080p = request_media(
            media_id=media_id,
            media_type=selected_result["mediaType"],
            requested_by=overseerr_user_id,
            is4k=False
        )

        await send_request_status(query, selected_result['title'], success_1080p=success_1080p, message_1080p=message_1080p)
        return

    elif data.startswith("confirm_4k_"):
        media_id = int(data.split("_")[2])
        selected_result = next((r for r in results if r["id"] == media_id), None)
        if not selected_result:
            logger.warning(f"Media ID {media_id} not found in search results.")
            await query.edit_message_text("Unable to find this media. Please try again.")
            return

        overseerr_user_id = context.user_data.get("overseerr_user_id")
        if not overseerr_user_id:
            await query.edit_message_text("No user selected. Use /settings first.")
            return

        success_4k, message_4k = request_media(
            media_id=media_id,
            media_type=selected_result["mediaType"],
            requested_by=overseerr_user_id,
            is4k=True
        )

        await send_request_status(query, selected_result['title'], success_4k=success_4k, message_4k=message_4k)
        return

    elif data.startswith("confirm_both_"):
        media_id = int(data.split("_")[2])
        selected_result = next((r for r in results if r["id"] == media_id), None)
        if not selected_result:
            logger.warning(f"Media ID {media_id} not found in search results.")
            await query.edit_message_text("Unable to find this media. Please try again.")
            return

        overseerr_user_id = context.user_data.get("overseerr_user_id")
        if not overseerr_user_id:
            await query.edit_message_text("No user selected. Use /settings first.")
            return

        success_1080p, message_1080p = request_media(
            media_id=media_id,
            media_type=selected_result["mediaType"],
            requested_by=overseerr_user_id,
            is4k=False
        )
        success_4k, message_4k = request_media(
            media_id=media_id,
            media_type=selected_result["mediaType"],
            requested_by=overseerr_user_id,
            is4k=True
        )

        await send_request_status(query, selected_result['title'], success_1080p, message_1080p, success_4k, message_4k)
        return

    # ---------------------------------------------------------
    # D) Report Issue
    # ---------------------------------------------------------
    elif data.startswith("report_"):
        # e.g. "report_12" => Overseerr media id
        overseerr_media_id = int(data.split("_")[1])
        selected_result = next((r for r in results if r.get("overseerr_id") == overseerr_media_id), None)
        if selected_result:
            logger.info(
                f"User {user_id} wants to report an issue for {selected_result['title']} "
                f"(Overseerr ID {overseerr_media_id})."
            )
            context.user_data['selected_result'] = selected_result

            # Prepare the inline buttons for selecting issue type
            issue_buttons = [
                [InlineKeyboardButton(text=ISSUE_TYPES[1], callback_data=f"issue_type_{1}")],
                [InlineKeyboardButton(text=ISSUE_TYPES[2], callback_data=f"issue_type_{2}")],
                [InlineKeyboardButton(text=ISSUE_TYPES[3], callback_data=f"issue_type_{3}")],
                [InlineKeyboardButton(text=ISSUE_TYPES[4], callback_data=f"issue_type_{4}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_issue")]
            ]
            reply_markup = InlineKeyboardMarkup(issue_buttons)

            await query.edit_message_caption(
                caption=f"🛠 *Report an Issue*\n\nSelect the issue type for *{selected_result['title']}*:",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        else:
            logger.warning(f"No matching search result found for Overseerr ID {overseerr_media_id}.")
            await query.edit_message_caption("Selected media not found. Please try again.")
        return

    elif data.startswith("issue_type_"):
        # e.g. "issue_type_2" -> issue type #2
        try:
            issue_type_id = int(data.split("_")[2])
        except (IndexError, ValueError):
            logger.warning(f"Invalid issue_type callback data: {data}")
            await query.edit_message_caption("Invalid issue type. Please start again.")
            return

        issue_type_name = ISSUE_TYPES.get(issue_type_id, "Other")
        context.user_data['reporting_issue'] = {
            'issue_type': issue_type_id,
            'issue_type_name': issue_type_name,
        }
        logger.info(f"User {user_id} selected issue type {issue_type_id} ({issue_type_name}).")

        cancel_button = InlineKeyboardButton("❌ Cancel", callback_data="cancel_issue")
        reply_markup = InlineKeyboardMarkup([[cancel_button]])

        selected_result = context.user_data.get('selected_result')
        if not selected_result:
            logger.warning("No selected_result found in context when choosing issue type.")
            await query.edit_message_caption("No media selected. Please try reporting again.")
            return

        # Define concise example messages based on issue type
        issue_examples = {
            1: "- *The video freezes at 1h 10m, but audio continues.*\n"
            "- *The quality is very bad despite selecting HD/4K.*\n"
            "- *Episode 2, Season 5 is missing entirely.*",
            
            2: "- *Episode 3, Season 2 has no sound from minute 10.*\n"
            "- *The audio is out of sync by 3 seconds.*\n"
            "- *No sound at all in the movie after 45 minutes.*",
            
            3: "- *No English subtitles available for the movie.*\n"
            "- *Subtitles are completely out of sync.*\n"
            "- *Wrong subtitles are shown (Spanish instead of German).*",
            
            4: "- *Playback keeps buffering despite a stable connection.*\n"
            "- *The wrong version of the movie is playing.*\n"
            "- *Plex error when trying to watch.*"
}

        # Get the example text for the selected issue type, default to a generic example
        example_text = issue_examples.get(issue_type_id, "- *Please describe the issue.*")

        # Construct the message
        prompt_message = (
            f"🛠 *Report an Issue*\n\n"
            f"You selected: *{issue_type_name}*\n\n"
            f"📋 *Describe the issue with {selected_result['title']}.*\n"
            "Example:\n"
            f"{example_text}\n\n"
            "Type your issue below:"
        )

        await query.edit_message_caption(
            caption=prompt_message,
            parse_mode="Markdown",
            reply_markup=reply_markup,
            )
        return

    elif data == "cancel_issue":
        logger.info(f"User {user_id} canceled the issue reporting process.")
        context.user_data.pop('reporting_issue', None)
        selected_result = context.user_data.get('selected_result')
        # Return to the media details
        await process_user_selection(query, context, selected_result, edit_message=True)
        return

    # ---------------------------------------------------------
    # E) Fallback
    # ---------------------------------------------------------
    logger.warning(f"User {user_id} triggered unknown callback data: {data}")
    await query.edit_message_text(
        text="Invalid action or unknown callback data. Please try again.",
        parse_mode="Markdown"
    )

async def send_request_status(query, title, success_1080p=None, message_1080p=None, success_4k=None, message_4k=None):
    """
    Sends a formatted status message for a media request.
    Handles 1080p, 4K, or both in a unified way.
    """
    status_1080p = "✅ 1080p requested successfully" if success_1080p else f"❌ 1080p: {message_1080p}" if message_1080p else "❌ 1080p request failed"
    status_4k = "✅ 4K requested successfully" if success_4k else f"❌ 4K: {message_4k}" if message_4k else "❌ 4K request failed"

    msg = f"*Request Status for {title}:*\n"
    if success_1080p is not None:
        msg += f"• {status_1080p}\n"
    if success_4k is not None:
        msg += f"• {status_4k}\n"

    await query.edit_message_caption(msg.strip(), parse_mode="Markdown")

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