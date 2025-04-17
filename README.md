# Overseerr Telegram Bot

The **Overseerr Telegram Bot** enables seamless interaction with your Overseerr instance through Telegram. Search for movies and TV shows, check availability, request new titles, report issues, and manage notifications—all from your Telegram chat. With flexible operation modes, admin controls, and optional password protection, the bot is designed for both individual and group use, making media management effortless.

📚 **Detailed Documentation**: Explore the [Wiki](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki) for comprehensive guides on setup, configuration, and advanced usage.

🐳 **Docker Image**: Pull the latest bot image from [Docker Hub](https://hub.docker.com/r/chimpanzeesweetrolls/overseerrrequestviatelegrambot).

---

## Features

- **Media Search**: Use `/check <title>` to find movies or TV shows (e.g., `/check The Matrix`) and view detailed results, including posters and availability.
- **Availability Check**: Instantly see if a title is available in HD (1080p) or 4K, based on your Overseerr library.
- **Title Requests**: Request missing titles in HD, 4K, or both, respecting Overseerr user permissions for quality settings.
- **Issue Reporting**: Report issues like video glitches, audio sync problems, missing subtitles, or other playback errors for existing titles.
- **Notification Management**: Customize Telegram notifications for Overseerr events (e.g., request approvals, media availability) with options to enable/disable or use silent mode.
- **Admin Controls**: Admins can switch operation modes, toggle Group Mode, create new Overseerr users, and manage bot settings via an intuitive menu.
- **Password Protection**: Secure bot access with an optional password, ensuring only authorized users can interact.
- **Group Mode**: Restrict bot usage to a specific Telegram group or thread, ideal for collaborative media management in shared environments like family or friend groups.

> [!Note]
> The language of media titles and descriptions matches the language setting configured in Overseerr (e.g., German titles and descriptions if Overseerr is set to German), while the bot's interface remains in English.

![1 Start](https://github.com/user-attachments/assets/55cc4796-7a4f-4909-a260-0395e7fb202a)

---

## Installation

For detailed installation instructions, refer to the [Wiki](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki):

- **Ubuntu (Source Installation)**: Follow the guide at [Installation on Ubuntu](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki#4-installation-on-ubuntu).
- **Docker**: Deploy with Docker or Docker Compose using the instructions at [Installation with Docker](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki#5-installation-with-docker).

---

## Operation Modes

The bot supports three operation modes, configurable by the admin via `/settings`, catering to different use cases:

- **Normal Mode**:

  - Users log in with their individual Overseerr credentials (email and password).
  - Requests and issue reports are tied to each user’s Overseerr account, ensuring personalized tracking.
  - Ideal for users with their own Overseerr accounts who want full control over their requests and notifications.

- **API Mode**:

  - Users select an existing Overseerr user from a list without needing credentials, using the Overseerr API key for requests.
  - Simplifies access for users without Overseerr accounts, with requests automatically approved by Overseerr.
  - Issue reports are attributed to the admin’s account due to API key usage.
  - Best for environments where quick access is prioritized over individual account management.

- **Shared Mode**:

  - All users share a single Overseerr account configured by the admin, streamlining group usage.
  - The admin logs in once, and all requests and issue reports use this shared account.
  - Perfect for small groups (e.g., families or friends) sharing a media server, with notifications sent to a common Telegram chat.

Learn more about configuring modes in the [Wiki](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki).

---

## Commands and Usage

### User Commands

- `/start`: Initializes the bot, displaying a welcome message with the bot’s version and prompting for a password (if enabled). Guides users to log in or select a user, depending on the mode.
- `/check <title>`: Searches Overseerr for movies or TV shows (e.g., `/check Breaking Bad`). Returns a paginated list with details, availability, and options to request or report issues.
- `/settings`: Opens a menu to manage Overseerr account settings or notifications:
  - In Normal Mode: Log in with credentials.
  - In API Mode: Select an Overseerr user.
  - In Shared Mode: Only admins can access; regular users rely on the shared account.

![2 settings](https://github.com/user-attachments/assets/1ab4f5a4-04af-4947-82c0-847988b9fc57)

### Admin Controls

Admins access additional options via `/settings`:

- **Toggle Group Mode**: Restrict bot interactions to a specific Telegram group or thread for centralized communication.
- **Change Operation Mode**: Switch between Normal, API, and Shared Mode to suit your setup.
- **Create New User**: Add new Overseerr users by providing an email and username, streamlining user management.
- **Login/Logout**: Manage sessions (admin-only in Shared Mode).

For detailed command usage, see the [Wiki](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki).

---

## Managing Notifications

Users can configure Overseerr Telegram notifications via `/settings`:

- **Enable/Disable Notifications**: Turn on/off notifications for events like request approvals, media availability, or errors.
- **Silent Mode**: Opt for silent notifications without sound, ideal for minimizing disruptions during quiet hours.
- In Shared Mode, only admins configure notifications for the shared account, applying to all users.

Example: Enable notifications to receive a Telegram message when "The Witcher" becomes available, or set silent mode for nighttime updates.

---

## Reporting Issues

From media details returned by `/check`, users can report issues for pending or available titles, such as:

- Video issues (e.g., pixelation, buffering)
- Audio issues (e.g., out-of-sync, missing tracks)
- Subtitle issues (e.g., incorrect timing, missing files)
- Other playback problems

Reports are submitted to Overseerr, with attribution based on the operation mode (individual user in Normal Mode, admin in API Mode, shared account in Shared Mode).

---

## Group Mode

Group Mode enhances collaborative usage by restricting bot interactions to a designated Telegram group or thread:

- **Enable Group Mode**: Only the admin can activate this via `/settings`, storing the setting in `data/bot_config.json`.
- **Set Primary Chat**: Running `/start` in a group or thread sets it as the primary chat, identified by `primary_chat_id`.
- **Usage**: When active, all commands (`/start`, `/check`) and notifications are confined to the primary chat/thread, ignoring other chats. This ensures a unified experience for group members.
- **Example**: In a family Telegram group, users request "Toy Story" via `/check`, and the bot responds only in that group, with notifications (e.g., “Toy Story is available”) sent to all members.
- **Use Case**: Ideal for shared media servers (e.g., Plex) where a group collaborates on requests, keeping communication centralized.

For setup details, visit the [Wiki](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki).

---

## FAQ and Troubleshooting

- **How do I set up the bot for the first time?**\
  Follow the installation guides in the [Wiki](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki) for Ubuntu or Docker.

- **What if I forget the bot password?**\
  The password is set via the `PASSWORD` environment variable or `config.py`. Admins can reset it by updating the configuration. See the [Wiki](https://github.com/LetsGoDude/OverseerrRequestViaTelegramBot/wiki) for details.

- **Why can’t I request 4K titles?**\
  4K requests depend on Overseerr permissions:

  - Normal Mode: Tied to the user’s account permissions.
  - API Mode: Tied to the selected Overse
