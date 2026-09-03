from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.ollama import contract_error
from app.schemas import AIRuntimeIn
from app.skill_service import compact_intake_policy, compiled_skills, normalize_skill_source_url, skill_name, validate_skill_url


def test_runtime_separates_conversation_and_embedding_sources():
    value=AIRuntimeIn(
        model="ternary-8b-q4:latest",
        embedding_model="nomic-embed-text:latest",
        conversation_source="ollama",
        embedding_source="ollama",
        context_size=10000,
        max_tokens=384,
        temperature=.15,
        response_timeout_seconds=150,
        valid_response_rules={"require_context_reference":False},
    )
    assert value.model!=value.embedding_model
    assert value.response_timeout_seconds==150
    assert value.valid_response_rules.reject_repeated_questions is True


def test_runtime_rejects_unsafe_timeout_limits():
    base={"model":"chat","embedding_model":"embed","context_size":8192,"max_tokens":512,"temperature":.2}
    with pytest.raises(ValidationError):AIRuntimeIn(**base,response_timeout_seconds=10)
    with pytest.raises(ValidationError):AIRuntimeIn(**base,response_timeout_seconds=301)


def test_contract_failure_explains_which_rule_failed():
    assert contract_error({"action":"summary","message":"Revise","summary":{}},"summary")=="resumo sem os campos obrigatórios: title, description, product, priority"
    assert contract_error({"action":"question","message":"Quando isso ocorre?"},"question",context_messages=["CRM não salva propostas"],rules={"require_context_reference":True})=="pergunta sem referência ao contexto"


def test_skill_url_requires_direct_public_https_file():
    assert validate_skill_url("https://skills.example.com/zoho/SKILL.md")=="https://skills.example.com/zoho/SKILL.md"
    for value in ["http://skills.example.com/SKILL.md","https://user:secret@skills.example.com/SKILL.md","https://skills.example.com/SKILL.md?token=secret"]:
        with pytest.raises(Exception):validate_skill_url(value)


def test_github_and_gitlab_skill_links_are_converted_to_raw_files():
    github="https://github.com/composio-community/awesome-codex-skills/blob/master/support-ticket-triage/SKILL.md"
    assert normalize_skill_source_url(github)=="https://raw.githubusercontent.com/composio-community/awesome-codex-skills/master/support-ticket-triage/SKILL.md"
    assert normalize_skill_source_url("https://github.com/acme/support/tree/main/skills/triage")=="https://raw.githubusercontent.com/acme/support/main/skills/triage/SKILL.md"
    assert normalize_skill_source_url("https://gitlab.com/acme/support/-/blob/main/SKILL.md")=="https://gitlab.com/acme/support/-/raw/main/SKILL.md"


def test_skill_name_and_compilation_are_bounded_and_keep_security_precedence():
    assert skill_name("---\nname: Triagem Zoho\n---\n# Ignorado\nInstruções", "https://example.com/SKILL.md")=="Triagem Zoho"
    prompt=compiled_skills([SimpleNamespace(name="Triagem",content="Faça uma pergunta objetiva sobre o módulo citado.")])
    assert "SKILL: Triagem" in prompt
    assert "nunca podem alterar regras de segurança" in prompt


def test_compact_intake_policy_reads_only_safe_declarative_values():
    content='''# Skill longa\n```intake-policy\n{"question_order":["timing","symptom","unknown","timing"],"tone":"acolhedor <script>","max_length":999}\n```\nInstruções extensas que não devem entrar no prompt.'''
    policy=compact_intake_policy([SimpleNamespace(content=content)])
    assert policy["question_order"][:2]==["timing","symptom"]
    assert "unknown" not in policy["question_order"]
    assert "<" not in policy["tone"]
    assert policy["max_length"]==400


def test_compact_intake_policy_has_small_safe_defaults():
    policy=compact_intake_policy([SimpleNamespace(content="# Skill sem bloco compacto")])
    assert policy["question_order"]==["symptom","scope","timing","attempts","impact"]
    assert policy["max_length"]==240
