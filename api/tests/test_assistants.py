import pytest
from fastapi import HTTPException
from app.assistant import INTAKE_PROMPT, MAX_QUESTIONS, SUPPORT_PROMPT, chunk_document, choose_intake_topic, compact_intake_request, compact_summary_evidence, contextualize_question, extract_document, fallback_intake_question, fallback_ticket_summary, finalize_ticket_summary, format_numbered_question, known_intake_topics, normalize_summary, question_has_context, question_is_repeated, related_ticket_similarity, read_conversation_state, sign_conversation_state, summary_description_is_transcript, summary_is_usable

def test_intake_and_support_assistants_have_separate_scopes():
    assert "abertura de chamados" in INTAKE_PROMPT
    assert "não exponha raciocínio interno" in INTAKE_PROMPT.lower()
    assert "sem JSON" in INTAKE_PROMPT
    assert "Use somente as fontes" in SUPPORT_PROMPT
    assert "referência não confiável" in SUPPORT_PROMPT
    assert "sem tentar resolver ou diagnosticar" in INTAKE_PROMPT
    assert "confirme frases ambíguas" in INTAKE_PROMPT
    assert "não repita pergunta" in INTAKE_PROMPT

def test_intake_request_is_short_contextual_and_preserves_question_answer_pairs():
    conversation=[{"role":"user","content":"Estou sem acesso ao Zoho Sign"},{"role":"assistant","content":"Isso afeta mais pessoas?"},{"role":"user","content":"Só eu"}]
    system,messages=compact_intake_request(conversation,"timing","simples e direto",240)
    assert len(system)<1400
    assert "exatamente um ponto de interrogação" in system
    assert "quando começou" in system
    assert messages==[{"role":"user","content":"Produto confirmado: Zoho Sign.\nHistórico confirmado:\nSolicitante: Estou sem acesso ao Zoho Sign\nAssistente: Isso afeta mais pessoas?\nSolicitante: Só eu"}]
    assert "sem JSON" in SUPPORT_PROMPT

def test_topic_selection_and_fallback_do_not_repeat_the_previous_subject():
    messages=[{"role":"user","content":"Estou sem acesso ao Zoho Sign"},{"role":"assistant","content":"Ao tentar usar o Zoho Sign, o que aparece na tela?"}]
    topic=choose_intake_topic(["symptom","scope","timing"],messages)
    assert topic=="scope"
    question=fallback_intake_question(topic,["Estou sem acesso ao Zoho Sign"])
    assert question=="Para dimensionar o problema no Zoho Sign, ele afeta somente você ou outras pessoas também?"
    assert question.count("?")==1
    assert choose_intake_topic(["symptom","scope","timing"],[],2)=="symptom"

def test_volunteered_answers_are_recognized_before_asking_again():
    messages=[{"role":"user","content":"Começou hoje, só eu estou afetado e já reiniciei o navegador"}]
    assert {"scope","timing","attempts"}<=known_intake_topics(messages)
    assert choose_intake_topic(["scope","timing","attempts","impact"],messages)=="impact"
    complete=[*messages,{"role":"user","content":"Isso impede que eu assine os documentos"}]
    assert choose_intake_topic(["scope","timing","attempts","impact"],complete) is None

def test_generic_model_filler_is_replaced_by_natural_context():
    question=contextualize_question("Entendi. Quando começou?",["Estou sem acesso ao Zoho Sign"])
    assert question=="Considerando o problema relatado no Zoho Sign, quando começou?"

def test_summary_fallback_is_editable_detects_product_and_redacts_secrets():
    summary=fallback_ticket_summary(["Estou sem acesso ao Zoho Sign","token: abc123","É urgente"])
    assert summary["product"]=="Zoho Sign"
    assert summary["priority"]=="high"
    assert "abc123" not in summary["description"]

def test_backend_numbers_questions_without_trusting_the_model():
    assert format_numbered_question("Quando o problema começou?",2)=="Pergunta 2: Quando o problema começou?"
    assert format_numbered_question("Pergunta 4: Qual mensagem aparece?",3)=="Pergunta 3: Qual mensagem aparece?"

