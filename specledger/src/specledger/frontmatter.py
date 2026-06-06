import yaml

_DELIM = "---"


def split(text: str) -> tuple[dict, str]:
    if not text.startswith(_DELIM):
        return {}, text
    parts = text.split("\n")
    for i in range(1, len(parts)):
        if parts[i].strip() == _DELIM:
            raw = "\n".join(parts[1:i])
            body = "\n".join(parts[i + 1:])
            meta = yaml.safe_load(raw) or {}
            return meta, body
    return {}, text


def render(meta: dict, body: str) -> str:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{_DELIM}\n{front}\n{_DELIM}\n{body if body.endswith(chr(10)) else body + chr(10)}"
