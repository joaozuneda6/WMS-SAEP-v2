# Plano — Fechar superfícies residuais do admin (#113)

## Escopo

Fechar as brechas residuais do achado R4 (auditoria de admin): superfícies onde
o superusuário ainda contorna ledger, numeração ou trilha de auditoria pelo
Django admin. `RequisicaoAdmin`/`ItemRequisicaoAdmin`/`TimelineRequisicaoAdmin`
e `SaldoEstoqueAdmin`/`EstoqueAdmin`/`MaterialAdmin` já foram blindados nos
issues #102/#104/#105 — este issue cobre o que sobrou.

**Muda:**

- `apps/estoque/admin.py`
  - `MovimentacaoEstoqueAdmin`: `has_add_permission = False` (LED-01/LED-02 —
    linha de ledger sem mutação de saldo correspondente quebra reconciliação).
  - `SaidaExcepcionalAdmin`: `has_add_permission`, `has_change_permission`,
    `has_delete_permission` → `False`. Leitura (`list_display`, filtros,
    inline de itens em modo consulta) permanece.
  - `SequenciaSaidaExcepcionalAdmin`: `ultimo_numero` (e `ano`) somente-leitura
    — regressão de `ultimo_numero` colide com `numero_publico` unique no
    próximo envio (`IntegrityError` → 500).
  - `ImportacaoSCPIAdmin`: `has_delete_permission = False` — apagar libera
    reimportação do mesmo arquivo (dedup por `arquivo_hash`).
- `apps/requisicoes/admin.py`
  - `SequenciaRequisicaoAdmin`: mesmo guard de somente-leitura em
    `ultimo_numero`/`ano`.
  - `RequisicaoAdmin`: `has_delete_permission = False`; `criador`,
    `beneficiario`, `setor_beneficiario` movidos para `readonly_fields` (e
    saem do formulário via `get_form`, mesmo padrão já usado para `estado`).

**Não muda:**

- Nenhum service, policy, model ou migration.
- Leitura (`list_display`, `list_filter`, `search_fields`, changelist,
  `has_view_permission` default) segue aberta em todos os models acima.
- `ItemSaidaExcepcionalInline` não ganha guard próprio neste issue — a inline
  já herda `has_add/change/delete_permission` do parent `SaidaExcepcionalAdmin`
  quando o parent nega (`InlineModelAdmin` consulta o admin do model pai por
  padrão só se o inline não sobrescrever; aqui `ItemSaidaExcepcionalInline`
  não sobrescreve nada, então herda do próprio `ModelAdmin` do inline, que é
  o default do Django — **confirmar em teste** que negar no
  `SaidaExcepcionalAdmin` basta para a inline, ou adicionar guard explícito se
  o teste mostrar que não basta).

## Arquivos tocados

| Arquivo | Símbolo | Mudança |
|---|---|---|
| `apps/estoque/admin.py` | `MovimentacaoEstoqueAdmin` | `has_add_permission` |
| `apps/estoque/admin.py` | `SaidaExcepcionalAdmin` | `has_add/change/delete_permission` |
| `apps/estoque/admin.py` | `SequenciaSaidaExcepcionalAdmin` | `readonly_fields` (+ `has_add_permission`? não — sequência já existe via migration/signal; só bloquear edição destrutiva de `ultimo_numero`) |
| `apps/estoque/admin.py` | `ImportacaoSCPIAdmin` | `has_delete_permission` |
| `apps/requisicoes/admin.py` | `SequenciaRequisicaoAdmin` | `readonly_fields` |
| `apps/requisicoes/admin.py` | `RequisicaoAdmin` | `has_delete_permission`, `readonly_fields` |
| `apps/estoque/tests/test_admin.py` | novo | cobertura das 4 mudanças de estoque |
| `apps/requisicoes/tests/test_admin.py` | novo | cobertura das 2 mudanças de requisições |

