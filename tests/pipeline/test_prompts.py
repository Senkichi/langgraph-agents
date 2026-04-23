"""Smoke tests on prompt templates — catch accidental deletions or formatting drift."""

from __future__ import annotations

from langgraph_agents.pipeline import prompts


def test_generator_base_is_non_empty():
    assert prompts.GENERATOR_BASE.strip()


def test_critic_personas_are_distinct():
    """The asymmetry is the point — a silent collapse into equal prompts would
    undo the adversarial dynamic the plan is trying to preserve."""
    assert prompts.CRITIC_CHALLENGER != prompts.CRITIC_BUILDER
    assert "challenger" in prompts.CRITIC_CHALLENGER.lower()
    assert "builder" in prompts.CRITIC_BUILDER.lower()


def test_reviser_base_discourages_blind_acceptance():
    assert prompts.REVISER_BASE.strip()
    # Intent check: the reviser must not be told to simply apply every critique.
    text = prompts.REVISER_BASE.lower()
    assert "uncritically" in text or "weak signal" in text


def test_debate_system_prompt_has_required_slots():
    """The system prompt holds role + rules/format only — proposals go in the
    opening user message so Windows CreateProcess arg limits don't bite."""
    assert "{role}" in prompts.DEBATE_SYSTEM_PROMPT
    assert "{proposals_section}" not in prompts.DEBATE_SYSTEM_PROMPT
    assert "STANCE:" in prompts.DEBATE_SYSTEM_PROMPT
    assert "KEY_POINT:" in prompts.DEBATE_SYSTEM_PROMPT


def test_debate_system_prompt_fits_windows_cli_limit():
    """Windows CreateProcess limits a single command-line arg to ~32KB. Leave
    generous headroom — the CLI also carries cwd, model, allowed tools, etc."""
    rendered = prompts.DEBATE_SYSTEM_PROMPT.format(role="Reviewer 1")
    assert len(rendered.encode("utf-8")) < 4_000  # currently ~900 bytes


def test_debate_opening_user_message_has_required_slots():
    assert "{task}" in prompts.DEBATE_OPENING_USER_MESSAGE
    assert "{proposals_section}" in prompts.DEBATE_OPENING_USER_MESSAGE


def test_debate_templates_format_cleanly():
    system = prompts.DEBATE_SYSTEM_PROMPT.format(role="Reviewer 1")
    opening = prompts.DEBATE_OPENING_USER_MESSAGE.format(
        task="the user task",
        proposals_section="## Proposal A\nX\n\n## Proposal B\nY",
    )
    assert "Reviewer 1" in system
    assert "Proposal A" in opening
    assert "the user task" in opening


def test_synthesis_prompt_has_debate_slot():
    assert "{debate_section_or_empty}" in prompts.SYNTHESIS_JUDGE_PROMPT
    rendered = prompts.SYNTHESIS_JUDGE_PROMPT.format(debate_section_or_empty="")
    assert "final response" in rendered.lower()


def test_judge_pairwise_prompt_has_required_slots():
    p = prompts.JUDGE_PAIRWISE_PROMPT
    for slot in ("{task}", "{response_x}", "{response_y}"):
        assert slot in p
    assert "PREFERENCE:" in p
