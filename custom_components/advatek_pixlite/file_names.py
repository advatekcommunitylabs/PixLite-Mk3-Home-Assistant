"""Display names for stored scenes and playlists."""


def display_name(filename: str | None) -> str | None:
    """Hide a recognized final extension without changing the stored filename."""
    if filename is not None and filename.lower().endswith((".scn", ".pl")):
        return filename.rsplit(".", 1)[0]
    return filename
