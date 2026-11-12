import pytest

from wlmem.benchmarks.base import external_root


def _have(*parts: str) -> bool:
    return (external_root().joinpath(*parts)).exists()


needs_stale = pytest.mark.skipif(not (_have("repos", "stale") and _have("data", "stale")), reason="run scripts/setup_external.py")
needs_lme = pytest.mark.skipif(not (_have("repos", "longmemeval") and _have("data", "longmemeval")), reason="run scripts/setup_external.py")
needs_memora = pytest.mark.skipif(not _have("repos", "memora"), reason="run scripts/setup_external.py")
