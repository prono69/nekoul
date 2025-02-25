import logging
import asyncio
import os
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Import your custom configuration and progress helpers
from plugins.functions.display_progress import humanbytes, TimeFormatter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


async def download_chunk(session, url, start, end, chunk_path, cancel_flag, progress_queue, retries=3):
    """Download a specific chunk of the file with retries."""
    headers = {"Range": f"bytes={start}-{end}"}
    for attempt in range(retries):
        try:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                if response.status != 200 and response.status != 206:
                    raise Exception(f"Failed to download chunk: {response.status}")

                with open(chunk_path, "wb") as f:
                    async for chunk in response.content.iter_any():
                        if cancel_flag.get("cancel", False):
                            return None  # Cancelled
                        f.write(chunk)
                        await progress_queue.put(len(chunk))  # Send progress update
                break  # Success
        except Exception as e:
            if attempt == retries - 1:
                raise e
            await asyncio.sleep(1)  # Wait before retrying
                
                
async def merge_chunks(chunk_paths, output_file):
    """Merge downloaded chunks into the final file."""
    with open(output_file, "wb") as outfile:
        for chunk_path in sorted(chunk_paths):
            with open(chunk_path, "rb") as infile:
                outfile.write(infile.read())
            os.remove(chunk_path)  # Clean up chunk file
            

async def parallel_download(session, url, file_path, total_size, num_chunks, cancel_flag, message, file_name, start_time):
    """Download the file in parallel using range requests."""
    chunk_size = total_size // num_chunks
    tasks = []
    progress_queue = asyncio.Queue()  # Queue for progress updates
    downloaded = 0
    last_update_time = start_time
    last_progress_text = ""
    chunk_paths = []
    cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]])

    # Create a temporary directory for chunks
    temp_dir = "temp_chunks"
    os.makedirs(temp_dir, exist_ok=True)

    # Pre-allocate file size
    with open(file_path, "wb") as f:
        f.truncate(total_size)

    # Check if the download was canceled
    if cancel_flag.get("cancel", False):
        await message.reply("❌ Download canceled.")
        os.remove(file_path)
        return None    

    # Start download tasks
    for i in range(num_chunks):
        start = i * chunk_size
        end = total_size - 1 if i == num_chunks - 1 else (start + chunk_size - 1)
        chunk_path = os.path.join(temp_dir, f"chunk_{i}")
        chunk_paths.append(chunk_path)
        tasks.append(download_chunk(session, url, start, end, chunk_path, cancel_flag, progress_queue))

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
                    await message.reply(progress_text, reply_markup=cancel_button)
                    last_progress_text = progress_text
                    last_update_time = now

    # Run download tasks and monitor progress
    monitor_task = asyncio.create_task(monitor_progress())
    await asyncio.gather(*tasks)
    monitor_task.cancel()  # Stop the progress monitor

    # Merge chunks into the final file
    await merge_chunks(chunk_paths, file_path)
    os.rmdir(temp_dir)  # Clean up temp directory

    logger.info(f"The path is {file_path}")
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
                        await message.reply(progress_text, reply_markup=cancel_button)
                        last_progress_text = progress_text
                        last_update_time = now
    logger.info(f"The file path is {file_path}")                    


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
async def cancel_download_handler(client, callback_query):
    """
    Handle the cancel button click.
    """
    # Set the cancel flag to True
    cancel_flag["cancel"] = True
    await callback_query.answer("Download canceled.")
    