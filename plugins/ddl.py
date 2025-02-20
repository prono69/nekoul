import logging
import asyncio
import aiohttp
import os
import time
import subprocess
from datetime import datetime
from urllib.parse import urlparse
from re import findall

from pyrogram import Client, filters, enums
from pyrogram.types import Message

# Import your custom configuration and progress helpers
from plugins.config import Config
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes, TimeFormatter
from plugins.dl_button import download_coroutine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

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

def gofile(url: str) -> str:
    from hashlib import sha256
    import requests
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
    
    def __get_token(session):
        headers = {
            "User-Agent": getattr(Config, "USER_AGENT", "Mozilla/5.0")
        }
        __url = "https://api.gofile.io/accounts"
        try:
            __res = session.post(__url, headers=headers).json()
            if __res["status"] != "ok":
                raise Exception("ERROR: Failed to get token.")
            return __res["data"]["token"]
        except Exception as e:
            raise e

    def __fetch_links(session, _id, folderPath=""):
        _url = f"https://api.gofile.io/contents/{_id}?wt=4fd6sg89d7s6&cache=true"
        headers = {
            "User-Agent": getattr(Config, "USER_AGENT", "Mozilla/5.0"),
            "Authorization": "Bearer " + token,
        }
        if _password:
            _url += f"&password={_password}"
        try:
            _json = session.get(_url, headers=headers).json()
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}")
        if _json["status"] in "error-passwordRequired":
            raise Exception("ERROR: Password required")
        if _json["status"] in "error-passwordWrong":
            raise Exception("ERROR: Wrong password!")
        if _json["status"] in "error-notFound":
            raise Exception("ERROR: File not found on gofile's server")
        if _json["status"] in "error-notPublic":
            raise Exception("ERROR: This folder is not public")
        data = _json["data"]
        contents = data.get("children", {})
        if len(contents) == 1:
            for key, value in contents.items():
                return value.get("link")
        raise Exception("ERROR: Multiple files found, cannot determine direct link")
    
    with requests.Session() as session:
        try:
            token = __get_token(session)
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}")
        return __fetch_links(session, _id)

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

def generate_thumbnail(video_path: str, thumbnail_path: str) -> None:
    """
    Generate a thumbnail screenshot from the video (at 1 second) using ffmpeg.
    """
    try:
        command = [
            "ffmpeg", "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            thumbnail_path
        ]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception as e:
        logger.error("Error generating thumbnail: %s", e)

############################################
# Download coroutine using aiohttp
############################################



############################################
# Main udl plugin command handler
############################################

@Client.on_message(filters.command("le"))
async def udl_handler(client: Client, message: Message):
    start_time = time.time()
    text = message.text
    args = text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("Usage: .udl [URL]")
    url = args[1].strip()
    # If no URL is provided, try to get it from the replied message
    if not url and message.reply_to_message and message.reply_to_message.text:
        url = message.reply_to_message.text.strip()
    if not url:
        return await message.reply_text("Usage: .udl [URL]")
    
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
            url = gofile(url)
            supported = True
        elif "streamtape.to" in domain:
            url = streamtape(url)
            supported = True

    # if supported:
        # status_msg = await message.reply_text("**Supported URL found!**\nBypassing and downloading...")
    # else:
        # status_msg = await message.reply_text("Downloading...")

    # Create a temporary directory for this user
    await message.reply("Dl......")
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(message.from_user.id))
    if not os.path.isdir(user_dir):
        os.makedirs(user_dir)
    # Determine file name (if empty, use a default name)
    file_name = os.path.basename(urlparse(url).path)
    if not file_name:
        file_name = "downloaded_file"
    download_path = os.path.join(user_dir, file_name)

    # Start the download using aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            downloaded_file = await download_coroutine(client, session, url, download_path, message.chat.id, message.id, start_time)
        except asyncio.TimeoutError:
            return await message.reply("❌ Download timed out!")
        except Exception as e:
            return await message.reply(f"❌ Error during download: {str(e)}")
    
    # Once downloaded, send the file with thumbnail if video
    if os.path.exists(downloaded_file):
        file_ext = os.path.splitext(downloaded_file)[1].lower()
        caption = f"**File Name:** `{os.path.basename(downloaded_file)}`"
        if file_ext in [".mp4", ".mkv", ".avi"]:
            thumb_path = os.path.splitext(downloaded_file)[0] + ".jpg"
            generate_thumbnail(downloaded_file, thumb_path)
            await client.send_video(
                chat_id=message.chat.id,
                video=downloaded_file,
                thumb=thumb_path if os.path.exists(thumb_path) else None,
                caption=caption,
                reply_to_message_id=message.message_id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading...", message, time.time())
            )
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=downloaded_file,
                caption=caption,
                reply_to_message_id=message.message_id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading...", message, time.time())
            )
        # await status_msg.delete()
        os.remove(downloaded_file)
    else:
        await message.reply_text("❌ Downloaded file not found.")
        