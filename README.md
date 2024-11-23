# OverseerrRequestViaTelegramBot
A phyton script to request movies and series via a Telegram bot via Overseerr

## How to use
1. Open a chat with your Telegram bot
2. /start
3. /check MOVIE / TV-Show

ℹ️Note: The language of the media titles and descriptions will match the language setting configured in Overseerr.

![2 1 - 1](https://github.com/user-attachments/assets/948de1d0-9fd6-494d-b1c7-44a7a8c10cda)
![2 1 - 2](https://github.com/user-attachments/assets/73c45385-5221-4930-93ce-721e1516768d)
![2 1 - 4](https://github.com/user-attachments/assets/4cae88f0-708f-4149-8ae9-8f67d70a3c02)
![2 1 - 3](https://github.com/user-attachments/assets/e7d1fc30-84a7-448a-a809-b670e053bb4d)
![2 1 - 5](https://github.com/user-attachments/assets/f2c1f4d7-06ae-46bb-82fb-3ad882c34547)



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
