from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace


FAKE_SECRET = "sk-" + "abcdefghijklmnop"
FAKE_PASSWORD = "sample-password-value"
FAKE_ACCESS_TOKEN = "sample-access-token-value"
FAKE_BEARER = "sample.bearer.token.value"
FAKE_GITHUB_PAT = "github_pat_" + ("a" * 30)
TEST_IP = "192.0.2.20"
PRIVATE_TERM = "SensitiveContact"
WINDOWS_USER_PATH = r"C:\Users\example-user\Documents\notes.txt"


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "distill_claudia.py"
    spec = importlib.util.spec_from_file_location("distill_claudia", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pair() -> dict:
    return {
        "messages": [
            {"role": "system", "content": "system"},
            {
                "role": "user",
                "content": (
                    f"{PRIVATE_TERM} emailed person@example.com from /Users/example-user "
                    f"at {TEST_IP} with {FAKE_SECRET}, password={FAKE_PASSWORD}, "
                    f"access_token={FAKE_ACCESS_TOKEN}, Authorization: Bearer {FAKE_BEARER}, "
                    f"{FAKE_GITHUB_PAT}, and {WINDOWS_USER_PATH}."
                ),
            },
            {
                "role": "assistant",
                "content": "Call 212-555-0100 and answer directly enough for this test.",
            },
        ],
        "domain": "witness",
        "sample_id": "source-sample",
        "_metadata": {},
    }


def test_neutral_or_weakly_styled_session_is_not_claudia() -> None:
    module = _load_module()
    neutral = module.Session(
        session_id="neutral",
        project_path="project",
        source_file="session.jsonl",
        turns=[
            module.Turn("user", "Here is a long neutral project update. " * 40),
            module.Turn("assistant", "Thanks for the update. " * 40),
            module.Turn("user", "Honestly this is another neutral status note. " * 40),
            module.Turn("assistant", "Understood. " * 40),
        ],
    )
    strong = module.Session(
        session_id="strong",
        project_path="project",
        source_file="session.jsonl",
        turns=[
            module.Turn("user", "I need to vent about relationship feelings and trust."),
            module.Turn("assistant", "Go ahead."),
            module.Turn("user", "I feel caught in the same relationship cycle."),
            module.Turn("assistant", "Let's name the cycle."),
        ],
    )

    assert module.score_session(neutral) == 0.0
    assert module.score_session(strong) >= 0.4


def test_event_does_not_match_vent_signal() -> None:
    module = _load_module()
    event_session = module.Session(
        session_id="event-only",
        project_path="project",
        source_file="session.jsonl",
        turns=[
            module.Turn("user", "The event schedule has another event tomorrow."),
            module.Turn("assistant", "The event is on the calendar."),
            module.Turn("user", "Please summarize the event schedule."),
            module.Turn("assistant", "There is one event tomorrow."),
        ],
    )

    assert module.has_signal("event", "vent") is False
    assert module.has_signal("I need to vent.", "vent") is True
    assert module.score_session(event_session) == 0.0


def test_claudia_tooling_and_code_prompts_are_not_witness_sessions() -> None:
    module = _load_module()
    tooling = module.Session(
        session_id="tooling",
        project_path="project",
        source_file="session.jsonl",
        turns=[
            module.Turn(
                "user",
                "Improve the Claudia dataset pipeline and refactor the training data script. " * 20,
            ),
            module.Turn("assistant", "I will inspect the pipeline."),
            module.Turn("user", "Add a benchmark and update the prompt pack."),
            module.Turn("assistant", "I will implement that."),
        ],
    )
    explicit_code = module.Session(
        session_id="explicit-code",
        project_path="project",
        source_file="session.jsonl",
        turns=[
            module.Turn(
                "user",
                "Claudia remote-control: implement this code variant. "
                "def run(): return value; class Runner; add a pytest unit test. " * 12,
            ),
            module.Turn("assistant", "I will refactor the function."),
            module.Turn("user", "Compile and test the implementation."),
            module.Turn("assistant", "The test passes."),
        ],
    )
    genuine_witness = module.Session(
        session_id="witness",
        project_path="project",
        source_file="session.jsonl",
        turns=[
            module.Turn(
                "user",
                "I need to vent: I feel trapped in this relationship while the dataset pipeline fails.",
            ),
            module.Turn("assistant", "The work failure is amplifying the relationship loop."),
            module.Turn("user", "I feel the same cycle again."),
            module.Turn("assistant", "Then the cycle, not the pipeline, is the real subject."),
        ],
    )

    assert module.score_session(tooling) == 0.0
    assert module.score_session(explicit_code) < 0.4
    assert module.score_session(genuine_witness) >= 0.4


def test_category_signals_do_not_match_inside_words() -> None:
    module = _load_module()

    assert (
        module.categorize_pair(
            "I am updating a plain status page.",
            "The update is complete.",
        )
        == "general"
    )
    assert module.categorize_pair("I am dating again.", "That is a change.") == "relationship_dynamics"
    assert module.categorize_pair("This AI model is a mirror.", "Maybe.") == "meta_awareness"


def test_source_discovery_discards_entire_corrupt_sessions(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    logs = tmp_path / "projects"
    project = logs / "example-project"
    project.mkdir(parents=True)
    turns = [
        {
            "type": role,
            "message": {"role": role, "content": text},
        }
        for role, text in (
            ("user", "I need to vent about this relationship."),
            ("assistant", "Start with what actually happened."),
            ("user", "I feel caught in the same relationship cycle."),
            ("assistant", "Then name the cycle instead of the latest trigger."),
        )
    ]

    valid_path = project / "valid.jsonl"
    valid_path.write_text(
        "".join(module.json.dumps(turn) + "\n" for turn in turns),
        encoding="utf-8",
    )
    (project / "invalid-json.jsonl").write_text(
        module.json.dumps(turns[0])
        + "\n{not-json}\n"
        + module.json.dumps(turns[1])
        + "\n",
        encoding="utf-8",
    )
    (project / "wrong-record.jsonl").write_text(
        "[]\n",
        encoding="utf-8",
    )
    (project / "wrong-message.jsonl").write_text(
        module.json.dumps({"type": "user", "message": "not-an-object"}) + "\n",
        encoding="utf-8",
    )
    (project / "wrong-text.jsonl").write_text(
        module.json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": ["not", "text"]}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "CLAUDE_LOGS", logs)

    sessions = module.discover_sessions()

    assert [session.session_id for session in sessions] == ["valid"]
    assert len(sessions[0].turns) == 4
    errors = capsys.readouterr().err
    for filename in (
        "invalid-json.jsonl",
        "wrong-record.jsonl",
        "wrong-message.jsonl",
        "wrong-text.jsonl",
    ):
        assert f"Skipping corrupt Claude session {filename}" in errors


def test_every_advertised_teacher_resolves_and_has_provider() -> None:
    module = _load_module()
    parser = module.build_arg_parser()

    assert set(module.SUPPORTED_EXTERNAL_TEACHERS) == {
        "claude",
        "claude_opus",
        "gemini",
        "gemini_flash",
        "gemini_pro",
    }
    for alias in module.SUPPORTED_EXTERNAL_TEACHERS:
        args = parser.parse_args(
            [
                "distill",
                "--teacher",
                alias,
                "--consent-to-external-processing",
                "--acknowledge-private-terms-reviewed",
                "--limit",
                "1",
            ]
        )
        assert args.teacher == alias
        assert module.resolve_teacher_model(alias)
        assert module.teacher_provider(alias) in {"anthropic", "gemini"}


def test_every_advertised_teacher_reaches_an_implemented_provider(monkeypatch) -> None:
    module = _load_module()
    calls: list[tuple[str, str]] = []

    class FakeGeminiModels:
        def generate_content(self, *, model: str, contents: str) -> SimpleNamespace:
            calls.append(("gemini", model))
            assert contents == "prompt"
            return SimpleNamespace(
                text="gemini response",
                candidates=[SimpleNamespace(finish_reason="STOP")],
            )

    class FakeGeminiClient:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "gemini-key"
            self.models = FakeGeminiModels()

    class FakeAnthropicMessages:
        def create(self, *, model: str, max_tokens: int, messages: list[dict]) -> SimpleNamespace:
            calls.append(("anthropic", model))
            assert max_tokens == 1024
            assert messages == [{"role": "user", "content": "prompt"}]
            return SimpleNamespace(
                content=[SimpleNamespace(text="anthropic response")],
                stop_reason="end_turn",
            )

    class FakeAnthropicClient:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "anthropic-key"
            self.messages = FakeAnthropicMessages()

    monkeypatch.setitem(
        sys.modules,
        "google",
        SimpleNamespace(genai=SimpleNamespace(Client=FakeGeminiClient)),
    )
    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=FakeAnthropicClient),
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    for alias in module.SUPPORTED_EXTERNAL_TEACHERS:
        response = asyncio.run(
            module.call_external_teacher(
                "prompt",
                alias,
                module.resolve_teacher_model(alias),
            )
        )
        assert response.endswith("response")

    assert len(calls) == len(module.SUPPORTED_EXTERNAL_TEACHERS)


def test_provider_text_rejects_blocked_or_non_text_results() -> None:
    module = _load_module()
    for value in (None, "", "   ", object()):
        try:
            module.require_provider_text(value, "test-provider")
        except RuntimeError as error:
            assert "no usable text" in str(error)
        else:
            raise AssertionError(f"provider result was accepted: {value!r}")


def test_refined_text_rejects_scaffolding_placeholders_and_refusals() -> None:
    module = _load_module()
    invalid = (
        module.DISTILL_PROMPT.format(user_msg="private", assistant_msg="answer"),
        "USER: private\nASSISTANT: answer",
        "[REDACTED_TERM] [REDACTED_EMAIL]",
        "I cannot assist with that request.",
        "As an AI, I cannot respond.",
        "Unfortunately, I cannot assist with that.",
        "Apologies, but I can't help with that.",
        "No, I can't help with that.",
        "I'm sorry, but I can't do that.",
        "I must decline this request.",
        "Sorry, I am unable to help with that.",
        "Here is the refined response:\n```text\nanswer\n```",
        "REFINED ASSISTANT RESPONSE: answer",
        "[redacted] [ REDACTED ]",
        "USER : private\nASSISTANT : answer",
    )
    for value in invalid:
        try:
            module.validate_refined_text(value)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"invalid refined text was accepted: {value!r}")

    assert module.validate_refined_text("That read is too certain; test it.") == (
        "That read is too certain; test it."
    )
    valid_boundaries = (
        "I can't help but notice you're repeating the same move.",
        "I cannot help thinking this is about trust.",
        "No, I can't help him make that decision for you.",
        "I can't provide certainty, but that pattern is real.",
        "I must decline to agree with that framing.",
    )
    for value in valid_boundaries:
        assert module.validate_refined_text(value) == value


def test_external_teacher_rejects_truncated_provider_results(monkeypatch) -> None:
    module = _load_module()

    class TruncatedGeminiClient:
        def __init__(self, *, api_key: str) -> None:
            self.models = SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(
                    text="partial response",
                    candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
                )
            )

    class TruncatedAnthropicClient:
        def __init__(self, *, api_key: str) -> None:
            self.messages = SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    content=[
                        SimpleNamespace(text="first partial block"),
                        SimpleNamespace(text="second partial block"),
                    ],
                    stop_reason="max_tokens",
                )
            )

    monkeypatch.setitem(
        sys.modules,
        "google",
        SimpleNamespace(genai=SimpleNamespace(Client=TruncatedGeminiClient)),
    )
    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=TruncatedAnthropicClient),
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    for alias in ("gemini", "claude"):
        try:
            asyncio.run(
                module.call_external_teacher(
                    "prompt",
                    alias,
                    module.resolve_teacher_model(alias),
                )
            )
        except RuntimeError as error:
            assert "did not complete normally" in str(error)
        else:
            raise AssertionError(f"truncated {alias} result was accepted")


