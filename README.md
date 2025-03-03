# Overseerr Telegram Bot ![Logo32](https://github.com/user-attachments/assets/4344ff43-92a4-4834-8485-620756ba8a90)

A phyton script to request media via a Telegram bot via Overseerr 


The **Overseerr Telegram Bot** bridges your Telegram account with Overseerr, enabling you to request movies and TV shows directly within Telegram.

### 🌟 Features

- **🔍 Simple Search** - Quickly search for movies and series
- **📥 Easy Requests** - Submit media requests with just a few taps
- **🛠 Issue Reporting** - Report any issues or problems
- **📊 Check Availability** – See if a movie or show is already in your library, pending approval, or being processed
- **🔔 Get Notified** – Get notification updates for your requests 
- **👥 User Management** - Multi-user support to share the bot with friends
- **👌 User-Friendly** - Intuitive and easy to use, ensuring a seamless media management experience
- **🔒 Access Control** – Set up a password to restrict access


## How to use
1. Open a chat with your Telegram bot
2. /start
3. /check MOVIE / TV-Show

> [!Note]
> The language of the media titles and descriptions will match the language setting configured in Overseerr.

![2 7 - 1](https://github.com/user-attachments/assets/98a53f45-dff1-4d0f-8195-d02f0fe28cd1)

![2 7 - 4](https://github.com/user-attachments/assets/7b66b137-b7e9-4cbc-b6c0-a008e3d35897)
![2 7 - 3](https://github.com/user-attachments/assets/f406b8f8-1f0c-4929-b5fa-32826ecebea0)

![2 7 - 7](https://github.com/user-attachments/assets/554aa8e3-ef51-40d3-9b3f-2f628c44693b)
![2 1 - 4](https://github.com/user-attachments/assets/000d286f-b0ac-4ebe-b6bb-9b66fa619da8)

![2 7 - 8](https://github.com/user-attachments/assets/e5600e44-3766-4df7-a3c1-2330fcb4d6d2)


## Update on Ubuntu / Linux
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



### Installation on Ubuntu / Linux (without Docker)

> [!Note]
> If you prefer to install using Docker, please refer to the section [Installation with Docker](#installation-with-docker).  

---

## 1. Prerequisites

Ensure the following are installed on your system:

- **Python 3.12.x** or newer  
- **pip** (Python's package manager)  
- **git** (for cloning the repository)

Install them using the following commands:

```bash
sudo apt update
sudo apt install python3 python3-pip git
```

---

## 2. Download and Set Up the Bot

1. Clone the repository and navigate to the bot's directory:

    ```bash
    git clone https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot.git
    cd OverseerrRequestViaTelegramBot
    ```

2. Ensure you have all required Python dependencies installed. They are listed in `requirements.txt`. Install them using:

    ```bash
    pip install -r requirements.txt
    ```

---

## 3. Configure the Bot

Rename the configuration template and update it with your actual values:

```bash
mv config_template.py config.py
nano config.py
```


``` python
# config.py

OVERSEERR_API_URL = 'http://YOUR_IP_ADDRESS:5055/api/v1' # Replace with your Overseerr URL
OVERSEERR_API_KEY = 'YOUR_OVERSEERR_API_KEY'             # Replace with your API key
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'                   # Replace with your Telegram bot token

# Access Control Configuration (Optional)
# Set a password to protect access. If empty, no access control is applied.
PASSWORD = "your-secure-password"  # or "" for no access control
```

---

## 4. Run the Bot Manually (Optional)

To verify that everything works correctly, you can run the bot manually:

```bash
python3 telegram_overseerr_bot.py
```

---

## 5. Run the Bot as a Service (Recommended)

To ensure the bot starts automatically at boot, create a **systemd service**:

1. Open a new service file:

	```bash
	sudo nano /etc/systemd/system/telegram_bot.service
	```

2. Add the following configuration (replace paths and username as needed):

	```ini
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

3. Save and exit the file (`Ctrl+O`, `Enter`, `Ctrl+X`).
4. Reload systemd to apply changes, Enable and start the service

	```
	sudo systemctl daemon-reload
	sudo systemctl enable telegram_bot.service
	sudo systemctl start telegram_bot.service
	```

6. Check the service status to ensure it’s running:

	```bash
	sudo systemctl status telegram_bot.service
	```

## Installation with Docker

Our [Docker Hub](https://hub.docker.com/repository/docker/chimpanzeesweetrolls/overseerrrequestviatelegrambot/general)

### docker-compose.yml
```
version: "3.9" # Specifies the version of the Docker Compose file format
services:
  telegram-bot: # The name of the service (container)
	image: chimpanzeesweetrolls/overseerrrequestviatelegrambot:latest
	environment:
	  OVERSEERR_API_URL: "http://your-overseerr-ip:5055/api/v1"
	  OVERSEERR_API_KEY: "your_overseerr_api_key"
	  TELEGRAM_TOKEN: "your_telegram_token"
	  PASSWORD: "your_password"
	volumes:
	  - ./data:/app/data
	restart: unless-stopped
```

### Without compose:
```
docker run -d \
    --name telegram-bot \
    -v $(pwd)/data:/app/data \ 
    -e OVERSEERR_API_URL="http://your-overseerr-ip:5055/api/v1" \ 
    -e OVERSEERR_API_KEY="your_overseerr_api_key" \ 
    -e TELEGRAM_TOKEN="your_telegram_token" \ 
    -e PASSWORD="your_password" \
    chimpanzeesweetrolls/overseerrrequestviatelegrambot:latest
```

### NAS GUI (QNAP as an example, other manufacturers should be similar)

![1](https://github.com/user-attachments/assets/2fa3d40f-5be4-45b7-b61c-b3b8645340a4)
![2](https://github.com/user-attachments/assets/79601018-ed27-41b9-87e1-69a5b9cd0f1b)
![3](https://github.com/user-attachments/assets/9528cec9-a2e8-4e44-a710-39e002fa084b)
![4](https://github.com/user-attachments/assets/88979017-e7a0-4877-b288-6044e52e2352)
![5](https://github.com/user-attachments/assets/612827f4-50c1-4ac8-8819-a083906eaa82)
![6](https://github.com/user-attachments/assets/35330e3d-a9a6-484a-9fda-3edb36aa59d9)
![7](https://github.com/user-attachments/assets/a35b5b52-b1ef-48dd-973d-3292c348a0ca)
![8](https://github.com/user-attachments/assets/b9d5a621-28f4-43d5-b78c-73178fe883fe)
![9](https://github.com/user-attachments/assets/dd2c98bc-7028-49b5-aa19-33e0d8c13939)


