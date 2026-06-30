import hashlib


def _normalize(body: str) -> str:
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return "\n".join(lines).strip("\n")


def content_hash(body: str) -> str:
    digest = hashlib.sha256(_normalize(body).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
