import mimetypes
import logging
import asyncio
import aiohttp
from hashlib import sha256
import requests
import os
import re
import time
import subprocess
from datetime import datetime
from re import findall
from pathlib import PurePath
from plugins.thumbnail import *
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, unquote_plus
from plugins.script import Translation

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Import your custom configuration and progress helpers
from plugins.config import Config
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes, TimeFormatter, get_readable_time
from plugins.functions.util import metadata, ss_gen
from plugins.dl_button import download_coroutine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

DUMP_CHAT_ID = -1001973199110

############################################
# Helper functions for direct download links
############################################

def yandex_disk(url: str) -> str:
    # Placeholder for Yandex Disk bypass logic
    return url

def mediafire(url: str) -> str:
    # Placeholder for Mediafire bypass logic
    return url

def pixeldrain(url: str) -> str:
    url = url.strip("/ ")
    file_id = url.split("/")[-1]
    if url.split("/")[-2] == "l":
        info_link = f"https://pixeldra.in/api/list/{file_id}"
        dl_link = f"https://pixeldra.in/api/list/{file_id}/zip?download"
    else:
        info_link = f"https://pixeldra.in/api/file/{file_id}/info"
        dl_link = f"https://pixeldra.in/api/file/{file_id}?download"
    from cloudscraper import create_scraper
    with create_scraper() as session:
        try:
            resp = session.get(info_link).json()
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}") from e
        if resp.get("success"):
            return dl_link
        else:
            raise Exception(f"ERROR: Can't download due to {resp.get('message')}.")

def qiwi(url: str) -> str:
    # Using requests and lxml to parse the page
    import requests
    from lxml.etree import HTML
    with requests.Session() as session:
        file_id = url.split("/")[-1]
        try:
            res = session.get(url).text
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}") from e
        tree = HTML(res)
        if (name := tree.xpath('//h1[@class="page_TextHeading__VsM7r"]/text()')):
            ext = name[0].split(".")[-1]
            return f"https://spyderrock.com/{file_id}.{ext}"
        else:
            raise Exception("ERROR: File not found")

def gofile(url: str) -> Tuple[str, Dict[str, str]]:
    """
    Generate a direct download link for a GoFile URL and return the URL along with headers.
    """
    try:
        if "::" in url:
            _password = url.split("::")[-1]
            _password = sha256(_password.encode("utf-8")).hexdigest()
            url = url.split("::")[-2]
        else:
            _password = ""
        _id = url.split("/")[-1]
    except Exception as e:
        raise Exception(f"ERROR: {e.__class__.__name__}")

    def __get_token(session: requests.Session) -> str:
        """
        Fetch the account token from GoFile's API.
        """
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        __url = "https://api.gofile.io/accounts"
        try:
            __res = session.post(__url, headers=headers).json()
            if __res["status"] != "ok":
                raise Exception("ERROR: Failed to get token.")
            return __res["data"]["token"]
        except Exception as e:
            raise e

    def __fetch_links(session: requests.Session, _id: str) -> str:
        """
        Fetch the direct download link for the given GoFile ID.
        """
        _url = f"https://api.gofile.io/contents/{_id}?wt=4fd6sg89d7s6&cache=true"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Authorization": f"Bearer {token}",
        }
        if _password:
            _url += f"&password={_password}"
        try:
            _json = session.get(_url, headers=headers).json()
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}")
        if _json["status"] in "error-passwordRequired":
            raise Exception("ERROR: Password required.")
        if _json["status"] in "error-passwordWrong":
            raise Exception("ERROR: Wrong password!")
        if _json["status"] in "error-notFound":
            raise Exception("ERROR: File not found on GoFile's server.")
        if _json["status"] in "error-notPublic":
            raise Exception("ERROR: This folder is not public.")

        data = _json["data"]
        contents = data.get("children", {})
        if len(contents) == 1:
            for key, value in contents.items():
                return value.get("link")
        raise Exception("ERROR: Multiple files found, cannot determine direct link.")

    with requests.Session() as session:
        try:
            token = __get_token(session)
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}")
        try:
            direct_url = __fetch_links(session, _id)
        except Exception as e:
            raise Exception(f"ERROR: {e}")

    # Prepare headers with the Cookie
    headers = {
        "Cookie": f"accountToken={token}",
        "User-Agent": "Mozilla/5.0",
    }

    return direct_url, headers

def streamtape(url: str) -> str:
    import requests
    from lxml.etree import HTML
    splitted_url = url.split("/")
    _id = splitted_url[4] if len(splitted_url) >= 6 else splitted_url[-1]
    try:
        with requests.Session() as session:
            html = HTML(session.get(url).text)
    except Exception as e:
        raise Exception(f"ERROR: {e.__class__.__name__}") from e
    script = html.xpath("//script[contains(text(),'ideoooolink')]/text()") or html.xpath("//script[contains(text(),'ideoolink')]/text()")
    if not script:
        raise Exception("ERROR: requeries script not found")
    if not (links := findall(r"(&expires\S+)'", script[0])):
        raise Exception("ERROR: Download link not found")
    return f"https://streamtape.com/get_video?id={_id}{links[-1]}"

