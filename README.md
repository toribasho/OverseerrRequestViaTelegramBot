# Overseerr Telegram Bot
A phyton script to request media via a Telegram bot via Overseerr

The **Overseerr Telegram Bot** bridges your Telegram account with Overseerr, enabling you to request movies and TV shows directly within Telegram.

### 🌟 Features

- **🔍 Simple Search** - Quickly search for series and movies
- **📥 Easy Requests** - Submit media requests with just a few taps.
- **🛠 Issue Reporting** - Report any issues or problems
- **📊 Status Tracking** - View the status of requests to see if media has been requested, is available, or is being processed.
- **👌 User-Friendly** - Intuitive and easy to use, ensuring a seamless media management experience.
- **🔒 Access Control** - Optional password protection to restrict access to the bot.


## How to use
1. Open a chat with your Telegram bot
2. /start
3. /check MOVIE / TV-Show

> [!Note]
> The language of the media titles and descriptions will match the language setting configured in Overseerr.


![2 3 - 1](https://github.com/user-attachments/assets/a2191778-0b33-4de7-841d-7f7b4c53bf4d)

![2 1 - 2](https://github.com/user-attachments/assets/edb2c57a-6983-4b9a-8ed5-e9acacf3e143)
![2 1 - 6](https://github.com/user-attachments/assets/26f41f63-0a9d-4845-b0b2-61ffcba799bb)

![2 1 - 3](https://github.com/user-attachments/assets/4059e277-c608-44df-8c79-71df1ccb3b0f)
![2 1 - 4](https://github.com/user-attachments/assets/000d286f-b0ac-4ebe-b6bb-9b66fa619da8)




## How to update
```bash
cd OverseerrRequestViaTelegramBot
git pull
```

## Installation

### Create a Telegram Bot

Follow the instructions at [Telegram Bots: How do I create a bot?](https://core.telegram.org/bots#how-do-i-create-a-bot) to create a new Telegram bot. After creating the bot, you'll receive a bot token. Keep this token secure, as it will be needed later.

![image](https://github.com/user-attachments/assets/1a034159-2ba2-4573-948e-b4c643b87fa7)


### get overseerr API_KEY
Obtain your Overseerr API key from your Overseerr instance settings.

![image](https://github.com/user-attachments/assets/b612cfc3-baa9-49ad-96e2-4de8f9ebecde)



### Linux / Ubuntu:

Install Python 3.12.x or newer & git

```bash
sudo apt update
sudo apt install python3 python3-pip git
```

Install required Python libraries:

```bash
pip install python-telegram-bot requests
```

### Download
```bash
git clone https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot.git
cd OverseerrRequestViaTelegramBot
```

> [!IMPORTANT]
> Rename config file and replace each placeholder with your actual values
```bash
mv config_template.py config.py
nano config.py
```
``` python
# config.py

OVERSEERR_API_URL = 'http://YOUR_IP_ADDRESS:5055/api/v1'
OVERSEERR_API_KEY = 'YOUR_OVERSEERR_API_KEY'
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'

# Access Control Configuration (Optional)
# Set a password to protect access. If empty, no access control is applied.
PASSWORD = "your-secure-password"  # or "" for no access control

WHITELIST = []  # Once a user enters the correct password, they will be added here automatically.
```

## Add script as service
To start the script automatically, we create a service

```
sudo nano /etc/systemd/system/telegram_bot.service
```

```
[Unit]
Description=Overseerr Telegram Bot
After=network.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 /path/to/your/script.py   #e.g. /home/USERNAME/OverseerrRequestViaTelegramBot/telegram_overseerr_bot.py
WorkingDirectory=/path/to/your/script-directory      #e.g. /home/USERNAME/OverseerrRequestViaTelegramBot
Restart=always
User=your-username
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target

```

```
sudo systemctl daemon-reload
sudo systemctl enable telegram_bot.service
sudo systemctl start telegram_bot.service
sudo systemctl status telegram_bot.service
```
