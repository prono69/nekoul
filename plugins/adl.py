import logging
import asyncio
import aiohttp
import os
import re
import time
from mime_ext import get_extension
from plugins.thumbnail import *
from urllib.parse import urlparse, unquote_plus
from plugins.script import Translation

from pyrogram import Client, filters
from pyrogram.types import Message

# Import your custom configuration and progress helpers
from plugins.config import Config
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes, get_readable_time
from plugins.functions.util import metadata, ss_gen
from plugins.functions.aria import aria_dl
from plugins.functions.direct_links import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

DUMP_CHAT_ID = -1001973199110


def sanitize_filename(filename: str) -> str:
    """
    Replace invalid characters in filenames with a space
    and remove any occurrence of substrings that start with 'www' followed by non-whitespace characters.
    """
    # Replace invalid characters with a space
    sanitized = re.sub(r'[<>:"/\\|?*]', " ", filename)
    
    # Remove substrings starting with 'www' followed by non-whitespace characters
    sanitized = re.sub(r'www\S+', '', sanitized)
    
    return sanitized


@Client.on_message(filters.command("la"))
async def udl_handler(client: Client, message: Message):
    start_time = time.time()
    text = message.text
    args = text.split(maxsplit=1)
    headers = {}
    aria2_options = getattr(Config, 'ARIA_OPTIONS', {})
    api_keys = Config.TERA_API
    if not message.reply_to_message and len(args) < 2:
        return await message.reply_text("Usage: .le [URL]")
    url = args[1].strip()
    if not url and message.reply_to_message and message.reply_to_message.text:
        url = message.reply_to_message.text.strip()
    if not url:
        return await message.reply_text("Usage: .le [URL]")

    # Parse domain and determine if URL is supported for bypassing
    original_url = url
    domain = urlparse(url).hostname
    lol = await message.reply("📥 **__Downloading...__**")
    if domain:
        if "yadi.sk" in domain or "disk.yandex." in domain:
            url = yandex_disk(url)
        elif "mediafire.com" in domain:
            url = mediafire(url)
        elif any(x in domain for x in ["pixeldrain.com", "pixeldra.in"]):
            url = pixeldrain(url)
        elif "qiwi.gg" in domain:
            url = qiwi(url)
        elif "gofile.io" in domain:
            try:
                direct_url, headers = gofile(url)
                url = direct_url
            except Exception as e:
                logger.error(f"GoFile Error: {e}")
                return await message.reply_text(f"❌ GoFile Error: {str(e)}")
        elif "streamtape.to" in domain:
            url = streamtape(url)
        elif any(x in domain for x in ["terabox.com", "nephobox.com", "4funbox.com", "mirrobox.com", "momerybox.com", "teraboxapp.com", "1024tera.com", "terabox.app", "gibibox.com", "goaibox.com", "terasharelink.com", "teraboxlink.com", "freeterabox.com", "terafileshare.com", "1024terabox.com", "teraboxshare.com"]):
            url = terabox(url, api_keys)
        elif "send.cm" in domain:
        	  dl_link, headers = send_cm(url)
        	  url = dl_link
        elif any(x in domain for x in ["streamtape.com", "streamtape.co", "streamtape.cc", "streamtape.to", "streamtape.net", "streamta.pe", "streamtape.xyz", "streamtape.site"]):
            url = streamtape(url)
             

    
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(message.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    # Fetch headers asynchronously using aiohttp (HEAD request)
    async with aiohttp.ClientSession() as session:
        try:
            # Set a timeout for the HEAD request
            timeout = aiohttp.ClientTimeout(total=10)  # 10 seconds
            async with session.head(url, headers=headers, timeout=timeout, allow_redirects=True) as response:
                head = response.headers
                logger.info(f"Headers fetched: {headers}")
        except asyncio.TimeoutError:
            logger.error("Timeout while fetching headers")
            return await lol.edit("❌ Timeout while fetching headers.")
        except Exception as e:
            logger.error(f"Error fetching headers: {e}")
            return await lol.edit(f"❌ Error fetching headers: {str(e)}")

    # Determine file name
    file_name = None
    total_length = None
    
    # For streamtape domains, get filename using custom function
    if domain and any(x in domain for x in ["streamtape.com", "streamtape.co", "streamtape.cc", "streamtape.to", "streamtape.net", "streamta.pe", "streamtape.xyz", "streamtape.site"]):
        file_name = streamtape_name(original_url)
        
    else:
        # Original header-based filename logic
        if "Content-Disposition" in head:
            content_disposition = head["Content-Disposition"]
            if "filename=" in content_disposition:
                file_name = content_disposition.split("filename=")[1].strip('"\'')
            elif "filename*=" in content_disposition:
                file_name = content_disposition.split("filename*=")[1].split("'")[-1].strip('"\'')
            logger.info(f"File name from headers: {file_name}")
        
    if "Content-Length" in head:
      total_length = int(head.get("Content-Length", 0))

    # If file name is not found in headers, fallback to URL
    if not file_name:
        file_name = os.path.basename(urlparse(url).path) or "downloaded_file"
        logger.info(f"File name from URL: {file_name}")

    # Determine file extension
    if "Content-Type" in head:
        content_type = head["Content-Type"]
        file_ext = get_extension(content_type)
        if file_ext == ".mpv":
            file_ext = ".mkv"
        logger.info(f"File extension from headers: {file_ext}")
    else:
        file_ext = os.path.splitext(file_name)[1] or ".bin"
        logger.info(f"File extension from file name: {file_ext}")

    # Sanitize file name and add extension if missing
    file_name_ = unquote_plus(file_name)
    file_name = sanitize_filename(file_name_)
    if not file_name.endswith(file_ext):
        file_name += file_ext
    logger.info(f"Final file name: {file_name}")

    download_path = os.path.join(user_dir, file_name)
    cancel_flag = {"cancel": False}

    # Start the download using aiohttp (GET request)
    async with aiohttp.ClientSession() as session:
        try:
            # Set a timeout for the GET request
            timeout = aiohttp.ClientTimeout(total=Config.PROCESS_MAX_TIMEOUT)
            downloaded_file = await aria_dl(url, file_name, download_path, headers, total_length, lol, start_time, cancel_flag, aria2_options)
            logger.info(f"Download completed: {downloaded_file}")
        except asyncio.TimeoutError:
            logger.error("Download timed out")
            return await lol.edit("❌ Download timed out!")
        except Exception as e:
            logger.error(f"Error during download: {e}")
            return await lol.edit(f"❌ Error during download: {str(e)}")

    # Once downloaded, send the file with thumbnail if video
    if os.path.exists(downloaded_file):
        file_ext = os.path.splitext(downloaded_file)[1].lower()
        caption = f"**File Name:** `{os.path.basename(downloaded_file)}`"
        thumb_image_path = None
        sent_message = None  # To store the sent message object

        try:
            if file_ext in [".mp4", ".mkv", ".avi", ".mov"]:
                # Generate thumbnail and metadata
                meta = await metadata(downloaded_file)
                duration = meta.get("duration", 0)
                width = meta.get("width", 1280)
                height = meta.get("height", 720)
                
                thumb_image_path = os.path.splitext(downloaded_file)[0] + ".jpg"
                try:
                    await ss_gen(downloaded_file, thumb_image_path, duration)
                except Exception as e:
                    logger.error(f"Error generating thumbnail: {e}")
                    thumb_image_path = None

                # Send to original chat and store the message object
                sent_message = await message.reply_video(
                    video=downloaded_file,
                    duration=duration,
                    width=width,
                    height=height,
                    supports_streaming=True,
                    thumb=thumb_image_path if os.path.exists(thumb_image_path) else None,
                    caption=caption,
                    progress=progress_for_pyrogram,
                    progress_args=(Translation.UPLOAD_START, lol, time.time())
                )

            else:
                # Send to original chat and store the message object
                sent_message = await message.reply_document(
                    document=downloaded_file,
                    caption=caption,
                    progress=progress_for_pyrogram,
                    progress_args=(Translation.UPLOAD_START, lol, time.time())
                )

            # Prepare the formatted message
            file_size = humanbytes(os.path.getsize(downloaded_file))
            elapsed = get_readable_time((time.time() - start_time))
            formatted_message = (
                f"**__{file_name}__**\n"
                f"┃\n"
                f"┠ **Size:** {file_size}\n"
                f"┠ **Elapsed:** {elapsed}\n"
                f"┠ **Mode:** #leech || #Aria2\n"
                f"┠ **Total Files:** 1\n"
                f"┖ **By:** {message.from_user.mention}\n\n"
                f"➲ **__File(s) have been Sent. Access via Links...__**\n\n"
                f"1. [{file_name}](https://t.me/c/{str(message.chat.id).replace('-100', '')}/{sent_message.id})"
            )

            # Send the formatted message
            await message.reply_text(formatted_message, disable_web_page_preview=True)

            # Copy the message to dump chat if configured
            if DUMP_CHAT_ID and sent_message:
                await client.copy_message(
                    chat_id=DUMP_CHAT_ID,
                    from_chat_id=sent_message.chat.id,
                    message_id=sent_message.id
                )

        finally:
            # Cleanup
            if thumb_image_path and os.path.exists(thumb_image_path):
                os.remove(thumb_image_path)
            if os.path.exists(downloaded_file):
                os.remove(downloaded_file)
            await lol.delete()
    else:
        logger.error("Downloaded file not found")
        await lol.edit("❌ Downloaded file not found.")