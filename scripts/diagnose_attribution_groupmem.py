"""Feasibility on GroupMemBench: does message content carry enough signal to tell authors apart?

GroupMemBench (arXiv:2605.14498; data kimperyang/GroupMemBench on Hugging Face, CC-BY-4.0,
revision 163516af2d5a3bf20c1c1937c43e71f67752b9ad). All channels of one domain are merged in
time order, noise messages dropped, the first N messages kept. Each message is predicted to
belong to the author whose centroid of EARLIER messages is closest (TF-IDF over words or
character 4-grams). Author labels are used to build the centroids, so this is an upper-side
check ("is there a signal at all?"), not a method for the no-signal condition. IDF is computed
over the N messages (not causal; acceptable for a feasibility check).

    python -I scripts/diagnose_attribution_groupmem.py <domain>.json 6000
"""
from collections import Counter, defaultdict
path, n_msgs = sys.argv[1], int(sys.argv[2])
d = json.load(open(path))
msgs = sorted((m for ch, v in d.items() for m in v if not m.get("is_noise")), key=lambda m: m["timestamp"])[:n_msgs]
authors = sorted({m["author"] for m in msgs}); k = len(authors)
def feats(t, mode):
    t = t.lower()
    if mode == "word": return Counter(re.findall(r"[a-z0-9']+", t))
    t = re.sub(r"\s+", " ", t); return Counter(t[i:i+4] for i in range(len(t)-3))
res = {}
for mode in ("word", "char4"):
    F = [feats(m["content"], mode) for m in msgs]
    df = Counter(w for f in F for w in f); N = len(F)
    idf = {w: math.log((N+1)/(c+1))+1 for w, c in df.items()}
    V = []
    for f in F:
        v = {w: (1+math.log(c))*idf[w] for w, c in f.items()}; n = math.sqrt(sum(x*x for x in v.values())) or 1
        V.append({w: x/n for w, x in v.items()})
    cent = defaultdict(Counter); cnt = Counter(); hit = tot = 0; hit_role = 0
    role_of = {}
    for i, (m, v) in enumerate(zip(msgs, V)):
        if len(cnt) == k and i > 200:
            best, ba = -1, None
            for a in authors:
                c = cent[a]; nc = math.sqrt(sum(x*x for x in c.values())) or 1
                s = sum(x*c.get(w, 0) for w, x in v.items())/nc
                if s > best: best, ba = s, a
            hit += ba == m["author"]; tot += 1
        cent[m["author"]].update(v); cnt[m["author"]] += 1
    res[mode] = round(hit/tot, 4)
print(json.dumps({"file": path.split("/")[-1], "messages": len(msgs), "authors": k, "chance": round(1/k, 4),
                  "centroid_attribution": res, "evaluated": tot,
                  "roles": len({m['role'] for m in msgs}), "tone_values_per_author": round(sum(len({m['tone'] for m in msgs if m['author']==a}) for a in authors)/k,2)}))
