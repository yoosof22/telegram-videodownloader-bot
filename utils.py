"""Utilities: regex patterns, rate limiter, and helpers."""
import re
import time
import asyncio
from collections import defaultdict
from typing import Optional
from dataclasses import dataclass, field


# Regex patterns for supported platforms
TIKTOK_PATTERNS = [
    r"https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+",
    r"https?://vm\.tiktok\.com/[\w-]+",
    r"https?://vt\.tiktok\.com/[\w-]+",
    r"https?://(?:www\.)?tiktok\.com/t/[\w-]+",
]

INSTAGRAM_PATTERNS = [
    r"https?://(?:www\.)?instagram\.com/reel/[\w-]+",
    r"https?://(?:www\.)?instagram\.com/p/[\w-]+",
    r"https?://(?:www\.)?instagram\.com/tv/[\w-]+",
    r"https?://(?:www\.)?instagram\.com/reels/[\w-]+",
]

# Combined pattern for quick detection
TIKTOK_REGEX = re.compile("|".join(TIKTOK_PATTERNS), re.IGNORECASE)
INSTAGRAM_REGEX = re.compile("|".join(INSTAGRAM_PATTERNS), re.IGNORECASE)
URL_REGEX = re.compile(r"https?://\S+")


@dataclass
class RateLimiter:
    """
    Sliding window rate limiter per user.
    Tracks requests in the last N minutes.
    """
    max_requests: int
    window_seconds: int = 60
    _requests: dict[int, list[float]] = field(default_factory=lambda: defaultdict(list))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to make a request. Returns True if allowed."""
        async with self._lock:
            now = time.time()
            user_requests = self._requests[user_id]

            # Remove expired entries
            user_requests[:] = [ts for ts in user_requests if now - ts < self.window_seconds]

            if len(user_requests) >= self.max_requests:
                return False

            user_requests.append(now)
            return True

    async def get_retry_after(self, user_id: int) -> int:
        """Get seconds until next request is allowed."""
        async with self._lock:
            user_requests = self._requests.get(user_id, [])
            if not user_requests:
                return 0
            now = time.time()
            oldest = min(user_requests)
            return max(0, int(self.window_seconds - (now - oldest)) + 1)


@dataclass
class DownloadSemaphore:
    """Global concurrency limiter for downloads."""
    max_concurrent: int
    _semaphore: asyncio.Semaphore = field(init=False)

    def __post_init__(self):
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

    async def __aenter__(self):
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._semaphore.release()


def extract_urls(text: str) -> list[str]:
    """Extract all URLs from text."""
    return URL_REGEX.findall(text)


def detect_platform(url: str) -> Optional[str]:
    """
    Detect which platform a URL belongs to.
    Returns 'tiktok', 'instagram', or None.
    """
    if TIKTOK_REGEX.search(url):
        return "tiktok"
    if INSTAGRAM_REGEX.search(url):
        return "instagram"
    return None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize filename for safe filesystem usage."""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    # Limit length
    if len(filename) > max_length:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:max_length - len(ext) - 1] + ("." + ext if ext else "")
    return filename


class UserError(Exception):
    """User-facing error with Persian message."""
    def __init__(self, message_fa: str, message_en: str = ""):
        self.message_fa = message_fa
        self.message_en = message_en or message_fa
        super().__init__(message_fa)


class DownloadError(UserError):
    """Download-specific errors."""
    pass


class RateLimitError(UserError):
    """Rate limit exceeded error."""
    pass