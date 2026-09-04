"use client";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  BookOpen,
  Bot,
  Building2,
  Camera,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Columns3,
  ExternalLink,
  FileText,
  Inbox,
  LayoutDashboard,
  Layers3,
  List,
  LogOut,
  MoreHorizontal,
  Paperclip,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  ScrollText,
  Sparkles,
  TicketCheck,
  Upload,
  Users,
  UserCircle,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

type Area = { id: string; name: string; active: boolean; created_at?: string };
type Company = { id: string; name: string; public_slug: string; active: boolean; managers: number; manager_name:string;manager_email:string;areas: number; public_path: string };
type AuditEntry={id:string;tenant_id:string;tenant_name?:string|null;actor_name:string;actor_role:string;action:string;target_type:string;target_id?:string|null;details:Record<string,unknown>;created_at:string};

type User = {
  id: string;
  name: string;
  email: string;
  role: "platform_admin" | "company_admin" | "agent";
  tenant?: { id: string; name: string; slug: string } | null;
  area?: { id: string; name: string } | null;
  area_id?: string;
  area_name?: string;
  active?: boolean;
  avatar_url?: string | null;
};
type StatusHistory = {
  status: string;
  entered_at: string;
  changed_by: string | null;
};
type TicketResolution = {
  id: string;
  confirmed_problem: string;
  root_cause: string;
  solution: string;
  validation: string;
  reusable: boolean;
};
type Ticket = {
  id: string;
  area_id: string;
  area_name: string | null;
  protocol: number;
  requester_name: string;
  department: string;
  contact: string | null;
  title: string;
  summary: string;
  product: string;
  status: string;
  priority: string;
  created_at: string;
  resolution: TicketResolution | null;
  attachments:{id:string;filename:string;content_type:string;size_bytes:number;url:string}[];
  status_history: StatusHistory[];
};
type OllamaModel = {
  name: string;
  size?: number;
  modified_at?: string;
  details?: {
    family?: string;
    quantization_level?: string;
    parameter_size?: string;
  };
};
type AssistantMode = "intake" | "support";
type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  duration_ms?: number;
  response_tokens?: number;
  tokens_estimated?: boolean;
};
type TicketDraft = {
  requester_name: string;
  department: string;
  contact: string;
  title: string;
  description: string;
  product: string;
  priority: "low" | "normal" | "high";
};
type ChatReply = {
  message: string;
  model: string;
  phase: "question" | "summary" | "answer" | "offer_ticket";
  question_count: number;
  conversation_state: string | null;
  summary?: TicketDraft;
  duration_ms?: number;
  response_tokens?: number;
  tokens_estimated?: boolean;
};
type KnowledgeDocument = {
  id: string;
  area_id: string;
  area_name: string;
  kind: "document" | "resolution";
  title: string;
  filename: string;
  status: string;
  chunks: number;
  created_at: string;
};
type PendingChatRequest = {
  assistant: AssistantMode;
  action: "message" | "summarize";
  conversation_state: string | null;
  messages: ChatMessage[];
};
type ChatProgress = {
  response_tokens: number;
  tokens_estimated: boolean;
};
type AdminMetrics = {
  period_days: number;
  companies: number;
  active_providers: number;
  conversations: number;
  tickets_created: number;
  tickets_resolved: number;
  tickets_closed: number;
  documents_indexed: number;
  llm_requests: number;
  llm_failures: number;
  llm_response_tokens: number;
  average_llm_latency_ms: number;
  daily: { date: string; conversations: number; tickets: number }[];
};
function readableError(detail: unknown, fallback: string) {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail))
    return "Os dados da conversa não foram aceitos. Envie a mensagem novamente.";
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isForm =
    typeof FormData !== "undefined" && init.body instanceof FormData;
  if (!isForm && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/backend${path}`, {
    ...init,
    credentials: "same-origin",
    headers,
  });
  if (!response.ok) {
    let message = "Não foi possível concluir a operação";
    try {
      const data = await response.json();
      message = readableError(data.detail, message);
    } catch {}
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

async function streamChat(
  slug: string,
  request: PendingChatRequest & {
    area_id: string;
    public_context: string;
    requester_name: string;
    department: string;
  },
  onProgress: (progress: ChatProgress) => void,
): Promise<ChatReply> {
  const response = await fetch(
    `/backend/api/public/${encodeURIComponent(slug)}/chat/stream`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/x-ndjson",
      },
      body: JSON.stringify({
        ...request,
        messages: request.messages.map(({ role, content }) => ({
          role,
          content,
        })),
      }),
    },
  );
  if (!response.ok) {
    let message = "Não foi possível concluir a operação";
    try {
      const data = await response.json();
      message = readableError(data.detail, message);
    } catch {}
    throw new Error(message);
  }
  if (!response.body)
    throw new Error("O provedor não disponibilizou o progresso da resposta");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatReply | null = null;
  const consume = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "progress")
      onProgress({
        response_tokens: Number(event.response_tokens) || 0,
        tokens_estimated: event.tokens_estimated !== false,
      });
    if (event.type === "result") result = event.data as ChatReply;
    if (event.type === "error")
      throw new Error(
        readableError(event.detail, "Não foi possível concluir a resposta"),
      );
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) consume(line);
    if (done) break;
  }
  consume(buffer);
  if (!result) throw new Error("A resposta do assistente foi interrompida");
  return result;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [publicSlug, setPublicSlug] = useState<string | null>(null);
  useEffect(() => {
    const sync = () => { const match=location.hash.match(/^#\/abrir\/([a-z0-9-]+)$/);setPublicSlug(match?.[1] || null); };
    sync();
    addEventListener("hashchange", sync);
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
    return () => removeEventListener("hashchange", sync);
  }, []);
  if (loading) return <Loading />;
  if (publicSlug)
    return (
      <PublicPortal
        slug={publicSlug}
        onBack={() => {
          location.hash = "";
          setPublicSlug(null);
        }}
      />
    );
  if (!user) return <Login onLogin={setUser} />;
  return <Authenticated user={user} onUserChange={setUser} onLogout={() => setUser(null)} />;
}
function Loading() {
  return (
    <div className="login-page">
      <div className="login-card">
        <Brand />
        <p>Carregando ambiente seguro…</p>
      </div>
    </div>
  );
}
function Brand() {
  return (
    <div className="brand">
      <b>C</b>
      <span>
        <strong>Chamados</strong>
        <small>Suporte Zoho</small>
      </span>
    </div>
  );
}
function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ user: User }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ tenant_slug: tenantSlug.trim().toLowerCase(), email, password }),
      });
      onLogin(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <Brand />
        <div className="login-copy">
          <h1>Acessar central</h1>
          <p>Entre com sua conta da plataforma, empresa ou prestador.</p>
        </div>
        {error && <div className="form-error">{error}</div>}
        <label>
          Empresa
          <Input value={tenantSlug} onChange={(e) => setTenantSlug(e.target.value.toLowerCase())} placeholder="identificador-da-empresa" pattern="[a-z0-9-]{2,80}" required />
          <small>Administrador da plataforma: use <strong>plataforma</strong>.</small>
        </label>
        <label>
          E-mail
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Senha
          <div className="password-field">
            <Input
              type={show ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              minLength={8}
              required
            />
            <button type="button" onClick={() => setShow(!show)}>
              {show ? "Ocultar" : "Mostrar"}
            </button>
          </div>
        </label>
        <Button type="submit" disabled={busy}>
          {busy ? "Entrando…" : "Entrar"}
        </Button>
        <small>O link público é fornecido pela sua empresa.</small>
        <small>O acesso e as tentativas de autenticação são registrados.</small>
      </form>
    </div>
  );
}

function Authenticated({
  user,
  onUserChange,
  onLogout,
}: {
  user: User;
  onUserChange: (user: User) => void;
  onLogout: () => void;
}) {
  type Route = "dashboard" | "companies" | "audit" | "tickets" | "settings" | "users" | "areas" | "knowledge" | "account";
  const platform=user.role === "platform_admin";
  const companyAdmin=user.role === "company_admin";
  const [route, setRoute] = useState<Route>(
    platform ? "dashboard" : "tickets",
  );
  async function logout() {
    await api("/api/auth/logout", { method: "POST" });
    onLogout();
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav>
          {platform ? (
            <>
              <p>PLATAFORMA</p>
              <Nav
                active={route === "dashboard"}
                onClick={() => setRoute("dashboard")}
                icon={<LayoutDashboard />}
                label="Visão geral"
              />
              <Nav
                active={route === "companies"}
                onClick={() => setRoute("companies")}
                icon={<Building2 />}
                label="Empresas"
              />
              <Nav active={route === "audit"} onClick={() => setRoute("audit")} icon={<ScrollText />} label="Auditoria" />
              <Nav
                active={route === "settings"}
                onClick={() => setRoute("settings")}
                icon={<Settings />}
                label="Inteligência Artificial"
              />
            </>
          ) : (
            <>
              <p>ATENDIMENTO</p>
              <Nav active={route === "tickets"} onClick={() => setRoute("tickets")} icon={<Inbox />} label="Chamados" />
              {companyAdmin && <Nav active={route === "users"} onClick={() => setRoute("users")} icon={<Users />} label="Prestadores" />}
              {companyAdmin && <Nav active={route === "areas"} onClick={() => setRoute("areas")} icon={<Layers3 />} label="Áreas" />}
              {companyAdmin && <Nav active={route === "knowledge"} onClick={() => setRoute("knowledge")} icon={<BookOpen />} label="Base de conhecimento" />}
              {companyAdmin && <Nav active={route === "audit"} onClick={() => setRoute("audit")} icon={<ScrollText />} label="Auditoria" />}
              <Nav active={route === "account"} onClick={() => setRoute("account")} icon={<UserCircle />} label="Minha conta" />
            </>
          )}
          {!platform && user.tenant?.slug && <><p>PORTAL</p><a className="portal-link" href={`#/abrir/${user.tenant.slug}`}><ExternalLink /> Assistentes públicos</a></>}
        </nav>
        <div className="profile">
          {user.avatar_url ? <i className="profile-avatar" role="img" aria-label="Foto do perfil" style={{backgroundImage:`url(${user.avatar_url})`}} /> : <b>
            {user.name
              .split(" ")
              .map((x) => x[0])
              .join("")
              .slice(0, 2)}
          </b>}
          <span>
            <strong>{user.name}</strong>
            <small>
              {platform ? "Administrador da plataforma" : companyAdmin ? "Administrador da empresa" : user.area?.name || "Prestador"}
            </small>
          </span>
          <AlertDialog><AlertDialogTrigger asChild><button title="Sair"><LogOut /></button></AlertDialogTrigger><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Deseja sair do sistema?</AlertDialogTitle><AlertDialogDescription>Sua sessão será encerrada e será necessário entrar novamente.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancelar</AlertDialogCancel><AlertDialogAction onClick={logout}>Sair</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
        </div>
      </aside>
      <main>
        {route === "tickets" && !platform && <Tickets publicSlug={user.tenant?.slug} companyAdmin={companyAdmin} />}
        {route === "dashboard" && platform && <AdminDashboard />}
        {route === "companies" && platform && <CompanyManagement />}
        {route === "settings" && platform && <AISettings />}
        {route === "audit" && <AuditLogPage platform={platform} />}
        {route === "users" && companyAdmin && <UserManagement />}
        {route === "areas" && companyAdmin && <AreaManagement />}
        {route === "knowledge" && companyAdmin && <KnowledgeBase />}
        {route === "account" && !platform && <MyAccount user={user} onSaved={onUserChange} />}
      </main>
    </div>
  );
}
function Nav({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button className={active ? "active" : ""} onClick={onClick}>
      {icon}
      <span>{label}</span>
    </button>
  );
}
function PageHeader({
  eyebrow,
  title,
  actions,
}: {
  eyebrow: string;
  title: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="top">
      <div>
        <p>{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      {actions}
    </header>
  );
}

function Tickets({publicSlug,companyAdmin=false}:{publicSlug?:string;companyAdmin?:boolean}) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"list" | "kanban">("list");
  const [filters,setFilters]=useState({status:"all",priority:"all",department:"all",area:"all",product:"all"});
  const [selected, setSelected] = useState<Ticket | null>(null);
  const load = useCallback(
    () =>
      api<Ticket[]>("/api/tickets")
        .then((data) => {
          setTickets(data);
          setSelected((current) =>
            current
              ? data.find((ticket) => ticket.id === current.id) || null
              : null,
          );
          setError("");
        })
        .catch((e) => setError(e.message)),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
  const filtered = useMemo(
    () =>
      tickets.filter((t) =>
        [t.title,t.summary,t.product, t.requester_name, t.department,t.area_name||"", String(t.protocol)].some(
          (value) => value.toLowerCase().includes(query.toLowerCase()),
        ) && (filters.status==="all"||t.status===filters.status) && (filters.priority==="all"||t.priority===filters.priority) && (filters.department==="all"||t.department===filters.department) && (filters.area==="all"||t.area_id===filters.area) && (filters.product==="all"||t.product===filters.product),
      ),
    [tickets, query,filters],
  );
  const departments=useMemo(()=>Array.from(new Set(tickets.map(t=>t.department))).sort(),[tickets]);
  const areas=useMemo(()=>Array.from(new Map(tickets.map(t=>[t.area_id,{id:t.area_id,name:t.area_name||"Sem área"}])).values()),[tickets]);
  const products=useMemo(()=>Array.from(new Set(tickets.map(t=>t.product))).sort(),[tickets]);
  async function move(ticket: Ticket, status: string) {
    setError("");
    try {
      await api(`/api/tickets/${ticket.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      await load();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Não foi possível alterar o status",
      );
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="CENTRAL DE ATENDIMENTO"
        title="Chamados"
        actions={
          <div>
            <Button variant="outline" onClick={load}>
              <RefreshCw /> Atualizar
            </Button>
            <Button onClick={() => (location.hash = `#/abrir/${publicSlug}`)} disabled={!publicSlug}>
              <Plus /> Novo chamado
            </Button>
          </div>
        }
      />
      {error && <div className="form-error">{error}</div>}
      <section className="metrics">
        <Metric
          label="Novos"
          value={String(tickets.filter((t) => t.status === "new").length)}
          note="Aguardando triagem"
        />
        <Metric
          label="Em atendimento"
          value={String(
            tickets.filter((t) => ["analysis", "working"].includes(t.status))
              .length,
          )}
          note="Em andamento"
        />
        <Metric
          label="Aguardando"
          value={String(tickets.filter((t) => t.status === "waiting").length)}
          note="Resposta do solicitante"
        />
        <Metric
          label="Encerrados"
          value={String(tickets.filter((t) => t.status === "closed").length)}
          note="Finalizados"
        />
      </section>
      <section className="workspace">
        <div className="toolbar">
          <strong>
            Chamados da empresa <ChevronDown />
          </strong>
          <div className="tools">
            <label>
              <Search />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar por chamado, nome ou setor..."
              />
            </label>
            <span className="toggle">
              <button
                className={mode === "list" ? "on" : ""}
                onClick={() => setMode("list")}
                aria-label="Visualização em lista"
              >
                <List />
              </button>
              <button
                className={mode === "kanban" ? "on" : ""}
                onClick={() => setMode("kanban")}
                aria-label="Visualização em Kanban"
              >
                <Columns3 />
              </button>
            </span>
          </div>
        </div>
        <div className="ticket-filters" aria-label="Filtros personalizados">
          <Select value={filters.status} onValueChange={status=>setFilters({...filters,status})}><SelectTrigger><SelectValue placeholder="Status"/></SelectTrigger><SelectContent><SelectItem value="all">Todos os status</SelectItem>{columns.map(value=><SelectItem key={value} value={value}>{statusLabel[value]}</SelectItem>)}</SelectContent></Select>
          <Select value={filters.priority} onValueChange={priority=>setFilters({...filters,priority})}><SelectTrigger><SelectValue placeholder="Prioridade"/></SelectTrigger><SelectContent><SelectItem value="all">Todas as prioridades</SelectItem>{Object.entries(priorityLabel).map(([value,label])=><SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select>
          <Select value={filters.department} onValueChange={department=>setFilters({...filters,department})}><SelectTrigger><SelectValue placeholder="Setor"/></SelectTrigger><SelectContent><SelectItem value="all">Todos os setores</SelectItem>{departments.map(value=><SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select>
          <Select value={filters.area} onValueChange={area=>setFilters({...filters,area})}><SelectTrigger><SelectValue placeholder="Área"/></SelectTrigger><SelectContent><SelectItem value="all">Todas as áreas</SelectItem>{areas.map(value=><SelectItem key={value.id} value={value.id}>{value.name}</SelectItem>)}</SelectContent></Select>
          <Select value={filters.product} onValueChange={product=>setFilters({...filters,product})}><SelectTrigger><SelectValue placeholder="Problema/produto"/></SelectTrigger><SelectContent><SelectItem value="all">Todos os produtos</SelectItem>{products.map(value=><SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select>
          <Button variant="outline" onClick={()=>{setQuery("");setFilters({status:"all",priority:"all",department:"all",area:"all",product:"all"})}}>Limpar filtros</Button>
        </div>
        {tickets.length === 0 ? (
          <EmptyTickets publicSlug={publicSlug} />
        ) : mode === "list" ? (
          <TicketTable tickets={filtered} onSelect={setSelected} />
        ) : (
          <Kanban tickets={filtered} onSelect={setSelected} onMove={move} />
        )}
      </section>
      {selected && (
        <TicketDrawer
          ticket={selected}
          companyAdmin={companyAdmin}
          areas={areas}
          onClose={() => setSelected(null)}
          onChanged={load}
        />
      )}
    </>
  );
}
function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
      <i>
        <TicketCheck />
      </i>
    </article>
  );
}
function EmptyTickets({publicSlug}:{publicSlug?:string}) {
  return (
    <div className="empty-state">
      <Inbox />
      <h2>Nenhum chamado aberto</h2>
      <p>Os chamados enviados pelo portal público aparecerão aqui.</p>
      <Button onClick={() => (location.hash = `#/abrir/${publicSlug}`)} disabled={!publicSlug}>
        Abrir chamado de teste
      </Button>
    </div>
  );
}
const statusLabel: Record<string, string> = {
  new: "Novo",
  analysis: "Em análise",
  working: "Em execução",
  waiting: "Aguardando",
  validation: "Validação",
  resolved: "Resolvido",
  closed: "Encerrado",
  cancelled: "Cancelado",
};
const columns = [
  "new",
  "analysis",
  "working",
  "waiting",
  "validation",
  "resolved",
  "closed",
  "cancelled",
];
const priorityLabel: Record<string, string> = {
  low: "Baixa",
  normal: "Normal",
  high: "Alta",
};
const formatDate = (value: string) =>
  new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
function TicketTable({
  tickets,
  onSelect,
}: {
  tickets: Ticket[];
  onSelect: (t: Ticket) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Chamado</th>
            <th>Solicitante</th>
            <th>Setor</th>
            <th>Área</th>
            <th>Prioridade</th>
            <th>Abertura</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id} onClick={() => onSelect(t)}>
              <td>
                <small>#{t.protocol}</small>
                <strong>{t.title}</strong>
              </td>
              <td>{t.requester_name}</td>
              <td>{t.department}</td>
              <td>{t.area_name||"—"}</td>
              <td>
                <Badge variant="outline" className={t.priority}>
                  {priorityLabel[t.priority] || t.priority}
                </Badge>
              </td>
              <td>{formatDate(t.created_at)}</td>
              <td>
                <span className="status">
                  <i />
                  {statusLabel[t.status] || t.status}
                </span>
              </td>
              <td>
                <MoreHorizontal />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Kanban({
  tickets,
  onSelect,
  onMove,
}: {
  tickets: Ticket[];
  onSelect: (t: Ticket) => void;
  onMove: (t: Ticket, status: string) => void;
}) {
  const [dragged, setDragged] = useState<Ticket | null>(null);
  return (
    <div className="kanban">
      {columns.map((c) => (
        <section
          key={c}
          className="kanban-column"
          data-status={c}
          onDragOver={(event) => event.preventDefault()}
          onDrop={() => {
            if (dragged && dragged.status !== c) void onMove(dragged, c);
            setDragged(null);
          }}
        >
          <header>
            <span>
              <i />
              {statusLabel[c]}
            </span>
            <em>{tickets.filter((t) => t.status === c).length}</em>
          </header>
          {tickets
            .filter((t) => t.status === c)
            .map((t) => (
              <button
                key={t.id}
                draggable
                onDragStart={() => setDragged(t)}
                onDragEnd={() => setDragged(null)}
                onClick={() => onSelect(t)}
                aria-label={`Abrir chamado ${t.protocol}`}
              >
                <div>
                  <small>#{t.protocol}</small>
                  <Badge variant="outline" className={t.priority}>
                    {priorityLabel[t.priority]}
                  </Badge>
                </div>
                <strong>{t.title}</strong>
                <p>
                  {t.requester_name} · {t.department} · {t.area_name}
                </p>
                <footer>
                  <Clock3 /> {formatDate(t.created_at)}
                </footer>
              </button>
            ))}
        </section>
      ))}
    </div>
  );
}
function TicketDrawer({
  ticket,
  companyAdmin,
  areas,
  onClose,
  onChanged,
}: {
  ticket: Ticket;
  companyAdmin:boolean;
  areas:{id:string;name:string}[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [edit,setEdit]=useState({requester_name:ticket.requester_name,department:ticket.department,contact:ticket.contact||"",title:ticket.title,summary:ticket.summary,product:ticket.product,priority:ticket.priority,area_id:ticket.area_id});
  const [editError,setEditError]=useState("");
  async function changeStatus(status: string) {
    await api(`/api/tickets/${ticket.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    onChanged();
  }
  async function saveTicket(e:FormEvent){e.preventDefault();setEditError("");try{await api(`/api/tickets/${ticket.id}`,{method:"PATCH",body:JSON.stringify({...edit,contact:edit.contact||null})});onChanged()}catch(error){setEditError(error instanceof Error?error.message:"Não foi possível editar o chamado")}}
  const history = ticket.status_history.length
    ? ticket.status_history
    : [{ status: "new", entered_at: ticket.created_at, changed_by: null }];
  return (
    <div className="backdrop" onMouseDown={onClose}>
      <article className="drawer" onMouseDown={(e) => e.stopPropagation()}>
        <header>
          <div>
            <small>CHAMADO #{ticket.protocol}</small>
            <h2>{ticket.title}</h2>
          </div>
          <button onClick={onClose} aria-label="Fechar">
            <X />
          </button>
        </header>
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Visão geral</TabsTrigger>
            <TabsTrigger value="edit">Editar</TabsTrigger>
            <TabsTrigger value="history">Histórico</TabsTrigger>
            <TabsTrigger value="resolution">Resolução</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">
            <div className="ai-summary">
              <Sparkles />
              <div>
                <strong>Resumo da demanda</strong>
                <p>{ticket.summary}</p>
                <small>
                  <ShieldCheck /> Isolado pela empresa autenticada
                </small>
              </div>
            </div>
            {ticket.attachments.length>0&&<div className="ticket-attachments"><strong><Paperclip/> Imagens anexadas</strong>{ticket.attachments.map(item=><a key={item.id} href={item.url} target="_blank" rel="noreferrer"><Paperclip/>{item.filename}<small>{(item.size_bytes/1024/1024).toFixed(2)} MB</small></a>)}</div>}
            <div className="details ticket-details">
              <div>
                <span>Solicitante</span>
                <strong>{ticket.requester_name}</strong>
              </div>
              <div>
                <span>Setor</span>
                <strong>{ticket.department}</strong>
              </div>
              <div>
                <span>Produto</span>
                <strong>{ticket.product}</strong>
              </div>
              <div><span>Área</span><strong>{ticket.area_name||"—"}</strong></div>
              <div>
                <span>Status</span>
                <strong>{statusLabel[ticket.status]}</strong>
              </div>
              <div>
                <span>Prioridade</span>
                <strong>{priorityLabel[ticket.priority]}</strong>
              </div>
              <div>
                <span>Aberto em</span>
                <strong>{formatDate(ticket.created_at)}</strong>
              </div>
            </div>
            <label className="status-change">
              Alterar etapa
              <Select value={ticket.status} onValueChange={changeStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {columns.map((status) => (
                    <SelectItem key={status} value={status}>
                      {statusLabel[status]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
          </TabsContent>
          <TabsContent value="edit">
            <form className="ticket-edit-form" onSubmit={saveTicket}>
              {editError&&<div className="form-error">{editError}</div>}
              <label>Solicitante<Input value={edit.requester_name} onChange={e=>setEdit({...edit,requester_name:e.target.value})} required/></label>
              <label>Setor<Input value={edit.department} onChange={e=>setEdit({...edit,department:e.target.value})} required/></label>
              <label>Contato<Input value={edit.contact} onChange={e=>setEdit({...edit,contact:e.target.value})}/></label>
              <label>Título<Input value={edit.title} onChange={e=>setEdit({...edit,title:e.target.value})} required/></label>
              <label className="wide">Descrição<Textarea value={edit.summary} onChange={e=>setEdit({...edit,summary:e.target.value})} required/></label>
              <label>Produto<Input value={edit.product} onChange={e=>setEdit({...edit,product:e.target.value})} required/></label>
              <label>Prioridade<Select value={edit.priority} onValueChange={priority=>setEdit({...edit,priority})}><SelectTrigger><SelectValue/></SelectTrigger><SelectContent><SelectItem value="low">Baixa</SelectItem><SelectItem value="normal">Normal</SelectItem><SelectItem value="high">Alta</SelectItem></SelectContent></Select></label>
              {companyAdmin&&<label>Área<Select value={edit.area_id} onValueChange={area_id=>setEdit({...edit,area_id})}><SelectTrigger><SelectValue/></SelectTrigger><SelectContent>{areas.map(area=><SelectItem key={area.id} value={area.id}>{area.name}</SelectItem>)}</SelectContent></Select></label>}
              <Button type="submit" disabled={ticket.status==="closed"}><Pencil/>Salvar alterações</Button>
              {ticket.status==="closed"&&<small>Chamados encerrados permanecem somente para consulta.</small>}
            </form>
          </TabsContent>
          <TabsContent value="history">
            <div className="history status-timeline">
              {history.map((item, index) => (
                <p key={`${item.status}-${item.entered_at}-${index}`}>
                  <strong>{statusLabel[item.status] || item.status}</strong>
                  <small>{formatDate(item.entered_at)}</small>
                </p>
              ))}
            </div>
          </TabsContent>
          <TabsContent value="resolution">
            <Resolution
              key={`${ticket.id}-${ticket.resolution?.id || "new"}-${ticket.status}`}
              ticketId={ticket.id}
              existing={ticket.resolution}
              closed={ticket.status === "closed"}
              onResolved={onChanged}
            />
          </TabsContent>
        </Tabs>
      </article>
    </div>
  );
}
const EMPTY_RESOLUTION = {
  confirmed_problem: "",
  root_cause: "",
  solution: "",
  validation: "",
  reusable: true,
};
function Resolution({
  ticketId,
  existing,
  closed,
  onResolved,
}: {
  ticketId: string;
  existing: TicketResolution | null;
  closed: boolean;
  onResolved: () => void;
}) {
  const [form, setForm] = useState(
    existing
      ? {
          confirmed_problem: existing.confirmed_problem,
          root_cause: existing.root_cause,
          solution: existing.solution,
          validation: existing.validation,
          reusable: existing.reusable,
        }
      : EMPTY_RESOLUTION,
  );
  const [error, setError] = useState("");
  const set = (key: string, value: string | boolean) =>
    setForm({ ...form, [key]: value });
  async function save() {
    setError("");
    try {
      await api(`/api/tickets/${ticketId}/resolution`, {
        method: "POST",
        body: JSON.stringify(form),
      });
      onResolved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro");
    }
  }
  return (
    <div className="resolution">
      <h3>{existing ? "Resolução registrada" : "Registrar resolução"}</h3>
      {closed && (
        <div className="form-success">
          Esta resolução foi preservada após o encerramento do chamado.
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
      <label>
        Problema confirmado
        <Textarea
          value={form.confirmed_problem}
          onChange={(e) => set("confirmed_problem", e.target.value)}
          disabled={closed}
        />
      </label>
      <label>
        Causa encontrada
        <Textarea
          value={form.root_cause}
          onChange={(e) => set("root_cause", e.target.value)}
          disabled={closed}
        />
      </label>
      <label>
        Solução aplicada
        <Textarea
          value={form.solution}
          onChange={(e) => set("solution", e.target.value)}
          disabled={closed}
        />
      </label>
      <label>
        Como foi validado
        <Input
          value={form.validation}
          onChange={(e) => set("validation", e.target.value)}
          disabled={closed}
        />
      </label>
      <div>
        <span>
          <strong>Adicionar à base de conhecimento</strong>
          <small>
            {form.reusable
              ? "Esta resolução está disponível para o assistente virtual."
              : "Esta resolução não foi compartilhada com o assistente virtual."}
          </small>
        </span>
        <Switch
          checked={form.reusable}
          onCheckedChange={(v) => set("reusable", v)}
          disabled={closed}
        />
      </div>
      {!closed && (
        <Button onClick={save}>
          <CheckCircle2 />{" "}
          {existing ? "Atualizar resolução" : "Resolver chamado"}
        </Button>
      )}
    </div>
  );
}

function AdminDashboard() {
  const [days, setDays] = useState("30");
  const [data, setData] = useState<AdminMetrics | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(
    () =>
      api<AdminMetrics>(`/api/admin/metrics?days=${days}`)
        .then((value) => {
          setData(value);
          setError("");
        })
        .catch((e) => setError(e.message)),
    [days],
  );
  useEffect(() => {
    load();
  }, [load]);
  const peak = Math.max(
    1,
    ...(data?.daily.map((item) => item.conversations) || [1]),
  );
  return (
    <>
      <PageHeader
        eyebrow="ADMINISTRAÇÃO"
        title="Visão geral"
        actions={
          <div>
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="period-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Últimos 7 dias</SelectItem>
                <SelectItem value="30">Últimos 30 dias</SelectItem>
                <SelectItem value="90">Últimos 90 dias</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={load}>
              <RefreshCw /> Atualizar
            </Button>
          </div>
        }
      />
      {error && <div className="form-error">{error}</div>}
      {data && (
        <>
          <section className="metrics admin-metrics">
            <Metric label="Empresas ativas" value={String(data.companies)} note="Ambientes cadastrados" />
            <Metric
              label="Prestadores ativos"
              value={String(data.active_providers)}
              note="Contas habilitadas"
            />
            <Metric
              label="Conversas"
              value={String(data.conversations)}
              note={`Últimos ${data.period_days} dias`}
            />
            <Metric
              label="Chamados criados"
              value={String(data.tickets_created)}
              note="Somente volume agregado"
            />
            <Metric
              label="Encerrados"
              value={String(data.tickets_closed)}
              note={`${data.tickets_resolved} resolvidos`}
            />
          </section>
          <div className="admin-grid">
            <section className="usage-chart">
              <header>
                <div>
                  <h2>Uso dos assistentes</h2>
                  <p>Conversas por dia, sem expor conteúdo dos chamados.</p>
                </div>
                <Activity />
              </header>
              <div className="usage-bars">
                {data.daily.map((item) => (
                  <i
                    key={item.date}
                    title={`${item.date}: ${item.conversations} conversas`}
                    style={{
                      height: `${Math.max(4, (item.conversations / peak) * 100)}%`,
                    }}
                  />
                ))}
              </div>
              <footer>
                <span>{data.daily[0]?.date}</span>
                <span>{data.daily.at(-1)?.date}</span>
              </footer>
            </section>
            <section className="platform-metrics">
              <h2>Operação da plataforma</h2>
              <div>
                <span>
                  Requisições ao modelo<strong>{data.llm_requests}</strong>
                </span>
                <span>
                  Falhas do modelo<strong>{data.llm_failures}</strong>
                </span>
                <span>
                  Tokens de resposta
                  <strong>{data.llm_response_tokens.toLocaleString("pt-BR")}</strong>
                </span>
                <span>
                  Latência média
                  <strong>{data.average_llm_latency_ms} ms</strong>
                </span>
                <span>
                  Documentos indexados<strong>{data.documents_indexed}</strong>
                </span>
              </div>
              <small>
                <ShieldCheck /> Métricas agregadas; nomes, setores e textos dos
                chamados não são enviados ao painel administrativo.
              </small>
            </section>
          </div>
        </>
      )}
    </>
  );
}

type AIProvider =
  "ollama" | "openai" | "deepseek" | "groq" | "openrouter" | "custom";
type AIConnection = {
  provider: AIProvider;
  api_base_url: string;
  has_api_key: boolean;
};
type AIValidRules = {
  allow_plain_text_repair: boolean;
  reject_repeated_questions: boolean;
  require_context_reference: boolean;
  require_summary_fields: boolean;
};
type AIRuntimeForm = {
  assistant?: AssistantMode;
  model: string;
  embedding_model: string;
  conversation_source: "ollama" | "external";
  embedding_source: "ollama" | "external";
  context_size: number;
  max_tokens: number;
  temperature: number;
  response_timeout_seconds: number;
  valid_response_rules: AIValidRules;
};
type ExternalModel = { name: string; source: "external"; provider: AIProvider };
type AIModelCatalog = {
  ollama: OllamaModel[];
  external: ExternalModel[];
  ollama_error: string | null;
  external_error: string | null;
  provider: AIProvider;
  has_api_key: boolean;
};
type AISkill = {
  id: string;
  name: string;
  source_url: string;
  scope: "all" | "intake" | "support";
  active: boolean;
  content_preview: string;
  last_test_model: string | null;
  last_test_success: boolean | null;
  last_test_ms: number | null;
  last_test_at: string | null;
  created_at: string | null;
};
const PROVIDER_OPTIONS: { value: AIProvider; label: string }[] = [
  { value: "ollama", label: "Ollama local" },
  { value: "openai", label: "OpenAI" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "groq", label: "Groq" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "custom", label: "API compatível personalizada" },
];
const PROVIDER_URLS: Partial<Record<AIProvider, string>> = {
  openai: "https://api.openai.com/v1",
  deepseek: "https://api.deepseek.com",
  groq: "https://api.groq.com/openai/v1",
  openrouter: "https://openrouter.ai/api/v1",
};
const EMPTY_RULES: AIValidRules = {
  allow_plain_text_repair: true,
  reject_repeated_questions: true,
  require_context_reference: false,
  require_summary_fields: true,
};
const EMPTY_RUNTIME: AIRuntimeForm = {
  model: "",
  embedding_model: "",
  conversation_source: "ollama",
  embedding_source: "ollama",
  context_size: 8192,
  max_tokens: 512,
  temperature: 0.2,
  response_timeout_seconds: 90,
  valid_response_rules: EMPTY_RULES,
};
function ModelPicker({
  label,
  source,
  value,
  onChange,
  catalog,
}: {
  label: string;
  source: "ollama" | "external";
  value: string;
  onChange: (value: string) => void;
  catalog: AIModelCatalog;
}) {
  const choices =
    source === "ollama"
      ? catalog.ollama.map((item) => item.name)
      : catalog.external.map((item) => item.name);
  return (
    <label>
      {label}
      {choices.length ? (
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue placeholder="Selecione um modelo" />
          </SelectTrigger>
          <SelectContent>
            {choices.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Nome exato do modelo"
          maxLength={120}
        />
      )}
      <small>
        {source === "ollama"
          ? "Catálogo instalado nesta máquina."
          : "Modelo do provedor externo conectado."}
      </small>
    </label>
  );
}
function AISettings() {
  const [connection, setConnection] = useState<AIConnection>({
    provider: "ollama",
    api_base_url: "",
    has_api_key: false,
  });
  const [apiKey, setApiKey] = useState("");
  const [runtime, setRuntime] = useState<AIRuntimeForm>(EMPTY_RUNTIME);
  const [runtimeAssistant, setRuntimeAssistant] = useState<AssistantMode>("support");
  const [catalog, setCatalog] = useState<AIModelCatalog>({
    ollama: [],
    external: [],
    ollama_error: null,
    external_error: null,
    provider: "ollama",
    has_api_key: false,
  });
  const [skills, setSkills] = useState<AISkill[]>([]);
  const [skillUrl, setSkillUrl] = useState("");
  const [skillScope, setSkillScope] = useState<"all" | "intake" | "support">(
    "all",
  );
  const [testPrompt, setTestPrompt] = useState(
    "Mostre como esta Skill ajuda a elaborar uma pergunta contextualizada para um chamado sobre Zoho CRM.",
  );
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("Carregando configuração…");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const refreshCatalog = useCallback(async () => {
    const result = await api<AIModelCatalog>("/api/admin/ai/catalog");
    setCatalog(result);
    return result;
  }, []);
  const loadSkills = useCallback(
    async () => setSkills(await api<AISkill[]>("/api/admin/ai/skills")),
    [],
  );
  const load = useCallback(async () => {
    setError("");
    try {
      const [storedConnection, storedRuntime] = await Promise.all([
        api<{
          provider: AIProvider;
          api_base_url: string | null;
          has_api_key: boolean;
        }>("/api/admin/ai/connection"),
        api<AIRuntimeForm>("/api/admin/ai/runtime?assistant=support"),
      ]);
      setConnection({
        ...storedConnection,
        api_base_url: storedConnection.api_base_url || "",
      });
      setRuntime(storedRuntime);
      await Promise.all([refreshCatalog(), loadSkills()]);
      setStatus("Configuração carregada");
    } catch (e) {
      setStatus("Não foi possível carregar a configuração");
      setError(e instanceof Error ? e.message : "Erro ao carregar");
    }
  }, [loadSkills, refreshCatalog]);
  useEffect(() => {
    void load();
  }, [load]);
  async function selectRuntimeAssistant(value: string) {
    const assistant=value as AssistantMode;setRuntimeAssistant(assistant);setError("");
    try{setRuntime(await api<AIRuntimeForm>(`/api/admin/ai/runtime?assistant=${assistant}`));setStatus(`Configuração do ${assistant==="support"?"Assistente virtual":"Abrir um chamado"} carregada`)}catch(e){setError(e instanceof Error?e.message:"Erro ao carregar configuração")}
  }
  function chooseProvider(provider: AIProvider) {
    setConnection({
      ...connection,
      provider,
      api_base_url: provider === "ollama" ? "" : PROVIDER_URLS[provider] || "",
    });
    setApiKey("");
    setError("");
  }
  async function saveConnection() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<AIConnection & { saved: boolean }>(
        "/api/admin/ai/connection",
        {
          method: "PUT",
          body: JSON.stringify({
            provider: connection.provider,
            api_base_url: connection.api_base_url || undefined,
            api_key: apiKey || undefined,
          }),
        },
      );
      setConnection({
        provider: result.provider,
        api_base_url: result.api_base_url || "",
        has_api_key: result.has_api_key,
      });
      setApiKey("");
      await refreshCatalog();
      setNotice(
        connection.provider === "ollama"
          ? "Ollama definido como conexão local."
          : "API externa conectada com segurança.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao conectar provedor");
    } finally {
      setBusy(false);
    }
  }
  async function saveRuntime() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<AIRuntimeForm & { saved: boolean }>(
        "/api/admin/ai/runtime",
        { method: "PUT", body: JSON.stringify({ ...runtime, assistant: runtimeAssistant }) },
      );
      setRuntime(result);
      setNotice(`Configuração de ${runtimeAssistant==="support"?"Assistente virtual":"Abrir um chamado"} salva.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar modelos");
    } finally {
      setBusy(false);
    }
  }
  async function testModel() {
    setBusy(true);
    setError("");
    setStatus(`Testando ${runtime.model}…`);
    try {
      const result = await api<{
        model: string;
        latency_ms: number;
        message: string;
      }>(`/api/admin/ai/test?assistant=${runtimeAssistant}`, { method: "POST" });
      setStatus(
        `${result.model} respondeu corretamente em ${result.latency_ms} ms`,
      );
    } catch (e) {
      setStatus("O modelo não concluiu o teste");
      setError(e instanceof Error ? e.message : "Erro ao testar modelo");
    } finally {
      setBusy(false);
    }
  }
  async function importSkill(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const item = await api<AISkill>("/api/admin/ai/skills/import", {
        method: "POST",
        body: JSON.stringify({ source_url: skillUrl, scope: skillScope }),
      });
      setSkillUrl("");
      await loadSkills();
      setNotice(`${item.name} importada inativa. Teste antes de ativar.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao importar Skill");
    } finally {
      setBusy(false);
    }
  }
  async function updateSkill(
    item: AISkill,
    active = item.active,
    scope = item.scope,
  ) {
    setError("");
    try {
      await api(`/api/admin/ai/skills/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ active, scope }),
      });
      await loadSkills();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao atualizar Skill");
    }
  }
  async function testSkill(item: AISkill) {
    setBusy(true);
    setError("");
    setTestResults((current) => ({ ...current, [item.id]: "Testando…" }));
    try {
      const result = await api<{
        message: string;
        model: string;
        latency_ms: number;
      }>(`/api/admin/ai/skills/${item.id}/test`, {
        method: "POST",
        body: JSON.stringify({ prompt: testPrompt }),
      });
      setTestResults((current) => ({
        ...current,
        [item.id]: `${result.message} · ${result.model} em ${result.latency_ms} ms`,
      }));
      await loadSkills();
    } catch (e) {
      setTestResults((current) => ({
        ...current,
        [item.id]: e instanceof Error ? e.message : "Falha no teste",
      }));
    } finally {
      setBusy(false);
    }
  }
  const externalConnection = connection.provider !== "ollama";
  const externalReady = externalConnection && connection.has_api_key;
  return (
    <>
      <PageHeader
        eyebrow="ADMINISTRAÇÃO"
        title="Inteligência Artificial"
        actions={
          <Button variant="outline" onClick={() => void refreshCatalog()}>
            <RefreshCw /> Atualizar catálogo
          </Button>
        }
      />
      {error && <div className="form-error">{error}</div>}
      {notice && <div className="form-success">{notice}</div>}
      <Tabs defaultValue="add" className="ai-tabs">
        <TabsList>
          <TabsTrigger value="add">Adicionar Modelos</TabsTrigger>
          <TabsTrigger value="configure">Configurar Modelos</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
        </TabsList>
        <TabsContent value="add" className="ai-tab-panel">
          <div className="ai-grid">
            <section className="ai-card">
              <header>
                <i>
                  <Bot />
                </i>
                <span>
                  <h2>Ollama local</h2>
                  <p>
                    {catalog.ollama_error ||
                      `${catalog.ollama.length} modelo(s) reconhecido(s)`}
                  </p>
                </span>
                <em>
                  {catalog.ollama_error ? "● Indisponível" : "● Conectado"}
                </em>
              </header>
              <div className="model-list">
                <h3>Modelos instalados</h3>
                {catalog.ollama.map((model) => (
                  <article key={model.name}>
                    <Bot />
                    <span>
                      <strong>{model.name}</strong>
                      <small>
                        {[
                          model.details?.family,
                          model.details?.parameter_size,
                          model.details?.quantization_level,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "Detalhes não informados"}
                      </small>
                    </span>
                    <em>
                      {model.size
                        ? `${(model.size / 1024 / 1024 / 1024).toFixed(2)} GB`
                        : "—"}
                    </em>
                  </article>
                ))}
              </div>
            </section>
            <section className="ai-card">
              <header>
                <i>
                  <ExternalLink />
                </i>
                <span>
                  <h2>Conectar API externa</h2>
                  <p>Conexão compatível com Chat Completions.</p>
                </span>
                <em>
                  {externalReady ? "● Credencial pronta" : "● Não conectada"}
                </em>
              </header>
              <div className="form ai-provider-form">
                <label className="wide">
                  Provedor
                  <Select
                    value={connection.provider}
                    onValueChange={(value: AIProvider) => chooseProvider(value)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PROVIDER_OPTIONS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </label>
                {externalConnection && (
                  <>
                    <label className="wide">
                      URL base da API
                      <Input
                        type="url"
                        value={connection.api_base_url}
                        onChange={(event) =>
                          setConnection({
                            ...connection,
                            api_base_url: event.target.value,
                          })
                        }
                        placeholder="https://api.exemplo.com/v1"
                      />
                    </label>
                    <label className="wide">
                      Segredo da API
                      <Input
                        type="password"
                        value={apiKey}
                        onChange={(event) => setApiKey(event.target.value)}
                        placeholder={
                          connection.has_api_key
                            ? "Credencial já configurada"
                            : "Cole a chave da API"
                        }
                        autoComplete="new-password"
                      />
                      <small>
                        {connection.has_api_key
                          ? "Deixe vazio para manter a credencial atual."
                          : "O segredo não será exibido novamente."}
                      </small>
                    </label>
                    <div className="external-data-warning">
                      <ShieldCheck />
                      <span>
                        <strong>Fluxo de dados externo</strong>
                        <small>
                          Mensagens e contexto serão enviados ao provedor
                          somente quando um modelo externo for escolhido na aba
                          Configurar Modelos.
                        </small>
                      </span>
                    </div>
                  </>
                )}
              </div>
              <footer>
                <Button
                  onClick={saveConnection}
                  disabled={
                    busy ||
                    (externalConnection &&
                      (!connection.api_base_url ||
                        (!apiKey && !connection.has_api_key)))
                  }
                >
                  {busy ? "Salvando…" : "Salvar conexão"}
                </Button>
              </footer>
              {catalog.external.length > 0 && (
                <div className="model-list">
                  <h3>Modelos disponíveis na API</h3>
                  {catalog.external.map((model) => (
                    <article key={model.name}>
                      <ExternalLink />
                      <span>
                        <strong>{model.name}</strong>
                        <small>{model.provider}</small>
                      </span>
                    </article>
                  ))}
                </div>
              )}
              {catalog.external_error && (
                <div className="form-error">{catalog.external_error}</div>
              )}
            </section>
          </div>
        </TabsContent>
        <TabsContent value="configure" className="ai-tab-panel">
          <Tabs value={runtimeAssistant} onValueChange={selectRuntimeAssistant} className="assistant-runtime-tabs">
            <TabsList>
              <TabsTrigger value="support">Assistente virtual</TabsTrigger>
              <TabsTrigger value="intake">Abrir um chamado</TabsTrigger>
            </TabsList>
          </Tabs>
          <section className="ai-card runtime-card">
            <header>
              <i>
                <Settings />
              </i>
              <span>
                <h2>{runtimeAssistant==="support"?"Assistente virtual":"Abertura de chamados"}</h2>
                <p>{status}</p>
              </span>
              <em>{runtimeAssistant==="support"?"Orientação mais flexível":"Triagem com regras rigorosas"}</em>
            </header>
            <div className="runtime-grid">
              <label>
                Origem da conversação
                <Select
                  value={runtime.conversation_source}
                  onValueChange={(value: "ollama" | "external") =>
                    setRuntime({ ...runtime, conversation_source: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ollama">Ollama local</SelectItem>
                    <SelectItem value="external" disabled={!externalReady}>
                      API externa
                    </SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <ModelPicker
                label="Modelo de conversação"
                source={runtime.conversation_source}
                value={runtime.model}
                onChange={(model) => setRuntime({ ...runtime, model })}
                catalog={catalog}
              />
              <label>
                Origem dos embeddings
                <Select
                  value={runtime.embedding_source}
                  onValueChange={(value: "ollama" | "external") =>
                    setRuntime({ ...runtime, embedding_source: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ollama">Ollama local</SelectItem>
                    <SelectItem value="external" disabled={!externalReady}>
                      API externa
                    </SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <ModelPicker
                label="Modelo de embeddings"
                source={runtime.embedding_source}
                value={runtime.embedding_model}
                onChange={(embedding_model) =>
                  setRuntime({ ...runtime, embedding_model })
                }
                catalog={catalog}
              />
              <label>
                Contexto máximo
                <Input
                  type="number"
                  min={1024}
                  max={32768}
                  value={runtime.context_size}
                  onChange={(event) =>
                    setRuntime({
                      ...runtime,
                      context_size: Number(event.target.value),
                    })
                  }
                />
                <small>Tokens de entrada enviados ao modelo.</small>
              </label>
              <label>
                Tokens por resposta
                <Input
                  type="number"
                  min={64}
                  max={8192}
                  value={runtime.max_tokens}
                  onChange={(event) =>
                    setRuntime({
                      ...runtime,
                      max_tokens: Number(event.target.value),
                    })
                  }
                />
                <small>
                  Teto geral; cada pergunta de abertura usa no máximo 192
                  tokens.
                </small>
              </label>
              <label>
                Temperatura
                <Input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={runtime.temperature}
                  onChange={(event) =>
                    setRuntime({
                      ...runtime,
                      temperature: Number(event.target.value),
                    })
                  }
                />
                <small>Use 0,1–0,3 para respostas mais previsíveis.</small>
              </label>
              <label>
                Tempo limite de resposta (segundos)
                <Input
                  type="number"
                  min={15}
                  max={300}
                  value={runtime.response_timeout_seconds}
                  onChange={(event) =>
                    setRuntime({
                      ...runtime,
                      response_timeout_seconds: Number(event.target.value),
                    })
                  }
                />
                <small>
                  Teto geral; perguntas usam até 60 s e recebem fallback seguro
                  se o modelo falhar.
                </small>
              </label>
            </div>
            <div className="rule-list">
              <h3>Regras para respostas válidas</h3>
              <RuleSwitch
                label="Reparar texto simples"
                description="Converte uma resposta útil sem JSON para o contrato interno."
                checked={runtime.valid_response_rules.allow_plain_text_repair}
                onChange={(checked) =>
                  setRuntime({
                    ...runtime,
                    valid_response_rules: {
                      ...runtime.valid_response_rules,
                      allow_plain_text_repair: checked,
                    },
                  })
                }
              />
              <RuleSwitch
                label="Bloquear perguntas repetidas"
                description="Rejeita perguntas semanticamente muito parecidas no mesmo chamado."
                checked={runtime.valid_response_rules.reject_repeated_questions}
                onChange={(checked) =>
                  setRuntime({
                    ...runtime,
                    valid_response_rules: {
                      ...runtime.valid_response_rules,
                      reject_repeated_questions: checked,
                    },
                  })
                }
              />
              <RuleSwitch
                label="Exigir referência ao contexto"
                description="Mais rigoroso; modelos pequenos podem falhar repetidamente nesta regra."
                checked={runtime.valid_response_rules.require_context_reference}
                onChange={(checked) =>
                  setRuntime({
                    ...runtime,
                    valid_response_rules: {
                      ...runtime.valid_response_rules,
                      require_context_reference: checked,
                    },
                  })
                }
              />
              <RuleSwitch
                label="Exigir campos do resumo"
                description="Só aceita o resumo quando contém os campos mínimos do chamado."
                checked={runtime.valid_response_rules.require_summary_fields}
                onChange={(checked) =>
                  setRuntime({
                    ...runtime,
                    valid_response_rules: {
                      ...runtime.valid_response_rules,
                      require_summary_fields: checked,
                    },
                  })
                }
              />
            </div>
            <footer>
              <Button
                onClick={saveRuntime}
                disabled={busy || !runtime.model || !runtime.embedding_model}
              >
                Salvar configuração
              </Button>
              <Button
                variant="outline"
                onClick={testModel}
                disabled={busy || !runtime.model}
              >
                Testar modelo
              </Button>
            </footer>
          </section>
        </TabsContent>
        <TabsContent value="skills" className="ai-tab-panel">
          <div className="skill-layout">
            <form className="ai-card skill-import" onSubmit={importSkill}>
              <header>
                <i>
                  <Sparkles />
                </i>
                <span>
                  <h2>Importar Skill</h2>
                  <p>
                    Cole o link HTTPS do arquivo no GitHub, GitLab ou de uma
                    fonte Markdown pública.
                  </p>
                </span>
              </header>
              <label>
                Link da Skill
                <Input
                  type="url"
                  value={skillUrl}
                  onChange={(event) => setSkillUrl(event.target.value)}
                  placeholder="https://github.com/empresa/repositorio/blob/main/SKILL.md"
                  required
                />
              </label>
              <label>
                Aplicação
                <Select
                  value={skillScope}
                  onValueChange={(value: "all" | "intake" | "support") =>
                    setSkillScope(value)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Ambos os assistentes</SelectItem>
                    <SelectItem value="intake">Abertura de chamados</SelectItem>
                    <SelectItem value="support">Assistente virtual</SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <Button type="submit" disabled={busy || !skillUrl}>
                <Plus /> Importar Skill
              </Button>
              <small>
                <ShieldCheck /> Links comuns são convertidos para o arquivo
                bruto. O sistema bloqueia redes privadas e não executa scripts
                ou comandos contidos na Skill. Na abertura, somente a política
                compacta da Skill é enviada ao modelo local.
              </small>
            </form>
            <section className="ai-card skill-catalog">
              <header>
                <i>
                  <BookOpen />
                </i>
                <span>
                  <h2>Skills importadas</h2>
                  <p>
                    {skills.length} Skill(s) disponível(is) · uma Skill ativa
                    por assistente
                  </p>
                </span>
              </header>
              <label className="skill-test-prompt">
                Pergunta usada no teste
                <Textarea
                  value={testPrompt}
                  onChange={(event) => setTestPrompt(event.target.value)}
                  maxLength={1500}
                />
              </label>
              {skills.length === 0 ? (
                <div className="empty-knowledge">
                  <Sparkles />
                  <strong>Nenhuma Skill importada</strong>
                  <p>
                    Cole o link do arquivo SKILL.md para importar a primeira
                    Skill.
                  </p>
                </div>
              ) : (
                <div className="skill-list">
                  {skills.map((item) => (
                    <article key={item.id}>
                      <header>
                        <div>
                          <strong>{item.name}</strong>
                          <a
                            href={item.source_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Abrir fonte <ExternalLink />
                          </a>
                        </div>
                        <Switch
                          checked={item.active}
                          onCheckedChange={(checked) =>
                            void updateSkill(item, checked)
                          }
                        />
                      </header>
                      <p>{item.content_preview}</p>
                      <div>
                        <Select
                          value={item.scope}
                          onValueChange={(
                            scope: "all" | "intake" | "support",
                          ) => void updateSkill(item, item.active, scope)}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">Ambos</SelectItem>
                            <SelectItem value="intake">Abertura</SelectItem>
                            <SelectItem value="support">Suporte</SelectItem>
                          </SelectContent>
                        </Select>
                        <Button
                          variant="outline"
                          onClick={() => void testSkill(item)}
                          disabled={busy || testPrompt.length < 3}
                        >
                          Testar Skill
                        </Button>
                        <Badge variant="outline">
                          {item.active ? "Ativa" : "Inativa"}
                        </Badge>
                      </div>
                      {testResults[item.id] && (
                        <output>{testResults[item.id]}</output>
                      )}
                      {item.last_test_at && (
                        <small>
                          Último teste:{" "}
                          {item.last_test_success ? "aprovado" : "falhou"} ·{" "}
                          {item.last_test_model} · {item.last_test_ms} ms
                        </small>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </TabsContent>
      </Tabs>
    </>
  );
}
function RuleSwitch({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div>
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

const auditLabels:Record<string,string>={"auth.login":"Login realizado","auth.login_failed":"Tentativa de login recusada","auth.login_denied":"Login bloqueado","auth.logout":"Logout realizado","ticket.created":"Chamado criado","ticket.updated":"Chamado editado","ticket.status_changed":"Etapa alterada","ticket.resolution_saved":"Resolução salva","provider.created":"Prestador criado","provider.updated":"Prestador editado","provider.deleted":"Prestador excluído","area.created":"Área criada","area.updated":"Área editada","company.created":"Empresa criada","company.updated":"Empresa editada","account.updated":"Conta atualizada","ai.connection_updated":"Conexão de IA alterada","ai.runtime_updated":"Modelo configurado"};
function AuditLogPage({platform}:{platform:boolean}){
  const [entries,setEntries]=useState<AuditEntry[]>([]);const [error,setError]=useState("");const [action,setAction]=useState("all");
  const load=useCallback(()=>api<AuditEntry[]>(platform?"/api/platform/audit":"/api/company/audit").then(setEntries).catch(e=>setError(e.message)),[platform]);useEffect(()=>{load()},[load]);
  const actions=Array.from(new Set(entries.map(item=>item.action))).sort();const shown=action==="all"?entries:entries.filter(item=>item.action===action);
  return <><PageHeader eyebrow={platform?"PLATAFORMA":"EMPRESA"} title="Logs de auditoria" actions={<Button variant="outline" onClick={load}><RefreshCw/>Atualizar</Button>}/>{error&&<div className="form-error">{error}</div>}<section className="workspace audit-workspace"><div className="toolbar"><strong><ScrollText/>Ações registradas</strong><Select value={action} onValueChange={setAction}><SelectTrigger className="audit-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="all">Todas as ações</SelectItem>{actions.map(value=><SelectItem key={value} value={value}>{auditLabels[value]||value}</SelectItem>)}</SelectContent></Select></div><div className="table-wrap"><table><thead><tr><th>Data</th>{platform&&<th>Empresa</th>}<th>Responsável</th><th>Ação</th><th>Alvo</th><th>Detalhes</th></tr></thead><tbody>{shown.map(item=><tr key={item.id}><td>{formatDate(item.created_at)}</td>{platform&&<td>{item.tenant_name||"—"}</td>}<td><strong>{item.actor_name}</strong><small>{item.actor_role}</small></td><td>{auditLabels[item.action]||item.action}</td><td>{item.target_type}{item.target_id?` · ${item.target_id.slice(0,8)}`:""}</td><td><code>{Object.entries(item.details).map(([key,value])=>`${key}: ${Array.isArray(value)?value.join(", "):String(value)}`).join(" · ")||"—"}</code></td></tr>)}</tbody></table></div></section></>;
}

function CompanyManagement() {
  const [companies,setCompanies]=useState<Company[]>([]);const [error,setError]=useState("");const [notice,setNotice]=useState("");const [editing,setEditing]=useState<Company|null>(null);
  const [form,setForm]=useState({name:"",public_slug:"",manager_name:"",manager_email:"",manager_password:""});
  const load=useCallback(()=>api<Company[]>("/api/platform/companies").then(setCompanies).catch(e=>setError(e.message)),[]);useEffect(()=>{load()},[load]);
  async function create(e:FormEvent){e.preventDefault();setError("");setNotice("");try{const result=await api<{name:string;public_path:string}>("/api/platform/companies",{method:"POST",body:JSON.stringify(form)});setNotice(`${result.name} criada. Link público: ${location.origin}${result.public_path}`);setForm({name:"",public_slug:"",manager_name:"",manager_email:"",manager_password:""});load()}catch(err){setError(err instanceof Error?err.message:"Erro ao criar empresa")}}
  async function saveEdit(e:FormEvent){e.preventDefault();if(!editing)return;setError("");try{await api(`/api/platform/companies/${editing.id}`,{method:"PATCH",body:JSON.stringify(editing)});setEditing(null);setNotice("Empresa atualizada.");load()}catch(err){setError(err instanceof Error?err.message:"Erro ao editar empresa")}}
  return <><PageHeader eyebrow="PLATAFORMA" title="Empresas"/>{error&&<div className="form-error">{error}</div>}{notice&&<div className="form-success">{notice}</div>}<div className="users-layout"><form className="user-form" onSubmit={create}><h2>Nova empresa</h2><label>Nome<Input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} required/></label><label>Identificador do link<Input value={form.public_slug} onChange={e=>setForm({...form,public_slug:e.target.value.toLowerCase().replace(/[^a-z0-9-]/g,"")})} placeholder="minha-empresa" pattern="[a-z0-9-]{2,80}" required/></label><label>Nome do responsável<Input value={form.manager_name} onChange={e=>setForm({...form,manager_name:e.target.value})} required/></label><label>E-mail do responsável<Input type="email" value={form.manager_email} onChange={e=>setForm({...form,manager_email:e.target.value})} required/></label><label>Senha temporária<Input type="password" minLength={12} value={form.manager_password} onChange={e=>setForm({...form,manager_password:e.target.value})} required/></label><Button type="submit"><Plus/>Criar empresa</Button></form><section className="user-list"><h2>Empresas cadastradas</h2>{companies.map(company=><article key={company.id}><b><Building2/></b><span><strong>{company.name}</strong><small>{company.manager_name} · {company.manager_email}</small><a href={company.public_path}><ExternalLink/> Abrir portal</a></span><Badge variant="outline">{company.active?"Ativa":"Inativa"}</Badge><Button variant="outline" size="icon" aria-label={`Editar ${company.name}`} onClick={()=>setEditing({...company})}><Pencil/></Button></article>)}</section></div><Dialog open={!!editing} onOpenChange={open=>!open&&setEditing(null)}><DialogContent><DialogHeader><DialogTitle>Editar empresa</DialogTitle><DialogDescription>Altere a organização e a conta gestora. O histórico será preservado.</DialogDescription></DialogHeader>{editing&&<form className="dialog-form" onSubmit={saveEdit}><label>Nome<Input value={editing.name} onChange={e=>setEditing({...editing,name:e.target.value})}/></label><label>Identificador<Input value={editing.public_slug} onChange={e=>setEditing({...editing,public_slug:e.target.value.toLowerCase().replace(/[^a-z0-9-]/g,"")})}/></label><label>Nome do responsável<Input value={editing.manager_name} onChange={e=>setEditing({...editing,manager_name:e.target.value})}/></label><label>E-mail do responsável<Input type="email" value={editing.manager_email} onChange={e=>setEditing({...editing,manager_email:e.target.value})}/></label><label className="switch-line"><span><strong>Empresa ativa</strong><small>Ao desativar, login e portal público são bloqueados.</small></span><Switch checked={editing.active} onCheckedChange={active=>setEditing({...editing,active})}/></label><DialogFooter><Button type="submit">Salvar alterações</Button></DialogFooter></form>}</DialogContent></Dialog></>;
}

function AreaManagement() {
  const [areas,setAreas]=useState<Area[]>([]);const [name,setName]=useState("");const [error,setError]=useState("");const [editing,setEditing]=useState<Area|null>(null);
  const load=useCallback(()=>api<Area[]>("/api/company/areas").then(setAreas).catch(e=>setError(e.message)),[]);useEffect(()=>{load()},[load]);
  async function create(e:FormEvent){e.preventDefault();setError("");try{await api("/api/company/areas",{method:"POST",body:JSON.stringify({name})});setName("");load()}catch(err){setError(err instanceof Error?err.message:"Erro ao criar área")}}
  async function save(e:FormEvent){e.preventDefault();if(!editing)return;setError("");try{await api(`/api/company/areas/${editing.id}`,{method:"PATCH",body:JSON.stringify({name:editing.name,active:editing.active})});setEditing(null);load()}catch(err){setError(err instanceof Error?err.message:"Erro ao editar área")}}
  return <><PageHeader eyebrow="EMPRESA" title="Áreas de atendimento"/>{error&&<div className="form-error">{error}</div>}<div className="users-layout"><form className="user-form" onSubmit={create}><h2>Nova área</h2><p>Áreas isolam prestadores, chamados e fontes da IA.</p><label>Nome<Input value={name} onChange={e=>setName(e.target.value)} placeholder="Ex.: Financeiro" required/></label><Button type="submit"><Plus/>Criar área</Button></form><section className="user-list"><h2>Áreas cadastradas</h2>{areas.map(area=><article key={area.id}><b><Layers3/></b><span><strong>{area.name}</strong><small>Base e chamados próprios</small></span><Badge variant="outline">{area.active?"Ativa":"Inativa"}</Badge><Button variant="outline" size="icon" aria-label={`Editar ${area.name}`} onClick={()=>setEditing({...area})}><Pencil/></Button></article>)}</section></div><Dialog open={!!editing} onOpenChange={open=>!open&&setEditing(null)}><DialogContent><DialogHeader><DialogTitle>Editar área</DialogTitle><DialogDescription>Prestadores ativos precisam ser movidos ou desativados antes da área.</DialogDescription></DialogHeader>{editing&&<form className="dialog-form" onSubmit={save}><label>Nome<Input value={editing.name} onChange={e=>setEditing({...editing,name:e.target.value})}/></label><label className="switch-line"><span><strong>Área ativa</strong><small>Áreas inativas deixam de aparecer no portal.</small></span><Switch checked={editing.active} onCheckedChange={active=>setEditing({...editing,active})}/></label><DialogFooter><Button type="submit">Salvar alterações</Button></DialogFooter></form>}</DialogContent></Dialog></>;
}

function MyAccount({user,onSaved}:{user:User;onSaved:(user:User)=>void}) {
  const [name,setName]=useState(user.name);const [email,setEmail]=useState(user.email);const [photo,setPhoto]=useState<File|null>(null);const [error,setError]=useState("");const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);
  async function save(e:FormEvent){e.preventDefault();setBusy(true);setError("");setNotice("");const data=new FormData();data.append("name",name);data.append("email",email);if(photo)data.append("avatar",photo);try{const updated=await api<User>("/api/account",{method:"PUT",body:data});onSaved(updated);setNotice("Dados da conta atualizados.");setPhoto(null)}catch(err){setError(err instanceof Error?err.message:"Erro ao atualizar conta")}finally{setBusy(false)}}
  const companyAdmin=user.role==="company_admin";
  return <><PageHeader eyebrow="CONTA" title="Minha conta"/><form className="account-form" onSubmit={save}>{error&&<div className="form-error">{error}</div>}{notice&&<div className="form-success">{notice}</div>}<div className="account-photo">{user.avatar_url?<i className="account-avatar" role="img" aria-label="Foto do perfil" style={{backgroundImage:`url(${user.avatar_url})`}}/>:<UserCircle/>}<label><Camera/> Escolher foto<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setPhoto(e.target.files?.[0]||null)}/></label><small>JPEG, PNG ou WebP · máximo de 2 MB.</small></div><label>Nome<Input value={name} onChange={e=>setName(e.target.value)} maxLength={120} required/></label><label>E-mail<Input type="email" value={email} onChange={e=>setEmail(e.target.value)} maxLength={254} required disabled={companyAdmin}/>{companyAdmin&&<small>Solicite ao administrador master a alteração do e-mail.</small>}</label><label>Organização<Input value={user.tenant?.name||""} disabled/>{companyAdmin&&<small>A organização só pode ser alterada pelo administrador master.</small>}</label>{user.area&&<label>Área<Input value={user.area.name} disabled/></label>}<Button type="submit" disabled={busy}>{busy?"Salvando…":"Salvar alterações"}</Button></form></>;
}

function KnowledgeBase() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [areas,setAreas]=useState<Area[]>([]);
  const [areaId,setAreaId]=useState("");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(
    () =>
      api<KnowledgeDocument[]>(`/api/company/knowledge/documents${areaId?`?area_id=${areaId}`:""}`)
        .then(setDocuments)
        .catch((e) => setError(e.message)),
    [areaId],
  );
  useEffect(() => {
    load();
  }, [load]);
  useEffect(()=>{api<Area[]>("/api/company/areas").then(value=>{setAreas(value);setAreaId(current=>current||value[0]?.id||"")}).catch(e=>setError(e.message))},[]);
  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    const data = new FormData();
    data.append("file", file);
    data.append("title", title);
    data.append("area_id",areaId);
    try {
      const result = await api<{ title: string; chunks: number }>(
        "/api/company/knowledge/documents",
        { method: "POST", body: data },
      );
      setNotice(
        `${result.title} adicionado com ${result.chunks} trechos pesquisáveis.`,
      );
      setTitle("");
      setFile(null);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao enviar documento");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader eyebrow="ADMINISTRAÇÃO" title="Base de conhecimento" />
      <div className="knowledge-layout">
        <form className="knowledge-upload" onSubmit={upload}>
          <header>
            <i>
              <Upload />
            </i>
            <div>
              <h2>Adicionar documento</h2>
              <p>
                O assistente usa documentos e resoluções aprovadas como fontes.
              </p>
            </div>
          </header>
          {error && <div className="form-error">{error}</div>}
          {notice && <div className="form-success">{notice}</div>}
          <label>
            Título da fonte
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex.: Manual de automações do Zoho CRM"
              maxLength={180}
            />
          </label>
          <label>Área<Select value={areaId} onValueChange={setAreaId}><SelectTrigger><SelectValue placeholder="Selecione a área"/></SelectTrigger><SelectContent>{areas.map(area=><SelectItem key={area.id} value={area.id}>{area.name}</SelectItem>)}</SelectContent></Select></label>
          <label>
            Arquivo
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              required
            />
          </label>
          <small>
            PDF, DOCX, TXT ou Markdown · máximo de 10 MB · até 200 páginas.
          </small>
          <Button type="submit" disabled={!file || !areaId || busy}>
            <Upload /> {busy ? "Processando…" : "Enviar para a base"}
          </Button>
        </form>
        <section className="knowledge-list">
          <header>
            <div>
              <h2>Fontes disponíveis</h2>
              <p>{documents.length} fonte(s) ativa(s)</p>
            </div>
            <Button variant="outline" onClick={load}>
              <RefreshCw /> Atualizar
            </Button>
          </header>
          {documents.length === 0 ? (
            <div className="empty-knowledge">
              <BookOpen />
              <strong>A base ainda está vazia</strong>
              <p>
                Adicione documentos ou aprove uma resolução para o assistente
                virtual começar a responder com fontes internas.
              </p>
            </div>
          ) : (
            documents.map((document) => (
              <article key={`${document.kind}-${document.id}`}>
                <i>
                  {document.kind === "resolution" ? (
                    <TicketCheck />
                  ) : (
                    <FileText />
                  )}
                </i>
                <span>
                  <strong>{document.title}</strong>
                  <small>
                    {document.area_name} · {document.filename}
                    {document.kind === "document"
                      ? ` · ${document.chunks} trechos`
                      : " · disponível no RAG"}
                  </small>
                </span>
                <Badge variant="outline">
                  {document.kind === "resolution"
                    ? "Resolução aprovada"
                    : "Documento"}
                </Badge>
              </article>
            ))
          )}
        </section>
      </div>
    </>
  );
}

function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [areas,setAreas]=useState<Area[]>([]);
  const [editing,setEditing]=useState<User|null>(null);
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    area_id: "",
    role: "agent" as const,
  });
  const [error, setError] = useState("");
  const load = useCallback(
    () =>
      api<User[]>("/api/company/users")
        .then(setUsers)
        .catch((e) => setError(e.message)),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
  useEffect(()=>{api<Area[]>("/api/company/areas").then(value=>{setAreas(value);setForm(current=>({...current,area_id:current.area_id||value.find(area=>area.active)?.id||""}))}).catch(e=>setError(e.message))},[]);
  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/company/users", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setForm({ name: "", email: "", password: "", area_id:areas.find(area=>area.active)?.id||"", role: "agent" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro");
    }
  }
  async function saveEdit(e:FormEvent){e.preventDefault();if(!editing)return;setError("");try{await api(`/api/company/users/${editing.id}`,{method:"PATCH",body:JSON.stringify({name:editing.name,email:editing.email,area_id:editing.area_id,active:editing.active})});setEditing(null);load()}catch(err){setError(err instanceof Error?err.message:"Erro ao editar prestador")}}
  async function remove(user:User){setError("");try{await api(`/api/company/users/${user.id}`,{method:"DELETE"});load()}catch(err){setError(err instanceof Error?err.message:"Erro ao excluir prestador")}}
  return (
    <>
      <PageHeader eyebrow="ADMINISTRAÇÃO" title="Prestadores" />
      {error && <div className="form-error">{error}</div>}
      <div className="users-layout">
        <form className="user-form" onSubmit={create}>
          <h2>Novo prestador</h2>
          <label>
            Nome
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </label>
          <label>
            E-mail
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </label>
          <label>
            Senha temporária
            <Input
              type="password"
              minLength={12}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </label>
          <label>Área<Select value={form.area_id} onValueChange={area_id=>setForm({...form,area_id})}><SelectTrigger><SelectValue placeholder="Selecione a área"/></SelectTrigger><SelectContent>{areas.filter(area=>area.active).map(area=><SelectItem key={area.id} value={area.id}>{area.name}</SelectItem>)}</SelectContent></Select></label>
          <Button type="submit">
            <Plus /> Criar prestador
          </Button>
        </form>
        <section className="user-list">
          <h2>Prestadores cadastrados</h2>
          {users.map((u) => (
            <article key={u.id}>
              <b>
                {u.name
                  .split(" ")
                  .map((x) => x[0])
                  .join("")
                  .slice(0, 2)}
              </b>
              <span>
                <strong>{u.name}</strong>
                <small>{u.email} · {u.area_name}</small>
              </span>
              <Badge variant="outline">{u.active?"Ativo":"Inativo"}</Badge>
              <Button variant="outline" size="icon" aria-label={`Editar ${u.name}`} onClick={()=>setEditing({...u})}><Pencil/></Button>
              <AlertDialog><AlertDialogTrigger asChild><Button variant="outline" size="icon" aria-label={`Excluir ${u.name}`}><Trash2/></Button></AlertDialogTrigger><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Excluir este prestador?</AlertDialogTitle><AlertDialogDescription>O acesso será removido, mas o histórico de ações e chamados será preservado.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancelar</AlertDialogCancel><AlertDialogAction onClick={()=>remove(u)}>Excluir prestador</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
            </article>
          ))}
        </section>
      </div>
      <Dialog open={!!editing} onOpenChange={open=>!open&&setEditing(null)}><DialogContent><DialogHeader><DialogTitle>Editar prestador</DialogTitle><DialogDescription>Atualize o cadastro, a área e o acesso.</DialogDescription></DialogHeader>{editing&&<form className="dialog-form" onSubmit={saveEdit}><label>Nome<Input value={editing.name} onChange={e=>setEditing({...editing,name:e.target.value})}/></label><label>E-mail<Input type="email" value={editing.email} onChange={e=>setEditing({...editing,email:e.target.value})}/></label><label>Área<Select value={editing.area_id} onValueChange={area_id=>setEditing({...editing,area_id})}><SelectTrigger><SelectValue/></SelectTrigger><SelectContent>{areas.filter(area=>area.active||area.id===editing.area_id).map(area=><SelectItem key={area.id} value={area.id}>{area.name}</SelectItem>)}</SelectContent></Select></label><label className="switch-line"><span><strong>Prestador ativo</strong><small>Prestadores inativos não conseguem entrar.</small></span><Switch checked={editing.active!==false} onCheckedChange={active=>setEditing({...editing,active})}/></label><DialogFooter><Button type="submit">Salvar alterações</Button></DialogFooter></form>}</DialogContent></Dialog>
    </>
  );
}

const PRODUCTS = [
  "Zoho CRM",
  "Zoho Analytics",
  "Zoho Desk",
  "Zoho Creator",
  "Zoho Flow",
  "Zoho WorkDrive",
  "Zoho Sign",
  "Outro produto Zoho",
];
const EMPTY_TICKET: TicketDraft = {
  requester_name: "",
  department: "",
  contact: "",
  title: "",
  description: "",
  product: "Zoho CRM",
  priority: "normal",
};
function formatGenerationTime(milliseconds: number) {
  return `${(milliseconds / 1000).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} s`;
}
function PublicPortal({ slug,onBack }: { slug:string;onBack: () => void }) {
  const [context, setContext] = useState("");
  const [company,setCompany]=useState("");
  const [areas,setAreas]=useState<Area[]>([]);
  const [areaId,setAreaId]=useState("");
  const [model, setModel] = useState("Assistente");
  const [mode, setMode] = useState<AssistantMode | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [chatError, setChatError] = useState("");
  const [lastRequest, setLastRequest] = useState<PendingChatRequest | null>(
    null,
  );
  const [identity, setIdentity] = useState({
    requester_name: "",
    department: "",
  });
  const [protocol, setProtocol] = useState<number | null>(null);
  const [state, setState] = useState<string | null>(null);
  const [questionCount, setQuestionCount] = useState(0);
  const [summary, setSummary] = useState<TicketDraft | null>(null);
  const [attachments,setAttachments]=useState<File[]>([]);
  const [offerTicket, setOfferTicket] = useState(false);
  const [generationElapsed, setGenerationElapsed] = useState(0);
  const [generationTokens, setGenerationTokens] = useState(0);
  const [generationTokensEstimated, setGenerationTokensEstimated] =
    useState(true);
  useEffect(() => {
    api<{ public_context: string; model: string;company:string;areas:Area[] }>(`/api/public/${encodeURIComponent(slug)}`)
      .then((r) => {
        setContext(r.public_context);
        setModel(r.model);
        setCompany(r.company);
        setAreas(r.areas);
        setAreaId(r.areas[0]?.id||"");
      })
      .catch((e) => setError(e.message));
  }, [slug]);
  useEffect(() => {
    if (!busy) return;
    const started = performance.now();
    const timer = window.setInterval(
      () => setGenerationElapsed(performance.now() - started),
      100,
    );
    return () => window.clearInterval(timer);
  }, [busy]);
  function start(selected: AssistantMode) {
    setMode(selected);
    setState(null);
    setQuestionCount(0);
    setSummary(null);
    setAttachments([]);
    setOfferTicket(false);
    setChatError("");
    setLastRequest(null);
    setMessages([
      {
        role: "assistant",
        content:
          selected === "intake"
            ? "Preencha nome e setor acima e descreva o que está acontecendo. Farei até 5 perguntas contextualizadas para confirmar o entendimento e organizar o chamado; se as informações já estiverem completas, o resumo será preparado antes."
            : "Descreva sua dúvida. Vou procurar uma orientação nos documentos e nas resoluções aprovadas.",
      },
    ]);
  }
  async function runRequest(request: PendingChatRequest) {
    setGenerationElapsed(0);
    setGenerationTokens(0);
    setGenerationTokensEstimated(true);
    setBusy(true);
    setError("");
    setChatError("");
    setLastRequest(request);
    try {
      const result = await streamChat(
        slug,
        {
          area_id:areaId,
          public_context: context,
          requester_name: identity.requester_name,
          department: identity.department,
          ...request,
        },
        (progress) => {
          setGenerationTokens(progress.response_tokens);
          setGenerationTokensEstimated(progress.tokens_estimated);
        },
      );
      setModel(result.model);
      setState(result.conversation_state);
      setQuestionCount(result.question_count);
      setMessages([
        ...request.messages,
        {
          role: "assistant",
          content: result.message,
          duration_ms: result.duration_ms,
          response_tokens: result.response_tokens,
          tokens_estimated: result.tokens_estimated,
        },
      ]);
      setOfferTicket(result.phase === "offer_ticket");
      if (result.phase === "summary" && result.summary)
        setSummary({
          ...EMPTY_TICKET,
          ...result.summary,
          requester_name:
            identity.requester_name || result.summary.requester_name,
          department: identity.department || result.summary.department,
        });
      setLastRequest(null);
    } catch (e) {
      setChatError(
        e instanceof Error
          ? e.message
          : "O assistente demorou mais que o esperado",
      );
    } finally {
      setBusy(false);
    }
  }
  async function send(action: "message" | "summarize" = "message") {
    if (!mode || !context || !areaId || busy) return;
    if (action === "message" && !draft.trim()) return;
    if (
      action === "summarize" &&
      (!identity.requester_name.trim() || !identity.department.trim())
    ) {
      setChatError("Preencha nome e setor antes de gerar o resumo.");
      return;
    }
    const next =
      action === "message"
        ? [...messages, { role: "user" as const, content: draft.trim() }]
        : messages;
    if (action === "message") {
      setMessages(next);
      setDraft("");
    }
    await runRequest({
      assistant: mode,
      action,
      conversation_state: state,
      messages: next,
    });
  }
  function handoff() {
    setMode("intake");
    setState(null);
    setQuestionCount(0);
    setSummary(null);
    setAttachments([]);
    setOfferTicket(false);
    setChatError("");
    setLastRequest(null);
    setMessages((previous) => [
      ...previous,
      {
        role: "assistant",
        content:
          "Vou transformar esta conversa em chamado. Preencha nome e setor nos campos acima; farei até 5 perguntas para organizar a demanda, sem repetir o que já foi esclarecido.",
      },
    ]);
  }
  async function submitTicket() {
    if (!summary || !context) return;
    if (
      !summary.requester_name.trim() ||
      !summary.department.trim() ||
      summary.description.trim().length < 10
    ) {
      setError(
        "Revise o resumo e informe pelo menos nome, setor e uma descrição da demanda.",
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      if(attachments.length>5||attachments.reduce((total,file)=>total+file.size,0)>15*1024*1024)throw new Error("Envie no máximo 5 imagens somando até 15 MB.");
      const payload={...summary,area_id:areaId,assistant_mode:"intake",public_context:context};let result:{protocol:number};
      if(attachments.length){const body=new FormData();body.append("payload",JSON.stringify(payload));attachments.forEach(file=>body.append("files",file));result=await api<{protocol:number}>(`/api/public/${encodeURIComponent(slug)}/tickets/with-attachments`,{method:"POST",body})}else{result=await api<{protocol:number}>(`/api/public/${encodeURIComponent(slug)}/tickets`,{method:"POST",body:JSON.stringify(payload)})}
      setProtocol(result.protocol);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao criar chamado");
    } finally {
      setBusy(false);
    }
  }
  if (protocol)
    return (
      <div className="public">
        <section className="success-card">
          <CheckCircle2 />
          <h1>Chamado #{protocol} criado</h1>
          <p>Sua solicitação foi encaminhada ao suporte.</p>
          <Button onClick={onBack}>Voltar</Button>
        </section>
      </div>
    );
  if (!mode)
    return (
      <div className="public">
        <button className="back-login" onClick={onBack}>
          ← Voltar ao login
        </button>
        <section className="assistant-choice">
          <Brand />
          <div>
            <small>COMO PODEMOS AJUDAR?</small>
            <h1>{company||"Escolha o tipo de atendimento"}</h1>
            <p>
              Você pode tentar encontrar uma solução ou abrir um chamado
              diretamente.
            </p>
          </div>
          <label className="area-choice">Área do atendimento<Select value={areaId} onValueChange={setAreaId}><SelectTrigger><SelectValue placeholder="Selecione a área"/></SelectTrigger><SelectContent>{areas.map(area=><SelectItem key={area.id} value={area.id}>{area.name}</SelectItem>)}</SelectContent></Select><small>A escolha define quais prestadores, documentos e chamados a IA poderá consultar.</small></label>
          {error && <div className="form-error">{error}</div>}
          <button onClick={() => start("support")} disabled={!context||!areaId}>
            <i>
              <Sparkles />
            </i>
            <span>
              <strong>Assistente virtual</strong>
              <small>
                Consulta documentos e resoluções aprovadas para tentar orientar
                você.
              </small>
            </span>
            <ChevronDown />
          </button>
          <button onClick={() => start("intake")} disabled={!context||!areaId}>
            <i>
              <TicketCheck />
            </i>
            <span>
              <strong>Abrir um chamado</strong>
              <small>
                Faz até 5 perguntas direcionadas e prepara um resumo editável
                para envio.
              </small>
            </span>
            <ChevronDown />
          </button>
          <small className="privacy-note">
            <ShieldCheck /> Nunca envie senhas, tokens ou códigos de acesso.
          </small>
        </section>
      </div>
    );
  return (
    <div className="public">
      <button className="back-login" onClick={() => setMode(null)}>
        ← Escolher outro atendimento
      </button>
      <section className="chat public-chat">
        <header>
          <i>{mode === "support" ? <Sparkles /> : <Bot />}</i>
          <span>
            <strong>
              {mode === "support"
                ? "Assistente virtual"
                : "Assistente de abertura"}
            </strong>
            <small>
              {context
                ? mode === "intake" && questionCount
                  ? `Pergunta ${questionCount} de 5 · ${model}`
                  : `● Online · ${model}`
                : "Conectando…"}
            </small>
          </span>
        </header>
        {mode === "intake" && (
          <div className="public-fields">
            <label>
              Nome
              <Input
                placeholder="Seu nome"
                value={identity.requester_name}
                onChange={(event) =>
                  setIdentity({
                    ...identity,
                    requester_name: event.target.value,
                  })
                }
                maxLength={120}
              />
            </label>
            <label>
              Setor
              <Input
                placeholder="Seu setor"
                value={identity.department}
                onChange={(event) =>
                  setIdentity({ ...identity, department: event.target.value })
                }
                maxLength={120}
              />
            </label>
          </div>
        )}
        <div className="chat-body" aria-live="polite">
          {error && <div className="form-error">{error}</div>}
          {messages.map((message, index) => (
            <p
              key={index}
              className={message.role === "user" ? "user" : "assistant"}
            >
              <span>{message.content}</span>
              {message.role === "assistant" &&
                message.duration_ms !== undefined &&
                message.duration_ms > 0 && (
                  <small className="generation-metrics">
                    <Clock3 /> {formatGenerationTime(message.duration_ms)} ·{" "}
                    {message.tokens_estimated ? "≈" : ""}
                    {message.response_tokens ?? 0}{" "}
                    {(message.response_tokens ?? 0) === 1 ? "token" : "tokens"}
                  </small>
                )}
            </p>
          ))}
          {busy && (
            <div className="typing" role="status">
              <Bot />
              <span>
                {model} está digitando · {formatGenerationTime(generationElapsed)} ·{" "}
                {generationTokensEstimated ? "≈" : ""}
                {generationTokens} {generationTokens === 1 ? "token" : "tokens"}
              </span>
              <i />
              <i />
              <i />
            </div>
          )}
          {chatError && (
            <div className="chat-retry" role="alert">
              <Bot />
              <span>
                <strong>Não consegui concluir agora</strong>
                <small>{chatError}</small>
              </span>
              {lastRequest && (
                <Button
                  variant="outline"
                  onClick={() => runRequest(lastRequest)}
                >
                  Enviar novamente
                </Button>
              )}
            </div>
          )}
          {offerTicket && (
            <Button variant="outline" className="handoff" onClick={handoff}>
              <TicketCheck /> Abrir chamado com esta conversa
            </Button>
          )}
        </div>
        {summary && (
          <section className="summary-editor">
            <header>
              <Sparkles />
              <div>
                <strong>Resumo do chamado</strong>
                <small>Revise e edite antes de enviar.</small>
              </div>
            </header>
            <div>
              <label>
                Seu nome
                <Input
                  value={summary.requester_name}
                  onChange={(e) =>
                    setSummary({ ...summary, requester_name: e.target.value })
                  }
                />
              </label>
              <label>
                Setor
                <Input
                  value={summary.department}
                  onChange={(e) =>
                    setSummary({ ...summary, department: e.target.value })
                  }
                />
              </label>
              <label className="wide">
                Título
                <Input
                  value={summary.title}
                  onChange={(e) =>
                    setSummary({ ...summary, title: e.target.value })
                  }
                />
              </label>
              <label className="wide">
                Descrição
                <Textarea
                  value={summary.description}
                  onChange={(e) =>
                    setSummary({ ...summary, description: e.target.value })
                  }
                />
              </label>
              <label>
                Produto
                <Select
                  value={summary.product || "Zoho CRM"}
                  onValueChange={(value) =>
                    setSummary({ ...summary, product: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PRODUCTS.map((product) => (
                      <SelectItem key={product} value={product}>
                        {product}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label>
                Prioridade
                <Select
                  value={summary.priority}
                  onValueChange={(value: "low" | "normal" | "high") =>
                    setSummary({ ...summary, priority: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Baixa</SelectItem>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="high">Alta</SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <label className="wide ticket-image-upload"><span><Paperclip/> Imagens do problema</span><input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={e=>{const files=Array.from(e.target.files||[]);const total=files.reduce((sum,file)=>sum+file.size,0);if(files.length>5||total>15*1024*1024){setError("Envie no máximo 5 imagens somando até 15 MB.");e.target.value="";setAttachments([])}else{setError("");setAttachments(files)}}}/><small>Até 5 imagens JPEG, PNG ou WebP, somando no máximo 15 MB.</small>{attachments.length>0&&<em>{attachments.length} arquivo(s) · {(attachments.reduce((sum,file)=>sum+file.size,0)/1024/1024).toFixed(2)} MB</em>}</label>
            </div>
            <Button onClick={submitTicket} disabled={busy}>
              <Send /> Enviar chamado
            </Button>
          </section>
        )}
        {!summary && (
          <footer>
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder={
                mode === "support"
                  ? "Escreva sua dúvida..."
                  : "Descreva a demanda..."
              }
              disabled={busy}
            />
            <Button
              onClick={() => send()}
              disabled={busy || !context || !draft.trim()}
              aria-label="Enviar mensagem"
            >
              <Send />
            </Button>
            {mode === "intake" &&
              messages.some((message) => message.role === "user") && (
                <Button
                  className="finish-ticket"
                  variant="outline"
                  onClick={() => send("summarize")}
                  disabled={busy}
                >
                  Gerar resumo agora
                </Button>
              )}
            {mode === "support" &&
              messages.some((message) => message.role === "user") &&
              !offerTicket && (
                <Button
                  className="finish-ticket"
                  variant="outline"
                  onClick={handoff}
                >
                  Prefiro abrir um chamado
                </Button>
              )}
            <small>Não compartilhe senhas, tokens ou códigos de acesso.</small>
          </footer>
        )}
      </section>
    </div>
  );
}
