# Chamados — MVP de suporte Zoho

Central de chamados com dois assistentes públicos, gestão em lista e Kanban arrastável, histórico de etapas, resolução estruturada, documentos internos e seleção de modelos instalados no Ollama.

As áreas internas exigem login. O administrador gerencia prestadores, documentos e IA e acompanha apenas métricas agregadas da plataforma. O prestador é o único perfil que acessa, movimenta e resolve chamados. O portal de abertura permanece público.

## Executar

1. Copie `.env.example` para `.env` e troque todos os segredos.
2. Para usar o Ollama, confirme que ele está ativo na máquina e que o nome em `DEFAULT_MODEL` coincide com `ollama list`.
3. Execute `docker compose up --build`.
4. Abra `http://localhost:3001`. A interface encaminha as requisições internamente para a API. Para diagnóstico, a API também responde em `http://localhost:8001/health`.

O navegador não acessa mais a porta da API diretamente. Login, chat e administração usam `/backend`, evitando falhas por CORS, IP da máquina ou porta compilada no frontend.

`POSTGRES_PASSWORD` aceita senhas fortes com caracteres especiais como `@`, `:`, `/` e `#`. A API recebe host, usuário e senha em variáveis separadas para que esses caracteres não corrompam o endereço do banco.

O portal inicial usa o slug `zoho-suporte`. O primeiro administrador é criado com `BOOTSTRAP_ADMIN_EMAIL` e `BOOTSTRAP_ADMIN_PASSWORD`.

Defina também `AI_CREDENTIALS_KEY` no `.env` antes de salvar segredos de APIs externas. No PowerShell, você pode gerar uma chave com:

```powershell
[Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
```

Guarde esse valor e não o altere depois: ele protege as credenciais já gravadas.

Entre na tela de login com esses dois valores. Em **Prestadores**, o administrador pode criar contas de atendimento. A área **Inteligência Artificial** possui três menus:

- **Adicionar Modelos:** reconhece todos os modelos reais do Ollama por `/api/tags` e conecta uma API externa compatível com Chat Completions. Existem presets para OpenAI, DeepSeek, Groq e OpenRouter, além de URL personalizada.
- **Configurar Modelos:** seleciona separadamente o modelo de conversação e o modelo de embeddings, inclusive com origens diferentes. Também configura contexto máximo, tokens por resposta, temperatura, tempo limite entre 15 e 300 segundos e as regras que validam a saída do modelo.
- **Skills:** importa um arquivo Markdown por link HTTPS direto, permite escolher em qual assistente ele atua, testar a instrução com o modelo de conversação e ativá-la somente depois da validação.

Depois de salvar a configuração, use **Testar modelo**. O teste confirma que o modelo selecionado consegue cumprir o contrato de resposta antes de colocá-lo no chat. Modelos identificados pelo Ollama como exclusivos para embeddings não podem ser salvos como modelo de conversação.

O portal público oferece dois caminhos:

- **Assistente virtual:** consulta documentos e resoluções aprovadas. Quando não encontra base suficiente, oferece a abertura de um chamado sem inventar uma resposta.
- **Assistente de abertura:** mantém nome e setor em campos fixos, anuncia e faz cinco perguntas úteis sem repetir assuntos. Cada pergunta cita o módulo, ação, erro ou sintoma já descrito; mensagens curtas ou ambíguas geram uma confirmação explícita, sem o modelo presumir o significado. Na primeira mensagem, verifica se existe chamado semelhante sem revelar dados de outro solicitante. Após a quinta resposta, gera um resumo editável; o usuário também pode antecipar isso com **Gerar resumo agora**.

Respostas do modelo que não respeitam o contrato esperado são refeitas silenciosamente pelo tempo configurado. A integração aceita JSON puro, blocos de código JSON e, quando a regra estiver ativa, repara texto simples útil para o contrato interno. O administrador pode manter o bloqueio de perguntas repetidas, exigir os campos mínimos do resumo e optar por uma validação mais rigorosa de referência ao contexto. A falha final informa qual regra não foi satisfeita, em vez de apresentar apenas uma mensagem genérica. Durante esse período, a interface mantém o indicador de digitação. Se o limite for atingido, a própria conversa oferece **Enviar novamente**.

As Skills são tratadas como instruções administrativas não confiáveis: somente arquivos de texto/Markdown de até 128 KB são aceitos, redirecionamentos e destinos privados são bloqueados, o conteúdo nunca é executado e não pode substituir as regras de segurança ou permissões do sistema.

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
- segredos de APIs externas cifrados no PostgreSQL com `pgcrypto`/AES-256 e nunca devolvidos ao navegador;
- APIs externas limitadas a HTTPS, sem credenciais na URL e com bloqueio de destinos privados/reservados;
- Skills importadas somente por HTTPS direto, limitadas, isoladas por empresa, inativas por padrão e sem execução de código;
- containers sem privilégios, API/banco em rede interna e sistema de arquivos somente leitura;
- resoluções entram no RAG somente após confirmação do atendente.
- documentos da base são isolados por empresa, limitados e tratados como conteúdo não confiável;
- o contador de perguntas da abertura é assinado pelo servidor e não depende do navegador.
- perguntas repetidas são rejeitadas no backend e refeitas silenciosamente pelo modelo;
- perguntas vagas que não mencionam o contexto do usuário também são rejeitadas e refeitas;
- cada mudança de etapa, inclusive **Resolvido** e **Encerrado**, recebe data e responsável em histórico próprio.

Para produção externa, coloque um proxy HTTPS na frente do `web`, remova a porta pública da API e substitua o limitador em memória por Redis.