def test_distill_pair_resolves_alias_and_redacts_external_prompt(monkeypatch) -> None:
    module = _load_module()
    captured: dict[str, str] = {}

    async def fake_call(prompt: str, teacher: str, model_name: str) -> str:
        captured.update(prompt=prompt, teacher=teacher, model_name=model_name)
        return "refined response"

    monkeypatch.setattr(module, "call_external_teacher", fake_call)
    result = asyncio.run(
        module.distill_pair(
            _pair(),
            "gemini_pro",
            consent_to_external_processing=True,
            private_terms_reviewed=True,
            redact_terms=[PRIVATE_TERM],
        )
    )

    assert result is not None
    assert captured["teacher"] == "gemini_pro"
    assert captured["model_name"] == module.resolve_teacher_model("gemini_pro")
    for private_value in (
        PRIVATE_TERM,
        "person@example.com",
        "/Users/example-user",
        TEST_IP,
        FAKE_SECRET,
        FAKE_PASSWORD,
        FAKE_ACCESS_TOKEN,
        FAKE_BEARER,
        FAKE_GITHUB_PAT,
        WINDOWS_USER_PATH,
        r"Documents\notes.txt",
        "212-555-0100",
    ):
        assert private_value not in captured["prompt"]
    assert "[REDACTED_TERM]" in captured["prompt"]
    assert "[REDACTED_EMAIL]" in captured["prompt"]
    assert "[REDACTED_CREDENTIAL]" in captured["prompt"]
    assert "[REDACTED_TOKEN]" in captured["prompt"]
    assert result["_metadata"]["teacher_alias"] == "gemini_pro"
    assert result["_metadata"]["teacher_model"] == module.resolve_teacher_model("gemini_pro")
    assert result["_metadata"]["external_processing_consent"] is True
    assert result["_metadata"]["private_terms_reviewed"] is True
    assert result["_metadata"]["human_review_recommended"] is True
    assert result["_metadata"]["external_redaction"] == "patterns_plus_caller_terms"
    assert result["_metadata"]["caller_redact_term_count"] == 1
    assert result["_metadata"]["pair_fingerprint"] == module.pair_fingerprint(result)


