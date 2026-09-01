import test from "node:test";import assert from "node:assert/strict";import fs from "node:fs";
const page=fs.readFileSync(new URL("../app/page.tsx",import.meta.url),"utf8");
test("MVP expõe as superfícies principais",()=>{for(const text of ["Chamados","Portal público","Inteligência Artificial","Ternary-Bonsai 8B","RWKV-7 7B","Registrar resolução","Casos semelhantes"])assert.match(page,new RegExp(text))});
test("o fechamento revisado controla a base de conhecimento",()=>{assert.match(page,/Adicionar à base de conhecimento/);assert.match(page,/Resolver chamado/)})
