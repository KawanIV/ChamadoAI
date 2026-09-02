# Chamados — MVP de suporte Zoho

Central de chamados com abertura pública conversacional, gestão em lista e Kanban, registro completo, resolução estruturada e seleção de modelos instalados no Ollama.

As áreas internas exigem login. O administrador gerencia usuários e a IA; o prestador acessa e resolve chamados. O portal de abertura permanece público.

## Executar

1. Copie `.env.example` para `.env` e troque todos os segredos.
2. Confirme que o Ollama está ativo na máquina e que o nome em `DEFAULT_MODEL` coincide com `ollama list`.
3. Execute `docker compose up --build`.
4. Abra `http://localhost:3001`. A interface encaminha as requisições internamente para a API. Para diagnóstico, a API também responde em `http://localhost:8001/health`.

O navegador não acessa mais a porta da API diretamente. Login, chat e administração usam `/backend`, evitando falhas por CORS, IP da máquina ou porta compilada no frontend.

`POSTGRES_PASSWORD` aceita senhas fortes com caracteres especiais como `@`, `:`, `/` e `#`. A API recebe host, usuário e senha em variáveis separadas para que esses caracteres não corrompam o endereço do banco.

O portal inicial usa o slug `zoho-suporte`. O primeiro administrador é criado com `BOOTSTRAP_ADMIN_EMAIL` e `BOOTSTRAP_ADMIN_PASSWORD`.

Entre na tela de login com esses dois valores. Em **Usuários**, o administrador pode criar contas de prestador. Em **Inteligência Artificial**, a aplicação consulta `/api/tags` e mostra todos os modelos realmente instalados no Ollama.

Se você tentou uma versão anterior que falhou durante a imagem web, force a reconstrução com `docker compose build --no-cache web` antes de executar novamente.

## Testes

- Interface: `npm test`
- API e segurança: `cd api && pytest`

## Segurança implementada

- isolamento por `tenant_id` e políticas RLS forçadas no PostgreSQL;
- autorização administrativa validada na API;
- senha com Argon2 e sessão JWT curta armazenada em cookie `HttpOnly`;
- links públicos assinados e vinculados ao tenant;
- rate limit no login e portal público;
- CORS restrito e cabeçalhos de segurança;
- Ollama acessado somente pelo backend e modelos validados contra `/api/tags`;
- containers sem privilégios, API/banco em rede interna e sistema de arquivos somente leitura;
- resoluções entram no RAG somente após confirmação do atendente.

Para produção externa, coloque um proxy HTTPS na frente do `web`, remova a porta pública da API e substitua o limitador em memória por Redis.
