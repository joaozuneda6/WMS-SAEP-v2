# Plano de implementação — issue #128

**Resolver a Regra da Reversão Não é Erro no estorno de requisição**

> **Dois fluxos de estorno, não um.** O domínio distingue o **estorno de
> requisição** (`requisicoes:estornar`, encerra a requisição e devolve a
> entregue líquida ao saldo físico) do **estorno de saída excepcional**
> (`estoque:estornar_saida_excepcional`, registrado à parte). Neste documento,
> "estorno" sem qualificador significa sempre **estorno de requisição**. O
> estorno de saída excepcional aparece só no escopo D-4b.
>
> **Invariante da saída excepcional** (`EstadoSaidaExcepcional`,
> `apps/estoque/models.py:135`): o documento nasce em `registrada` e só chega a
> `estornada` por estorno explícito **daquele documento**, pelo service próprio
> `estornar_saida_excepcional` (`apps/estoque/services.py:560`). Não reutiliza a
> transição da requisição, não aceita outro documento como alvo, e o botão de UI
> desta PR não abre nenhum caminho novo — ele só troca de família de cor.

Issue: https://github.com/JMZR-SAEP/WMS-SAEP-v2/issues/128
Origem: Etapa 2 (Feedback e estado) do `docs/plans/audit-frontend-restante.md`.
Tipo: **HITL** — a fonte da verdade se contradiz; a decisão vem antes do código.

## Decisões tomadas (dono do produto, 2026-08-21)

Estas decisões destravam a issue. Estão registradas aqui para que uma revisão
futura não reabra o assunto apontando o outro trecho do mesmo documento.

### D-1 — Opção A: o estorno de requisição é reversão, não recusa

D-1 decide **um** fluxo: o estorno de requisição. O caminho inteiro dele passa
para teal (`return`). A irreversibilidade
continua comunicada por copy (`"Esta operação é irreversível"`, já presente no
modal) e pelo próprio modal de confirmação — que já fazem esse trabalho sem
depender da cor.

Motivo registrado: o argumento da Named Rule é mais forte e mais específico do
que a menção *en passant* na descrição da família `danger`, e o `PRODUCT.md`
trata o estorno como parte do ciclo normal, não como acidente. A Named Rule
fica intacta; quem cede é a lista de usos de `danger` no `DESIGN.md:222`.

### D-2 — o caminho do cancelamento sai do vermelho

Cancelar é evento legítimo do ciclo — o próprio criador cancela o que criou.
Pela Named Rule, não pode receber a cor da recusa. O caminho migra de `danger`
para `warning` (âmbar de pendência); o badge `orange` do estado final fica.

Segue exatamente o padrão que o retorno para rascunho já usa hoje
(`detalhe.html:265`): painel `warning`, disparo `warning-outline`, confirmação
`neutral`, ícone de modal `warning`.

### D-3 — nasce a escala de botão preenchido `return`

Medição: `--color-return` é teal-600 (`#0d9488`); com `text-on-primary` branco
dá **3.74:1** e reprova a WCAG AA 4.5:1 para texto de botão. Comparação na
mesma medida: red-600 dá 4.83:1 e blue-600 dá 5.17:1 — as duas famílias que
hoje têm botão preenchido passam, e o teal não passa.

Logo o preenchimento de teal não pode ser `--color-return`. Nascem três
tokens em `input.css`:

| Token | Valor | Contraste com branco |
|---|---|---|
| `--color-return-strong` | teal-700 | 5.47:1 |
| `--color-return-hover` | teal-800 | 7.58:1 |
| `--color-return-active` | teal-900 | maior ainda |

Consequência documental: `DESIGN.md:222` afirma que `danger` é a *única*
família além de `primary` com escala de botão completa. Deixa de ser verdade e
a frase é corrigida no mesmo passe.

Divergência de nomenclatura, registrada de propósito: em `primary` e em
`danger`, o token **base** da família (`--color-primary`, `--color-danger`) é o
próprio preenchimento de botão, e `-hover`/`-active` descem a partir dele. Em
`return` isso não pode valer, porque `--color-return` já é teal-600 e teal-600
reprova AA como fundo de botão. Rebaixar `--color-return` para teal-700
mudaria o anel de foco que `return-outline` já usa e contradiria o
`DESIGN.md:225`, que define a família como teal-600. Daí o `-strong`: o
preenchimento é um degrau abaixo do token base, e só nesta família.

