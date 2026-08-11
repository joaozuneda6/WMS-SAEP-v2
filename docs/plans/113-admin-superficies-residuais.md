# Plano — Fechar superfícies residuais do admin (#113)

## Escopo

Fechar as brechas residuais do achado R4 (auditoria de admin): superfícies onde
o superusuário ainda contorna ledger, numeração ou trilha de auditoria pelo
Django admin. `RequisicaoAdmin`/`ItemRequisicaoAdmin`/`TimelineRequisicaoAdmin`
e `SaldoEstoqueAdmin`/`EstoqueAdmin`/`MaterialAdmin` já foram blindados nos
issues #102/#104/#105 — este issue cobre o que sobrou.

**Muda:**

- `apps/estoque/admin.py`
  - `MovimentacaoEstoqueAdmin`: `has_add_permission(self, request)`,
    `has_change_permission(self, request, obj=None)`,
    `has_delete_permission(self, request, obj=None)` → todos retornam
    `False`. Add fecha a brecha do issue (LED-01/LED-02 — linha de ledger sem
    mutação de saldo correspondente quebra reconciliação). Change/delete
    também precisam do guard: `save()`/`delete()` do model já levantam
    `MovimentacaoEstoqueImutavel` (`apps/estoque/models.py:320-366`), mas
    essa exceção não é `ErroDominio` e `MovimentacaoEstoqueAdmin` não tem
    `changeform_view` que a capture — sem o guard no admin, a tentativa de
    editar/apagar pelo admin cai em 500, não 403. Cobrir com o smoke
    `test_admin_index_responde_para_superusuario` (classe de regressão do
    #104: `has_*_permission` mal implementado derruba `admin:index` inteiro).
  - `SaidaExcepcionalAdmin`: `has_add_permission`, `has_change_permission`,
    `has_delete_permission` → `False`. Leitura via `list_display`/filtros na
    changelist permanece; a change view individual continua respondendo GET
    200 em modo consulta — `has_view_permission` não é sobrescrito e segue
    default (baseado na permissão Django `view_*`), independente de
    `has_change_permission`. Só o POST fecha em 403.
  - `SequenciaSaidaExcepcionalAdmin`: `ultimo_numero` (e `ano`) somente-leitura
    — regressão de `ultimo_numero` colide com `numero_publico` unique no
    próximo envio (`IntegrityError` → 500). `has_add_permission = False`: a
    linha nasce por `get_or_create` no service na primeira emissão de número
    do ano; add manual pelo admin não tem caminho legítimo e cai no mesmo
    princípio já aplicado a `SaldoEstoqueAdmin`/`ItemRequisicaoAdmin` (criação
    é sempre do service, não da tela). `has_delete_permission = False`: apagar
    tem o mesmo efeito prático de regredir `ultimo_numero` — o próximo
    `get_or_create` recria a linha do zero e o service reemite números já
    usados naquele ano.
  - `ImportacaoSCPIAdmin`: `has_add_permission`, `has_change_permission`,
    `has_delete_permission` → `False`. Add não tem caminho legítimo sem
    CSV/preview por trás. Change fecha achado de review pós-implementação:
    `status`/`total_linhas`/`total_novos`/`total_divergentes`/`importado_por`
    ficavam editáveis, permitindo falsificar a trilha de quem importou o quê
    — não estava na AC original, mas é a mesma classe de brecha do issue
    (metadado de auditoria mutável pelo admin). Apagar libera reimportação do
    mesmo arquivo (dedup por `arquivo_hash`).
- `apps/requisicoes/admin.py`
  - `SequenciaRequisicaoAdmin`: mesmo guard de somente-leitura em
    `ultimo_numero`/`ano` + `has_add_permission = False` +
    `has_delete_permission = False` (mesma razão acima).
  - `RequisicaoAdmin`: `has_add_permission = False`, `has_delete_permission =
    False`; `criador`, `beneficiario`, `setor_beneficiario` movidos para
    `readonly_fields` (e saem do formulário via `get_form`, mesmo padrão já
    usado para `estado`). `has_add_permission = False` é obrigatório junto com
    o readonly: os três campos são `ForeignKey` sem `null=True` — se ficarem
    readonly (logo fora do form de add) sem bloquear o add, o POST cai em
    `IntegrityError` (NOT NULL) → 500 em vez de 403. Criação passa a ser
    exclusiva do service `criar_requisicao`, mesmo padrão já usado em
    `ItemRequisicaoAdmin`/`TimelineRequisicaoAdmin`.

**Não muda:**

- Nenhum service, policy, model ou migration.
- Leitura (`list_display`, `list_filter`, `search_fields`, changelist,
  `has_view_permission` default) segue aberta em todos os models acima.
- **Correção pós-implementação**: `ItemSaidaExcepcionalInline` **precisou** de
  guard próprio — `InlineModelAdmin.has_add_permission` não herda do
  `ModelAdmin` do model pai (chama `super().has_add_permission(request)`, que
  olha só a permissão Django de `ItemSaidaExcepcional`). Confirmado por teste
  (`test_item_inline_nega_add_change_e_delete`) e implementado.
## Arquivos tocados

| Arquivo | Símbolo | Mudança |
|---|---|---|
| `apps/estoque/admin.py` | `MovimentacaoEstoqueAdmin` | `has_add/change/delete_permission` |
| `apps/estoque/admin.py` | `SaidaExcepcionalAdmin` | `has_add/change/delete_permission` |
| `apps/estoque/admin.py` | `ItemSaidaExcepcionalInline` | `has_add/change/delete_permission` |
| `apps/estoque/admin.py` | `SequenciaSaidaExcepcionalAdmin` | `has_add_permission`, `has_delete_permission`, `readonly_fields` |
| `apps/estoque/admin.py` | `ImportacaoSCPIAdmin` | `has_add/change/delete_permission` |
| `apps/requisicoes/admin.py` | `SequenciaRequisicaoAdmin` | `has_add_permission`, `has_delete_permission`, `readonly_fields` |
| `apps/requisicoes/admin.py` | `RequisicaoAdmin` | `has_add_permission`, `has_delete_permission`, `readonly_fields` |
| `apps/estoque/tests/test_admin.py` | já existia (issues #102/#104/#105) | +37 casos cobrindo as mudanças acima |
| `apps/requisicoes/tests/test_admin.py` | já existia (issue #105) | +11 casos cobrindo as mudanças acima |

## Estratégia de testes

Seguir o padrão já estabelecido em `apps/requisicoes/tests/test_admin.py`
(issue #105): fixtures `request_de` (RequestFactory autenticado) e um staff
**não superusuário** com a permissão Django concedida, para provar que a
negação vem do guard e não do sistema de permissões padrão.

Por superfície:

- **`MovimentacaoEstoqueAdmin`**: `has_add/change/delete_permission` →
  `False` direto; GET add → 403; POST change/delete em movimentação existente
  → 403 sem mutar/apagar (prova de que o guard evita o 500 de
  `MovimentacaoEstoqueImutavel`); changelist segue 200.
- **`SaidaExcepcionalAdmin`**: `has_add/change/delete_permission` → `False`;
  GET add → 403; GET change → 200 (modo consulta — `has_view_permission`
  segue default); POST change → 403 sem mutar; POST delete → 403 sem apagar;
  changelist segue 200. `ItemSaidaExcepcionalInline`: guard próprio de
  add/change/delete (não herda do parent — ver "Correção pós-implementação"
  abaixo).
- **`SequenciaSaidaExcepcionalAdmin` / `SequenciaRequisicaoAdmin`**: contrato
  de change é **GET 200 / POST 302 sem mutação** — `has_change_permission`
  não é sobrescrito (fica no default `True`); a proteção é só via
  `readonly_fields`, que tira `ultimo_numero` **e `ano`** do formulário. Não
  há caminho de dado (nenhum campo é obrigatório em add, então não há risco
  de `IntegrityError` como em `RequisicaoAdmin`), então bloquear a view
  inteira com `has_change_permission = False` seria mais restritivo que o
  necessário — mesmo padrão de `TimelineRequisicao`/`estado` (readonly, não
  view fechada). `has_add_permission`/`has_delete_permission` → `False`; GET
  add → 403; POST delete → 403 sem apagar; `get_form` confirma os dois campos
  fora do formulário de change; POST com `ultimo_numero` ou `ano` alterado
  responde 302 mas não muta o valor no banco (trocar `ano` tem o mesmo efeito
  prático de apagar — achado de review pós-implementação, campo ficou de fora
  da primeira rodada).
- **`ImportacaoSCPIAdmin`**: `has_add/change/delete_permission` → `False`;
  GET add → 403; POST change (status/totais/`importado_por`) → 403 sem
  mutar; POST delete → 403 sem apagar; reimportação do mesmo hash seguiria
  bloqueada (já coberto por teste de service — não duplicar aqui).
- **`RequisicaoAdmin`**: `has_add_permission`/`has_delete_permission` →
  `False`; GET add → 403; POST delete → 403 sem apagar;
  `criador`/`beneficiario`/`setor_beneficiario` em `readonly_fields`;
  `get_form` confirma os três fora do formulário de change; POST que tenta
  trocar `beneficiario` não muta (caminho feliz de campo não-derivado —
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
