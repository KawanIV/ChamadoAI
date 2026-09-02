import test from "node:test";import assert from "node:assert/strict";import fs from "node:fs";
const page=fs.readFileSync(new URL("../app/page.tsx",import.meta.url),"utf8");
test("MVP expõe login e superfícies protegidas",()=>{for(const text of ["Acessar central","Administrador","Prestador","Chamados","Inteligência Artificial","Registrar resolução","Usuários cadastrados"])assert.match(page,new RegExp(text))});
test("o fechamento revisado controla a base de conhecimento",()=>{assert.match(page,/Adicionar à base de conhecimento/);assert.match(page,/Resolver chamado/)})
test("modelos são carregados dinamicamente do backend",()=>{assert.match(page,/api\/admin\/ai\/models/);assert.match(page,/models\.map/);assert.doesNotMatch(page,/Ternary-Bonsai 8B|RWKV-7 7B/)})
test("requisições autenticadas usam proxy de mesma origem e cookie HttpOnly",()=>{assert.match(page,/fetch\(`\/backend/);assert.match(page,/credentials:"same-origin"/);assert.doesNotMatch(page,/localStorage.*token|sessionStorage.*token|localhost:8001/)})
test("proxy interno não expõe o endereço da API ao navegador",()=>{const proxy=fs.readFileSync(new URL("../app/backend/[...path]/route.ts",import.meta.url),"utf8");assert.match(proxy,/API_INTERNAL_URL/);assert.match(proxy,/http:\/\/api:8000/);assert.match(proxy,/cache: "no-store"/)})
