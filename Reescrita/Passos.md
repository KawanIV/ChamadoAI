# Roteiro: Reescrevendo o ChamadoAI do Zero

Este é o seu plano de ação para reescrever a aplicação manualmente, passo a passo.  
Use este documento como checklist e guia de referência.  
Responda às perguntas conforme avança para definir os detalhes.

---

## 1. Análise do Projeto Original (Funcionalidades Essenciais)

Antes de codar, liste o que o sistema precisa fazer.  
O ChamadoAI original parece ter estes módulos:

- [ ] **Usuários**: cadastro, login, logout, autenticação (JWT ou sessão)
- [ ] **Chamados**: criar, listar (com filtros), visualizar detalhes, editar, fechar
- [ ] **IA**: classificação ou sugestão de respostas (pode ser adicionado depois)
- [ ] **Anexos**: upload de PDF, DOCX, imagens (opcional no início)
- [ ] **Dashboard**: indicadores (total de chamados, abertos, etc.)

**Decisão:** Qual módulo você vai implementar primeiro? Sugiro começar por **Usuários**.

---

## 2. Escolha da Stack

Defina as ferramentas que usará para construir tudo.  
Responda as perguntas abaixo:

- **Backend:** Python (Flask, FastAPI?) | Node (Express?) | PHP | Go | Java?
- **Banco de dados:** SQLite (mais simples) | PostgreSQL | MySQL?
- **Frontend:** HTML + CSS + JS puro? Ou algum framework leve (Vue, Svelte)?
- **Comunicação:** REST API? GraphQL?

**Minha sugestão didática:**  
- Backend: Python + Flask  
- Banco: SQLite (para começar)  
- Frontend: HTML + CSS + JS puro (com `fetch` para consumir a API)

**Sua escolha:**  

Backend: ___________
Banco: _____________
Frontend: __________

===========================================================================////===


---

## 3. Modelagem de Dados

Desenhe as tabelas necessárias. Use um rascunho SQL ou diagrama.

### Tabela `usuarios`
| Campo       | Tipo          | Descrição                     |
|-------------|---------------|-------------------------------|
| id          | INTEGER (PK)  | Identificador único           |
| nome        | TEXT          | Nome do usuário               |
| email       | TEXT (UNIQUE) | Login do usuário              |
| senha_hash  | TEXT          | Hash da senha (bcrypt/argon2) |
| criado_em   | DATETIME      | Data de cadastro              |

### Tabela `chamados`
| Campo          | Tipo          | Descrição                            |
|----------------|---------------|--------------------------------------|
| id             | INTEGER (PK)  | Identificador único                  |
| titulo         | TEXT          | Título do chamado                    |
| descricao      | TEXT          | Descrição detalhada                  |
| status         | TEXT          | aberto, em_andamento, fechado        |
| prioridade     | TEXT          | baixa, media, alta                   |
| usuario_id     | INTEGER (FK)  | Quem abriu o chamado                 |
| atendente_id   | INTEGER (FK)  | Quem está resolvendo (pode ser nulo) |
| criado_em      | DATETIME      | Data de abertura                     |
| atualizado_em  | DATETIME      | Última atualização                   |

### Tabela `anexos` (opcional)
| Campo        | Tipo          | Descrição                    |
|--------------|---------------|------------------------------|
| id           | INTEGER (PK)  | Identificador único          |
| chamado_id   | INTEGER (FK)  | Chamado associado            |
| nome_arquivo | TEXT          | Nome original                |
| caminho      | TEXT          | Onde o arquivo está salvo    |
| enviado_em   | DATETIME      | Data do upload               |

**Pergunta:** Você já tem experiência com modelagem? Precisa de ajuda para refinar as relações?

---

## 4. Ordem de Desenvolvimento (Passo a Passo)

Siga esta sequência para construir a aplicação de forma incremental e funcional.

### ✅ Passo 0: Configuração do Ambiente
- Crie a estrutura de pastas (ex: `/backend`, `/frontend`, `/database`).
- Inicie o gerenciador de dependências (pip, npm, etc.).
- Instale as bibliotecas básicas (framework web, driver do banco, hash de senha, JWT se usar).
- Configure o servidor para escutar na porta desejada.

### ✅ Passo 1: Rota de Cadastro de Usuário
- Endpoint: `POST /api/registrar`
- Recebe nome, email, senha.
- Valida se o email já existe.
- Gera hash da senha e salva no banco.
- Retorna sucesso ou erro.

### ✅ Passo 2: Rota de Login
- Endpoint: `POST /api/login`
- Recebe email e senha.
- Verifica credenciais e retorna token JWT (ou inicia sessão).
- No frontend, armazene o token (localStorage ou cookie).

### ✅ Passo 3: Middleware de Autenticação
- Crie um middleware que verifique o token JWT em todas as rotas protegidas.
- Se inválido, retorne 401 (Não autorizado).

### ✅ Passo 4: CRUD de Chamados (protegido)
- **Criar:** `POST /api/chamados` (enviar título, descrição, prioridade)
- **Listar:** `GET /api/chamados` (com filtros opcionais: status, prioridade)
- **Visualizar:** `GET /api/chamados/{id}`
- **Editar:** `PUT /api/chamados/{id}` (atualizar campos)
- **Fechar:** `PATCH /api/chamados/{id}/fechar` (mudar status para fechado)

### ✅ Passo 5: Frontend Básico
- Crie as páginas HTML:
  - Página de login
  - Página de cadastro
  - Dashboard (lista de chamados)
  - Formulário de criação/edição
  - Página de detalhes do chamado
- Use JavaScript para fazer requisições `fetch` para sua API.
- Atualize a UI conforme as respostas.

### ✅ Passo 6: Integração com IA (opcional)
- Defina qual serviço de IA quer usar (OpenAI, Gemini, etc.).
- Crie uma rota no backend que recebe o chamado e chama a API externa.
- Retorne a classificação/sugestão para o frontend ou salve no banco.

### ✅ Passo 7: Upload de Arquivos (opcional)
- Endpoint: `POST /api/chamados/{id}/anexos`
- Receba o arquivo via `multipart/form-data`.
- Salve em uma pasta local ou em serviço de nuvem.
- Registre o caminho na tabela `anexos`.

### ✅ Passo 8: Testes e Melhorias
- Teste todas as rotas manualmente (use Postman/Insomnia).
- Adicione validações extras (campos obrigatórios, tamanhos).
- Melhore a UI com CSS (torne responsivo).
- Refatore o código para manter a organização.

---

## 5. Próximos Passos: Suas Respostas

Para começar, responda a estas perguntas e compartilhe comigo. A partir delas, traçaremos o plano detalhado para o Passo 0.

1. **Qual stack você escolheu?** (Backend, banco, frontend)
2. **Você já tem algum código escrito ou vai começar do zero?**
3. **Qual a primeira parte que você quer atacar?** (Sugiro cadastro/login, como no Passo 1)

---

Boa sorte! Estou aqui para tirar dúvidas, revisar sua lógica e sugerir melhorias – tudo sem gerar código para você, apenas mentorando. 


===========================================================================//////////=======

