import os
import base64
import asyncio
import zipfile
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
STATUS_MESSAGE_ID = os.environ.get("STATUS_MESSAGE_ID", "")
SHOULD_ZIP = os.environ.get("SHOULD_ZIP", "false").lower() == "true"

SESSION_FILE = "rubsession.rp"
ALLOWED_USER = 8172175112

def decode_rubika_session():
    try:
        session_data = base64.b64decode(RUBIKA_SESSION_BASE64)
        with open(SESSION_FILE, "wb") as file:
            file.write(session_data)
        return True
    except Exception as e:
        print(f"Session decoding failed: {e}")
        return False

def zip_target_file(file_path: Path) -> Path:
    """Zips the downloaded file."""
    zip_path = file_path.with_suffix(file_path.suffix + ".zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(file_path, arcname=file_path.name)
    return zip_path

async def update_status(app, text):
    """Edits the existing message if STATUS_MESSAGE_ID exists, otherwise sends a new one."""
    if STATUS_MESSAGE_ID and STATUS_MESSAGE_ID.isdigit():
        try:
            await app.edit_message_text(CHAT_ID, int(STATUS_MESSAGE_ID), text)
        except Exception as e:
            print(f"Failed to edit message: {e}")
    else:
        await app.send_message(CHAT_ID, text)

async def main():
    # Security check
    if CHAT_ID != ALLOWED_USER:
        print("Unauthorized access attempt.")
        return

    if not decode_rubika_session():
        return

    tg_app = Client("telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    rubika_app = RubikaClient(name="rubsession")

    await tg_app.start()
    
    try:
        await update_status(tg_app, "⚙️ سرور گیت‌هاب روشن شد. در حال بررسی درخواست...")
        
        message = await tg_app.get_messages(CHAT_ID, MESSAGE_ID)
        
        if not message or message.empty:
            await update_status(tg_app, "❌ خطا: پیام مورد نظر در تلگرام یافت نشد.")
            return

        await update_status(tg_app, "📥 در حال دانلود فایل از سرورهای تلگرام...\n⏳ (بسته به حجم فایل لطفاً صبور باشید)")
        
        # Download media
        downloaded_path_str = await tg_app.download_media(message)
        
        if not downloaded_path_str or not Path(downloaded_path_str).exists():
            await update_status(tg_app, "❌ خطا: دانلود فایل موفقیت‌آمیز نبود.")
            return
            
        downloaded_path = Path(downloaded_path_str)
        target_path = downloaded_path
        file_name = target_path.name

        # Process Zip if requested
        if SHOULD_ZIP:
            await update_status(tg_app, f"🗜 در حال فشرده‌سازی فایل `{file_name}`...")
            target_path = zip_target_file(downloaded_path)
            file_name = target_path.name

        await update_status(tg_app, f"✅ دانلود کامل شد: `{file_name}`\n📤 در حال آپلود در روبیکا...")

        await rubika_app.start()
        
        # Robust Upload Logic with Retries (Fix for 503 Mimetype Error)
        max_retries = 5
        upload_success = False
        last_error = ""

        for attempt in range(1, max_retries + 1):
            try:
                await rubika_app.send_document("me", str(target_path))
                upload_success = True
                break
            except Exception as e:
                last_error = str(e)
                error_text = last_error.lower()
                transient_errors = ["502", "503", "bad gateway", "timeout", "cannot connect", "unexpected mimetype"]
                
                if any(err in error_text for err in transient_errors) and attempt < max_retries:
                    await update_status(tg_app, f"⚠️ خطای موقت روبیکا. در حال تلاش مجدد ({attempt} از {max_retries})...")
                    await asyncio.sleep(3)
                else:
                    raise e
                    
        if upload_success:
            await update_status(tg_app, f"🎉 عملیات موفق!\nفایل `{file_name}` با موفقیت در فضای ذخیره‌سازی روبیکا آپلود شد.")
        else:
            raise Exception(last_error)

    except Exception as e:
        error_msg = str(e)
        await update_status(tg_app, f"⚠️ خطای غیرمنتظره رخ داد:\n`{error_msg}`")
        print(f"Error: {error_msg}")

    finally:
        # Cleanup securely
        try:
            if 'downloaded_path' in locals() and Path(downloaded_path).exists():
                Path(downloaded_path).unlink()
            if 'target_path' in locals() and Path(target_path).exists() and target_path != downloaded_path:
                Path(target_path).unlink()
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
