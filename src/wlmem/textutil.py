"""Token estimates and lexical retrieval helpers."""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None


@lru_cache(maxsize=1)
def _encoder():
    return tiktoken.get_encoding("cl100k_base") if tiktoken else None


def estimate_tokens(text: str) -> int:
    """cl100k_base token count, used only for context budgeting.

    The local model's tokenizer differs, so budgets are estimates; the true prompt size is
    the ``prompt_tokens`` reported by the backend and is logged for every call.
    """
    enc = _encoder()
    if enc is None:
        return len(text) // 4
    return len(enc.encode(text, disallowed_special=()))


_WORD = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class BM25:
    """Okapi BM25 (k1=1.5, b=0.75) over a growing list of documents."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: list[Counter] = []
        self.lens: list[int] = []
        self.df: Counter = Counter()

    def add(self, text: str) -> None:
        toks = tokenize(text)
        c = Counter(toks)
        self.docs.append(c)
        self.lens.append(len(toks))
        self.df.update(c.keys())

    def scores(self, query: str) -> list[float]:
        n = len(self.docs)
        if n == 0:
            return []
        avg = sum(self.lens) / n or 1.0
        q = tokenize(query)
        out = []
        for doc, dl in zip(self.docs, self.lens):
            s = 0.0
            for t in q:
                f = doc.get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / avg))
            out.append(s)
        return out