def test_related_ticket_requires_the_same_concrete_incident_not_only_product():
    assert related_ticket_similarity("Estou sem acesso ao Zoho Sign","Sem acesso ao Sign","Usuário não consegue acessar o Zoho Sign","Zoho Sign")>=.72
    assert related_ticket_similarity("O Zoho Sign não envia o documento","Sem acesso ao Sign","Usuário não consegue acessar o Zoho Sign","Zoho Sign")==0
    assert related_ticket_similarity("Estou sem acesso ao Zoho CRM","Sem acesso ao Sign","Usuário não consegue acessar o Zoho Sign","Zoho Sign")==0

def test_summary_uses_labeled_facts_and_fallback_is_narrative():
    conversation=[
        {"role":"user","content":"Estou sem acesso ao Zoho Sign"},
        {"role":"assistant","content":"Pergunta 1: Ao acessar o Zoho Sign, qual mensagem aparece?"},
        {"role":"user","content":"Aparece acesso negado"},
        {"role":"assistant","content":"Pergunta 2: Isso afeta somente você ou outras pessoas?"},
        {"role":"user","content":"Só eu"},
    ]
    evidence=compact_summary_evidence(conversation,"Valdir","Comercial")
    assert "Comportamento observado: Aparece acesso negado" in evidence
    assert "Abrangência: Só eu" in evidence
    summary=fallback_ticket_summary([item["content"] for item in conversation if item["role"]=="user"],conversation)
    assert "mensagem de acesso negado" in summary["description"]
    assert "afeta somente o solicitante" in summary["description"]
    assert "\n" not in summary["description"]
    assert not summary_description_is_transcript(summary["description"],["Estou sem acesso ao Zoho Sign","Aparece acesso negado","Só eu"])
    assert summary_description_is_transcript("Resposta 1: sem acesso\nResposta 2: só eu",["sem acesso","só eu"])

def test_final_summary_turns_short_answers_into_a_cohesive_ticket():
    conversation=[
        {"role":"user","content":"Olá chat, estou sem acesso ao Zoho CRM"},
        {"role":"assistant","content":"Pergunta 1: Ao tentar acessar o Zoho CRM, aparece alguma mensagem ou ele não carrega?"},
        {"role":"user","content":"Não carrega"},
        {"role":"assistant","content":"Pergunta 2: Isso afeta somente você ou outras pessoas?"},
        {"role":"user","content":"Só eu"},
        {"role":"assistant","content":"Pergunta 3: Quando o problema começou?"},
        {"role":"user","content":"Hoje cedo"},
        {"role":"assistant","content":"Pergunta 4: O que você já tentou fazer?"},
        {"role":"user","content":"Troquei de navegador"},
        {"role":"assistant","content":"Pergunta 5: Qual atividade ficou impedida?"},
        {"role":"user","content":"Não consigo consultar os clientes"},
    ]
    users=[item["content"] for item in conversation if item["role"]=="user"]
    baseline=fallback_ticket_summary(users,conversation)
    assert baseline["title"]=="Zoho CRM não carrega"
    assert "O solicitante relata que está sem acesso ao Zoho CRM." in baseline["description"]
    assert "a aplicação não carrega" in baseline["description"]
    assert "afeta somente o solicitante" in baseline["description"]
    assert "hoje cedo" in baseline["description"]
    assert "consultar os clientes" in baseline["description"]
    assert summary_is_usable(baseline,users)

def test_generic_or_transcribed_model_summary_is_replaced_by_safe_baseline():
    users=["Estou sem acesso ao Zoho CRM","Não carrega","Só eu"]
    baseline={"title":"Zoho CRM não carrega","description":"O solicitante relata que está sem acesso ao Zoho CRM. Ao tentar acessar o Zoho CRM, a aplicação não carrega. A ocorrência afeta somente o solicitante.","product":"Zoho CRM","priority":"normal"}
    weak={"title":"Problema","description":"Resposta 1: sem acesso\nResposta 2: não carrega","product":"Zoho CRM","priority":"normal"}
    assert finalize_ticket_summary(weak,baseline,users)["description"]==baseline["description"]

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
