import logging
import requests
from urllib.parse import quote
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Constants for the API
OVERSEERR_API_URL = 'http://YOUR_IP_ADDRESS:5055/api/v1'
OVERSEERR_API_KEY = 'YOUR_OVERSEERR_API_KEY'
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'
VERSION = "1.2"

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

async def check_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide a title to check.")
        return

    media_name = ' '.join(context.args)
    logging.info(f"Checking if media is in library: {media_name}")
    encoded_media_name = quote(media_name)

    # Search for the media in Overseerr
    try:
        search_response = requests.get(
            f"{OVERSEERR_API_URL}/search",
            headers={
                'Content-Type': 'application/json',
                'X-Api-Key': OVERSEERR_API_KEY
            },
            params={'query': encoded_media_name}
        )

        logging.info(f"Search response status code: {search_response.status_code}")

        if search_response.status_code != 200:
            await update.message.reply_text("Error during search. Please try again later.")
            logging.error(f"Error during search: {search_response.status_code} - {search_response.text}")
            return

        search_data = search_response.json()
        results = search_data.get("results", [])

        if not results:
            await update.message.reply_text("No results found. Please try a different title.")
            logging.info(f"No results found for '{media_name}'.")
            return

        # Check if any result is already available
        for result in results:
            # Versuche zuerst `name` und `originalName` zu verwenden
            media_title = result.get('name') or result.get('originalName') or 'Unknown Title'
            media_status = result.get('mediaInfo', {}).get('status', None)

            logging.info(f"Result found: Title='{media_title}', Status={media_status}")

            if media_status == 5:  # Verfügbarkeit in der Bibliothek prüfen
                await update.message.reply_text(f"'{media_title}' is already available in your library!")
                return

        # Wenn keine Ergebnisse verfügbar sind, eine Anfrage zum Hinzufügen senden
        await update.message.reply_text(f"An inquiry has been made to add '{media_name}'.")

        # Request to add the media to Overseerr (fix the endpoint to /request)
        media_id = results[0]['id']
        media_type = results[0]['mediaType']

        request_payload = {
            'mediaId': media_id,
            'mediaType': media_type
        }

        # For series: send seasons
        if media_type == "tv":
            request_payload['seasons'] = "all"  # Request all seasons here

        add_response = requests.post(
            f"{OVERSEERR_API_URL}/request",  # Correct endpoint
            headers={
                'Content-Type': 'application/json',
                'X-Api-Key': OVERSEERR_API_KEY
            },
            json=request_payload
        )

        # Debugging: Log the response for better error diagnosis
        if add_response.status_code != 201:
            logging.error(f"Failed to send request: {add_response.status_code} - {add_response.text}")
            await update.message.reply_text(f"Failed to send the request for '{media_name}'. Response: {add_response.text}")
        else:
            await update.message.reply_text(f"Your request to add '{media_name}' has been sent successfully!")
            logging.info(f"Request to add '{media_name}' sent successfully.")

    except Exception as e:
        logging.error(f"Unexpected error during media check: {e}")
        await update.message.reply_text(f"An unexpected error occurred: {e}. Please try again later.")

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("check", check_media))
    app.run_polling()

if __name__ == '__main__':
    main()