def test_external_redaction_covers_common_environment_credentials() -> None:
    module = _load_module()
    credentials = {
        "DATABASE_PASSWORD": "database-password-value",
        "AWS_SECRET_ACCESS_KEY": "aws-access-key-value",
        "GITHUB_TOKEN": "github-token-value",
        "OPENAI_API_KEY": "openai-api-key-value",
    }
    source = "\n".join(f"{name}={value}" for name, value in credentials.items())

    redacted = module.redact_for_external(source)

    for name, value in credentials.items():
        assert name not in redacted
        assert value not in redacted
    assert redacted.count("[REDACTED_CREDENTIAL]") == len(credentials)


def test_external_redaction_covers_json_and_cli_credentials() -> None:
    module = _load_module()
    values = (
        "json-password-value",
        "json-token-value",
        "single-quoted-key-value",
        "cli-password-value",
        "cli-token-value",
        "ruby-password-value",
        "private-password-value",
        "basic-auth-value",
        "xoxb-123456789012-secret",
        "glpat-1234567890123456",
        "hf_1234567890123456",
        "2001:db8::1234",
    )
    source = (
        f'{{"password":"{values[0]}","token":"{values[1]}"}}\n'
        f"{{'api_key':'{values[2]}'}}\n"
        f"--password {values[3]}\n"
        f"--access-token={values[4]}\n"
        f"password => {values[5]}\n"
        f"_PRIVATE_PASSWORD={values[6]}\n"
        f"Authorization: Basic {values[7]}\n"
        f"{values[8]}\n{values[9]}\n{values[10]}\n{values[11]}"
    )

    redacted = module.redact_for_external(source)

    for value in values:
        assert value not in redacted
    assert redacted.count("[REDACTED_CREDENTIAL]") >= 7
    assert "[REDACTED_TOKEN]" in redacted
    assert "[REDACTED_SECRET]" in redacted
    assert "[REDACTED_IP]" in redacted
    ordinary = "This is a basic relationship problem. I need basic trust."
    assert module.redact_for_external(ordinary) == ordinary


