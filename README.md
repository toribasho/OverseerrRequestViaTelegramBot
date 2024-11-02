# OverseerrRequestViaTelegramBot
A phyton script to request movies and series via a Telegram bot via Overseerr

## Preparation:

### Create a Telegram Bot

https://core.telegram.org/bots#how-do-i-create-a-bot

After you have created the bot, the bot token will be displayed. Write it down, we will need it later.

![image](https://github.com/user-attachments/assets/1a034159-2ba2-4573-948e-b4c643b87fa7)


### connect.sid-Cookie

The Overseerr API requires authentication through the connect.sid cookie.

1. log in to Overseerr on the computer where you run the script
2. open the developer tools (right click -> Explore or F12)
3. go to the tab “Application” or “Storage” and search for cookies
4. copy the value of the connect.sid cookie.

![connect sid cookie](https://github.com/user-attachments/assets/5b2a641a-7b2e-4b60-aa8e-64f36969e7b2)



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

# REPLACE PLACEHOLDER HERE
# Constants for the API
OVERSEERR_API_URL = 'http://your_overseerr_url/api/v1'  # Replace with your Overseerr API URL e.g. 'http://172.1.1.100:5055/api/v1'
CONNECT_SID = 'your_connect_sid_value'  # Replace with your connect.sid value
TELEGRAM_TOKEN = 'your_telegram_bot_token'  # Replace with your Telegram bot token

async def request_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide a title.")
        return

    media_name = ' '.join(context.args)
    logging.info(f"Received title: {media_name}")

    # URL-encode the title
    encoded_media_name = quote(media_name)
    logging.info(f"Searching for title: {media_name}")

    # Search for the media
    search_response = requests.get(
        f'{OVERSEERR_API_URL}/search',
        headers={
            'Content-Type': 'application/json',
            'Cookie': f'connect.sid={CONNECT_SID}'
        },
        params={'query': encoded_media_name}
    )

    logging.info(f"Search response: {search_response.status_code}, {search_response.text}")

    if search_response.status_code != 200:
        await update.message.reply_text("Error during search. Please try again later.")
        return

    search_data = search_response.json()
    if not search_data['results']:
        await update.message.reply_text("No results found. Please try another title.")
        return

    media_id = search_data['results'][0]['id']
    media_type = search_data['results'][0]['mediaType']  # Dynamically determine the type

    # Check for existing requests
    if 'mediaInfo' in search_data['results'][0]:
        media_info = search_data['results'][0]['mediaInfo']
        existing_requests = media_info.get('requests', [])
    else:
        await update.message.reply_text("No media information found. Please try again later.")
        return

    if existing_requests:
        await update.message.reply_text(f"The request for '{media_name}' has already been added.")
        logging.info(f"Existing request for '{media_name}' found, no new request sent.")
        return

    # Send a request to add the media
    request_response = requests.post(
        f'{OVERSEERR_API_URL}/request',
        headers={
            'Content-Type': 'application/json',
            'Cookie': f'connect.sid={CONNECT_SID}'
        },
        json={
            'mediaId': media_id,
            'mediaType': media_type
        }
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
            await update.message.reply_text(f"The '{media_type}' '{media_name}' has already been requested and is still in progress.")
        elif media_status == 2:
            await update.message.reply_text(f"Request for the '{media_type}' '{media_name}' was successfully sent!")
        else:
            await update.message.reply_text(f"The request for '{media_type}' '{media_name}' was successful, but the status is unknown.")
    else:
        error_message = request_response.json().get('message', 'Unknown error')
        await update.message.reply_text(f"Error with the request: {error_message}")

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("request", request_media))
    app.run_polling()

if __name__ == '__main__':
    main()

```

# Know Issues
1.
