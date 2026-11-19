"""Video downloader using yt-dlp with ffmpeg integration."""
import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yt_dlp

from config import config
from utils import DownloadError, format_file_size

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


@dataclass
class DownloadResult:
    """Result of a download operation."""
    file_path: Path
    title: str
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    filesize: Optional[int] = None
    temp_dir: Optional[Path] = field(default=None, repr=False)


class VideoDownloader:
    """
    Downloads videos from TikTok and Instagram using yt-dlp.
    Runs in executor to avoid blocking the event loop.

    Every download gets its own temporary directory, so concurrent downloads
    never delete each other's files.
    """

    def __init__(self, max_file_mb: int = 50, proxy_url: Optional[str] = None,
                 instagram_cookies: Optional[str] = None,
                 instagram_cookies_browser: Optional[str] = None):
        self.max_file_mb = max_file_mb
        self.max_file_bytes = max_file_mb * 1024 * 1024
        self.proxy_url = proxy_url
        self.instagram_cookies = instagram_cookies
        self.instagram_cookies_browser = instagram_cookies_browser
        self._temp_dirs: set[Path] = set()

    # --- temp dir handling -------------------------------------------------

    def _new_temp_dir(self) -> Path:
        """Create a fresh temporary directory for one download."""
        path = Path(tempfile.mkdtemp(prefix="tg_vid_dl_"))
        self._temp_dirs.add(path)
        return path

    def cleanup_result(self, result: "DownloadResult") -> None:
        """Delete the temp dir belonging to a finished download."""
        temp_dir = result.temp_dir
        if not temp_dir:
            return
        shutil.rmtree(temp_dir, ignore_errors=True)
        self._temp_dirs.discard(temp_dir)

    def cleanup(self) -> None:
        """Delete all leftover temporary directories (used on shutdown)."""
        for temp_dir in list(self._temp_dirs):
            shutil.rmtree(temp_dir, ignore_errors=True)
        self._temp_dirs.clear()

    # --- yt-dlp options ----------------------------------------------------

    def _build_ydl_opts(self, url: str, temp_dir: Path) -> dict:
        """Build yt-dlp options based on URL and config."""
        opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(temp_dir / "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": False,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
            "skip_unavailable_fragments": True,
            "postprocessors": [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        }

        # Add proxy if configured
        if self.proxy_url:
            opts["proxy"] = self.proxy_url

        # Instagram needs an authenticated session for most content
        if "instagram.com" in url:
            cookie_file = Path(self.instagram_cookies).expanduser() if self.instagram_cookies else None
            if cookie_file and cookie_file.is_file():
                opts["cookiefile"] = str(cookie_file)
                logger.debug(f"Using Instagram cookie file: {cookie_file}")
            elif self.instagram_cookies_browser:
                # yt-dlp expects a tuple: (browser, profile, keyring, container)
                opts["cookiesfrombrowser"] = (self.instagram_cookies_browser, None, None, None)
                logger.debug(f"Using cookies from browser: {self.instagram_cookies_browser}")
            elif cookie_file:
                logger.warning(
                    f"INSTAGRAM_COOKIES points to '{cookie_file}' but that file does not exist "
                    "- continuing without cookies"
                )

        return opts

    # --- helpers -----------------------------------------------------------

    def _check_file_size(self, file_path: Path) -> None:
        """Check if downloaded file exceeds size limit."""
        size = file_path.stat().st_size
        if size > self.max_file_bytes:
            file_path.unlink(missing_ok=True)
            raise DownloadError(
                f"❌ فایل دانلود شده بزرگ‌تر از حد مجاز ({self.max_file_mb} مگابایت) است.\n"
                f"حجم فایل: {format_file_size(size)}",
                f"Downloaded file exceeds size limit ({self.max_file_mb} MB). "
                f"File size: {format_file_size(size)}"
            )

    @staticmethod
    def _pick_single(info: dict) -> dict:
        """Reduce a playlist/carousel result to a single video entry."""
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            return info

        def score(entry: dict) -> tuple:
            ext = (entry.get("ext") or "").lower()
            is_video = ext not in IMAGE_EXTS or entry.get("vcodec") not in (None, "none")
            return (1 if is_video else 0, entry.get("duration") or 0)

        return max(entries, key=score)

    @staticmethod
    def _reject_non_video(info: dict) -> None:
        """Raise a friendly error for image-only posts."""
        ext = (info.get("ext") or "").lower()
        if ext in IMAGE_EXTS:
            raise DownloadError(
                "📷 این پست فقط شامل تصاویر است و ویدیو ندارد.\n"
                "در حال حاضر فقط دانلود ویدیو پشتیبانی می‌شود.",
                "This post contains only images, no video. "
                "Only video downloads are supported."
            )

    @staticmethod
    def _find_video_file(info: Optional[dict], temp_dir: Path) -> Optional[Path]:
        """Locate the downloaded video file."""
        for requested in (info or {}).get("requested_downloads") or []:
            filepath = requested.get("filepath")
            if filepath:
                candidate = Path(filepath)
                if candidate.is_file() and candidate.suffix.lower() in VIDEO_EXTS:
                    return candidate

        files = [
            p for p in temp_dir.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        ]
        return max(files, key=lambda p: p.stat().st_size) if files else None

    def _try_lower_quality(self, url: str, info: dict, temp_dir: Path) -> Optional[Path]:
        """Download a smaller format when the best one exceeds the size limit."""
        candidates = [
            f for f in (info.get("formats") or [])
            if f.get("ext") == "mp4"
            and f.get("vcodec") not in (None, "none")
            and f.get("filesize") is not None
            and f["filesize"] < self.max_file_bytes
        ]
        candidates.sort(key=lambda f: (f.get("height") or 0, f["filesize"]), reverse=True)

        for fmt in candidates:
            format_id = fmt["format_id"]
            prefix = f"low_{format_id}_"
            logger.info(
                f"Retrying with smaller format {format_id} "
                f"({fmt.get('height')}p, {format_file_size(fmt['filesize'])})"
            )
            try:
                opts = self._build_ydl_opts(url, temp_dir)
                opts["format"] = format_id
                opts["outtmpl"] = str(temp_dir / f"{prefix}%(id)s.%(ext)s")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                logger.warning(f"Lower quality format {format_id} failed: {e}")
                continue

            files = [
                p for p in temp_dir.iterdir()
                if p.is_file() and p.name.startswith(prefix) and p.suffix.lower() in VIDEO_EXTS
            ]
            if files:
                return max(files, key=lambda p: p.stat().st_size)

        return None

    # --- main entry point --------------------------------------------------

    def download(self, url: str) -> DownloadResult:
        """
        Download video from URL. Runs synchronously (meant to run in executor).
        """
        temp_dir = self._new_temp_dir()
        logger.info(f"Starting download for: {url}")

        try:
            opts = self._build_ydl_opts(url, temp_dir)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise DownloadError(
                        "❌ نمی‌توان اطلاعات ویدیو را دریافت کرد. ممکن است لینک معتبر نباشد یا ویدیو حذف شده باشد.",
                        "Could not extract video info. Link may be invalid or video removed."
                    )

                if info.get("is_live"):
                    raise DownloadError(
                        "🔴 پخش زنده (Live) قابل دانلود نیست.",
                        "Live streams are not supported."
                    )

                info = self._pick_single(info)
                self._reject_non_video(info)

                # Reuse the info we just extracted instead of hitting the site a
                # second time - fewer requests means far fewer Instagram rate limits.
                try:
                    downloaded = ydl.process_ie_result(info, download=True)
                except yt_dlp.utils.DownloadError:
                    raise
                except Exception as e:
                    logger.warning(
                        f"process_ie_result failed ({e}); falling back to a full download call"
                    )
                    downloaded = None
                    ydl.download([url])

            video_file = self._find_video_file(downloaded, temp_dir)
            if video_file is None:
                raise DownloadError(
                    "❌ فایل ویدیویی یافت نشد. ممکن است ویدیو در دسترس نباشد.",
                    "No video file found after download. Video may be unavailable."
                )

            # Too big for Telegram -> try a smaller format before failing
            if video_file.stat().st_size > self.max_file_bytes:
                smaller = self._try_lower_quality(url, downloaded or info, temp_dir)
                if smaller is not None:
                    video_file = smaller
            self._check_file_size(video_file)

            meta = downloaded or info
            width = meta.get("width") or info.get("width")
            height = meta.get("height") or info.get("height")
            if not height:
                # Instagram exposes resolution only on individual formats
                dims = [
                    (f.get("height") or 0, f.get("width") or 0)
                    for f in (meta.get("formats") or info.get("formats") or [])
                ]
                best_h, best_w = max(dims, default=(0, 0))
                height, width = best_h or None, best_w or None

            return DownloadResult(
                file_path=video_file,
                title=meta.get("title") or info.get("title") or "video",
                duration=meta.get("duration") or info.get("duration"),
                width=width,
                height=height,
                filesize=video_file.stat().st_size,
                temp_dir=temp_dir,
            )

        except BaseException:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self._temp_dirs.discard(temp_dir)
            raise


async def download_video(url: str, downloader: VideoDownloader) -> DownloadResult:
    """
    Async wrapper for video download. Runs blocking yt-dlp in executor.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, downloader.download, url)
