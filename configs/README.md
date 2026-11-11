# Run configurations

One TOML file = one run (benchmark × memory method × answer model). The run directory is
`runs/<[run].name>/`. Re-running the same file resumes it; editing a file after a run has
started is refused (the config hash is stored in `manifest.json`), so give changed
settings a new `name`.

- `smoke/`: engineering checks with `qwen3:0.6b` and a handful of questions. Their
  numbers mean nothing. They show that loading, ingestion, prompting, the official
  metric code and logging work end to end.
- `local/`: templates for real Local Adaptation runs on the Flow Z13. Check model names
  against `ollama list` (or `env_reports/*.json`) before use.

## Sections

```toml
[run]
name = "unique_run_name"          # output folder under runs/
label = "local_adaptation"        # or "smoke_test"; mock models override it
seed = 42
save_prompts = false              # true writes full prompts to prompts.jsonl (large for STALE)
output_dir = "runs"               # optional
cache_dir = ".cache"              # optional; embedding cache lives here
# answer_overrides = { max_tokens = 512 }   # override benchmark defaults (recorded)

[benchmark]
name = "stale" | "longmemeval" | "memora"
limit = 10                        # first N cases (optional)
case_ids = ["..."]                # explicit cases (optional)
# stale:       types = ["T1", "T2"]
# longmemeval: variant = "oracle" | "s"; history_format = "json" | "nl"; cot = false;
#              question_types = [...]; exclude_future_sessions = false
# memora:      periods = ["weekly", "monthly", "quarterly"]; personas = [...];
#              question_limit = N; pass_question_date = false;
#              drop_user_turns = false (true reproduces the official Track 1 prompt, which
#              prints no user turn; see docs/BENCHMARK_MATRIX.md)
# memora_mixed (DERIVED protocol, docs/MIXED_MEMORY_PROTOCOL.md):
#              period = "weekly"; personas = [...]; group_size = 10;
#              context_signal = "label" | "boundary" | "none"; lead_in_sessions = 1;
#              seed = 0; question_limit = N; prompt = "mixed" | "official"

[memory]
method = "no_memory" | "full_context" | "rag" | <your registered method>
# full_context: max_context_tokens
# rag: granularity = "round" | "session"; retriever = "bm25" | "dense"; top_k;
#      max_context_tokens; query_instruction
# full_context and rag: scope = "global" | "context". "context" keeps only sessions whose
#      context signal equals the question's (hard isolation; needs a benchmark that gives a signal)
# rag: decay = { lambda_base, beta, mu, importance, initial, mode = "multiply" | "dormant",
#      dormant_threshold }. FadeMem decay curve only (eq. 4-6), no reinforcement, no conflict
#      resolution; label results accordingly. See docs/DIAGNOSTICS.md.

[answer_model]                    # the reader that writes the final answer
backend = "ollama"
model = "qwen3:8b"
num_ctx = 32768                   # must cover the longest prompt; overflow is flagged per answer
num_predict = 512
temperature = 0.0
seed = 42
think = false                     # Qwen3-style models: no hidden reasoning output

[memory_model]                    # optional: LLM used inside a memory method (extraction etc.)
[embedding]                       # optional: needed for retriever = "dense"
backend = "ollama"
model = "qwen3-embedding:4b"

[judge]                           # used by `wlmem evaluate`
backend = "ollama"
model = "..."
```

Fixed for every method in a comparison: benchmark settings, answer model and its
options, judge, seed. Only `[memory]` (and `[memory_model]`/`[embedding]` when the method
needs them) may differ. See docs/EXPERIMENT_PROTOCOL.md.