Alternativa descartada: confirmar com `neutral` (grafite), como faz o retorno
para rascunho. Ela é mais barata e não pede token novo, mas quebra o critério
de aceite "o caminho e o estado final usam a **mesma** família de cor".
Registrada aqui porque a tensão é real: depois desta issue, estorno confirma em
teal preenchido enquanto retorno e cancelamento confirmam em `neutral`.

### D-4 — escopo lateral: corrigir junto, não só documentar

O critério de aceite manda revisar devolução e cancelamento no mesmo passe. A
auditoria achou três divergências além do estorno de requisição, e as três
entram no escopo planejado desta issue — serão corrigidas na Fase 2, junto com
o alvo principal, não neste commit de plano.

- **D-4a** — devolução de item: disparo já é teal, mas a confirmação do modal é
  `primary` e o ícone cai no ramo `info`.
- **D-4b** — estorno de **saída excepcional**: fluxo separado do estorno de
  requisição, mesmo veredito de D-1 pelo mesmo motivo. Confirmação migra de
  `danger` para a família `return`. Operação, estados, botão de UI e evento de
  timeline continuam distintos e intocados: só `confirm_variant` e
  `icon_variant` do modal mudam. A transição `registrada → estornada` segue
  exclusiva do service de estoque; nada nesta PR a toca.
- **D-4c** — cancelamento: é D-2, listado aqui só para fechar a conta das três.

## Auditoria — todo evento de domínio e sua família de cor

Levantada em `apps/requisicoes/templates/requisicoes/detalhe.html`,
`apps/requisicoes/templates/requisicoes/partials/_estado_badge.html` e
`apps/estoque/templates/estoque/detalhe_saida_excepcional.html`.

| Evento | Caminho hoje | Estado final hoje | Veredito |
|---|---|---|---|
| Autorizar | `info` / `primary` | badge `blue` | coerente |
| Retornar para rascunho | `warning` / `warning-outline` / `neutral` | volta a rascunho (`slate`) | coerente |
| Recusar | `danger` inteiro | badge `red-strong` | coerente — recusa **é** negação |
| Registrar devolução | disparo `return-outline`, **confirmação `primary`**, ícone `info` | — | **divergente** (D-4a) |
| Cancelar | `danger` inteiro | badge **`orange`** | **divergente** (D-2) |
| Estornar requisição | `danger` inteiro | badge **`teal`** | **divergente** — alvo da issue (D-1) |
| Estornar saída excepcional | modal `confirm_variant="danger"` | — | **divergente** (D-4b) |

Nenhum outro evento legítimo fica com a cor da recusa depois desta PR. `recusar`
permanece vermelho por ser exatamente aquilo que a Named Rule reserva ao
vermelho: negação.

## Escopo

### O que muda

**Documentação (a decisão, antes do código)**

- `DESIGN.md:222` — remove `estorno` da lista de usos de `danger`, e corrige a
  afirmação de que `danger` é a única família além de `primary` com escala de
  botão completa.
- `DESIGN.md:225` — a descrição do Teal de Reversão passa a nomear o estorno.
- `DESIGN.md` §Named Rules — a Regra da Reversão Não é Erro fica **inalterada**
  no texto; ganha a nota de que o mecanismo deixou de ser "revisão".
- `docs/design-system.md` §Regras invioláveis — a linha "Reversão não é erro"
  troca o mecanismo `revisão` pelo nome do teste novo.
- `docs/design-system.md` §Tokens — registra os três tokens novos de `return`.

**Tokens e componentes globais**

- `apps/core/static/core/css/input.css` — `--color-return-strong`,
  `--color-return-hover`, `--color-return-active`.
- `apps/core/templatetags/core_tags.py` — `_VARIANTES_BOTAO['return']`
  (preenchido) e `_PAINEL_DECISAO['return']`.
