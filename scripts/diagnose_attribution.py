"""Feasibility: without any context signal, how well can a memory tell whose session is whose?

Derived protocol (docs/MIXED_MEMORY_PROTOCOL.md): Memora weekly personas interleaved into one
stream, aliases hidden, context_signal = "none". The gold owner of every session is used ONLY
for scoring. No language model is called; sessions are represented by TF-IDF over their text
(and, with --embed-model, by an Ollama embedding).

Three measurements, all causal (a session is compared only with sessions before it):

  boundary   adjacent sessions: is the owner different? score = 1 - cosine(prev, cur).
             ROC AUC over all adjacent pairs (0.5 = chance). Detecting the start of a new
             encounter is the first step of any method in the "none" condition.
  relink     the first session of every block after the first block of each person: which
             earlier person is it? Predict the owner of its nearest earlier session (cosine),
             restricted to earlier sessions. Accuracy vs chance 1/k. This is the hard part:
             recognising a returning person from content alone.
  oracle_relink  the same, but the whole block is pooled into one vector (as if boundaries
             were known): the gap to `relink` is what boundary knowledge buys.

Also reported: share of sessions whose nearest earlier session belongs to the same owner
(any position), and the same restricted to sessions whose own block has already started
(within-block continuation), to separate "continuing" from "returning".

    python scripts/diagnose_attribution.py --group-sizes 2 5 10 --seeds 0 1 2
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wlmem.benchmarks import make_benchmark  # noqa: E402
from wlmem.textutil import tokenize  # noqa: E402


def session_text(s, user_only: bool) -> str:
    return " ".join(t.content for t in s.turns if not user_only or t.role == "user")


def tfidf(texts: list[str]) -> np.ndarray:
    docs = [Counter(tokenize(t)) for t in texts]
    df = Counter(w for d in docs for w in d)
    n = len(docs)
    vocab = {w: i for i, w in enumerate(w for w, c in df.items() if c >= 2)}
    idf = np.zeros(len(vocab))
    for w, i in vocab.items():
        idf[i] = math.log((n + 1) / (df[w] + 1)) + 1
    m = np.zeros((n, len(vocab)), dtype=np.float32)
    for r, d in enumerate(docs):
        for w, c in d.items():
            if w in vocab:
                m[r, vocab[w]] = (1 + math.log(c)) * idf[vocab[w]]
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(norms, 1e-9)


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks, i = {}, 0
    rank_sum = 0.0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        avg = (i + j + 1) / 2
        rank_sum += avg * sum(1 for x in allv[i:j] if x[1] == 1)
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def analyse(case, vecs: np.ndarray) -> dict:
    owner = [case.gold["owner"][s.session_id] for s in case.sessions]
    block = [case.gold["block"][s.session_id] for s in case.sessions]
    k = len(set(owner))
    sim = vecs @ vecs.T
    # boundary
    pos, neg = [], []
    for i in range(1, len(owner)):
        (pos if owner[i] != owner[i - 1] else neg).append(1 - float(sim[i, i - 1]))
    # nearest earlier session
    nn_same, nn_cont, nn_ret = [], [], []
    for i in range(1, len(owner)):
        j = int(np.argmax(sim[i, :i]))
        hit = owner[j] == owner[i]
        nn_same.append(hit)
        (nn_cont if block[i] == block[i - 1] else nn_ret).append(hit)
    # re-linking returning persons at the first session of a block
    seen_people: set[str] = set()
    relink, oracle = [], []
    starts = [i for i in range(len(block)) if i == 0 or block[i] != block[i - 1]]
    for bi, s in enumerate(starts):
        e = starts[bi + 1] if bi + 1 < len(starts) else len(block)
        if owner[s] in seen_people and s > 0:
            j = int(np.argmax(sim[s, :s]))
            relink.append(owner[j] == owner[s])
            pooled = vecs[s:e].mean(axis=0)
            pooled /= max(np.linalg.norm(pooled), 1e-9)
            # previous blocks pooled as well, then nearest previous block
            best, best_owner = -2.0, None
            for bj, ps in enumerate(starts[:bi]):
                pe = starts[bj + 1]
                pv = vecs[ps:pe].mean(axis=0)
                score = float(pooled @ pv / max(np.linalg.norm(pv), 1e-9))
                if score > best:
                    best, best_owner = score, owner[ps]
            oracle.append(best_owner == owner[s])
        seen_people.add(owner[s])
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
    return {"k": k, "sessions": len(owner), "blocks": len(starts),
            "boundary_auc": round(auc(pos, neg), 4) if pos and neg else None,
            "boundary_rate": round(len(pos) / (len(pos) + len(neg)), 4),
            "nn_same_owner": mean(nn_same), "nn_same_owner_within_block": mean(nn_cont),
            "nn_same_owner_at_block_start": mean(nn_ret),
            "relink_session": mean(relink), "relink_pooled_block": mean(oracle), "relink_n": len(relink),
            "chance": round(1 / k, 4)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group-sizes", type=int, nargs="+", default=[2, 5, 10])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--user-only", action="store_true", help="represent a session by its user turns only")
    ap.add_argument("--embed-model", default=None, help="Ollama embedding model; default TF-IDF only")
    ap.add_argument("--out", default="runs/diagnostics/attribution")
    args = ap.parse_args()
    embedder = None
    if args.embed_model:
        from wlmem.backends import OllamaEmbedder
        embedder = OllamaEmbedder(args.embed_model, cache_path=Path(args.out) / "embeddings.sqlite")
    rows = []
    for k in args.group_sizes:
        for seed in args.seeds:
            bench = make_benchmark("memora_mixed", {"group_size": k, "context_signal": "none", "seed": seed})
            for case in bench.cases():
                texts = [session_text(s, args.user_only) for s in case.sessions]
                reps = {"tfidf": tfidf(texts)}
                if embedder:
                    e = np.asarray(embedder.embed(texts), dtype=np.float32)
                    reps["embed"] = e / np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-9)
                for name, v in reps.items():
                    rows.append({"group_size": k, "seed": seed, "case": case.case_id, "rep": name,
                                 **analyse(case, v)})
                print(json.dumps(rows[-1]), flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = ("user" if args.user_only else "all")
    (out / f"per_case_{tag}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    summary = {}
    for (k, rep) in sorted({(r["group_size"], r["rep"]) for r in rows}):
        sub = [r for r in rows if r["group_size"] == k and r["rep"] == rep]
        summary[f"k{k}/{rep}"] = {m: round(statistics.mean(r[m] for r in sub if r[m] is not None), 4)
                                  for m in ("boundary_auc", "boundary_rate", "nn_same_owner",
                                            "nn_same_owner_within_block", "nn_same_owner_at_block_start",
                                            "relink_session", "relink_pooled_block", "chance")}
        summary[f"k{k}/{rep}"]["cases"] = len(sub)
    (out / f"summary_{tag}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
