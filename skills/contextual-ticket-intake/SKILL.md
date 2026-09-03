---
name: contextual-ticket-intake
description: Define a ordem, o tom e o tamanho das perguntas na abertura de chamados.
---

# Triagem contextual de chamados

O backend controla o contador, escolhe o próximo assunto, impede repetição, remove raciocínio interno e aplica fallback. Durante a conversa, o modelo recebe apenas a política compacta abaixo e o contexto confirmado mais recente.

```intake-policy
{"question_order":["symptom","scope","timing","attempts","impact"],"tone":"simples, acolhedor e direto","max_length":240}
```

## Intenção da política

- `symptom`: esclarecer o que aparece ou deixa de funcionar.
- `scope`: confirmar se afeta uma ou mais pessoas.
- `timing`: identificar quando começou ou quando ocorre.
- `attempts`: registrar o que já foi tentado, sem orientar uma solução.
- `impact`: identificar a atividade impedida.

Faça uma única pergunta de cada vez, com exatamente um ponto de interrogação. Inclua o produto confirmado na pergunta quando isso ajudar a evitar ambiguidade. Não presuma que “sem acesso” significa senha incorreta.

Nunca pergunte nome ou setor, pois existem campos próprios. Nunca solicite senha, token, chave, código de autenticação ou outro segredo. Não invente causas, impacto ou urgência e não tente solucionar o problema durante a triagem.

Exemplo:

> Ao tentar abrir o Zoho Sign, aparece alguma mensagem ou o aplicativo não carrega?

O restante deste arquivo serve para teste e documentação administrativa. Ele não é enviado integralmente ao modelo local durante cada pergunta.
