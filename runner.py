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

# لیست خطاهای موقت روبیکا
TRANSIENT_ERRORS = [
    "502", "503", "bad gateway", "timeout",
    "cannot connect", "connection reset",
    "temporarily unavailable",
    "error uploading chunk",
    "unexpected mimetype",
]

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
    zip_path = file_path.with_suffix(file_path.suffix + ".zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(file_path, arcname=file_path.name)
    return zip_path

async def update_status(app, text):
    if STATUS_MESSAGE_ID and STATUS_MESSAGE_ID.isdigit():
        try:
            await app.edit_message_text(CHAT_ID, int(STATUS_MESSAGE_ID), text)
        except Exception as e:
            print(f"Failed to edit message: {e}")
    else:
        await app.send_message(CHAT_ID, text)

def get_per_attempt_timeout(file_path: Path) -> int:
    """تعیین زمان مجاز آپلود بر اساس حجم فایل (مشابه سیستم قبلی شما)"""
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb < 100: return 180
    elif size_mb < 500: return 420
    elif size_mb < 1000: return 720
    else: return 1200

async def upload_with_retry(rubika_app, path: Path, tg_app, file_name: str):
    """مدیریت هوشمند آپلود با Retry و صف‌بندی منطقی"""
    max_retries = 5
    last_error = ""

    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                 await update_status(tg_app, f"🔄 تلاش مجدد ({attempt}/{max_retries}) برای فایل:\n`{file_name}`")
            
            # دریافت زمان مجاز برای جلوگیری از گیر کردن
            timeout_seconds = get_per_attempt_timeout(path)
            
            # آپلود با اعمال محدودیت زمانی
            await asyncio.wait_for(
                rubika_app.send_document("me", str(path)),
                timeout=timeout_seconds
            )
            return True

        except asyncio.TimeoutError:
            last_error = "آپلود بیشتر از حد مجاز طول کشید (Timeout)."
            if attempt < max_retries:
                 await update_status(tg_app, f"⚠️ زمان آپلود تمام شد. تلاش مجدد...")
                 await asyncio.sleep(3)
                 continue
                 
        except Exception as e:
            last_error = str(e)
            error_text = last_error.lower()
            
            transient = any(err in error_text for err in TRANSIENT_ERRORS)
            
            if transient and attempt < max_retries:
                await update_status(tg_app, f"⚠️ ارتباط موقتاً ناپایدار شد. در حال استراحت و تلاش مجدد...")
                await asyncio.sleep(3)
                continue
            else:
                raise e
                
    raise Exception(last_error)

async def main():
    if CHAT_ID != ALLOWED_USER:
        return

    if not decode_rubika_session():
        return

    tg_app = Client("telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    rubika_app = RubikaClient(name="rubsession")

    await tg_app.start()
    
    try:
        await update_status(tg_app, "⚙️ سرور گیت‌هاب (پردازش صفی) روشن شد...")
        message = await tg_app.get_messages(CHAT_ID, MESSAGE_ID)
        
        if not message or message.empty:
            await update_status(tg_app, "❌ پیام اصلی در تلگرام یافت نشد.")
            return

        await update_status(tg_app, "📥 در حال دانلود فایل از تلگرام...")
        downloaded_path_str = await tg_app.download_media(message)
        
        if not downloaded_path_str or not Path(downloaded_path_str).exists():
            await update_status(tg_app, "❌ دانلود موفقیت‌آمیز نبود.")
            return
            
        downloaded_path = Path(downloaded_path_str)
        target_path = downloaded_path
        file_name = target_path.name

        if SHOULD_ZIP:
            await update_status(tg_app, f"🗜 در حال فشرده‌سازی...\n`{file_name}`")
            target_path = zip_target_file(downloaded_path)
            file_name = target_path.name

        await update_status(tg_app, f"✅ آماده آپلود:\n`{file_name}`\n📤 در حال ارسال به روبیکا...")

        await rubika_app.start()
        
        try:
            # مرحله اول: آپلود نرمال
            await upload_with_retry(rubika_app, target_path, tg_app, file_name)
            await update_status(tg_app, f"🎉 عملیات موفق!\nفایل `{file_name}` در روبیکا ذخیره شد.")
            
        except Exception as e:
            error_text = str(e).lower()
            is_server_reject = any(err in error_text for err in TRANSIENT_ERRORS)
            
            if not SHOULD_ZIP and is_server_reject:
                await update_status(tg_app, "⚠️ روبیکا به فرمت یا ترافیک این فایل حساس شد.\n🔄 تبدیل به ZIP و تلاش نهایی...")
                
                # فال‌بک نهایی به حالت زیپ
                target_path = zip_target_file(downloaded_path)
                file_name = target_path.name
                
                try:
                    await upload_with_retry(rubika_app, target_path, tg_app, file_name)
                    await update_status(tg_app, f"🎉 موفق!\nنسخه ZIP فایل `{file_name}` در روبیکا ذخیره شد.")
                except Exception as fallback_err:
                    await update_status(tg_app, f"❌ خطای نهایی:\n`{str(fallback_err)}`")
            else:
                await update_status(tg_app, f"❌ آپلود لغو شد:\n`{str(e)}`")

    except Exception as e:
        await update_status(tg_app, f"⚠️ خطای غیرمنتظره:\n`{str(e)}`")

    finally:
        if 'downloaded_path' in locals() and downloaded_path.exists():
            try: downloaded_path.unlink()
            except: pass
        if 'target_path' in locals() and target_path.exists() and target_path != downloaded_path:
            try: target_path.unlink()
            except: pass
        if Path(SESSION_FILE).exists():
            try: Path(SESSION_FILE).unlink()
            except: pass
            
        try: await rubika_app.disconnect()
        except: pass
        await tg_app.stop()

if __name__ == "__main__":
    asyncio.run(main())
