"""Feasibility: GroupMemBench regrouped into one-person encounters, re-linked without labels.

Data: Hugging Face kimperyang/GroupMemBench @163516af (CC-BY-4.0). Noise messages dropped.
An encounter (block) = all messages of one author in one channel on one day, ordered by first
timestamp; a channel is treated as a scene. Each block is a pooled word TF-IDF vector
("@Team" and "User_N" tokens removed). For every block whose author appeared before, the
nearest EARLIER block is found (no labels used); scoring then asks whether it has the same
author, the same channel, or both. Labels are used only for scoring.

    python -I scripts/diagnose_attribution_groupmem_blocks.py <domain>.json
"""
import json, math, re, sys
from collections import Counter, defaultdict
import numpy as np
d = json.load(open(sys.argv[1]))
msgs = [dict(m, channel=ch) for ch, v in d.items() for m in v if not m.get("is_noise")]
msgs.sort(key=lambda m: m["timestamp"])
authors = sorted({m["author"] for m in msgs})
leak = sum(bool(re.search(r"User_\d+", m["content"])) for m in msgs) / len(msgs)
names = Counter(w for m in msgs for w in re.findall(r"@\w+", m["content"]))
# encounter = author x channel x day
blocks = defaultdict(list)
for m in msgs:
    blocks[(m["author"], m["channel"], m["timestamp"][:10])].append(m)
order = sorted(blocks, key=lambda k: blocks[k][0]["timestamp"])
sizes = [len(blocks[k]) for k in order]
# TF-IDF pooled block vectors (word level)
texts = [" ".join(x["content"] for x in blocks[k]) for k in order]
toks = [Counter(re.findall(r"[a-z0-9']+", re.sub(r"@\w+|user_\d+", " ", t.lower()))) for t in texts]
df = Counter(w for c in toks for w in c); N = len(toks)
vocab = {w: i for i, w in enumerate(w for w, c in df.items() if c >= 2)}
X = np.zeros((N, len(vocab)), dtype=np.float32)
for r, c in enumerate(toks):
    for w, n in c.items():
        if w in vocab: X[r, vocab[w]] = (1 + math.log(n)) * math.log((N + 1) / (df[w] + 1))
X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)
S = X @ X.T
same_a = same_c = same_ac = tot = 0
seen = set()
for i, k in enumerate(order):
    if i < 50 or k[0] not in {o[0] for o in order[:i]}: continue
    j = int(np.argmax(S[i, :i])); kj = order[j]
    tot += 1; same_a += kj[0] == k[0]; same_c += kj[1] == k[1]; same_ac += kj[:2] == k[:2]
chans = len({m["channel"] for m in msgs})
per_author_channels = np.mean([len({m["channel"] for m in msgs if m["author"] == a}) for a in authors])
print(json.dumps({"file": sys.argv[1].split("/")[-1], "messages": len(msgs), "authors": len(authors), "channels": chans,
    "channels_per_author": round(float(per_author_channels), 2), "blocks": N,
    "msgs_per_block_median": float(np.median(sizes)), "msgs_with_UserN_mention": round(leak, 4),
    "top_at_mentions": names.most_common(5),
    "relink_nearest_prev_block": {"same_author": round(same_a / tot, 4), "same_channel": round(same_c / tot, 4),
                                  "same_author_and_channel": round(same_ac / tot, 4), "n": tot,
                                  "chance_author": round(1 / len(authors), 4)}}))