def test_external_redaction_covers_compound_and_structured_secrets() -> None:
    module = _load_module()
    private_key = (
        "-----BEGIN PRIVATE KEY-----\n"
        "cHJpdmF0ZS1rZXktdGVzdC1vbmx5\n"
        "-----END PRIVATE KEY-----"
    )
    pgp_key = (
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\n"
        "cGdwLXByaXZhdGUta2V5LXRlc3Qtb25seQ==\n"
        "-----END PGP PRIVATE KEY BLOCK-----"
    )
    source = (
        '{"DATABASE_PASSWORD":"db-secret-plain",'
        '"GITHUB_TOKEN":"gh-secret-plain",'
        '"CLIENT_SECRET":"client-secret-plain",'
        '"PRIVATE_KEY":"pem-secret-plain"}\n'
        f"{private_key}\n{pgp_key}\n"
        "machine example.invalid login user password netrc-secret-plain\n"
        "postgresql://dbuser:db-password-plain@example.invalid/database\n"
        "amqp://guest:rabbit-secret@mq.invalid/vhost\n"
        "mssql://sa:sql-secret@sql.invalid/database\n"
        "aws_secret_access_key=ordinaryAwsSecret123/+=\n"
        "openai_api_key=ordinary-not-prefixed-key\n"
        "github_token=ordinary-github-token\n"
        "database_password=ordinary-database-password\n"
        "//registry.npmjs.org/:_authToken=npm-secret-plain\n"
        "oauth_token=ordinary-oauth-secret"
    )

    redacted = module.redact_for_external(source)

    for private_value in (
        "db-secret-plain",
        "gh-secret-plain",
        "client-secret-plain",
        "pem-secret-plain",
        "cHJpdmF0ZS1rZXktdGVzdC1vbmx5",
        "cGdwLXByaXZhdGUta2V5LXRlc3Qtb25seQ==",
        "netrc-secret-plain",
        "db-password-plain",
        "rabbit-secret",
        "sql-secret",
        "ordinaryAwsSecret123/+=",
        "ordinary-not-prefixed-key",
        "ordinary-github-token",
        "ordinary-database-password",
        "npm-secret-plain",
        "ordinary-oauth-secret",
    ):
        assert private_value not in redacted
    assert "[REDACTED_PRIVATE_KEY]" in redacted
    assert "[REDACTED_URL_CREDENTIALS]@" in redacted


def test_external_redaction_covers_natural_language_and_spaced_credentials() -> None:
    module = _load_module()
    values = (
        "hunter2-dont-share",
        "sk_not_a_recognized_short_value",
        "abc123defghijklmnop",
        "ordinarysecretvalue123",
        "first second third",
    )
    source = (
        f"my password is {values[0]}.\n"
        f"the API key is {values[1]}.\n"
        f"use token {values[2]}.\n"
        f"the client secret is {values[3]}.\n"
        f"DATABASE_PASSWORD={values[4]}"
    )

    redacted = module.redact_for_external(source)

    for value in values:
        assert value not in redacted
    assert redacted.count("[REDACTED_CREDENTIAL]") == 5
    natural = (
        "The secret: I still love her. "
        "My password: trust is hard after that. "
        "The token: gesture is what mattered. "
        "I need to vent; the secret is I miss him."
        " Use the token gesture to show you care."
    )
    assert module.redact_for_external(natural) == natural


def test_caller_redact_terms_run_before_baseline_patterns() -> None:
    module = _load_module()
    private_term = "/Users/alice/Project-Codename-X"

    redacted = module.redact_for_external(
        f"Keep {private_term} private.",
        [private_term],
    )

    assert private_term not in redacted
    assert "Project-Codename-X" not in redacted
    assert "[REDACTED_TERM]" in redacted


