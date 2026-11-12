from .base import Benchmark
from .longmemeval import LongMemEvalBenchmark
from .memora import MemoraBenchmark
from .memora_mixed import MemoraMixedBenchmark
from .stale import StaleBenchmark

BENCHMARKS = {
    "stale": StaleBenchmark,
    "longmemeval": LongMemEvalBenchmark,
    "memora": MemoraBenchmark,
    "memora_mixed": MemoraMixedBenchmark,  # derived protocol, not an official benchmark
}


def make_benchmark(name: str, params: dict) -> Benchmark:
    if name not in BENCHMARKS:
        raise ValueError(f"unknown benchmark {name!r}; available: {sorted(BENCHMARKS)}")
    return BENCHMARKS[name](**params)


__all__ = ["BENCHMARKS", "Benchmark", "make_benchmark"]
