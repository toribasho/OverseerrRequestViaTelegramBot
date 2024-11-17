from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import logging
import requests
from urllib.parse import quote
from config import OVERSEERR_API_URL, OVERSEERR_API_KEY, TELEGRAM_TOKEN

VERSION = "2.0"

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def search_media(media_name: str):
    """Search for media in Overseerr."""
    encoded_media_name = quote(media_name)
    response = requests.get(
        f"{OVERSEERR_API_URL}/search",
        headers={'Content-Type': 'application/json', 'X-Api-Key': OVERSEERR_API_KEY},
        params={'query': encoded_media_name}
    )
    return response.json() if response.status_code == 200 else None

def process_search_results(results: list):
    """Process Overseerr search results."""
    processed_results = []
    for result in results:
        media_title = result.get('name') or result.get('originalName') or result.get('title') or 'Unknown Title'
        
        # Use firstAirDate for TV shows and releaseDate for movies
        if result['mediaType'] == 'tv':
            media_year = result.get('firstAirDate', '').split('-')[0]
        else:
            media_year = result.get('releaseDate', '').split('-')[0]
        
        processed_results.append({
            'title': media_title,
            'year': media_year,
            'id': result['id'],
            'mediaType': result['mediaType'],
            'status': result.get('mediaInfo', {}).get('status', None)
        })
    return processed_results

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    start_message = (
        f"Welcome to the Overseerr Telegram Bot! v{VERSION}!\n\n"
        "🔍 *To search and request a movie or TV show:*\n"
        "Type `/check <title>`.\n"
        "_Example: /check Venom_\n\n"
        "🎬 *What I do:*\n"
        "- I’ll search for the title you specify.\n"
        "- If it’s found, I’ll check if a request already exists.\n"
        "- If it hasn’t been requested, I’ll submit a request for you and update you on the status.\n\n"
        "Try it out and let me handle your requests easily! 😊"
    )
    await update.message.reply_text(start_message, parse_mode='Markdown')

async def check_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /check command."""
    if not context.args:
        await update.message.reply_text("Please provide a title to check.")
        return

    media_name = ' '.join(context.args)
    search_data = search_media(media_name)
    if not search_data:
        await update.message.reply_text("Error during search. Please try again later.")
        return

    results = search_data.get("results", [])
    if not results:
        await update.message.reply_text("No results found. Please try a different title.")
        return

    processed_results = process_search_results(results)
    context.user_data['search_results'] = processed_results

    # Display the first 5 results with buttons
    await display_results_with_buttons(update, context, processed_results, offset=0)

async def display_results_with_buttons(update_or_query, context: ContextTypes.DEFAULT_TYPE, results: list, offset: int):
    """Display a paginated list of results using InlineKeyboardButtons."""
    keyboard = []
    has_more = False
    has_previous = offset > 0

    # Log the results to check if the 'year' is missing
    logging.info(f"Results to display (offset {offset}): {results[offset:offset + 5]}")

    # Generate the current results (max. 5 per page)
    for idx, result in enumerate(results[offset:offset + 5]):
        # Check if 'year' exists, otherwise use "Unknown Year" or skip parentheses
        year = result.get('year', None)

        # Log the year and title to check if it's missing
        logging.info(f"Processing result: {result['title']} - Year: {year}")

        if year:
            button_text = f"{result['title']} ({year})"
        else:
            button_text = f"{result['title']}"

        callback_data = f"select_{offset + idx}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Add navigation buttons
    navigation_buttons = []
    if has_previous:
        navigation_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"back_{offset - 5}"))
    if offset + 5 < len(results):
        has_more = True
        navigation_buttons.append(InlineKeyboardButton("➡️ More", callback_data=f"more_{offset + 5}"))

    if navigation_buttons:
        keyboard.append(navigation_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Check whether to send a new message or edit an old one
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text("Please select a result:", reply_markup=reply_markup)
    else:
        await update_or_query.edit_message_reply_markup(reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("select_"):
        result_index = int(data.split("_")[1])
        results = context.user_data.get('search_results', [])
        if result_index < len(results):
            selected_result = results[result_index]
            await process_user_selection(query, selected_result)
    elif data.startswith("more_"):
        offset = int(data.split("_")[1])
        results = context.user_data.get('search_results', [])
        await display_results_with_buttons(query, context, results, offset)
    elif data.startswith("back_"):
        offset = int(data.split("_")[1])
        results = context.user_data.get('search_results', [])
        await display_results_with_buttons(query, context, results, offset)

async def process_user_selection(query, result):
    """Process the user's selected result."""
    media_title = result['title']
    media_year = result['year']
    media_id = result['id']
    media_type = result['mediaType']
    is_tv = media_type == "tv"

    # Request the selected media
    success = request_media(media_id, media_type, is_tv)
    if success:
        await query.edit_message_text(f"Request for '{media_title} ({media_year})' has been sent successfully!")
    else:
        await query.edit_message_text(f"Failed to send request for '{media_title} ({media_year})'. Please try again later.")

def request_media(media_id: int, media_type: str, is_tv: bool):
    """Send a request to add the media to Overseerr."""
    payload = {'mediaId': media_id, 'mediaType': media_type}
    if is_tv:
        payload['seasons'] = "all"

    response = requests.post(
        f"{OVERSEERR_API_URL}/request",
        headers={'Content-Type': 'application/json', 'X-Api-Key': OVERSEERR_API_KEY},
        json=payload
    )
    return response.status_code == 201

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("check", check_media))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == '__main__':
    main()