- `apps/core/templates/components/button.html` — documenta a variante `return`.
- `apps/core/templates/components/_icone_nivel.html` — glifo `return` próprio.
  Sem ele, o painel teal cai no ramo `{% else %}` e usa o glifo de exclamação de
  `danger` — o sinal não-cromático continuaria dizendo "erro" numa caixa teal,
  que é precisamente o defeito que a issue ataca.
- `apps/core/templates/components/_modal_icon.html` — variante `return`
  (`bg-return-muted text-return-text` + ícone `estornar`).
- `apps/requisicoes/templates/requisicoes/partials/_painel_decisao.html` e
  `_confirmacao_acao.html` — atualiza a documentação de `variant_token` para
  incluir `return`.

**Telas**

- `detalhe.html:327` (estorno) — `variant_token`, `botao_variant`,
  `confirm_variant` e `icon_variant` migram para a família `return`.
- `detalhe.html:174-176` (devolução) — `confirm_variant` e `icon_variant`
  migram de `primary`/ausente para `return`.
- `detalhe.html:216` e `:300` (cancelamento, inline e banner) — migram de
  `danger` para `warning`/`neutral`, no padrão do retorno para rascunho.
- `estoque/detalhe_saida_excepcional.html:177` (estorno de saída) —
  `confirm_variant` e `icon_variant` migram para `return`.

**CSS compilado**

- `apps/core/static/core/css/app.css` via `make css-build`. As classes novas
  (`bg-return-strong`, `hover:bg-return-hover`, `active:bg-return-active`) não
  existem no bundle atual; sem recompilar, o botão renderiza sem fundo.

### O que NÃO muda

- `_estado_badge.html` — os oito mapeamentos ficam como estão. `estornada`
  continua `teal`, `cancelada` continua `orange`, `recusada` continua
  `red-strong`. A Opção A move o caminho até o destino, não o contrário.
- O texto da Named Rule em `DESIGN.md:243` e a coluna "O que diz" da linha
  correspondente em `docs/design-system.md`. A regra estava certa; quem estava
  errado era o código e a lista de usos de `danger`.
- Copy de irreversibilidade do estorno. Ela é o que carrega o peso da ação
  depois que a cor deixa de gritar — sai da PR intacta, de propósito.
- `alert.html`. O painel de decisão já saiu dele na #127; esta issue nasce
  depois exatamente para o ramo `return` não ser escrito no componente errado.
- Regra de negócio, transições, policies e services. Esta PR é de apresentação.

## Arquivos tocados

| Arquivo | Natureza |
|---|---|
| `DESIGN.md` | decisão |
| `docs/design-system.md` | decisão + tokens + mecanismo |
| `docs/plans/128-regra-reversao-estorno.md` | este plano |
| `apps/core/static/core/css/input.css` | token |
| `apps/core/static/core/css/app.css` | build |
| `apps/core/templatetags/core_tags.py` | variante de botão + variante de painel |
| `apps/core/templates/components/button.html` | doc de contrato |
| `apps/core/templates/components/_icone_nivel.html` | glifo |
| `apps/core/templates/components/_modal_icon.html` | ícone de modal |
| `apps/core/templates/components/modal.html` | doc de `confirm_variant`/`icon_variant` |
| `apps/requisicoes/templates/requisicoes/partials/_painel_decisao.html` | doc de contrato |
| `apps/requisicoes/templates/requisicoes/partials/_confirmacao_acao.html` | doc de contrato |
| `apps/requisicoes/templates/requisicoes/detalhe.html` | estorno, devolução, cancelamento |
| `apps/estoque/templates/estoque/detalhe_saida_excepcional.html` | estorno de saída |
| `apps/core/tests/test_core_tags.py` | variante nova |
| `apps/core/tests/test_componente_icone_nivel.py` | glifo novo |
| `apps/core/tests/test_tokens_semanticos.py` | contraste dos tokens novos |
| `apps/requisicoes/tests/test_painel_decisao.py` | painel `return` |
| `apps/requisicoes/tests/test_views.py` | amarração caminho ↔ estado final |
| `apps/estoque/tests/test_views.py` | estorno de saída excepcional em teal |

