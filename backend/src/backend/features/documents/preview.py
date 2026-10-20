"""Only verified raster images and plain text may render on the application origin."""


def preview_type(content: bytes, declared_type: str) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if declared_type.split(";", 1)[0].strip().lower() == "text/plain":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if b"\x00" not in content:
            return "text/plain"
    return None
