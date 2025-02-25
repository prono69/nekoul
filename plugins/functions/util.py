import asyncio
import json
from time import strftime, gmtime
import subprocess
import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)

async def bash(cmd):
    """Run a shell command and return its output."""
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return stdout.decode().strip(), stderr.decode().strip()

async def metadata(file):
    """Extract metadata using mediainfo."""
    out, err = await bash(f'mediainfo "{unquote(file)}" --Output=JSON')
    if err and "NOT_FOUND" in err:
        raise Exception("mediainfo is not installed! Install it to use this command.")
    
    data = {}
    try:
        _info = json.loads(out)["media"]["track"]
        info = _info[0]
        
        if info.get("Format") in ["GIF", "PNG"]:
            return {
                "height": _info[1]["Height"],
                "width": _info[1]["Width"],
                "bitrate": _info[1].get("BitRate", 320),
            }
        
        if info.get("AudioCount"):
            data["title"] = info.get("Title", file)
            data["performer"] = info.get("Performer") or "Unknown"
        
        if info.get("VideoCount"):
            data["height"] = int(float(_info[1].get("Height", 720)))
            data["width"] = int(float(_info[1].get("Width", 1280)))
            data["bitrate"] = int(_info[1].get("BitRate", 320))
        
        data["duration"] = int(float(info.get("Duration", 0)))
        return data
    except Exception as e:
        logger.error(f"Error parsing metadata: {e}")
        return {}

############################################
# Thumbnail generation using ffmpeg
############################################
        
async def ss_gen(video_path: str, thumbnail_path: str, duration) -> None:
    """
    Generate a thumbnail screenshot from the video using ffmpeg asynchronously.
    """
    try:
        # des_dir = os.path.join('Thumbnails', f"{time()}")
        # os.makedirs(des_dir, exist_ok=True)
        
        # Get video duration
        # meta = await metadata(video_path)
        # duration = meta.get("duration", 0)
        logger.info(f"got the duration {duration}")
        if duration == 0:
            duration = 3
        duration = duration - (duration * 2 / 100)
        
        # Take screenshot near the end of the adjusted duration
        op = str(int(duration))
        seek_time = strftime("%H:%M:%S", gmtime(float(op)))
        logger.info(f"Final ss time is {seek_time}")

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "debug",
            "-y",
            "-ss", seek_time,  # Will be set near the end of the duration
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
        
        if process.returncode == 0:
            # Move the generated thumbnail to desired location
            # os.rename(
                # os.path.join(des_dir, "wz_thumb_1.jpg"),
                # thumbnail_path
            #)
            logger.info("DONE")
        else:
            raise Exception(f"ffmpeg process returned non-zero exit code: {process.returncode}")
            
        # Cleanup temporary directory
        # os.rmdir(des_dir)
            
    except Exception as e:
        logger.error("Error generating thumbnail: %s", e)
        
        

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