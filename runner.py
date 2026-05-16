import os
import base64
import asyncio
from pathlib import Path
from pyrogram import Client
from rubpy import Client as RubikaClient

# Load Environment Variables
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
RUBIKA_SESSION_BASE64 = os.environ.get("RUBIKA_SESSION_BASE64", "")
CHAT_ID = int(os.environ.get("CHAT_ID", 0))
MESSAGE_ID = int(os.environ.get("MESSAGE_ID", 0))

SESSION_FILE = "rubsession.rp"

def decode_rubika_session():
    """Converts base64 string back to a valid Rubika session file."""
    try:
        session_data = base64.b64decode(RUBIKA_SESSION_BASE64)
        with open(SESSION_FILE, "wb") as file:
            file.write(session_data)
        return True
    except Exception as e:
        print(f"Session decoding failed: {e}")
        return False

async def main():
    if not decode_rubika_session():
        return

    # Initialize Clients
    tg_app = Client("telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    rubika_app = RubikaClient(name="rubsession")

    await tg_app.start()
    
    try:
        await tg_app.send_message(CHAT_ID, "⚙️ GitHub Action started processing your file...")
        
        # Fetch the target message
        message = await tg_app.get_messages(CHAT_ID, MESSAGE_ID)
        
        if not message or message.empty:
            await tg_app.send_message(CHAT_ID, "❌ Error: Could not find the message in Telegram.")
            return

        await tg_app.send_message(CHAT_ID, "📥 Downloading file from Telegram to GitHub server...")
        
        # Download media
        downloaded_path = await tg_app.download_media(message)
        
        if not downloaded_path or not Path(downloaded_path).exists():
            await tg_app.send_message(CHAT_ID, "❌ Error: Failed to download the file.")
            return
            
        file_name = Path(downloaded_path).name
        await tg_app.send_message(CHAT_ID, f"✅ Download complete: `{file_name}`\n📤 Uploading to Rubika Saved Messages...")

        # Upload to Rubika
        await rubika_app.start()
        await rubika_app.send_document("me", str(downloaded_path))
        
        await tg_app.send_message(CHAT_ID, "🎉 File successfully transferred to Rubika!")

    except Exception as e:
        error_msg = str(e)
        await tg_app.send_message(CHAT_ID, f"⚠️ System Error occurred:\n`{error_msg}`")
        print(f"Error: {error_msg}")

    finally:
        # Cleanup securely
        try:
            if 'downloaded_path' in locals() and Path(downloaded_path).exists():
                Path(downloaded_path).unlink()
            if Path(SESSION_FILE).exists():
                Path(SESSION_FILE).unlink()
        except Exception:
            pass
            
        try:
            await rubika_app.disconnect()
        except Exception:
            pass
        await tg_app.stop()

if __name__ == "__main__":
    asyncio.run(main())
