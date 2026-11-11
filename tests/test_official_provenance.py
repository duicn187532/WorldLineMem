"""The adapters must reproduce the official prompts and metrics exactly."""
import json

from conftest import needs_lme, needs_memora, needs_stale
from wlmem.benchmarks import make_benchmark
from wlmem.benchmarks import longmemeval as L
from wlmem.benchmarks.base import load_official, repo_dir
from wlmem.types import MemoryContext


@needs_lme
def test_longmemeval_templates_are_verbatim_copies():
    src = (repo_dir("longmemeval") / "src/generation/run_generation.py").read_text(encoding="utf-8")
    for s in (L.ANSWER_TEMPLATE, L.ANSWER_TEMPLATE_COT, L.SESSION_TEMPLATE, L.NL_TURN_TEMPLATE):
        assert repr(s)[1:-1] in src or s in src, s[:60]
    assert "gen_length = 500 if not args.cot else 800" in src


@needs_lme
def test_longmemeval_loader_strips_gold_and_neutralises_ids():
    b = make_benchmark("longmemeval", {"variant": "oracle", "limit": 50})
    for case in b.cases():
        for s in case.sessions:
            assert s.session_id.startswith("s") and "answer" not in s.session_id
        prompt = b.render(case, case.queries[0], MemoryContext(sessions=case.sessions))[0]["content"]
        assert "has_answer" not in prompt
        assert case.gold["answer"] is not None


@needs_lme
def test_longmemeval_full_history_prompt_matches_official_format():
    b = make_benchmark("longmemeval", {"variant": "oracle", "case_ids": ["gpt4_2655b836"]})
    case = next(b.cases())
    raw = next(r for r in b._records() if r["question_id"] == "gpt4_2655b836")
    items = sorted(zip(raw["haystack_dates"], raw["haystack_sessions"]), key=lambda x: L.parse_date(x[0]))
    hist = "".join(L.SESSION_TEMPLATE.format(i + 1, d, "\n" + json.dumps([{"role": t["role"], "content": t["content"]} for t in s]))
                   for i, (d, s) in enumerate(items))
    expected = L.ANSWER_TEMPLATE.format(hist, raw["question_date"], raw["question"])
    assert b.render(case, case.queries[0], MemoryContext(sessions=case.sessions))[0]["content"] == expected


@needs_stale
def test_stale_prompt_is_official_build_prompts():
    b = make_benchmark("stale", {"limit": 1})
    case = next(b.cases())
    off = load_official("stale", "STALE/Evaluation/run_target_model.py", extra_paths=["STALE"])
    raw = b._records()[0]
    hist = off.format_haystack(raw["haystack_session"], raw["timestamps"])
    for q in case.queries:
        msgs = b.render(case, q, MemoryContext(sessions=case.sessions))
        sys_p, user_p = off.build_prompts(hist, raw["probing_queries"][f"{q.meta['dim']}_query"], f"{q.meta['dim']}_query")
        assert msgs == [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}]


@needs_memora
def test_memora_loader_hides_annotations_and_prompt_matches_official():
    # drop_user_turns reproduces the official Track 1 prompt, which prints no user turn
    b = make_benchmark("memora", {"periods": ["weekly"], "personas": ["academic_researcher"], "drop_user_turns": True})
    case = next(b.cases())
    assert len(case.queries) == 15
    q = case.queries[0]
    msgs = b.render(case, q, MemoryContext(sessions=case.sessions))
    text = msgs[0]["content"] + msgs[1]["content"]
    for leak in ("share_memory", "memory_introduction", "memory_update", "operation_details"):
        assert leak not in text
    # official path: ConversationLoader + PromptBuilder over the same directory
    off = load_official("memora", "evals/model_eval/model_based_evaluator.py")
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        convs = off.ConversationLoader(repo_dir("memora") / "data/weekly/academic_researcher").load_all_conversations()
        pb = off.PromptBuilder(model_name=None)
        ctx, _ = pb.build_conversation_context(convs)
        sys_p, user_p = pb.build_question_prompt(ctx, q.text, None)
    assert msgs == [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}]


@needs_memora
def test_memora_keeps_user_turns_for_memory_and_default_prompt():
    b = make_benchmark("memora", {"periods": ["weekly"], "personas": ["academic_researcher"]})
    case = next(b.cases())
    roles = [t.role for s in case.sessions for t in s.turns]
    assert roles.count("user") == 1220 and roles.count("assistant") == 1296
    text = b.render(case, case.queries[0], MemoryContext(sessions=case.sessions))[1]["content"]
    # +1: the official question prompt itself contains one "User:" line
    assert text.count("\nUser: ") == 1220 + 1 and text.count("\nAssistant: ") == 1296
    dropped = make_benchmark("memora", {"periods": ["weekly"], "personas": ["academic_researcher"], "drop_user_turns": True})
    text = dropped.render(case, case.queries[0], MemoryContext(sessions=case.sessions))[1]["content"]
    assert text.count("\nUser: ") == 1


@needs_memora
def test_memora_fama_is_official():
    off = load_official("memora", "evals/model_eval/model_based_evaluator.py")
    assert off.fama_score(3, 4, 1, 2) == max(0.0, 0.75 - (2 / 6) * 0.5)
