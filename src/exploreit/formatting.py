"""Small display helpers with no heavy imports, shared by the command line and the window."""

# Crawl depth 0..5+, from dark to light blue: the HTML graph and the window use the same.
LEVEL_COLOURS = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"]


def format_duration(seconds: float) -> str:
    """Format seconds as "m:ss", e.g. 75.4 -> "1:15"."""
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}:{rest:02d}"
