# Live News Monitor

A standalone, ultra-lightweight daemon script designed to run 24/7 on a 1GB Cloud VM (e.g., Oracle Cloud Always Free). It continuously monitors the NSE API for corporate announcements on a target stock and sends push notifications to a Telegram Bot.

## Setup Instructions

1. **Install minimal dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your Telegram Bot:**
   - Message `@BotFather` on Telegram to create a bot and get the Token.
   - Message your new bot to start a chat.
   - Go to `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` to find your `chat_id`.
   - Add these to your `.env` file:
     ```env
     TELEGRAM_BOT_TOKEN=your_bot_token
     TELEGRAM_CHAT_ID=your_chat_id
     ```

3. **Run the Daemon:**
   ```bash
   python3 live_monitor.py
   ```
   
> Note: The script is automatically time-gated to only poll the NSE API between 09:00 AM and 03:30 PM IST on weekdays to avoid unnecessary requests and IP bans.
