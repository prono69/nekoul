import asyncio
import json
import subprocess
from urllib.parse import unquote

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
