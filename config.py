"""Configuration loader for the Telegram video downloader bot."""
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""
    bot_token: str
    proxy_url: str | None
    instagram_cookies: str | None
    instagram_cookies_browser: str | None
    max_file_mb: int
    rate_limit_per_min: int

    @classmethod
    def from_env(cls) -> "Config":
        """Create Config instance from environment variables."""
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise ValueError("BOT_TOKEN is required in .env file")

        return cls(
            bot_token=token,
            proxy_url=os.getenv("PROXY_URL") or None,
            instagram_cookies=os.getenv("INSTAGRAM_COOKIES") or None,
            instagram_cookies_browser=os.getenv("INSTAGRAM_COOKIES_BROWSER") or None,
            max_file_mb=int(os.getenv("MAX_FILE_MB", "50")),
            rate_limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "5")),
        )


# Global config instance
config = Config.from_env()