def test_ambiguous_credentials_fail_closed_until_explicitly_redacted(
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    pair = _pair()
    ambiguous_value = "correcthorsebattery"
    pair["messages"][1]["content"] = f"My password is {ambiguous_value}."
    called = False
    captured_prompt = ""

    async def fake_call(prompt: str, teacher: str, model_name: str) -> str:
        nonlocal called, captured_prompt
        called = True
        captured_prompt = prompt
        return "That framing needs a real test."

    monkeypatch.setattr(module, "call_external_teacher", fake_call)

    result = asyncio.run(
        module.distill_pair(
            pair,
            "gemini",
            consent_to_external_processing=True,
            private_terms_reviewed=True,
        )
    )
    error = capsys.readouterr().err
    assert result is None
    assert called is False
    assert "ambiguous credential-like text" in error
    assert ambiguous_value not in error

    result = asyncio.run(
        module.distill_pair(
            pair,
            "gemini",
            consent_to_external_processing=True,
            private_terms_reviewed=True,
            redact_terms=[ambiguous_value],
        )
    )
    assert result is not None
    assert called is True
    assert ambiguous_value not in captured_prompt
    assert "[REDACTED_" in captured_prompt

    for natural_but_ambiguous in (
        "The secret: communication is what failed.",
        "My password: vulnerability is hard to admit.",
    ):
        try:
            module.ensure_no_ambiguous_credentials(natural_but_ambiguous)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"ambiguous credential prose was allowed: {natural_but_ambiguous}"
            )


def test_distill_preflights_entire_batch_before_credentials(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    first = _pair()
    second = _pair()
    second["sample_id"] = "ambiguous-sample"
    ambiguous_value = "abcdefghijklmnopqrstuvwxyz"
    second["messages"][1]["content"] = f"api_key: {ambiguous_value}"
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        module.json.dumps(first) + "\n" + module.json.dumps(second) + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "output.jsonl"
    credential_reads = 0

    def unexpected_credential_read() -> None:
        nonlocal credential_reads
        credential_reads += 1

    monkeypatch.setattr(module, "load_teacher_environment", unexpected_credential_read)
    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=True,
        input=str(input_path),
        output=str(output_path),
        teacher="gemini",
        limit=2,
        redact_term=[],
    )

    assert module.cmd_distill(args) == 2
    error = capsys.readouterr().err
    assert "Refusing external processing" in error
    assert ambiguous_value not in error
    assert credential_reads == 0
    assert not output_path.exists()


def test_distill_pair_requires_consent_before_calling_provider(monkeypatch) -> None:
    module = _load_module()
    called = False

    async def should_not_call(prompt: str, teacher: str, model_name: str) -> str:
        nonlocal called
        called = True
        return "response"

    monkeypatch.setattr(module, "call_external_teacher", should_not_call)

    try:
        asyncio.run(module.distill_pair(_pair(), "gemini"))
    except PermissionError as error:
        assert "explicit consent" in str(error)
    else:
        raise AssertionError("distill_pair accepted external processing without consent")
    assert called is False

    malformed = _pair()
    malformed["messages"][1]["content"] = ["not", "text"]
    try:
        asyncio.run(
            module.distill_pair(
                malformed,
                "gemini",
                consent_to_external_processing=True,
                private_terms_reviewed=True,
            )
        )
    except ValueError as error:
        assert "valid system/user/assistant pair" in str(error)
    else:
        raise AssertionError("direct distillation accepted malformed content")
    assert called is False


def test_distill_pair_requires_private_term_review_before_provider(monkeypatch) -> None:
    module = _load_module()
    called = False

    async def should_not_call(prompt: str, teacher: str, model_name: str) -> str:
        nonlocal called
        called = True
        return "response"

    monkeypatch.setattr(module, "call_external_teacher", should_not_call)

    try:
        asyncio.run(
            module.distill_pair(
                _pair(),
                "gemini",
                consent_to_external_processing=True,
                redact_terms=[PRIVATE_TERM],
            )
        )
    except PermissionError as error:
        assert "private terms must be reviewed" in str(error)
    else:
        raise AssertionError("distill_pair accepted unreviewed private terms")
    assert called is False


def test_empty_teacher_response_is_a_failed_pair(monkeypatch, capsys) -> None:
    module = _load_module()

    async def empty_call(prompt: str, teacher: str, model_name: str) -> str:
        return "   "

    monkeypatch.setattr(module, "call_external_teacher", empty_call)

    assert (
        asyncio.run(
            module.distill_pair(
                _pair(),
                "gemini",
                consent_to_external_processing=True,
                private_terms_reviewed=True,
                redact_terms=[PRIVATE_TERM],
            )
        )
        is None
    )
    assert "no usable text" in capsys.readouterr().err


def test_distill_requires_explicit_external_consent(tmp_path: Path, capsys) -> None:
    module = _load_module()
    args = argparse.Namespace(
        consent_to_external_processing=False,
        acknowledge_private_terms_reviewed=False,
        input=str(tmp_path / "input.jsonl"),
        output=str(tmp_path / "output.jsonl"),
        teacher="gemini",
        limit=None,
        redact_term=[],
    )

    assert module.cmd_distill(args) == 2
    assert "--consent-to-external-processing" in capsys.readouterr().err


