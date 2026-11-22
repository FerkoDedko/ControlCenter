"""Sorts the files on a drive into friendly categories (Games, Photos, Videos…).

How a file is categorised, in order:
  1. Where it lives: Windows/recycle bin -> System, game launcher folders
     (Steam, Epic, Riot…) -> Games, Program Files -> Apps.
  2. Otherwise by file type: .jpg -> Photos, .mp4 -> Videos, and so on.
  3. Anything left is Other.
"""
import heapq
import os
import time

# key, display name, icon
CATEGORIES = (
    ("games", "Games", "🎮"),
    ("photos", "Photos", "🖼"),
    ("videos", "Videos", "🎬"),
    ("music", "Music", "🎵"),
    ("documents", "Documents", "📄"),
    ("archives", "Archives & installers", "🗃"),
    ("apps", "Apps", "📦"),
    ("system", "System", "⚙"),
    ("other", "Other", "📁"),
)

_EXTENSIONS = {
    "photos": "jpg jpeg png gif bmp webp heic heif tif tiff raw cr2 nef arw dng svg ico psd",
    "videos": "mp4 mkv avi mov wmv flv webm m4v mpg mpeg 3gp m2ts",
    "music": "mp3 wav flac aac ogg m4a wma opus aiff",
    "documents": "pdf doc docx xls xlsx ppt pptx txt rtf odt ods odp csv md epub",
    "archives": "zip rar 7z tar gz bz2 xz iso img dmg msi cab",
}
EXTENSION_KIND = {ext: kind for kind, exts in _EXTENSIONS.items()
                  for ext in exts.split()}

GAME_MARKERS = ("/steamapps/", "/epic games/", "/riot games/", "/gog galaxy/games/",
                "/gog games/", "/xboxgames/", "/battle.net/", "/ubisoft game launcher/",
                "/origin games/", "/ea games/", "/games/")
APP_MARKERS = ("/program files/", "/program files (x86)/", "/programdata/",
               "/appdata/local/programs/", "/windowsapps/")
SYSTEM_FILES = {"pagefile.sys", "hiberfil.sys", "swapfile.sys"}

# Windows marks OneDrive "online-only" files with these; they take no real space.
_CLOUD_ONLY = 0x00040000 | 0x00400000


def classify_dir(path):
    """Category forced by a folder's location, or None to decide per file."""
    p = "/" + path.replace("\\", "/").lower().strip("/") + "/"
    if ("/$recycle.bin/" in p or "/system volume information/" in p
            or "/$windows.~bt/" in p):
        return "system"
    if "/program files" not in p and "/users/" not in p and "/windows/" in p:
        return "system"
    if any(marker in p for marker in GAME_MARKERS):
        return "games"
    if any(marker in p for marker in APP_MARKERS):
        return "apps"
    return None


def classify_name(name):
    lowered = name.lower()
    if lowered in SYSTEM_FILES:
        return "system"
    return EXTENSION_KIND.get(os.path.splitext(lowered)[1].lstrip("."), "other")


class StorageScan:
    """Walks a folder tree once. Meant to run on a background thread; the UI
    can read the running totals at any time."""

    TOP = 10

    def __init__(self, root):
        self.root = root
        self.bytes = {key: 0 for key, _n, _i in CATEGORIES}
        self.files = {key: 0 for key, _n, _i in CATEGORIES}
        self._top = {key: [] for key, _n, _i in CATEGORIES}
        self.done = False
        self.cancelled = False
        self.error = None
        self.started = time.monotonic()
        self.elapsed = 0.0

    @property
    def total_bytes(self):
        return sum(self.bytes.values())

    @property
    def total_files(self):
        return sum(self.files.values())

    def cancel(self):
        self.cancelled = True

    def top_files(self, key):
        """Largest files in a category as [(size, path), ...], biggest first."""
        return sorted(self._top[key], reverse=True)

    def run(self):
        try:
            self._walk()
        except Exception as exc:          # never let a thread die silently
            self.error = str(exc)
        self.elapsed = time.monotonic() - self.started
        self.done = True

    def _walk(self):
        stack = [self.root]
        while stack and not self.cancelled:
            current = stack.pop()
            forced = classify_dir(current)
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if self.cancelled:
                            return
                        try:
                            if entry.is_symlink() or getattr(
                                    entry, "is_junction", lambda: False)():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                info = entry.stat(follow_symlinks=False)
                                if getattr(info, "st_file_attributes", 0) & _CLOUD_ONLY:
                                    continue
                                self._add(forced or classify_name(entry.name),
                                          info.st_size, entry.path)
                        except OSError:
                            continue
            except OSError:
                continue

    def _add(self, key, size, path):
        self.bytes[key] += size
        self.files[key] += 1
        heap = self._top[key]
        item = (size, path)
        if len(heap) < self.TOP:
            heapq.heappush(heap, item)
        elif size > heap[0][0]:
            heapq.heapreplace(heap, item)
