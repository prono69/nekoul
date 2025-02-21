# Credits by @neomatrix90

import asyncio
import aiohttp
import random
import time
import requests
from random import choice
from datetime import datetime as dt

from pyrogram import filters, Client
from pyrogram.types import Message
from plugins import StartTime
from plugins.config import Config
from plugins.functions.display_progress import get_readable_time

PING_DISABLE_NONPREM = {}
ANIME_WAIFU_IS_RANDOM = {}

def waifu_hentai():
    LIST_SFW_JPG = ["trap", "waifu", "blowjob", "neko"]
    waifu_link = "https"
    waifu_api = "api.waifu.pics"
    waifu_types = "nsfw"
    waifu_category = choice(LIST_SFW_JPG)
    waifu_param = f"{waifu_link}://{waifu_api}/{waifu_types}/{waifu_category}"
    response = requests.get(waifu_param).json()
    return response["url"]

def waifu_random():
    LIST_SFW_JPG = ["neko", "waifu", "megumin"]
    waifu_link = "https"
    waifu_api = "api.waifu.pics"
    waifu_types = "sfw"
    waifu_category = choice(LIST_SFW_JPG)
    waifu_param = f"{waifu_link}://{waifu_api}/{waifu_types}/{waifu_category}"
    response = requests.get(waifu_param).json()
    return response["url"]

async def fetch_server_status():
    """Fetch the server status from the given URL."""
    url = "https://kawaiimizo-riasudl.hf.space/status"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("message", "Unknown")
                return "Server Unreachable"
    except Exception as e:
        return f"Error: {str(e)}"

def get_caption(client, duration: float, server_status: str, uptime: str, is_premium: bool) -> str:
    """Generate the caption for the ping response."""
    if is_premium:
        return f"**Pong !!** `{duration}ms`\n**Server:** {server_status}\n**Uptime** - `{uptime}`\n"
    return (
        f"🏓 **Pɪɴɢᴇʀ :** `{duration}ms`\n"
        f"👨‍💻 **Sᴇʀᴠᴇʀ:** `{server_status}`\n"
        f"⌛ **Uᴘᴛɪᴍᴇ :** `{uptime}`\n"
        f"🤴 **Oᴡɴᴇʀ :** **__{client.me.mention}__**"
    )

async def send_ping_response(client, message: Message, duration: float, server_status: str, uptime: str, is_premium: bool, photo=None):
    """Send the ping response with optional photo."""
    caption = get_caption(client, duration, server_status, uptime, is_premium)
    if photo:
        await message.reply_photo(photo, caption=caption)
    else:
        await message.reply_text(caption)

@Client.on_message(filters.command("pingset") & filters.user(Config.OWNER_ID) & ~filters.forwarded)
async def pingsetsetting(client, message: Message):
    global PING_DISABLE_NONPREM, ANIME_WAIFU_IS_RANDOM
    args = message.text.lower().split()[1:]
    chat = message.chat

    if chat.type != "private" and args:
        if args[0] == "anime":
            ANIME_WAIFU_IS_RANDOM[message.from_user.id] = {"anime": True, "hentai": False}
            await message.reply_text(f"Turned on ping {args[0]}.")
        elif args[0] == "hentai":
            ANIME_WAIFU_IS_RANDOM[message.from_user.id] = {"anime": False, "hentai": True}
            await message.reply_text(f"Turned on ping {args[0]}.")
        elif args[0] in ("no", "off", "false"):
            PING_DISABLE_NONPREM[message.from_user.id] = False
            ANIME_WAIFU_IS_RANDOM[message.from_user.id] = {"anime": False, "hentai": False}
            await message.reply_text("Turned off ping automatic.")
    else:
        ping_mode = "On" if PING_DISABLE_NONPREM.get(message.from_user.id) else \
                    "Anime" if ANIME_WAIFU_IS_RANDOM.get(message.from_user.id) else "Off"
        await message.reply_text(f"Ping Mode: {ping_mode}")

@Client.on_message(filters.command("ping") & ~filters.forwarded)
async def custom_ping_handler(client, message: Message):
    uptime = get_readable_time((time.time() - StartTime))
    start = dt.now()
    lol = await message.reply_text("**__Pong!!__**")
    # await asyncio.sleep(1.5)
    duration_ = (dt.now() - start).microseconds / 1000
    duration = round(duration_)

    is_premium = client.me.is_premium
    is_anime = ANIME_WAIFU_IS_RANDOM.get(message.from_user.id)
    server_status = await fetch_server_status()

    if PING_DISABLE_NONPREM.get(message.from_user.id):
        await lol.edit_text(get_caption(client, duration, server_status, uptime, is_premium))
        return

    if is_anime:
        photo = waifu_random() if is_anime.get("anime") else waifu_hentai() if is_anime.get("hentai") else None
        if photo:
            await send_ping_response(client, message, duration, server_status, uptime, is_premium, photo)
            await lol.delete()
            return

    await send_ping_response(client, message, duration, server_status, uptime, is_premium)
    await lol.delete()