"""wlmem: benchmark runner for agent long-term memory experiments.

Data flow (one benchmark case at a time):

    Benchmark.cases() -> Case(sessions, queries, gold)
        sessions are ingested in chronological order into a fresh MemoryAdapter
        before each query, only the sessions visible at that query's time are ingested
    MemoryAdapter.retrieve(query) -> MemoryContext
    Benchmark.render(query, context) -> chat messages (official answer prompt)
    ChatBackend.chat(messages) -> answer, logged with costs
    Benchmark.evaluate(answers) -> official metric code, run with a configured judge

Gold labels (``Case.gold``) never reach a MemoryAdapter.
"""

__version__ = "0.1.0"
