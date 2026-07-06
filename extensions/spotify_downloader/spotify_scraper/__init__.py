from SpotipyFree import Spotify as _Spotify
from SpotipyFree import validateSpotifyCookies


class SpotifyClient:
    def __init__(self, cookie_file=None):
        self._sp = _Spotify()
        if cookie_file:
            validateSpotifyCookies(cookie_file)

    def get_playlist_info(self, url):
        import re
        m = re.search(r'playlist/([a-zA-Z0-9]+)', url)
        pid = m.group(1) if m else url.split('/')[-1].split('?')[0]
        info = self._sp.playlist(pid)
        items = self._sp.playlist_items(pid, limit=50)
        tracks = []
        page = items
        while page:
            for item in page.get('items', []):
                track = item.get('track')
                if track:
                    tracks.append({
                        "track": {
                            "name": track.get("name", ""),
                            "artists": [{"name": a.get("name", "")} for a in (track.get("artists") or [])],
                            "duration_ms": track.get("duration_ms") or 0,
                            "album": {
                                "name": (track.get("album") or {}).get("name", ""),
                                "release_date": (track.get("album") or {}).get("release_date", ""),
                            },
                        }
                    })
            if page.get('next'):
                offset = page.get('offset', 0) + len(page.get('items', []))
                page = self._sp.playlist_items(pid, limit=50, offset=offset)
            else:
                break
        return {
            "name": info.get("name", "Unknown"),
            "tracks": tracks,
        }

    def get_track_info(self, url):
        import re
        m = re.search(r'track/([a-zA-Z0-9]+)', url)
        tid = m.group(1) if m else url.split('/')[-1].split('?')[0]
        track = self._sp.track(tid)
        return {
            "name": track.get("name", ""),
            "artists": [{"name": a.get("name", "")} for a in (track.get("artists") or [])],
            "duration_ms": track.get("duration_ms") or 0,
            "track_number": track.get("track_number"),
            "disc_number": track.get("disc_number"),
            "popularity": track.get("popularity"),
        }

    def download_cover(self, url):
        import re, os, requests
        m = re.search(r'track/([a-zA-Z0-9]+)', url)
        tid = m.group(1) if m else url.split('/')[-1].split('?')[0]
        track = self._sp.track(tid)
        images = track.get("album", {}).get("images", [])
        if images:
            img_url = images[0]["url"]
            r = requests.get(img_url, timeout=10)
            ext = img_url.split('.')[-1].split('?')[0] or 'jpg'
            path = f"{tid}_cover.{ext}"
            with open(path, 'wb') as f:
                f.write(r.content)
            return os.path.abspath(path)
        return None

    def close(self):
        pass
