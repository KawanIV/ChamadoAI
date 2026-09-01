# Chamados — MVP de suporte Zoho

Central de chamados com abertura pública conversacional, gestão em lista e Kanban, registro completo, resolução estruturada e seleção de modelos instalados no Ollama.

## Executar

1. Copie `.env.example` para `.env` e troque todos os segredos.
2. Confirme que o Ollama está ativo na máquina e que o nome em `DEFAULT_MODEL` coincide com `ollama list`.
3. Execute `docker compose up --build`.
4. Abra `http://localhost:3000`. A API responde em `http://localhost:8000/health`.

O portal inicial usa o slug `zoho-suporte`. O primeiro administrador é criado com `BOOTSTRAP_ADMIN_EMAIL` e `BOOTSTRAP_ADMIN_PASSWORD`.

## Testes

- Interface: `npm test`
- API e segurança: `cd api && pytest`

## Segurança implementada

- isolamento por `tenant_id` e políticas RLS forçadas no PostgreSQL;
- autorização administrativa validada na API;
- senha com Argon2 e sessão JWT curta;
- links públicos assinados e vinculados ao tenant;
- rate limit no login e portal público;
- CORS restrito e cabeçalhos de segurança;
- Ollama acessado somente pelo backend e modelos validados contra `/api/tags`;
- containers sem privilégios, API/banco em rede interna e sistema de arquivos somente leitura;
- resoluções entram no RAG somente após confirmação do atendente.

Para produção externa, coloque um proxy HTTPS na frente do `web`, remova a porta pública da API e substitua o limitador em memória por Redis.
