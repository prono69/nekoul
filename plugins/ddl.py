import mimetypes
import logging
import asyncio
import aiohttp
import aiofiles
import os
import re
import time
from pathlib import PurePath
from mime_ext import get_extension
from plugins.thumbnail import *
from typing import Dict, Optional
from urllib.parse import urlparse, unquote_plus
from plugins.script import Translation

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Import your custom configuration and progress helpers
from plugins.config import Config
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes, TimeFormatter, get_readable_time
from plugins.functions.util import metadata, ss_gen
from plugins.dl_button import download_coroutine
from plugins.functions.direct_links import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

DUMP_CHAT_ID = -1001973199110

############################################
# Download coroutine using aiohttp
############################################


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


def parse_content_disposition(content_disposition: str) -> Optional[str]:
    """
    Parse the Content-Disposition header to extract the filename.
    """
    parts = content_disposition.split(";")
    filename = None
    for part in parts:
        part = part.strip()
        if part.startswith("filename="):
            filename = part.split("=", 1)[1].strip(' "')
        elif part.startswith("filename*="):
            match = re.match(r"filename\*=(\S*)''(.*)", part)
            if match:
                encoding, value = match.groups()
                try:
                    filename = unquote_plus(value, encoding=encoding)
                except ValueError:
                    filename = None
    return filename


def get_filename(headers: Dict[str, str], url: str, unique_id: str) -> str:
    """
    Determine the filename from HTTP headers, URL, or generate a default.
    """
    filename = None
    if headers.get("Content-Disposition"):
        filename = parse_content_disposition(headers["Content-Disposition"])
    if not filename:
        filename = unquote_plus(url.rstrip("/").split("/")[-1].strip(' "'))
    if not filename or "." not in filename:
        if headers.get("Content-Type"):
            extension = mimetypes.guess_extension(headers["Content-Type"])
            filename = f"{unique_id}{extension or ''}".strip()
        else:
            filename = unique_id
    filename = unquote_plus(filename.strip().replace("/", "_"))
    return PurePath(sanitize_filename(filename))



async def download_coroutine(
    session, 
    url: str, 
    file_name: str, 
    headers: Dict[str, str], 
    file_path: str, 
    message: Message, 
    start_time: float,
    cancel_flag: Dict[str, bool],
    max_retries: int = 3
) -> str:
    """
    Download a file with retry and resume capabilities
    """
    downloaded = 0
    last_update_time = start_time
    last_progress_text = ""
    chunk_size = 1024 * 1024  # 1MB chunks
    retry_count = 0

    cancel_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]]
    )

    # Check if partial download exists
    if os.path.exists(file_path):
        downloaded = os.path.getsize(file_path)
        if downloaded > 0:
            headers['Range'] = f'bytes={downloaded}-'

    while retry_count < max_retries:
        try:
            async with session.get(url, headers=headers, timeout=Config.PROCESS_MAX_TIMEOUT, allow_redirects=True) as response:
                # Handle resume capability
                if response.status == 206:  # Partial content
                    total_length = downloaded + int(response.headers.get("Content-Length", 0))
                else:  # Full content
                    total_length = int(response.headers.get("Content-Length", 0))
                    downloaded = 0  # Reset if we're starting fresh

                progress_message = await message.edit(
                    f"📥 **{'Resuming' if downloaded else 'Starting'} Download**\n\n"
                    f"**File Name:** `{file_name}`\n"
                    f"**File Size:** {humanbytes(total_length)}",
                    reply_markup=cancel_button
                )

                # Open file in append mode if resuming, write mode if starting fresh
                mode = 'ab' if downloaded > 0 else 'wb'
                async with aiofiles.open(file_path, mode) as f_handle:
                    try:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            if cancel_flag.get("cancel", False):
                                await message.reply("❌ Download canceled.")
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                return None

                            await f_handle.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            diff = now - start_time

                            if now - last_update_time >= 5 or downloaded == total_length:
                                percentage = (downloaded / total_length) * 100
                                speed = downloaded / diff if diff > 0 else 0
                                time_to_completion = round((total_length - downloaded) / speed) * 1000 if speed > 0 else 0

                                progress_bar = "⬢" * int(percentage / 5) + "⬡" * (20 - int(percentage / 5))
                                progress_text = (
                                    f"📥 **Downloading...**\n\n"
                                    f"**File Name:** `{file_name}`\n"
                                    f"**Progress:** [{progress_bar}] {round(percentage, 2)}%\n"
                                    f"**Downloaded:** {humanbytes(downloaded)} of {humanbytes(total_length)}\n"
                                    f"**Speed:** {humanbytes(speed)}/s\n"
                                    f"**ETA:** {TimeFormatter(time_to_completion)}"
                                )

                                if progress_text != last_progress_text:
                                    await progress_message.edit(
                                        progress_text,
                                        reply_markup=cancel_button
                                    )
                                    last_progress_text = progress_text
                                    last_update_time = now

                    except (aiohttp.ClientPayloadError, asyncio.TimeoutError) as e:
                        logger.warning(f"Download interrupted: {str(e)}. Retrying...")
                        retry_count += 1
                        if retry_count < max_retries:
                            await message.edit(
                                f"⚠️ Download interrupted. Retrying ({retry_count}/{max_retries})...",
                                reply_markup=cancel_button
                            )
                            # Update headers with current downloaded bytes for resume
                            headers['Range'] = f'bytes={downloaded}-'
                            await asyncio.sleep(5)  # Wait before retry
                            continue
                        else:
                            raise Exception(f"Max retries ({max_retries}) reached")

                # Verify download completion
                if downloaded != total_length:
                    raise Exception("Download incomplete")

                return file_path

        except Exception as e:
            logger.error(f"Error in download attempt {retry_count + 1}: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise Exception(f"Download failed after {max_retries} attempts: {str(e)}")
            
            await message.edit(
                f"⚠️ Download error: {str(e)}\nRetrying ({retry_count}/{max_retries})...",
                reply_markup=cancel_button
            )
            await asyncio.sleep(5)  # Wait before retry

    raise Exception("Download failed: Max retries exceeded")


@Client.on_callback_query(filters.regex("^cancel_download$"))
async def cancel_download_handler(client, callback_query):
    """
    Handle the cancel button click.
    """
    # Set the cancel flag to True
    cancel_flag["cancel"] = True
    await callback_query.answer("Download canceled.")


@Client.on_message(filters.command("le"))
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
            downloaded_file = await download_coroutine(session, url, file_name, headers, download_path, lol, start_time, cancel_flag)
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
                f"┠ **Mode:** #leech || #aiohttp\n"
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