## Estratégia de teste

A regra que esta issue conserta já existia e mesmo assim foi violada, porque o
mecanismo que a verificava era a palavra `revisão`. `docs/design-system.md`
avisa: **regra sem mecanismo vira sugestão**. O teste é o entregável central,
não o acessório.

### O teste que amarra cada ação à sua família de cor

**Não existe invariante universal "caminho e estado final são da mesma
família".** Ela é falsa de propósito em dois fluxos: o retorno para rascunho
termina em `slate` (o estado neutro para onde a requisição volta) e o
cancelamento termina em `orange` (catálogo cru, que distingue *cancelada* de
*recusada* na listagem). Transformar a igualdade em regra geral obrigaria a
estragar um dos dois lados desses dois fluxos.

O que o teste amarra é uma **tabela de valores esperados por ação**, declarada
uma vez no módulo de teste. Cada ação declara os seus cinco valores de forma
independente.

**A camada da tabela é a variante semântica** — o valor que a tela passa em
`variant_token`, `botao_variant`, `confirm_variant`, `icon_variant` e `variant`,
antes de qualquer resolução de classe. É a camada em que a decisão de design
vive: `_estado_badge.html` escolhe `teal`, não `bg-return-muted`.

O teste, porém, assere contra o **HTML renderizado**, porque uma tabela que
comparasse argumento com argumento passaria mesmo se `classes_botao` perdesse a
variante. A ponte entre as duas camadas é explícita, e é ela que o teste
percorre:

| Ação | Painel | Disparo | Confirmação | Ícone do modal | Estado final |
|---|---|---|---|---|---|
| Autorizar | `info` | `primary` | `primary` | `info` | badge `blue` |
| Retornar para rascunho | `warning` | `warning-outline` | `neutral` | `warning` | badge `slate` |
| Recusar | `danger` | `danger-outline` | `danger` | `danger` | badge `red-strong` |
| Cancelar | `warning` | `warning-outline` | `neutral` | `warning` | badge `orange` |
| Estornar requisição | `return` | `return-outline` | `return` | `return` | badge `teal` |
| Registrar devolução | — | `return-outline` | `return` | `return` | — |

Ponte variante → marca no HTML. A coluna da direita é o que a asserção procura;
a fonte de cada linha é `classes_painel_decisao` e `classes_botao`
(`apps/core/templatetags/core_tags.py`), `_modal_icon.html` e `badge.html`:

| Slot | Variante | Marca renderizada |
|---|---|---|
| Painel | `info` / `warning` / `danger` / **`return`** | `bg-primary-subtle` / `bg-warning-subtle` / `bg-danger-subtle` / **`bg-return-subtle`** |
| Disparo | `primary` | `bg-primary` |
| Disparo | `warning-outline` / `danger-outline` / `return-outline` | `border-warning-border-strong` / `border-danger-border-strong` / `border-return-border` |
| Confirmação | `primary` / `neutral` / `danger` / **`return`** | `bg-primary` / `bg-text-secondary` / `bg-danger` / **`bg-return-strong`** |
| Ícone do modal | `info` / `warning` / `danger` / **`return`** | `bg-primary-muted` / `bg-warning-muted` / `bg-danger-muted` / **`bg-return-muted`** |
| Badge | `slate` / `blue` / `red-strong` / `orange` / `teal` | `bg-bg-subtle` / `bg-primary-muted` / `bg-danger-muted-strong` / `bg-orange-100` / `bg-return-muted` |

Em **negrito**, o que nasce nesta PR. As três variantes `return` novas caem em
tokens da mesma família que o badge `teal` já consome hoje (`bg-return-muted`,
`text-return-text-strong`, `ring-return-border`) — é por isso que a asserção 3
consegue dizer que caminho e destino são a mesma família sem comparar strings
soltas.

O disparo é o único slot cuja marca não é o fundo: as três variantes `-outline`
compartilham `bg-surface`, e quem as distingue é a borda.

Registrar devolução não tem painel de decisão nem muda o estado da requisição:
é botão + modal dentro da linha do item. As duas células vazias são ausência
declarada, não valor a preencher depois.

