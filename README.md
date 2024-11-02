# OverseerrRequestViaTelegramBot
A phyton script to request movies and series via a Telegram bot via Overseerr

## Preparation:

### Create a Telegram Bot

https://core.telegram.org/bots#how-do-i-create-a-bot

After you have created the bot, the bot token will be displayed. Write it down, we will need it later.

![image](https://github.com/user-attachments/assets/1a034159-2ba2-4573-948e-b4c643b87fa7)


### get overseerr API_KEY

![image](https://github.com/user-attachments/assets/b612cfc3-baa9-49ad-96e2-4de8f9ebecde)



### Linux / Ubuntu:

Install Python 3.12.x or newer

```bash
sudo apt install python3
```

Install pip

```bash
sudo apt install python3-pip
```

Install the libraries to interact with the Telegram API and the Overseerr API:

```bash
pip install python-telegram-bot requests
```

### Create the script:
Open a text editor of your choice to insert the script

```bash
nano telegram_overseerr_bot.py
```

> [!IMPORTANT]
> Replace each placeholder with your actual values


```python
import logging
import requests
import asyncio
from urllib.parse import quote
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Constants for the API
OVERSEERR_API_URL = 'http://YOUR_IP_ADDRESS:5055/api/v1'
OVERSEERR_API_KEY = 'YOUR_OVERSEERR_API_KEY'
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'

async def request_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide a title.")
        return

    media_name = ' '.join(context.args)
    logging.info(f"Title received: {media_name}")

    # URL-encode the title
    encoded_media_name = quote(media_name)
    logging.info(f"Searching for the title: {media_name}")

    # Search for the media
    search_response = requests.get(
        f'{OVERSEERR_API_URL}/search',
        headers={
            'Content-Type': 'application/json',
            'X-Api-Key': OVERSEERR_API_KEY
        },
        params={'query': encoded_media_name}
    )

    logging.info(f"Search response: {search_response.status_code}, {search_response.text}")

    if search_response.status_code != 200:
        await update.message.reply_text("Error during the search. Please try again later.")
        return

    search_data = search_response.json()
    if not search_data['results']:
        await update.message.reply_text("No results found. Please try a different title.")
        return

    media_id = search_data['results'][0]['id']
    media_type = search_data['results'][0]['mediaType']  # Dynamically determine the type

    # Check for existing requests
    media_info = search_data['results'][0].get('mediaInfo', None)
    if media_info:
        existing_requests = media_info.get('requests', [])
    else:
        existing_requests = []

    # Send request to request the media
    request_payload = {
        'mediaId': media_id,
        'mediaType': media_type
    }

    # For series: send seasons
    if media_type == "tv":
        request_payload['seasons'] = "all"  # Request all seasons here

    request_response = requests.post(
        f'{OVERSEERR_API_URL}/request',
        headers={
            'Content-Type': 'application/json',
            'X-Api-Key': OVERSEERR_API_KEY
        },
        json=request_payload
    )

    logging.info(f"Request response: {request_response.status_code}, {request_response.text}")

    # Wait a few seconds to ensure the request is processed
    await asyncio.sleep(2)

    if request_response.status_code == 201:
        request_data = request_response.json()
        media_status = request_data.get('media', {}).get('status')

        # Check the status of the requested media
        if media_status == 5:
            await update.message.reply_text(f"The '{media_type}' '{media_name}' is already available. No new request needed.")
        elif media_status == 3:
            await update.message.reply_text(f"The '{media_type}' '{media_name}' has already been requested and is still being processed.")
        elif media_status == 2:
            await update.message.reply_text(f"Request for the '{media_type}' '{media_name}' has been successfully sent!")
        else:
            await update.message.reply_text(f"The request for the '{media_type}' '{media_name}' was successful, but the status is unknown.")
    else:
        error_message = request_response.json().get('message', 'Unknown error')
        await update.message.reply_text(f"Error during the request: {error_message}")

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("request", request_media))
    app.run_polling()

if __name__ == '__main__':
    main()
```

# Know Issues
1.
