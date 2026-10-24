"""Abuse protection: per-client rate limiting, upload checks, browser security headers."""
import io
import time
import zipfile
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

# ---------- rate limiting ----------


class RateLimiter:
    """Sliding-window limit per key (client IP).

    In memory: correct for a single server process, which is how this app runs. With several workers or
    instances the counts would need a shared store (e.g. Redis).
    """

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> int:
        """Record a hit. Returns 0 if allowed, otherwise seconds until the next hit is allowed."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return int(hits[0] + self.window_s - now) + 1
            hits.append(now)
            return 0


def client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy and (xff := request.headers.get("x-forwarded-for")):
        # Our proxy appends the real client address last; anything before it is client-controlled.
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


# ---------- uploads ----------
_MAGIC = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}
MAX_DOCX_UNPACKED = 30 * 1024 * 1024  # a 5 MB .docx is a zip; refuse "zip bombs" that unpack to gigabytes
MAX_DOCX_ENTRIES = 2000


def check_upload(filename: str, data: bytes) -> str | None:
    """Return a user-facing error message, or None if the file looks like what its extension says."""
    ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in (".pdf", ".docx", ".txt"):
        return "Yalnız .pdf, .docx və .txt faylları qəbul olunur."
    if ext in _MAGIC and not data.startswith(_MAGIC[ext]):
        return f"Fayl {ext} formatında deyil (məzmunu uzantısına uyğun gəlmir)."
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = z.infolist()
        except zipfile.BadZipFile:
            return "DOCX faylı zədələnib."
        if len(infos) > MAX_DOCX_ENTRIES or sum(i.file_size for i in infos) > MAX_DOCX_UNPACKED:
            return "DOCX faylı həddən artıq böyükdür."
    if ext == ".txt" and b"\x00" in data[:4096]:
        return "Mətn faylı deyil (binary məzmun)."
    return None


# ---------- response headers ----------
CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "  # inline style="" attributes in the UI
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",  # analysis links are secrets: never leak them to other sites
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Frame-Options": "DENY",
}
