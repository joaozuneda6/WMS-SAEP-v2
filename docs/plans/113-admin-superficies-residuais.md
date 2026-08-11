# Plano — Fechar superfícies residuais do admin (#113)

## Escopo

Fechar as brechas residuais do achado R4 (auditoria de admin): superfícies onde
o superusuário ainda contorna ledger, numeração ou trilha de auditoria pelo
Django admin. `RequisicaoAdmin`/`ItemRequisicaoAdmin`/`TimelineRequisicaoAdmin`
e `SaldoEstoqueAdmin`/`EstoqueAdmin`/`MaterialAdmin` já foram blindados nos
issues #102/#104/#105 — este issue cobre o que sobrou.

**Muda:**

- `apps/estoque/admin.py`
  - `MovimentacaoEstoqueAdmin`: `has_add_permission`, `has_change_permission`,
    `has_delete_permission` → `False`. Add fecha a brecha do issue (LED-01/
    LED-02 — linha de ledger sem mutação de saldo correspondente quebra
    reconciliação). Change/delete também precisam do guard: `save()`/
    `delete()` do model já levantam `MovimentacaoEstoqueImutavel`
    (`apps/estoque/models.py:320-366`), mas essa exceção não é `ErroDominio` e
    `MovimentacaoEstoqueAdmin` não tem `changeform_view` que a capture — sem o
    guard no admin, a tentativa de editar/apagar pelo admin cai em 500, não
    403.
  - `SaidaExcepcionalAdmin`: `has_add_permission`, `has_change_permission`,
    `has_delete_permission` → `False`. Leitura via `list_display`/filtros na
    changelist permanece; a change view individual (GET/POST) também fica
    403, já que `has_change_permission = False` desliga a tela inteira — não
    há modo "somente leitura" no admin sem `has_view_permission` separado, que
    este plano não introduz.
  - `SequenciaSaidaExcepcionalAdmin`: `ultimo_numero` (e `ano`) somente-leitura
    — regressão de `ultimo_numero` colide com `numero_publico` unique no
    próximo envio (`IntegrityError` → 500). Além disso `has_add_permission =
    False`: a linha nasce por `get_or_create` no service na primeira emissão
    de número do ano; add manual pelo admin não tem caminho legítimo e cai no
    mesmo princípio já aplicado a `SaldoEstoqueAdmin`/`ItemRequisicaoAdmin`
    (criação é sempre do service, não da tela).
  - `ImportacaoSCPIAdmin`: `has_delete_permission = False` — apagar libera
    reimportação do mesmo arquivo (dedup por `arquivo_hash`).
- `apps/requisicoes/admin.py`
  - `SequenciaRequisicaoAdmin`: mesmo guard de somente-leitura em
    `ultimo_numero`/`ano` + `has_add_permission = False` (mesma razão acima).
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
- GET na change view individual de `SaidaExcepcional` continua 200 (modo
  consulta) mesmo com `has_change_permission = False` — `has_view_permission`
  não foi sobrescrito e segue default (baseado na permissão Django `view_*`).
  Só o POST fecha em 403. Documentado errado numa revisão anterior deste
  plano; corrigido após rodar os testes.

## Arquivos tocados

| Arquivo | Símbolo | Mudança |
|---|---|---|
| `apps/estoque/admin.py` | `MovimentacaoEstoqueAdmin` | `has_add/change/delete_permission` |
| `apps/estoque/admin.py` | `SaidaExcepcionalAdmin` | `has_add/change/delete_permission` |
| `apps/estoque/admin.py` | `SequenciaSaidaExcepcionalAdmin` | `has_add_permission`, `readonly_fields` |
| `apps/estoque/admin.py` | `ImportacaoSCPIAdmin` | `has_delete_permission` |
| `apps/requisicoes/admin.py` | `SequenciaRequisicaoAdmin` | `has_add_permission`, `readonly_fields` |
| `apps/requisicoes/admin.py` | `RequisicaoAdmin` | `has_add_permission`, `has_delete_permission`, `readonly_fields` |
| `apps/estoque/tests/test_admin.py` | novo | cobertura das 4 mudanças de estoque |
| `apps/requisicoes/tests/test_admin.py` | novo | cobertura das 2 mudanças de requisições |

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
  GET add → 403; GET change → 403 (tela inteira fechada, não só o form); POST
  change em saída existente → 403 sem mutar; POST delete → 403 sem apagar;
  changelist segue 200 (única superfície de leitura que sobra).
- **`SequenciaSaidaExcepcionalAdmin` / `SequenciaRequisicaoAdmin`**:
  `has_add_permission` → `False`; GET add → 403; `readonly_fields` cobre
  `ultimo_numero`; `get_form` confirma campo fora do formulário de change;
  POST com `ultimo_numero` alterado não muta o valor no banco.
- **`ImportacaoSCPIAdmin`**: `has_delete_permission` → `False`; POST delete →
  403 sem apagar; reimportação do mesmo hash seguiria bloqueada (já coberto
  por teste de service — não duplicar aqui).
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
