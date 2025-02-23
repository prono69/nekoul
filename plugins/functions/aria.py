import asyncio
import os
import time
import logging
from typing import Dict, Optional
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# Logger
logger = logging.getLogger(__name__)

# List of valid aria2c global options
aria2c_global = [
    'bt-max-open-files', 'download-result', 'keep-unfinished-download-result', 'log', 'log-level',
    'max-concurrent-downloads', 'max-download-result', 'max-overall-download-limit', 'save-session',
    'max-overall-upload-limit', 'optimize-concurrent-downloads', 'save-cookies', 'server-stat-of',
    'split', 'min-split-size', 'max-connection-per-server'
]

# Utility functions
def humanbytes(size: float) -> str:
    """Convert bytes to human-readable format."""
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"

def TimeFormatter(milliseconds: int) -> str:
    """Convert milliseconds to a human-readable time format."""
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# Download function
async def download_coroutine(
    url: str, 
    file_name: str, 
    file_path: str, 
    headers: Dict[str, str],
    total_length,
    message: Message, 
    start_time: float,
    cancel_flag: Dict[str, bool],  # Shared flag to signal cancellation
    aria2_options: Optional[Dict[str, str]] = None  # Optional aria2c options
) -> Optional[str]:
    """
    Download a file using aria2c for high-speed multi-threaded downloads.
    Supports custom headers and real-time progress updates.
    """
    if aria2_options is None:
        aria2_options = {}

    cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]])
    progress_message = await message.edit(f"📥 **Initiating Download**\n\n**File Name:** `{file_name}`\n**File Size:** {humanbytes(total_length)}", reply_markup=cancel_button)

    # Ensure the directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Construct the aria2c command
    cmd = [
        "aria2c", "-l", "-", "--log-level", "notice", "-x", "16", "-s", "16", "-k", "1M", "--allow-overwrite=true",
        "-o", file_name, "-d", os.path.dirname(file_path), url
    ]

    # Add custom headers if provided
    for key, value in headers.items():
        cmd.extend(["--header", f"{key}: {value}"])

    # Add aria2_options to the command (only valid global options)
    for key, value in aria2_options.items():
        if key in aria2c_global:  # Only add valid global options
            cmd.extend([f"--{key}", str(value)])

    # Start aria2c process
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    last_update_time = start_time
    last_progress_text = ""

    try:
        while True:
            # Check for cancellation
            if cancel_flag.get("cancel", False):
                process.kill()
                await message.reply("❌ Download canceled.")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None

            # Read stdout for progress updates
            line = await process.stdout.readline()
            if not line:
                break

            # Log the raw output for debugging
            logger.debug(f"aria2lol output: {line.decode().strip()}")

            now = time.time()
            diff = now - start_time

            # Extract progress percentage, downloaded size, and speed
            line = line.decode().strip()
            if "%" in line:
                try:
                    # Example line: "[#1c59fa 3.0MiB/7.6MiB(39%) CN:1 DL:5.1MiB]"
                    parts = line.split()
                    downloaded = float(parts[1].split("/")[0].replace("MiB", "")) * 1024 * 1024  # Convert MiB to bytes
                    total_length = float(parts[1].split("/")[1].split("(")[0].replace("MiB", "")) * 1024 * 1024  # Convert MiB to bytes
                    percentage = float(parts[1].split("(")[1].replace("%)", ""))
                    speed = float(parts[3].split(":")[1].replace("MiB", "")) * 1024 * 1024  # Convert MiB/s to bytes/s
                    time_to_completion = round((total_length - downloaded) / speed) if speed > 0 else 0
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing progress: {e}")
                    continue  # Skip if parsing fails

                # Update every 5 seconds or when finished
                if now - last_update_time >= 5 or percentage == 100:
                    progress_bar = "⬢" * int(percentage / 5) + "⬡" * (20 - int(percentage / 5))
                    progress_text = (
                        f"📥 **Downloading...**\n\n"
                        f"**File Name:** `{file_name}`\n"
                        f"**Progress:** [{progress_bar}] {round(percentage, 2)}%\n"
                        f"**Downloaded:** {humanbytes(downloaded)} of {humanbytes(total_length)}\n"
                        f"**Speed:** {humanbytes(speed)}/s\n"
                        f"**ETA:** {TimeFormatter(time_to_completion * 1000)}"
                    )

                    if progress_text != last_progress_text:
                        try:
                            await progress_message.edit(progress_text, reply_markup=cancel_button)
                            last_progress_text = progress_text
                            last_update_time = now
                        except Exception as e:
                            logger.error(f"Error editing message: {e}")

        # Wait for process to complete
        await process.wait()

        if process.returncode == 0 and os.path.exists(file_path):
            logger.info(f"Download completed: {file_name}")
            return file_path
        else:
            stderr = await process.stderr.read()
            error_message = stderr.decode().strip()
            await message.reply(f"❌ Download failed: {error_message}")
            return None

    finally:
        if process.returncode is None:  # Process is still running
            process.kill()
            
            
            
@Client.on_callback_query(filters.regex("^cancel_download$"))
async def cancel_download_handler(client, callback_query):
    """
    Handle the cancel button click.
    """
    # Set the cancel flag to True
    cancel_flag["cancel"] = True
    await callback_query.answer("Download canceled.")
                