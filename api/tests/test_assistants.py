import pytest
from fastapi import HTTPException
from app.assistant import INTAKE_PROMPT, MAX_QUESTIONS, SUPPORT_PROMPT, chunk_document, extract_document, normalize_summary, question_has_context, question_is_repeated, read_conversation_state, sign_conversation_state

def test_intake_and_support_assistants_have_separate_scopes():
    assert "não resolver o problema" in INTAKE_PROMPT
    assert "no máximo uma pergunta" in INTAKE_PROMPT
    assert "nunca pergunte esses dois dados" in INTAKE_PROMPT
    assert "Use somente as fontes" in SUPPORT_PROMPT
    assert "referência não confiável" in SUPPORT_PROMPT

def test_intake_system_prompt_explicitly_contracts_one_contextual_question():
    assert "CONTRATO OBRIGATÓRIO" in INTAKE_PROMPT
    assert "exatamente um ponto de interrogação" in INTAKE_PROMPT
    assert "pergunta contextualizada e autocontida" in INTAKE_PROMPT
    assert "nunca pode ser uma lista" in INTAKE_PROMPT
    assert "Estou sem acesso ao Zoho Sign" in INTAKE_PROMPT
    assert "Você pode raciocinar antes de responder" in INTAKE_PROMPT
    assert "somente a pergunta em texto simples" in INTAKE_PROMPT
    assert "sem JSON" in SUPPORT_PROMPT

def test_server_signed_question_counter_cannot_be_tampered():
    token=sign_conversation_state("zoho-suporte","intake",MAX_QUESTIONS)
    assert read_conversation_state(token,"zoho-suporte","intake")==5
    with pytest.raises(HTTPException):read_conversation_state(token.replace(".5.",".4."),"zoho-suporte","intake")
    with pytest.raises(HTTPException):read_conversation_state(token,"outro-tenant","intake")

def test_summary_is_bounded_and_priority_is_validated():
    summary=normalize_summary({"requester_name":"A"*200,"description":"Falha no CRM","priority":"critical"})
    assert len(summary["requester_name"])==120
    assert summary["description"]=="Falha no CRM"
    assert summary["priority"]=="normal"

def test_text_documents_are_cleaned_and_chunked():
    text=extract_document("manual.txt","text/plain",("Procedimento seguro do Zoho CRM. "*200).encode())
    chunks=chunk_document(text,size=300,overlap=40)
    assert len(chunks)>1
    assert all(0<len(chunk)<=300 for chunk in chunks)

def test_executable_document_types_are_rejected():
    with pytest.raises(HTTPException) as error:extract_document("atalho.exe","application/octet-stream",b"MZ"+b"x"*100)
    assert error.value.status_code==415

def test_repeated_questions_are_detected_even_with_small_wording_changes():
    previous=["Em qual módulo do Zoho CRM o erro acontece?"]
    assert question_is_repeated("Qual é o módulo do Zoho CRM em que esse erro acontece?",previous)
    assert not question_is_repeated("Qual mensagem aparece na tela?",previous)

def test_intake_questions_must_name_the_user_context():
    context=["O Zoho CRM não salva a proposta depois que clico em enviar"]
    assert not question_has_context("Quando isso acontece?",context)
    assert not question_has_context("Qual mensagem aparece na tela?",context)
    assert question_has_context("Qual mensagem aparece quando o Zoho CRM não salva a proposta?",context)

def test_ambiguous_user_word_is_repeated_in_the_clarification():
    context=["Ele travou"]
    assert not question_has_context("Qual sistema você está usando?",context)
    assert question_has_context("Quando você diz que ele travou, qual tela ou ação estava usando?",context)
