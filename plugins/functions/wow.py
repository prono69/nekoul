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
from mime_ext import get_extension
from typing import Dict, Optional, Tuple
from pyrogram import Client
from urllib.parse import urlparse, unquote_plus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Import your custom configuration and progress helpers
from plugins.config import Config
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes, TimeFormatter, get_readable_time


async def download_chunk(session, url, start, end, file_path, cancel_flag, progress_queue):
    """Download a specific chunk of the file."""
    headers = {"Range": f"bytes={start}-{end}"}
    async with session.get(url, headers=headers, allow_redirects=True) as response:
        if response.status != 200 and response.status != 206:
            raise Exception(f"Failed to download chunk: {response.status}")

        with open(file_path, "r+b") as f:
            f.seek(start)
            async for chunk in response.content.iter_any():
                if cancel_flag.get("cancel", False):
                    return None  # Cancelled
                f.write(chunk)
                await progress_queue.put(len(chunk))  # Send progress update

async def parallel_download(session, url, file_path, total_size, num_chunks, cancel_flag, message, file_name, start_time):
    """Download the file in parallel using range requests."""
    chunk_size = total_size // num_chunks
    tasks = []
    progress_queue = asyncio.Queue()  # Queue for progress updates
    downloaded = 0
    last_update_time = start_time
    last_progress_text = ""

    # Pre-allocate file size
    with open(file_path, "wb") as f:
        f.truncate(total_size)

    # Start download tasks
    for i in range(num_chunks):
        start = i * chunk_size
        end = total_size - 1 if i == num_chunks - 1 else (start + chunk_size - 1)
        tasks.append(download_chunk(session, url, start, end, file_path, cancel_flag, progress_queue))

    # Start a task to monitor progress
    async def monitor_progress():
        nonlocal downloaded, last_update_time, last_progress_text
        while downloaded < total_size:
            chunk_size = await progress_queue.get()
            downloaded += chunk_size
            now = time.time()
            diff = now - last_update_time

            # Update progress every 5 seconds
            if now - last_update_time >= 5 or downloaded == total_size:
                percentage = (downloaded / total_size) * 100
                speed = downloaded / diff if diff > 0 else 0
                time_to_completion = round((total_size - downloaded) / speed) if speed > 0 else 0

                progress_bar = "⬢" * int(percentage / 5) + "⬡" * (20 - int(percentage / 5))
                progress_text = (
                    f"📥 **Downloading...**\n\n"
                    f"**File Name:** `{file_name}`\n"
                    f"**Progress:** [{progress_bar}] {round(percentage, 2)}%\n"
                    f"**Downloaded:** {humanbytes(downloaded)} / {humanbytes(total_size)}\n"
                    f"**Speed:** {humanbytes(speed)}/s\n"
                    f"**ETA:** {TimeFormatter(time_to_completion * 1000)}"
                )

                if progress_text != last_progress_text:
                    await message.edit(progress_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]]))
                    last_progress_text = progress_text
                    last_update_time = now

    # Run download tasks and monitor progress
    monitor_task = asyncio.create_task(monitor_progress())
    await asyncio.gather(*tasks)
    monitor_task.cancel()  # Stop the progress monitor

    # Check if the download was canceled
    if cancel_flag.get("cancel", False):
        os.remove(file_path)
        return None

    return file_path
    
    
async def normal_download(session, url, file_path, message, file_name, total_size, cancel_flag, start_time):
    """Download file normally if range requests are not supported."""
    downloaded = 0
    last_update_time = start_time
    last_progress_text = ""

    cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]])

    async with session.get(url) as response:
        with open(file_path, "wb") as f:
            async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB chunks
                if cancel_flag.get("cancel", False):
                    await message.reply("❌ Download canceled.")
                    os.remove(file_path)
                    return None
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                diff = now - start_time

                # Update progress every 5 seconds
                if now - last_update_time >= 5 or downloaded == total_size:
                    percentage = (downloaded / total_size) * 100
                    speed = downloaded / diff if diff > 0 else 0
                    time_to_completion = round((total_size - downloaded) / speed) if speed > 0 else 0

                    progress_bar = "⬢" * int(percentage / 5) + "⬡" * (20 - int(percentage / 5))
                    progress_text = (
                        f"📥 **Downloading...**\n\n"
                        f"**File Name:** `{file_name}`\n"
                        f"**Progress:** [{progress_bar}] {round(percentage, 2)}%\n"
                        f"**Downloaded:** {downloaded} / {total_size} bytes\n"
                        f"**Speed:** {speed:.2f} bytes/s\n"
                        f"**ETA:** {time_to_completion} sec"
                    )

                    if progress_text != last_progress_text:
                        await message.edit(progress_text, reply_markup=cancel_button)
                        last_progress_text = progress_text
                        last_update_time = now

    return file_path
    
    
async def download_coroutine(session, url, file_name, headers, file_path, message, start_time, cancel_flag):
    """Download a file using parallel requests if supported, else fallback to normal download."""
    try:
        # Check if the server supports range requests
        async with session.head(url, headers=headers, allow_redirects=True) as response:
            if response.status != 200:
                raise Exception(f"Server returned status code: {response.status}")
            
            total_size = int(response.headers.get("Content-Length", 0))
            if total_size == 0:
                raise Exception("Invalid or missing Content-Length header")

            supports_range = response.headers.get("Accept-Ranges", "none").lower() == "bytes"

        # Download the file
        if supports_range:
            # Use parallel downloads if range requests are supported
            num_chunks = min(16, max(4, total_size // (1024 * 1024)))  # Dynamic chunk count
            return await parallel_download(
                session, url, file_path, total_size, num_chunks, cancel_flag, message, file_name, start_time
            )
        else:
            # Fallback to normal download
            return await normal_download(session, url, file_path, message, file_name, total_size, cancel_flag, start_time)

    except Exception as e:
        logger.error(f"Download error: {e}")
        raise e
        
        
@Client.on_callback_query(filters.regex("^cancel_download$"))
async def cancel_download_handler(client: Client, callback_query: CallbackQuery):
    """
    Handle the cancel button click.
    """
    # Set the cancel flag to True
    cancel_flag["cancel"] = True
    await callback_query.answer("Download canceled.")
    