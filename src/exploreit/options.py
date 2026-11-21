"""Choices offered by the crawler and the ranking, with no heavy imports.

The application builds its forms from these before the libraries that do the work
(HTTP, HTML parsing, numpy) have loaded, so the window can appear at once.
"""

from enum import StrEnum

from exploreit import __version__

USER_AGENT = f"ExploreIT/{__version__}"


class LinkMode(StrEnum):
    """Which kinds of links the crawler follows."""

    HYPERLINKS = "hyperlinks"
    IMAGES = "images"
    ALL = "all"


class ContentField(StrEnum):
    """A column that can be saved for every page."""

    URL = "url"
    TITLE = "title"
    DESCRIPTION = "description"
    KEYWORDS = "keywords"
    BODY = "body"


class Normalization(StrEnum):
    """How prestige is rescaled after every step."""

    SUM = "sum"
    MAX = "max"
    NONE = "none"


class Dangling(StrEnum):
    """What happens to the prestige of a page without outgoing links."""

    LOST = "lost"
    SPREAD = "spread"