def test_distill_requires_private_term_review_ack(tmp_path: Path, capsys) -> None:
    module = _load_module()
    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=False,
        input=str(tmp_path / "input.jsonl"),
        output=str(tmp_path / "output.jsonl"),
        teacher="gemini",
        limit=None,
        redact_term=[PRIVATE_TERM],
    )

    assert module.cmd_distill(args) == 2
    assert "--acknowledge-private-terms-reviewed" in capsys.readouterr().err


def test_dotenv_loading_is_deferred_past_all_safety_guards(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[object] = []

    def fake_load_dotenv(path=None):
        calls.append(path)
        return True

    monkeypatch.setitem(
        sys.modules,
        "dotenv",
        SimpleNamespace(load_dotenv=fake_load_dotenv),
    )
    module = _load_module()
    assert calls == []

    guarded_args = argparse.Namespace(
        consent_to_external_processing=False,
        acknowledge_private_terms_reviewed=False,
        input=str(tmp_path / "missing.jsonl"),
        output=str(tmp_path / "output.jsonl"),
        teacher="gemini",
        limit=1,
        redact_term=[],
    )
    assert module.cmd_distill(guarded_args) == 2
    assert calls == []

    guarded_args.consent_to_external_processing = True
    assert module.cmd_distill(guarded_args) == 2
    assert calls == []

    guarded_args.acknowledge_private_terms_reviewed = True
    guarded_args.limit = 0
    assert module.cmd_distill(guarded_args) == 2
    assert calls == []

    try:
        asyncio.run(module.distill_pair(_pair(), "gemini"))
    except PermissionError:
        pass
    else:
        raise AssertionError("direct distillation bypassed the consent boundary")
    assert calls == []

    input_path = tmp_path / "input.jsonl"
    input_path.write_text(module.json.dumps(_pair()) + "\n")
    guarded_args.input = str(input_path)
    guarded_args.limit = 1
    monkeypatch.setattr(
        module,
        "missing_teacher_env",
        lambda teacher: (True, ("GEMINI_API_KEY",)),
    )
    assert module.cmd_distill(guarded_args) == 1
    assert calls == [module.AFS_ROOT / ".env", None]


def test_distill_rejects_nonpositive_limit_before_transmission(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    for value in ("0", "-1"):
        try:
            module.build_arg_parser().parse_args(
                [
                    "distill",
                    "--teacher",
                    "gemini",
                    "--consent-to-external-processing",
                    "--acknowledge-private-terms-reviewed",
                    "--limit",
                    value,
                ]
            )
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError(f"parser accepted nonpositive limit {value}")

    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=True,
        input=str(tmp_path / "missing.jsonl"),
        output=str(tmp_path / "output.jsonl"),
        teacher="gemini",
        limit=0,
        redact_term=[PRIVATE_TERM],
    )
    assert module.cmd_distill(args) == 2
    assert "--limit must be greater than zero" in capsys.readouterr().err


def test_cli_requires_command_positive_extract_limit_and_distill_bound(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    parser = module.build_arg_parser()
    for command in (
        [],
        ["extract", "--min-turns", "0"],
        [
            "distill",
            "--teacher",
            "gemini",
            "--consent-to-external-processing",
            "--acknowledge-private-terms-reviewed",
        ],
    ):
        try:
            parser.parse_args(command)
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError(f"unsafe CLI invocation was accepted: {command}")

    output = tmp_path / "empty.jsonl"
    monkeypatch.setattr(module, "discover_sessions", lambda: [])
    assert (
        module.cmd_extract(
            argparse.Namespace(min_turns=6, output=str(output))
        )
        == 1
    )
    assert "no output was created" in capsys.readouterr().err
    assert not output.exists()

    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=True,
        input=str(tmp_path / "input.jsonl"),
        output=str(tmp_path / "output.jsonl"),
        teacher="gemini",
        limit=None,
        redact_term=[],
    )
    assert module.cmd_distill(args) == 2
    assert "--limit is required" in capsys.readouterr().err


def test_distill_rejects_corrupt_or_wrong_schema_input_before_credentials(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    credential_reads = 0

    def unexpected_credential_read() -> None:
        nonlocal credential_reads
        credential_reads += 1

    monkeypatch.setattr(module, "load_teacher_environment", unexpected_credential_read)
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=True,
        input=str(input_path),
        output=str(output_path),
        teacher="gemini",
        limit=1,
        redact_term=[],
    )

    malformed_pairs = (
        {"messages": [{"role": "system", "content": "system"}, {"role": "user"}, {"role": "assistant", "content": "answer"}]},
        {"messages": [{"role": "system", "content": "system"}, {"role": "user", "content": None}, {"role": "assistant", "content": "answer"}]},
        {"messages": [{"role": "system", "content": "system"}, {"role": "user", "content": ["private"]}, {"role": "assistant", "content": "answer"}]},
        {"messages": [{"role": "user", "content": "wrong"}, {"role": "user", "content": "private"}, {"role": "assistant", "content": "answer"}]},
        {"messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "private"}, {"role": "assistant", "content": "answer"}, {"role": "assistant", "content": "extra"}]},
        {**_pair(), "_metadata": {"distilled": "false"}},
    )
    payloads = [
        "not-json\n",
        '{"unrelated": true}\n',
        "",
        *(module.json.dumps(pair) + "\n" for pair in malformed_pairs),
    ]
    for payload in payloads:
        input_path.write_text(payload, encoding="utf-8")
        assert module.cmd_distill(args) == 1
        assert "Invalid distillation data" in capsys.readouterr().err
        assert credential_reads == 0
        assert not output_path.exists()


def test_distill_requires_distinct_input_and_distilled_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(module.json.dumps(_pair()) + "\n", encoding="utf-8")
    credential_reads = 0

    def unexpected_credential_read() -> None:
        nonlocal credential_reads
        credential_reads += 1

    monkeypatch.setattr(module, "load_teacher_environment", unexpected_credential_read)
    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=True,
        input=str(input_path),
        output=str(input_path),
        teacher="gemini",
        limit=1,
        redact_term=[],
    )
    assert module.cmd_distill(args) == 1
    assert "must be different files" in capsys.readouterr().err
    assert credential_reads == 0

    output_path.write_text(module.json.dumps(_pair()) + "\n", encoding="utf-8")
    args.output = str(output_path)
    assert module.cmd_distill(args) == 1
    assert "invalid distilled Claudia pair" in capsys.readouterr().err
    assert credential_reads == 0


def test_distill_preflights_output_writability_before_credentials(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(module.json.dumps(_pair()) + "\n", encoding="utf-8")
    output_path = tmp_path / "private" / "output.jsonl"
    credential_reads = 0
    provider_calls = 0
    real_open = module.os.open

    def guarded_open(path, flags, mode=0o777):
        if ".preflight-" in str(path):
            raise PermissionError("simulated unwritable output directory")
        return real_open(path, flags, mode)

    def unexpected_credential_read() -> None:
        nonlocal credential_reads
        credential_reads += 1

    async def unexpected_provider(*args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return "response"

    monkeypatch.setattr(module.os, "open", guarded_open)
    monkeypatch.setattr(module, "load_teacher_environment", unexpected_credential_read)
    monkeypatch.setattr(module, "call_external_teacher", unexpected_provider)
    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=True,
        input=str(input_path),
        output=str(output_path),
        teacher="gemini",
        limit=1,
        redact_term=[PRIVATE_TERM],
    )

    assert module.cmd_distill(args) == 1
    assert "Invalid distillation paths" in capsys.readouterr().err
    assert credential_reads == 0
    assert provider_calls == 0
    assert not output_path.exists()


def test_distill_uses_current_raw_content_fingerprint(monkeypatch) -> None:
    module = _load_module()
    pair = _pair()
    pair["_metadata"]["pair_fingerprint"] = "0" * 64

    async def fake_call(prompt: str, teacher: str, model_name: str) -> str:
        return "refined response"

    monkeypatch.setattr(module, "call_external_teacher", fake_call)
    result = asyncio.run(
        module.distill_pair(
            pair,
            "gemini",
            consent_to_external_processing=True,
            private_terms_reviewed=True,
        )
    )

    assert result is not None
    assert result["_metadata"]["source_pair_fingerprint"] == module.pair_fingerprint(pair)
    assert result["_metadata"]["source_pair_fingerprint"] != "0" * 64


def test_local_dataset_commands_fail_closed_on_corrupt_data(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    corrupt = tmp_path / "corrupt.jsonl"
    output = tmp_path / "output.jsonl"
    corrupt.write_text("not-json\n", encoding="utf-8")

    assert module.cmd_stats(argparse.Namespace(input=str(corrupt))) == 1
    assert "Invalid statistics data" in capsys.readouterr().err

    assert (
        module.cmd_narrative(
            argparse.Namespace(
                input=str(corrupt),
                output=str(output),
                limit=1,
            )
        )
        == 1
    )
    assert "Invalid narrative data" in capsys.readouterr().err
    assert not output.exists()

    assert (
        module.cmd_contrast(
            argparse.Namespace(
                input=str(corrupt),
                raw_input=None,
                distilled_input=None,
                output=str(output),
                limit=1,
            )
        )
        == 1
    )
    assert "Invalid contrast data" in capsys.readouterr().err
    assert not output.exists()

    try:
        module.append_unique_records(
            corrupt,
            [_pair()],
            module.pair_fingerprint,
            validator=module.is_raw_pair_record,
        )
    except ValueError as error:
        assert "not valid JSON" in str(error)
    else:
        raise AssertionError("append silently ignored a corrupt existing dataset")


def test_dataset_outputs_are_private_under_umask(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    output_path = tmp_path / "private-dataset.jsonl"

    previous_umask = os.umask(0o022)
    try:
        written, skipped = module.append_unique_records(
            output_path,
            [_pair()],
            module.pair_fingerprint,
        )
    finally:
        os.umask(previous_umask)

    assert (written, skipped) == (1, 0)
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600

    assert module.append_unique_records(
        output_path,
        [_pair()],
        module.pair_fingerprint,
    ) == (0, 1)

    output_path.chmod(0o644)
    module.append_unique_records(output_path, [], module.pair_fingerprint)
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600

    monkeypatch.delattr(module.os, "fchmod")
    fallback_path = tmp_path / "windows-fallback.jsonl"
    module.append_unique_records(fallback_path, [_pair()], module.pair_fingerprint)
    assert stat.S_IMODE(fallback_path.stat().st_mode) == 0o600


def test_distilled_uniqueness_uses_source_fingerprint_without_rejecting_raw_mate(
    tmp_path: Path,
) -> None:
    module = _load_module()
    raw = _pair()
    raw_fingerprint = module.pair_fingerprint(raw)

    def distilled(sample_id: str, assistant: str) -> dict:
        record = _pair()
        record["sample_id"] = sample_id
        record["messages"][2]["content"] = assistant
        record["_metadata"] = {
            "distilled": True,
            "source_pair_fingerprint": raw_fingerprint,
        }
        record["_metadata"]["pair_fingerprint"] = module.pair_fingerprint(record)
        return record

    first = distilled("distilled-one", "first teacher response")
    second = distilled("distilled-two", "second teacher response")
    mixed_path = tmp_path / "mixed.jsonl"
    mixed_path.write_text(
        module.json.dumps(raw) + "\n" + module.json.dumps(first) + "\n",
        encoding="utf-8",
    )
    assert module.load_pair_records_strict(mixed_path) == [raw, first]

    duplicates_path = tmp_path / "distilled.jsonl"
    duplicates_path.write_text(
        module.json.dumps(first) + "\n" + module.json.dumps(second) + "\n",
        encoding="utf-8",
    )
    try:
        module.load_pair_records_strict(
            duplicates_path,
            expected_distilled=True,
        )
    except ValueError as error:
        assert "duplicate pair content fingerprint" in str(error)
    else:
        raise AssertionError("distilled variants for one raw source were accepted")


def test_append_rejects_duplicate_fingerprints_already_on_disk(
    tmp_path: Path,
) -> None:
    module = _load_module()
    first = _pair()
    second = _pair()
    second["sample_id"] = "different-id"
    output = tmp_path / "duplicates.jsonl"
    output.write_text(
        module.json.dumps(first) + "\n" + module.json.dumps(second) + "\n",
        encoding="utf-8",
    )

    try:
        module.append_unique_records(
            output,
            [],
            module.pair_fingerprint,
            validator=module.is_raw_pair_record,
        )
    except ValueError as error:
        assert "duplicate content fingerprint" in str(error)
    else:
        raise AssertionError("append accepted an existing duplicate fingerprint")


def test_private_dataset_outputs_inside_repo_must_be_gitignored() -> None:
    module = _load_module()
    module.require_private_dataset_output(
        module.DATA_DIR / "safe-private-output.jsonl"
    )

    try:
        module.require_private_dataset_output(
            module.AFS_ROOT / "unsafe-private-output.jsonl"
        )
    except ValueError as error:
        assert "must be gitignored" in str(error)
    else:
        raise AssertionError("unignored in-repo private output was accepted")


def test_dataset_writer_refuses_linked_outputs(tmp_path: Path) -> None:
    module = _load_module()
    victim = tmp_path / "victim.jsonl"
    victim.write_text(module.json.dumps(_pair()) + "\n", encoding="utf-8")

    for kind in ("symlink", "hardlink"):
        output = tmp_path / f"{kind}.jsonl"
        if kind == "symlink":
            output.symlink_to(victim)
        else:
            os.link(victim, output)
        try:
            module.append_unique_records(
                output,
                [_pair()],
                module.pair_fingerprint,
                validator=module.is_raw_pair_record,
            )
        except ValueError as error:
            assert "refusing" in str(error)
        else:
            raise AssertionError(f"dataset writer followed a {kind}")
        assert victim.read_text(encoding="utf-8") == module.json.dumps(_pair()) + "\n"


def test_provider_failure_makes_batch_fail_nonzero(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(module.json.dumps(_pair()) + "\n")

    async def failed_distill(pair: dict, teacher: str, **kwargs):
        return None

    monkeypatch.setattr(module, "distill_pair", failed_distill)
    monkeypatch.setattr(module, "missing_teacher_env", lambda teacher: (False, ()))
    args = argparse.Namespace(
        consent_to_external_processing=True,
        acknowledge_private_terms_reviewed=True,
        input=str(input_path),
        output=str(output_path),
        teacher="gemini",
        limit=1,
        redact_term=[],
    )

    assert module.cmd_distill(args) == 1
    assert not output_path.exists()
    assert "Distillation batch failed" in capsys.readouterr().err
