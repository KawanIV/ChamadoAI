# Chamados — MVP de suporte Zoho

Central de chamados com dois assistentes públicos, gestão em lista e Kanban arrastável, histórico de etapas, resolução estruturada, documentos internos e seleção de modelos instalados no Ollama.

As áreas internas exigem login. O administrador gerencia prestadores, documentos e IA e acompanha apenas métricas agregadas da plataforma. O prestador é o único perfil que acessa, movimenta e resolve chamados. O portal de abertura permanece público.

## Executar

1. Copie `.env.example` para `.env` e troque todos os segredos.
2. Confirme que o Ollama está ativo na máquina e que o nome em `DEFAULT_MODEL` coincide com `ollama list`.
3. Execute `docker compose up --build`.
4. Abra `http://localhost:3001`. A interface encaminha as requisições internamente para a API. Para diagnóstico, a API também responde em `http://localhost:8001/health`.

O navegador não acessa mais a porta da API diretamente. Login, chat e administração usam `/backend`, evitando falhas por CORS, IP da máquina ou porta compilada no frontend.

`POSTGRES_PASSWORD` aceita senhas fortes com caracteres especiais como `@`, `:`, `/` e `#`. A API recebe host, usuário e senha em variáveis separadas para que esses caracteres não corrompam o endereço do banco.

O portal inicial usa o slug `zoho-suporte`. O primeiro administrador é criado com `BOOTSTRAP_ADMIN_EMAIL` e `BOOTSTRAP_ADMIN_PASSWORD`.

Entre na tela de login com esses dois valores. Em **Usuários**, o administrador pode criar contas de prestador. Em **Inteligência Artificial**, a aplicação consulta `/api/tags` e mostra todos os modelos realmente instalados no Ollama.

O portal público oferece dois caminhos:

- **Assistente virtual:** consulta documentos e resoluções aprovadas. Quando não encontra base suficiente, oferece a abertura de um chamado sem inventar uma resposta.
- **Assistente de abertura:** mantém nome e setor em campos fixos, anuncia e faz cinco perguntas úteis sem repetir assuntos. Na primeira mensagem, verifica se existe chamado semelhante sem revelar dados de outro solicitante. Após a quinta resposta, gera um resumo editável; o usuário também pode antecipar isso com **Gerar resumo agora**.

Respostas do modelo que não respeitam o JSON esperado são refeitas silenciosamente por até 90 segundos. Durante esse período, a interface mantém o indicador de digitação. Se o limite for atingido, a própria conversa oferece **Enviar novamente**.

Em **Base de conhecimento**, administradores podem enviar PDF, DOCX, TXT e Markdown de até 10 MB. Os arquivos são validados, têm o texto extraído e são divididos em trechos pesquisáveis. Instalações existentes recebem as novas tabelas automaticamente durante a inicialização da API.

Se você tentou uma versão anterior que falhou durante a imagem web, force a reconstrução com `docker compose build --no-cache web` antes de executar novamente.

## Testes

- Interface: `npm test`
- API e segurança: `cd api && pytest`

## Segurança implementada

- isolamento por `tenant_id` e políticas RLS forçadas no PostgreSQL;
- autorização administrativa validada na API;
- separação de funções: administradores recebem somente métricas agregadas e prestadores gerenciam chamados;
- senha com Argon2 e sessão JWT curta armazenada em cookie `HttpOnly`;
- links públicos assinados e vinculados ao tenant;
- rate limit no login e portal público;
- CORS restrito e cabeçalhos de segurança;
- Ollama acessado somente pelo backend e modelos validados contra `/api/tags`;
- containers sem privilégios, API/banco em rede interna e sistema de arquivos somente leitura;
- resoluções entram no RAG somente após confirmação do atendente.
- documentos da base são isolados por empresa, limitados e tratados como conteúdo não confiável;
- o contador de perguntas da abertura é assinado pelo servidor e não depende do navegador.
- perguntas repetidas são rejeitadas no backend e refeitas silenciosamente pelo modelo;
- cada mudança de etapa, inclusive **Resolvido** e **Encerrado**, recebe data e responsável em histórico próprio.

Para produção externa, coloque um proxy HTTPS na frente do `web`, remova a porta pública da API e substitua o limitador em memória por Redis.
