"""Query match: how well the text of a page answers a search query (TF-IDF).

A page scores for every query word it uses: often on the page (term frequency) and
rare on the other pages (inverse document frequency), so "python" counts for more than
a word every page repeats. A query word also matches longer words that start with it,
so "program" finds "programming" and "programowanie".
"""

import math
from collections import Counter
from collections.abc import Mapping, Sequence

import numpy as np

from exploreit.ranking.words import STOPWORDS, WORD


def query_words(query: str) -> list[str]:
    """The meaningful words of a query, in lower case, without repeats."""
    return list(dict.fromkeys(w for w in WORD.findall(query.lower()) if w not in STOPWORDS))


def query_match(pages: Sequence[str], texts: Mapping[str, str], query: str) -> np.ndarray:
    """TF-IDF score of every page for the query; 0 for pages using none of its words."""
    wanted = query_words(query)
    scores = np.zeros(len(pages))
    if not wanted:
        return scores
    counts = [Counter(WORD.findall(texts.get(page, "").lower())) for page in pages]
    lengths = np.array([max(page.total(), 1) for page in counts])
    for word in wanted:
        hits = np.array(
            [sum(n for token, n in page.items() if token.startswith(word)) for page in counts]
        )
        on_pages = int((hits > 0).sum())
        if on_pages:
            scores += hits / lengths * (math.log(len(pages) / on_pages) + 1)
    return scores