Sobre a tabela, três asserções separadas:

1. **Valores por ação** — a marca renderizada de cada célula preenchida está no
   HTML, pela ponte acima.
   É isto que impede a regressão silenciosa, e vale para as seis linhas.
2. **Nenhum evento legítimo em vermelho** — só `Recusar` pode usar a família
   `danger`, nas quatro colunas de caminho. É a Regra da Reversão Não é Erro
   virando mecanismo, e é a asserção que teria pego o defeito original.
3. **Caminho igual ao destino, onde foi decidido** — restrita ao **estorno de
   requisição** (D-1) e a `Recusar`, os dois fluxos em que a decisão registrada
   diz que caminho e destino contam a mesma história. As outras quatro linhas
   ficam explicitamente fora, cada uma com o motivo na própria tabela.

O estorno de **saída excepcional** não passa pelo detalhe da requisição e não
cabe nessa tabela: ganha asserção própria em `apps/estoque/tests/test_views.py`,
cobrando a família `return` no modal.

É o mesmo arranjo de três lados que a #124 usou na paridade banner/faixa, e pelo
mesmo motivo: comparar só dois templates entre si passa se alguém mudar os dois
para o mesmo valor errado.

### Caminho feliz

- Estorno de requisição renderiza painel `return-subtle`, disparo
  `return-outline`, confirmação `return` preenchida e ícone de modal teal.
- Devolução renderiza disparo `return-outline`, confirmação `return` e ícone
  teal — sem painel e sem mudança de estado.
- Cancelamento renderiza painel `warning`, disparo `warning-outline`,
  confirmação `neutral`, ícone `warning` e badge final `orange`.
- Estorno de saída excepcional renderiza confirmação `return` e ícone teal.

### Violação de domínio / contrato

- `classes_painel_decisao('return')` devolve `conhecida=True` e superfície com
  os três tokens de `return` — e nenhuma cor crua de paleta, pela guarda que já
  existe em `test_painel_decisao_nao_emite_cor_crua_de_paleta`.
- `classes_botao(variant='return')` devolve o fundo `return-strong`, não
  `return` — a guarda que impede alguém de "simplificar" o token de volta ao
  teal-600 que reprova AA.
- Variante desconhecida continua caindo na Decisão A-1 (falha alta, fundo
  `danger` preenchido). A família nova não abre exceção no fallback.
- `_icone_nivel.html` com `variant="return"` emite o glifo próprio, e **não** o
  de exclamação. Sem essa asserção, remover o ramo passa despercebido.

### Regressão que não pode quebrar

- `apps/requisicoes/tests/test_views.py:2713` — a contagem de `role="alert"` == 1
  e `role="status"` == 1 no `_messages.html`. Nada nesta PR toca ali, mas a
  contagem é frágil o bastante para ser conferida antes de fechar.
- `apps/core/tests/test_tokens_semanticos.py` — a allowlist de cor crua tem
  contagem exata. Nenhuma classe crua nova entra nesta PR; se a contagem mudar,
  algo vazou.
- `test_nenhum_controle_abaixo_do_piso_de_44px` — o piso não vem do mapa de
  variantes e sim de `_FORMA_BOTAO` (`core_tags.py:130`), que traz `min-h-11`
  literal e é emitido por `classes_botao` para toda variante que não seja
  `link`. `return` não é `link`, logo herda o piso. Como isso é inferência sobre
  a montagem da string, vira medição: asserção direta de que
  `classes_botao(variant='return')` contém `min-h-11`, junto da que já cobra o
  fundo `return-strong`. Sem ela, alguém que desse a `return` uma forma própria
  — como `link` tem — derrubaria o piso sem quebrar nada.

## Invariantes

- **Reversão não é erro** (`docs/design-system.md` §Regras invioláveis): é a
  invariante que a issue existe para restaurar. Sai desta PR com teste, não com
  a palavra `revisão`.
- **Token, nunca shade**: os três tokens novos nascem em `input.css` e as
  telas consomem só a utility semântica. Nenhuma cor crua de paleta entra.
