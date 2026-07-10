import json
import logging
import os
import re
import shutil
import subprocess as _subprocess
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

# ── Force no console windows on every subprocess (yt-dlp spawns ffmpeg without CREATE_NO_WINDOW) ──
if sys.platform.startswith('win'):
    import ctypes
    _CREATE_NO_WINDOW = 0x08000000
    _SW_HIDE = 0
    _STARTF_USESHOWWINDOW = 0x00000001
    _si = _subprocess.STARTUPINFO()
    _si.dwFlags |= _STARTF_USESHOWWINDOW
    _si.wShowWindow = _SW_HIDE
    _orig_init = _subprocess.Popen.__init__
    def _patched_init(self, *args, **kwargs):
        old = kwargs.get('creationflags', 0)
        kwargs['creationflags'] = old | _CREATE_NO_WINDOW
        if kwargs.get('startupinfo') is None:
            kwargs['startupinfo'] = _si
        return _orig_init(self, *args, **kwargs)
    _subprocess.Popen.__init__ = _patched_init
subprocess = _subprocess

# Ensure the local spotify_scraper package is findable
_ext_dir = Path(__file__).parent
if str(_ext_dir) not in sys.path:
    sys.path.insert(0, str(_ext_dir))

logger = logging.getLogger("spotify_downloader")

BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "Downloads_playlists"
CONFIG_PATH = BASE_DIR / "config.json"
MAX_WORKERS = 6

_state = {
    "status": "idle",
    "progress": 0,
    "total": 0,
    "current": "",
    "playlist_name": "",
    "zip_path": "",
    "error": "",
    "missing": [],
}
_state_lock = threading.Lock()


def _set_state(**kw):
    with _state_lock:
        _state.update(kw)


def _get_state():
    with _state_lock:
        return dict(_state)


def _check_ytdlp():
    try:
        import yt_dlp
        return True
    except ImportError:
        return False


def _check_ffmpeg():
    try:
        return subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0
    except Exception:
        return False

_ffmpeg_cache = None

def _ensure_ffmpeg():
    global _ffmpeg_cache
    if _ffmpeg_cache is None:
        _ffmpeg_cache = _check_ffmpeg()
    return _ffmpeg_cache


def _clean_name(text):
    return text.translate(str.maketrans('\\/.:*?"<>|', "__________")).strip()


