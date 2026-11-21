"""Word cascade: rank pages by how many of the site's most repeated words they use.

Round 1 takes the `start` words found on the most pages and gives every page one point
per word it contains. Round 2 takes the next `start - 1` words, round 3 the next
`start - 2`, and so on down to one word. Pages are ordered by round 1; a tie is settled
by round 2, then round 3, like comparing words letter by letter. A page that uses most
of the vocabulary the whole site keeps returning to is central to what the site is about.

Words found on nearly every page come from the page template (menus, footers such as
"Made with love by ..."), not from the content, so they are left out of the rounds.
"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

WORD = re.compile(r"[^\W\d_]{3,}")  # letters only, any alphabet, at least three of them

# Words that appear everywhere and say nothing about a page's topic.
_STOPWORDS = """
    the and for are but not you all any can had her was one our out has have from this that
    with they them their there which will would about into than then what when who your
    more also been were its his him how may other some such only over most very just like
    here these those each where while after before because through under between both being
    does did doing should could off own same too why want get got use used using page pages
    home next previous login log sign menu search back top oraz jest się nie dla przez jako
    tak ale lub czy jak już tylko może które który która tego tym ich jego jej był była
    było są być ten ta te to też jeszcze bardzo gdzie kiedy której którym tej tych przy pod
    nad bez nas wam nam mnie
"""
STOPWORDS = frozenset(re.findall(r"\S+", _STOPWORDS))


@dataclass(frozen=True)
class Cascade:
    rounds: list[list[str]]  # the words of every round, most repeated first
    hits: np.ndarray  # hits[page, round]: how many of that round's words the page uses
    scores: np.ndarray  # one number per page that keeps the round-by-round order


def words(text: str) -> set[str]:
    """Distinct meaningful words of a text, in lower case."""
    return {word for word in WORD.findall(text.lower()) if word not in STOPWORDS}


TEMPLATE_SHARE = 0.8  # a word on more than this share of pages is template text


def word_cascade(
    pages: Sequence[str],
    texts: Mapping[str, str],
    start: int = 10,
    template_share: float = TEMPLATE_SHARE,
) -> Cascade:
    """Score `pages` by the word cascade, starting with `start` words in the first round."""
    if start < 1:
        raise ValueError("the first round needs at least one word")
    vocabulary = [words(texts.get(page, "")) for page in pages]
    # "Repeated" means used on many pages, so one long page cannot fill a round alone.
    on_pages = Counter(word for page_words in vocabulary for word in page_words)
    with_text = sum(bool(page_words) for page_words in vocabulary)
    ranked = sorted(
        (word for word, count in on_pages.items() if count <= template_share * with_text),
        key=lambda word: (-on_pages[word], word),
    )

    rounds: list[list[str]] = []
    position = 0
    for size in range(start, 0, -1):
        chunk = ranked[position : position + size]
        if not chunk:
            break
        rounds.append(chunk)
        position += size

    hits = np.array(
        [[len(page_words & set(chunk)) for chunk in rounds] for page_words in vocabulary],
        dtype=float,
    ).reshape(len(pages), len(rounds))
    # A round can add at most `start` points, so weighting round r by (start + 1)^-r
    # never lets a later round outweigh an earlier one.
    weights = float(start + 1) ** -np.arange(len(rounds))
    return Cascade(rounds, hits, hits @ weights)