- **Falha alta, nunca plausível** (Decisão A-1, #122): a variante nova entra no
  catálogo conhecido; o ramo de fallback continua gritando em `danger`
  preenchido, sem exceção para `return`.
- **Botão tem uma definição só**: a variante `return` nasce em
  `classes_botao`, nunca numa tela.
- **Piso de 44px**: preservado por vir de `classes_botao`.
- **Nível por mais do que cor**: o glifo próprio de `return` é o que impede a
  família nova de ser comunicada só por cor.
- **Raio crescente** e **quatro degraus de elevação**: intocados — nada de
  geometria muda, só família de cor.

## Riscos

- **`make css-build` esquecido.** É o risco mais provável e o mais silencioso:
  a classe existe no template, o teste de template passa, e o botão renderiza
  sem fundo no navegador. `app.css` é versionado; o build entra no mesmo commit
  das classes novas.
- **Contraste do texto sobre o painel teal — medido, não presumido.**
  `text-return-text-strong` (teal-900) sobre `return-subtle` (teal-50) dá
  **9.09:1**; o degrau `-text` (teal-700) sobre o mesmo fundo dá 5.25:1. Os dois
  passam AA, e o painel usa o primeiro. Risco fechado antes de escrever código.
- **Regressão visual em tela não auditada.** A migração do cancelamento toca
  dois pontos de chamada (`inline` e `banner`) com copy resolvida por
  templatetag. Os dois precisam da mesma família, senão a issue troca uma
  divergência por outra.
- **Escopo lateral crescendo.** `estoque/detalhe_saida_excepcional.html` entra
  como D-4b: é fluxo separado do estorno de requisição, mas cai sob a mesma
  Named Rule pelo mesmo motivo. Qualquer outro achado fora
  destes quatro caminhos vira issue nova, não commit desta PR.
- **Sem risco de concorrência, de migração ou de contrato de dados.** Nenhum
  model, service, policy ou transição é tocado.

## Fluxo de trabalho

Segue o `/ship-issue`, com o comando recomendado pela issue encaixado na
Fase 2, depois da decisão e antes do fechamento:

1. **Fase 1** — este plano, revisão do CodeRabbit, portão de aprovação.
2. **Fase 2** — TDD por comportamento: primeiro a decisão no `DESIGN.md` e no
   `docs/design-system.md`, depois token → componente global → tela, cada um
   com RED → GREEN → REFACTOR.
3. **Fase 2, passo de cor** — rodar o comando recomendado na issue **depois**
   de a contradição no `DESIGN.md` estar resolvida:

   ```text
   /impeccable colorize apps/requisicoes/templates/requisicoes/detalhe.html apps/requisicoes/templates/requisicoes/partials/_estado_badge.html DESIGN.md
   ```

   `colorize` alinha o caminho ao destino; ele não decide qual dos dois está
   certo. Rodá-lo antes da decisão seria pedir ao comando que adivinhasse D-1.
4. **Fase 2, fechamento** — `make css-build`, `uv run ruff format .`,
   `uv run ruff check .`, `uv run mypy apps` e a suíte completa.
5. **Fase 3** — corpo da PR, CodeRabbit, resposta a cada thread.

## Linha de base

Suíte na `main`, antes de qualquer alteração desta branch: **2162 passed**
(`uv run pytest -q -ra --tb=short --strict-markers --disable-warnings -n logical`,
saída limpa). Qualquer contagem final abaixo disso é regressão.

## Critérios de aceite (espelho da issue)

- [ ] Contradição do `DESIGN.md` resolvida, com o motivo registrado (D-1)
- [ ] `docs/design-system.md` §Regras invioláveis reflete a decisão
- [ ] Caminho do estorno de requisição e estado final usam a mesma família de cor
- [ ] Painel de decisão tem ramo `return`/teal; irreversibilidade segue por copy
      e pelo modal
- [ ] Nenhum outro evento legítimo ficou com a cor da recusa — devolução e
      cancelamento revisados e corrigidos no mesmo passe
- [ ] Teste amarra a família de cor do caminho à do estado final
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` e
      `uv run mypy apps` verdes