Nota sobre `Sequencia*Admin`: não há `has_add_permission = False` no plano —
a sequência é criada por `get_or_create` no service na primeira emissão de
número; bloquear add pelo admin não é pedido pelo issue e a AC só fala em
"editável" (change). Ficamos com `readonly_fields = ('ano', 'ultimo_numero')`
+ manter `has_change_permission` default (a view de change ainda abre, mas
sem campos editáveis — mesmo padrão de `TimelineRequisicao`/`estado`). Se o
AC exigir 403 explícito em vez de formulário vazio, ajustar para
`has_change_permission = False` durante o TDD.

## Estratégia de testes

Seguir o padrão já estabelecido em `apps/requisicoes/tests/test_admin.py`
(issue #105): fixtures `request_de` (RequestFactory autenticado) e um staff
**não superusuário** com a permissão Django concedida, para provar que a
negação vem do guard e não do sistema de permissões padrão.

Por superfície:

- **`MovimentacaoEstoqueAdmin`**: `has_add_permission` → `False` direto;
  GET em `admin:estoque_movimentacaoestoque_add` → 403; changelist segue 200.
- **`SaidaExcepcionalAdmin`**: `has_add/change/delete_permission` → `False`;
  GET add → 403; POST change em saída existente → 403 sem mutar; POST delete
  → 403 sem apagar; changelist e change-view (GET, só leitura) seguem 200/leem.
- **`SequenciaSaidaExcepcionalAdmin` / `SequenciaRequisicaoAdmin`**:
  `readonly_fields` cobre `ultimo_numero`; `get_form` confirma campo fora do
  formulário; POST com `ultimo_numero` alterado não muta o valor no banco.
- **`ImportacaoSCPIAdmin`**: `has_delete_permission` → `False`; POST delete →
  403 sem apagar; reimportação do mesmo hash seguiria bloqueada (já coberto
  por teste de service — não duplicar aqui).
- **`RequisicaoAdmin`**: `has_delete_permission` → `False`; POST delete → 403
  sem apagar; `criador`/`beneficiario`/`setor_beneficiario` em
  `readonly_fields`; `get_form` confirma os três fora do formulário; POST que
  tenta trocar `beneficiario` não muta (caminho feliz de campo não-derivado —
  `observacao_geral` — continua editável, replicando
  `test_post_no_admin_altera_campo_nao_derivado_da_requisicao`).

Casos por mudança: happy path (permissão negada / campo fora do form),
permissão Django concedida mas guard nega mesmo assim (staff fixture),
leitura/changelist permanece 200.

## Invariantes relevantes (`docs/matriz-invariantes.md`)

- **LED-01** — toda mutação de `SaldoEstoque` pelos services gera
  `MovimentacaoEstoque` na mesma transação. `MovimentacaoEstoqueAdmin.add`
  quebra isso ao inserir linha de ledger sem tocar o saldo.
- **LED-02** — `Σ delta` por `(estoque, material)` reconcilia com o saldo.
  Mesma brecha acima quebra a reconciliação.
- **REQ-08** — timeline visível a autorizados. Não é tocado por escrita aqui,
  mas justifica manter leitura aberta em todos os admins deste plano.

## Riscos

- **Regressão de admin index/menu**: qualquer `ModelAdmin` com
  `has_*_permission` mal implementado pode derrubar `admin:index` inteiro
  (classe de regressão do #104) — cobrir com o mesmo smoke
  (`test_admin_index_responde_para_superusuario`) se ainda não cobre os models
  tocados aqui.
- **Inline de `SaidaExcepcional`**: risco de a inline não herdar a negação do
  parent e continuar permitindo add de item pela change view mesmo com o
  parent bloqueado para add — mitigado pelo teste dedicado descrito acima.
- **Sem migration**: mudança é só de `ModelAdmin`, não há schema envolvido —
  não aciona o fluxo de `make setup`.