class Extension:
    def __init__(self, config):
        self.config = config
        self._ffmpeg_ok = None
        DOWNLOADS_DIR.mkdir(exist_ok=True)

    def _load_config(self):
        default = {"quality": "320", "format": "mp3", "download_path": str(DOWNLOADS_DIR)}
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return {**default, **json.load(f)}
        except Exception:
            return default

    def get_config(self):
        return {"value": self._load_config()}

    def save_config(self, data):
        cfg = self._load_config()
        for k in ("quality", "format", "download_path"):
            if k in data:
                cfg[k] = data[k]
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return {"value": True}

    def get_status(self):
        return {"value": _get_state()}

    def start_download(self, data):
        if not _check_ytdlp():
            return {"error": "yt-dlp not installed. Run: pip install yt-dlp"}
        url = (data.get("url") or "").strip()
        if not url:
            return {"error": "Empty URL"}
        state = _get_state()
        if state["status"] == "downloading":
            return {"error": "A download is already in progress"}
        thread = threading.Thread(target=self._run, args=(url,), daemon=True)
        thread.start()
        return {"value": {"status": "started"}}

    def browse_folder(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(title="Select download location")
            root.destroy()
            if folder:
                return {"value": folder}
            return {"value": ""}
        except Exception as e:
            logger.error(f"Browse folder error: {e}")
            return {"error": str(e)}

    def open_folder(self, data):
        path = (data.get("path") or "").strip()
        if path and os.path.isdir(path):
            os.startfile(path)
            return {"value": True}
        return {"error": "Invalid path"}

    def _run(self, url):
        _set_state(status="downloading", progress=0, total=0, current="",
                   playlist_name="", zip_path="", error="", missing=[])
        try:
            from spotify_scraper import SpotifyClient
            sp = SpotifyClient()
            playlist = sp.get_playlist_info(url)
            name = _clean_name(playlist.get("name", "playlist"))
            raw_tracks = playlist.get("tracks", [])
            tracks = []
            seen = set()
            for item in raw_tracks:
                t = item.get("track")
                if not t:
                    continue
                tname = t.get("name")
                artists = [a.get("name") for a in (t.get("artists") or []) if a.get("name")]
                if not tname or not artists:
                    continue
                key = (tname.strip().lower(), tuple(a.strip().lower() for a in artists))
                if key in seen:
                    continue
                seen.add(key)
                album_data = t.get("album") or {}
                tracks.append({
                    "name": tname,
                    "artists": [{"name": a} for a in artists],
                    "duration_ms": t.get("duration_ms") or 0,
                    "album": album_data.get("name", ""),
                })
            sp.close()
            _set_state(playlist_name=name, total=len(tracks))
            if not tracks:
                _set_state(status="error", error="No tracks found")
                return
            cfg = self._load_config()
            base = Path(cfg.get("download_path", str(DOWNLOADS_DIR)))
            folder = base / name
            folder.mkdir(parents=True, exist_ok=True)
            failed = self._download_tracks(tracks, folder)
            zip_path = base / f"{name}.zip"
            self._zip_folder(folder, zip_path)
            _set_state(status="completed", progress=len(tracks), zip_path=str(zip_path), missing=failed)
        except Exception as e:
            logger.exception("Error en descarga")
            _set_state(status="error", error=str(e))

    # --- YouTube search (yt-dlp) ---
    @staticmethod
    def _entry_url(entry):
        return (entry.get("webpage_url") or entry.get("url")
                or (f"https://www.youtube.com/watch?v={entry['id']}" if entry.get("id") else None))

    @staticmethod
    def _tokenize(text):
        return {w for w in re.split(r"[\W_]+", text.lower()) if len(w) > 1 and not w.isdigit()}

    @staticmethod
    def _artist_in_uploader(artist_lower, uploader_lower):
        """Check if the artist name appears meaningfully in the uploader/channel name."""
        artist_lower = artist_lower.strip().replace(",", " & ").replace(";", " & ")
        parts = re.split(r"\s*[&,/]+\s*", artist_lower)
        for p in parts:
            p = p.strip()
            if len(p) <= 2:
                continue
            if p in uploader_lower:
                return True
        return False

    def _score_entry(self, entry, track, artist, duration_seconds, album=""):
        title = str(entry.get("title") or "").lower()
        uploader = str(entry.get("uploader") or entry.get("channel") or "").lower()
        dur = entry.get("duration") or 0

        # Tokenize
        title_tokens = self._tokenize(title)
        track_tokens = self._tokenize(track)
        artist_tokens = self._tokenize(artist)

        # --- Artist match (critical) ---
        artist_in_title = sum(1 for t in artist_tokens if t in title_tokens)
        artist_in_uploader = self._artist_in_uploader(artist.lower(), uploader)

        if not artist_in_uploader and artist_in_title == 0:
            return -500  # Wrong artist, reject

        score = 0

        # Artist scoring
        if artist_in_uploader:
            score += 80
        score += artist_in_title * 30

        # --- Title match ---
        title_match_count = sum(1 for t in track_tokens if t in title_tokens)
        title_pct = title_match_count / max(len(track_tokens), 1)
        score += title_match_count * 25
        if title_pct >= 0.8:
            score += 60
        elif title_pct >= 0.5:
            score += 25

        # Exact title in title (ignoring parenthesized suffixes)
        title_clean = re.sub(r"\s*\([^)]*\)\s*", "", title).strip()
        track_lower = track.lower()
        if track_lower in title_clean:
            score += 100

        # --- Duration match ---
        if duration_seconds and dur:
            diff = abs(dur - duration_seconds)
            if diff <= 1:
                score += 100
            elif diff <= 3:
                score += 70
            elif diff <= 6:
                score += 40
            elif diff <= 10:
                score += 20
            elif diff <= 20:
                score += 5
            else:
                score -= diff * 5

        # --- Uploader/channel bonus ---
        if " - topic" in uploader:
            score += 50
        if "official audio" in title or "official audio" in uploader:
            score += 35
        if "lyrics" in title or "lyric video" in title:
            score += 20
        if "official music video" in title or "official video" in title:
            score += 15
        if "vevo" in uploader:
            score += 30

        # --- Album match ---
        if album:
            album_tokens = self._tokenize(album)
            album_match = sum(1 for t in album_tokens if t in title_tokens)
            score += album_match * 20

        # --- Penalties ---
        forbidden = ["cover", "tribute", "karaoke", "instrumental", "remix",
                     "sped up", "slowed", "nightcore", "8d", "reverb", "live session"]
        for w in forbidden:
            if w in title and w not in track_lower:
                score -= 120

        # --- Channel mismatch penalty ---
        if not artist_in_uploader and artist_in_title <= 1:
            score -= 200

        return score

    def _find_youtube_url(self, track, artist, duration_seconds, album=""):
        from yt_dlp import YoutubeDL
        opts = {
            "quiet": 1, "no_warnings": 1, "extract_flat": "in_playlist",
            "socket_timeout": 20, "retries": 2,
        }

        # Single broad search in priority order
        queries = [
            f"{artist} - {track}",
            f"{artist} {track}",
        ]
        all_entries = []
        seen_urls = set()
        for q in queries:
            try:
                with YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(f"ytsearch10:{q}", download=False)
                for e in (result.get("entries") or []):
                    url = self._entry_url(e)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_entries.append(e)
            except Exception:
                continue

        if not all_entries:
            return None

        best = max(all_entries, key=lambda e: self._score_entry(e, track, artist, duration_seconds, album))
        best_score = self._score_entry(best, track, artist, duration_seconds, album)

        if best_score < -200:
            logger.warning(f"Low confidence ({best_score}) for {artist} - {track}: {best.get('title')}")
            return None

        return self._entry_url(best)

    def _download_file(self, youtube_url, folder, filename):
        from yt_dlp import YoutubeDL
        temp_name = f"tmp_{hash(youtube_url) % 10000}"
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(folder / f"{temp_name}.%(ext)s"),
            "ignoreerrors": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail"},
            ],
            "writethumbnail": True,
            "quiet": 1,
            "no_warnings": 1,
            "socket_timeout": 20,
            "retries": 1,
        }
        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([youtube_url])
            files = list(folder.glob(f"{temp_name}*.mp3"))
            if files:
                final = folder / f"{filename}.mp3"
                time.sleep(0.5)
                for _ in range(2):
                    try:
                        files[0].rename(final)
                        return final
                    except OSError:
                        time.sleep(1)
        except Exception:
            pass
        return None

    def _normalize_audio(self, path):
        if not _ensure_ffmpeg():
            return True
        if not path.exists():
            return False
        try:
            tmp = path.with_name(f"norm_{path.name}")
            cmd = ["ffmpeg", "-loglevel", "quiet", "-y", "-i", str(path),
                   "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "192k", str(tmp)]
            if subprocess.run(cmd, capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0 and tmp.exists():
                time.sleep(1)
                for _ in range(3):
                    try:
                        path.unlink()
                        tmp.rename(path)
                        return True
                    except OSError:
                        time.sleep(1)
                if tmp.exists():
                    tmp.unlink()
            return False
        except Exception:
            return False

    @staticmethod
    def _label(track):
        artists = ", ".join(a["name"] for a in track.get("artists", []))
        return f"{track.get('name', '?')} - {artists}".strip(" -")

    def _download_tracks(self, tracks, folder):
        failed = []
        completed = 0
        total = len(tracks)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            fut_map = {}
            for t in tracks:
                name = _clean_name(t["name"])
                artist = _clean_name(", ".join(a["name"] for a in t["artists"]))
                filename = f"{artist} - {name}"
                dur = t["duration_ms"] // 1000
                album = t.get("album", "")
                fut = pool.submit(self._process_one, name, artist, filename, dur, folder, album)
                fut_map[fut] = (t, name, artist)
            for fut in as_completed(fut_map):
                t, name, artist = fut_map[fut]
                _set_state(current=self._label(t))
                if fut.result():
                    completed += 1
                else:
                    failed.append(t)
                _set_state(progress=completed)
        if failed:
            second = []
            for t in failed:
                _set_state(current=self._label(t))
                time.sleep(0.5)
                name = _clean_name(t["name"])
                artist = _clean_name(", ".join(a["name"] for a in t["artists"]))
                filename = f"{artist} - {name}"
                dur = t["duration_ms"] // 1000
                album = t.get("album", "")
                if not self._process_one(name, artist, filename, dur, folder, album):
                    second.append(t)
            failed = second
        return failed

    def _process_one(self, name, artist, filename, duration_seconds, folder, album=""):
        existing = list(folder.glob("*.mp3"))
        for f in existing:
            if name.lower() in f.stem.lower():
                return True
        url = self._find_youtube_url(name, artist, duration_seconds, album)
        if not url:
            return False
        out = self._download_file(url, folder, filename)
        if out and out.exists():
            self._normalize_audio(out)
            return True
        return False

    @staticmethod
    def _zip_folder(folder, zip_path):
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in folder.glob("*.mp3"):
                    zf.write(f, f.name)
            shutil.rmtree(folder)
        except Exception as e:
            logger.error(f"ZIP creation error: {e}")