############################################
# Thumbnail generation using ffmpeg
############################################

async def generate_thumbnail(video_path: str, thumbnail_path: str) -> None:
    """
    Generate a thumbnail screenshot from the video using ffmpeg asynchronously.
    """
    try:
        command = [
            "ffmpeg", 
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-ss", "00:00:05",
            "-i", video_path,
            "-vf", "thumbnail",
            "-frames:v", "1",
            "-compression_level", "0",
            thumbnail_path
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"ffmpeg process returned non-zero exit code: {process.returncode}")
            
    except Exception as e:
        logger.error("Error generating thumbnail: %s", e)

############################################
# Download coroutine using aiohttp
############################################

# Initialize mimetypes
mimetypes.init()


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
    cancel_flag: Dict[str, bool]  # Shared flag to signal cancellation
) -> str:
    """
    Download a file from the given URL with optional headers and a cancel button.
    """
    downloaded = 0
    last_update_time = start_time
    last_progress_text = ""

    # Create a cancel button
    cancel_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]]
    )

    try:
        async with session.get(url, headers=headers, timeout=Config.PROCESS_MAX_TIMEOUT) as response:
            total_length = int(response.headers.get("Content-Length", 0))
            progress_message = await message.edit(
                f"📥 **Initiating Download**\n\n**File Name:** `{file_name}`\n**File Size:** {humanbytes(total_length)}",
                reply_markup=cancel_button
            )

            with open(file_path, "wb") as f_handle:
                while True:
                    # Check if the download has been canceled
                    if cancel_flag.get("cancel", False):
                        await progress_message.edit_text("❌ Download canceled.")
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        return None

                    chunk = await response.content.read(Config.CHUNK_SIZE)
                    if not chunk:
                        break
                    f_handle.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    diff = now - start_time

                    # Update progress every ~2 seconds or when finished
                    if now - last_update_time >= 5 or downloaded == total_length:
                        percentage = (downloaded / total_length) * 100
                        speed = downloaded / diff if diff > 0 else 0
                        time_to_completion = round((total_length - downloaded) / speed) if speed > 0 else 0
                        estimated_total_time = round(diff) + time_to_completion

                        # Stylish progress bar
                        progress_bar = "⬢" * int(percentage / 5) + "⬡" * (20 - int(percentage / 5))
                        progress_text = (
                            f"📥 **Downloading...**\n\n"
                            f"**File Name:** `{file_name}`\n"
                            f"**Progress:** [{progress_bar}] {round(percentage, 2)}%\n"
                            f"**Downloaded:** {humanbytes(downloaded)} of {humanbytes(total_length)}\n"
                            f"**Speed:** {humanbytes(speed)}/s\n"
                            f"**ETA:** {get_readable_time(time_to_completion)}"
                        )

                        # Only update the message if the content has changed
                        if progress_text != last_progress_text:
                            await progress_message.edit(
                                progress_text,
                                reply_markup=cancel_button
                            )
                            last_progress_text = progress_text
                            last_update_time = now

            return file_path
    except Exception as e:
        logger.error("Error in download_coroutine: %s", e)
        raise e


@Client.on_callback_query(filters.regex("^cancel_download$"))
async def cancel_download_handler(client: Client, callback_query: CallbackQuery):
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
    if len(args) < 2:
        return await message.reply_text("Usage: .le [URL]")
    url = args[1].strip()
    if not url and message.reply_to_message and message.reply_to_message.text:
        url = message.reply_to_message.text.strip()
    if not url:
        return await message.reply_text("Usage: .le [URL]")

    # Parse domain and determine if URL is supported for bypassing
    domain = urlparse(url).hostname
    supported = False
    if domain:
        if "yadi.sk" in domain or "disk.yandex." in domain:
            url = yandex_disk(url)
            supported = True
        elif "mediafire.com" in domain:
            url = mediafire(url)
            supported = True
        elif any(x in domain for x in ["pixeldrain.com", "pixeldra.in"]):
            url = pixeldrain(url)
            supported = True
        elif "qiwi.gg" in domain:
            url = qiwi(url)
            supported = True
        elif "gofile.io" in domain:
            try:
                direct_url, headers = gofile(url)
                url = direct_url
                supported = True
            except Exception as e:
                logger.error(f"GoFile Error: {e}")
                return await message.reply_text(f"❌ GoFile Error: {str(e)}")
        elif "streamtape.to" in domain:
            url = streamtape(url)
            supported = True

    lol = await message.reply("📥 **Downloading...**")
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(message.from_user.id))
    os.makedirs(user_dir, exist_ok=True)

    # Fetch headers asynchronously using aiohttp (HEAD request)
    async with aiohttp.ClientSession() as session:
        try:
            # Set a timeout for the HEAD request
            timeout = aiohttp.ClientTimeout(total=10)  # 10 seconds
            async with session.head(url, headers=headers, timeout=timeout) as response:
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
        file_ext = mimetypes.guess_extension(content_type) or ".bin"
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
                    await ss_gen(downloaded_file, thumb_image_path)
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
                f"┠ **Mode:** #UDL\n"
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