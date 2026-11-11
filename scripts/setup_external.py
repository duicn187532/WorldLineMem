"""Fetch the pinned official repositories and datasets listed in external.lock.json.

Standard library only, so it runs on a fresh Windows Python before anything else is installed.

    python scripts/setup_external.py                 # required benchmarks (STALE, LongMemEval, Memora)
    python scripts/setup_external.py --with-optional # also LoCoMo and MemoryAgentBench code
    python scripts/setup_external.py --verify-only   # check what is already on disk

Layout (default root: ./external, override with WLMEM_EXTERNAL):
    external/repos/<name>/        git checkout at the pinned commit
    external/data/<name>/<file>   dataset files, sha256-verified

Nothing in the downloaded material is modified. A file whose hash does not match is
reported and left for you to inspect; it is never "fixed" automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "external.lock.json"


def external_root() -> Path:
    return Path(os.environ.get("WLMEM_EXTERNAL", ROOT / "external")).resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree_sha256(data_dir: Path) -> tuple[str, int]:
    """Hash of (relative path, file sha256) over every *.json under data_dir."""
    h = hashlib.sha256()
    files = sorted(p for p in data_dir.rglob("*.json") if "eval_results" not in p.parts)
    for p in files:
        h.update(p.relative_to(data_dir).as_posix().encode())
        h.update(bytes.fromhex(sha256_file(p)))
    return h.hexdigest(), len(files)


def git(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def fetch_repo(name: str, spec: dict, dest: Path, verify_only: bool) -> bool:
    if (dest / ".git").exists():
        head = git("rev-parse", "HEAD", cwd=dest)
        if head == spec["commit"]:
            dirty = git("status", "--porcelain", cwd=dest)
            if dirty:
                print(f"[WARN] {name}: checkout has local modifications:\n{dirty}")
                return False
            print(f"[OK]   {name}: {head}")
            return True
        if verify_only:
            print(f"[FAIL] {name}: HEAD {head} != pinned {spec['commit']}")
            return False
        git("fetch", "--depth", "1", "origin", spec["commit"], cwd=dest)
        git("checkout", "--detach", spec["commit"], cwd=dest)
    else:
        if verify_only:
            print(f"[MISS] {name}: {dest} not found")
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"[GET]  {name}: cloning {spec['url']}")
        git("init", "-q", str(dest))
        git("remote", "add", "origin", spec["url"], cwd=dest)
        git("fetch", "--depth", "1", "origin", spec["commit"], cwd=dest)
        git("checkout", "-q", "--detach", "FETCH_HEAD", cwd=dest)
    head = git("rev-parse", "HEAD", cwd=dest)
    ok = head == spec["commit"]
    print(f"[{'OK' if ok else 'FAIL'}]   {name}: {head}")
    if ok and "data_tree_sha256" in spec:
        digest, count = tree_sha256(dest / "data")
        ok = digest == spec["data_tree_sha256"] and count == spec["data_file_count"]
        print(f"[{'OK' if ok else 'FAIL'}]   {name}/data tree: {count} files, sha256 {digest}")
    return ok


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "wlmem-setup"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            if total:
                print(f"\r       {dest.name}: {done / total:6.1%}", end="", flush=True)
    print()
    tmp.replace(dest)


def fetch_dataset(name: str, spec: dict, dest_dir: Path, verify_only: bool) -> bool:
    ok_all = True
    for fname, f in spec["files"].items():
        dest = dest_dir / fname
        if not dest.exists():
            if verify_only:
                print(f"[MISS] {name}/{fname}")
                ok_all = False
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            print(f"[GET]  {name}/{fname} ({f['bytes'] / 1e6:.0f} MB)")
            download(f["url"], dest)
        digest = sha256_file(dest)
        ok = digest == f["sha256"]
        ok_all &= ok
        print(f"[{'OK' if ok else 'FAIL'}]   {name}/{fname} sha256 {digest}")
    return ok_all


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--with-optional", action="store_true", help="also fetch optional (P1) repositories")
    ap.add_argument("--verify-only", action="store_true", help="do not download, only check")
    ap.add_argument("--only", nargs="*", help="limit to these names, e.g. --only stale longmemeval")
    args = ap.parse_args()

    if shutil.which("git") is None:
        print("git is required (https://git-scm.com/download/win).")
        return 2

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    root = external_root()
    print(f"external root: {root}")
    ok = True
    for name, spec in lock["repos"].items():
        if args.only and name not in args.only:
            continue
        if spec.get("optional") and not args.with_optional:
            continue
        ok &= fetch_repo(name, spec, root / "repos" / name, args.verify_only)
    for name, spec in lock["datasets"].items():
        if args.only and name not in args.only:
            continue
        ok &= fetch_dataset(name, spec, root / "data" / name, args.verify_only)
    print("ALL OK" if ok else "SOME CHECKS FAILED (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
