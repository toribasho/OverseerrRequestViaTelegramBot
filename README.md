# OverseerrRequestViaTelegramBot
A phyton script to request movies and series via a Telegram bot via Overseerr

## How to use
1. Open a chat with your Telegram bot
2. /start
3. /check MOVIE / TV-Show

![Screenshot](https://github.com/user-attachments/assets/b41f17b2-c350-41ca-96d7-cfa2f5a81ab1)




## To-Do List
- [x] Request movie / tv-show (v1.0)
- [x] Show instructions for the bot when you start it for the first time or at “/start” (v1.1)
- [x] Selection option if several suitable results exist (v2.0)
- [ ] Notify user when media has been added


## How to update
```bash
cd OverseerrRequestViaTelegramBot
git pull
```

## Installation

### Create a Telegram Bot

https://core.telegram.org/bots#how-do-i-create-a-bot

After you have created the bot, the bot token will be displayed. Write it down, we will need it later.

![image](https://github.com/user-attachments/assets/1a034159-2ba2-4573-948e-b4c643b87fa7)


### get overseerr API_KEY

![image](https://github.com/user-attachments/assets/b612cfc3-baa9-49ad-96e2-4de8f9ebecde)



### Linux / Ubuntu:

Install Python 3.12.x or newer & git

```bash
sudo apt install python3
sudo apt install git
```

Install pip & libraries to interact with the Telegram API and the Overseerr API

```bash
sudo apt install python3-pip
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
# Configuration file
OVERSEERR_API_URL = 'http://YOUR_IP_ADDRESS:5055/api/v1'
OVERSEERR_API_KEY = 'YOUR_OVERSEERR_API_KEY'
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'
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
ExecStart=/usr/bin/python3 /path/to/your/script.py
WorkingDirectory=/path/to/your/script-directory
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
