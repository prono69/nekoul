import os
from os import environ
import logging

logging.basicConfig(
    format='%(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('log.txt'),
              logging.StreamHandler()],
    level=logging.INFO
)

class Config(object):
    
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    API_ID = int(os.environ.get("API_ID", ))
    API_HASH = os.environ.get("API_HASH", "")
    
    DOWNLOAD_LOCATION = "./DOWNLOADS"
    MAX_FILE_SIZE = 2194304000
    TG_MAX_FILE_SIZE = 2194304000
    DUMP_CHAT_ID = -1001973199110
    SESSION_STR = ""
    FREE_USER_MAX_FILE_SIZE = 2194304000
    CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 128))
    DEF_THUMB_NAIL_VID_S = os.environ.get("DEF_THUMB_NAIL_VID_S", "https://placehold.it/90x90")
    HTTP_PROXY = os.environ.get("HTTP_PROXY", "")
    
    OUO_IO_API_KEY = ""
    MAX_MESSAGE_LENGTH = 4096
    PROCESS_MAX_TIMEOUT = 3600
    DEF_WATER_MARK_FILE = "@UploaderXNTBot"

    BANNED_USERS = set(int(x) for x in os.environ.get("BANNED_USERS", "").split())

    DATABASE_URL = os.environ.get("DATABASE_URL", "")

    LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", ""))
    LOGGER = logging
    OWNER_ID = int(os.environ.get("OWNER_ID", ""))
    SESSION_NAME = "UploaderXNTBot"
    UPDATES_CHANNEL = os.environ.get("UPDATES_CHANNEL", "-1001735477039")

    TG_MIN_FILE_SIZE = 2194304000
    BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
    ADL_BOT_RQ = {}

    # Set False off else True
    TRUE_OR_FALSE = os.environ.get("TRUE_OR_FALSE", "").lower() == "true"

    # Shortlink settings
    SHORT_DOMAIN = environ.get("SHORT_DOMAIN", "")
    SHORT_API = environ.get("SHORT_API", "")

    # Verification video link
    VERIFICATION = os.environ.get("VERIFICATION", "")
    TERA_API = os.environ.get("TERA_API", "7fbe2bb92amsh79d8e422672137cp1a5e3djsnb7b9f71940fe f7da56d8a0msh132d6fa978abd93p10f7c3jsna5deaf9c2fb7")
    ARIA_OPTIONS = {
        # "allow-overwrite": "true",  # Overwrite existing files
        "auto-file-renaming": True,  # Automatically rename files if they exist
        "max-connection-per-server": "10",  # Allow up to 16 connections per server
        "max-concurrent-downloads": "10",  # Allow up to 16 parallel downloads
        "split": "10",  # Split each file into 16 chunks
        "min-split-size": "10M",  # Only split files larger than 10MB
        "check-integrity": True,  # Verify file integrity after download
        "continue": True,  # Resume interrupted downloads
        "disk-cache": "40M",  # Use a 40MB disk cache
        "optimize-concurrent-downloads": True,  # Optimize concurrent downloads
        "http-accept-gzip": True,  # Enable gzip compression for HTTP downloads
        "max-tries": "5",  # Retry up to 5 times
        # "quiet": True,  # Suppress non-essential output
        "summary-interval": "0",  # Disable periodic summary output
        "max-upload-limit": "1K",  # Limit upload speed to 1KB/s
        "content-disposition-default-utf8": True,  # Use UTF-8 for content disposition
        "user-agent": "Wget/1.12",  # Set user agent for HTTP downloads
        "reuse-uri": True,  # Reuse URIs for multiple connections
    }    

    