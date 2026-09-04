# Design System — WMS-SAEP

Design system pragmático em Django templates + Tailwind CSS v4 + HTMX + Alpine.js.
Cobre tokens visuais, componentes globais e padrões de interação operacional.

Não é SPA, não é biblioteca JS pesada, não é identidade de marca. É ferramenta de
trabalho.

**Este documento é regra e índice, nunca cópia de API.** A documentação de cada
componente vive no bloco `{% comment %}` do próprio arquivo, que é onde ela não
apodrece — ali estão parâmetros, obrigatoriedade, contrato ARIA e o motivo de
cada decisão. Uma versão anterior deste arquivo mantinha um "inventário" paralelo
que descrevia quatro componentes inexistentes e uma API que `button.html` não
tinha há meses. O índice abaixo aponta; não repete.

A linguagem visual — a POV, o vocabulário de cor, a escala de elevação, as regras
nomeadas em prosa — vive em `DESIGN.md`. Aqui ficam as regras operacionais e o
mapa do catálogo.

## Princípios

- **Pragmático**: decidir com base em necessidade real, não antecipar
- **Operacional**: o usuário entende rápido o que pode fazer, em que estado está, onde há erro
- **Neutro**: sistema administrativo interno — visual profissional e acessível
- **Simples**: componentes com responsabilidade clara, sem excesso de parâmetros
- **Progressivo**: HTMX/Alpine para interação incremental; sem estado de domínio no JavaScript

## Regras invioláveis

Oito regras. Cada uma tem o mecanismo que a verifica, porque **regra sem
mecanismo vira sugestão** — foi assim que o piso de 44px e o raio de campo
saíram do ar em silêncio, sem quebrar teste nenhum.

| Regra | O que diz | O que verifica |
|---|---|---|
| **Falha alta, nunca plausível** | Variante ou estado que um componente global (`badge.html`, `alert.html`) não reconhece grita — fundo preenchido de falha, sinal visível, `role="alert"`, atributo `data-*-variant` cru para depuração — em vez de virar uma cor plausível ou cair num ramo silencioso. Partial de domínio que traduz enum para variante nunca intercepta o valor desconhecido: repassa sob o prefixo reservado `desconhecida:` e deixa o fallback do componente global fazer o trabalho. Decisão A-1 da issue #122. | `test_variant_desconhecida_cai_no_fallback_indisponivel`, `test_fallback_stack_usa_cor_preenchida_de_grito`, e os testes de "estado/tipo/status não mapeado" de `apps/requisicoes/tests/test_partials.py` e `apps/estoque/tests/test_partials.py` |
| **Token, nunca shade** | Template usa a utility semântica (`bg-primary`, `text-danger-text`), nunca a cor crua da paleta (`bg-blue-600`) nem a custom property no HTML. É o que torna um rebrand uma troca de valor em `input.css`. Exceção viva: o backdrop de `modal.html`, declarada — allowlist por classe exata com contagem em `apps/core/tests/test_tokens_semanticos.py`. | `test_cor_crua_de_marca_bate_exatamente_com_a_allowlist` |
| **Piso de 44px** | Todo controle acionável tem `min-h-11` — botão, campo, select, e a *label* que embrulha radio/checkbox. A mesma tela é operada com o dedo, em pé no galpão, e com teclado no escritório. **Exceção: a variante `link` de `button.html`**, que é texto inline no meio de prosa e teria a linha quebrada por uma caixa de 44px (WCAG 2.5.8 isenta link em sentença). `link` usado como ação isolada recebe `class="min-h-11"` explícito — ver `notificacoes/lista.html`. | `test_nenhum_controle_abaixo_do_piso_de_44px`, que varre `<a>` e `<button>` de `apps/**/*.html` e cobra **piso comprovável** de cada um: `min-h-11` literal fora de `{% if %}`, classe cujo bloco em `input.css` declara `--size-touch-target`, classe vinda de `{% classes_botao %}`, ou — para quem inclui `button.html` com `variant="link"` — `min-h-11` no `class`. Falha na **ausência** de piso, não só em número menor. Para o checkbox de filtro há um segundo guarda, `test_todo_checkbox_esta_dentro_da_label_que_carrega_o_piso`: contar `min-h-11` não prova que o piso está na label que **embrulha** o input, e é o aninhamento que faz a caixa de 44px inteira valer como alvo — medido no navegador com o CSS compilado, 120 sondas em 15 labels, todas resolvendo para a label (issue #160) |
| **Campo tem uma definição só** | Campo de texto, número, busca, select e textarea usam `class="campo"` (definida em `input.css`). Não se escreve a string de campo à mão, nem em template nem em `forms.py`. | `test_nenhum_template_escreve_campo_na_mao` |
| **Botão tem uma definição só** | Toda ação passa por `components/button.html`. Se uma variante não existe, ela nasce no componente — não numa tela. | revisão |
| **Raio crescente** | Controle 0.375rem → campo 0.5rem → papel 0.75rem → modal 1rem → pill. Um raio intermediário inventado quebra a leitura de hierarquia por geometria. | revisão |
| **Quatro degraus de elevação** | 0dp repouso, 1dp papel, 8dp menu, 24dp modal, mais o 4dp exclusivo da barra de aplicação. Nenhuma sombra nova para componente novo. | revisão |
| **Reversão não é erro** | Devolução e reversão usam teal (`return`), jamais vermelho. Vermelho é negação, falha ou divergência; devolver material é o processo funcionando. | revisão |

As demais regras nomeadas — Sinal Único, Cartão Único, Chrome Sem Parâmetro,
Caixa Alta Estrutural, 14px, Empilhamento Fechado — estão em `DESIGN.md` com a
prosa e a medição que as originaram.

## Tokens

Os tokens vivem em `@theme` de `assets/css/input.css`. As
famílias e o significado de cada shade estão em `DESIGN.md` §Colors; aqui fica só
o que é operacional.

### Escala de sufixos

| Sufixo | Shade | Uso |
|---|---|---|
| `-subtle` | 50 | fundo de alerta, item de navegação ativo |
| `-muted` | 100 | fundo de badge |
| `-muted-strong` | 200 | fundo de badge "forte" |
| `-border` | 200 | borda de alerta, ring de badge |
| `-border-strong` | 300 | ring de badge forte, borda de botão outline |
| `-text-subtle` | 700 | aviso inline menos enfático (só `warning`) |
| `-text` | 700 — **800 em `warning`** | texto colorido de corpo |
| `-text-emphasis` | 800 — não existe em `warning` | texto de banner de alerta |
| `-text-strong` | 900 | texto de badge e de caixa de erro |
| `-accent` | 500 | foco de botão destrutivo, asterisco de obrigatório (só `danger`) |
| `-border-input` | 400 | borda de campo inválido (só `danger`) |
| `-hover` / `-active` | 700 / 800 | pressão em botão (`primary` e `danger`) |

**`warning` é a exceção da escala de texto.** Ela é a única família com
`-text-subtle`, e por isso sua escada anda um degrau: `-text-subtle` 700,
`-text` **800**, `-text-strong` 900 — sem `-text-emphasis`. Nas outras famílias,
`-text` é 700 e o 800 se chama `-text-emphasis`. Consequência prática: o
equivalente de `-text-emphasis` em âmbar é `text-warning-text`, e é por isso que
a tabela de paridade abaixo usa nomes diferentes para o mesmo degrau.

### As três bordas

Distinção de contraste medido, não de gosto:

- `border` (slate-200) e `border-strong` (slate-300) são **estruturais** — borda
  de papel, divisor, contorno tracejado de estado vazio. Separam superfícies que
  já se distinguem por tom.
- `border-control` (slate-500) **identifica um controle** — campo, select, botão
  secundário, upload. Ali a linha é a única pista de que há um controle, e a
  WCAG 1.4.11 pede 3:1.

Medido contra branco: slate-300 dá 1.48:1, slate-400 dá 2.63:1, slate-500 dá
4.77:1. Só o último passa em todas as superfícies do sistema.

### Tailwind v4 só compila o que é usado

`@theme` declara o token, mas a custom property e a utility só entram no
`app.css` quando algum template referencia a classe. É JIT real, não um dump.
Consequência prática: usar `bg-info-subtle` num template novo funciona
normalmente após `npm run css:build`; só não espere a classe já existir no
`app.css` sem ter sido consumida antes.

A família `--color-info*` (slate) está declarada e não é consumida por nenhum
template — a variante `info` de `alert.html` e o nível padrão de `_messages.html`
renderizam **azul** via `primary-*`, por decisão. Use `info-*` só quando precisar
de um aviso realmente neutro.

### Tipografia

Fonte do sistema, sem CDN: `ui-sans-serif, system-ui, sans-serif`.

| Papel | Tamanho | Peso | Onde |
|---|---|---|---|
| Display | 1.875rem | 600 | título de tela em desktop, um por página |
| Headline | 1.5rem | 600 | título de tela em mobile |
| Title | 1rem → 1.125rem em `sm` | 500 | título e marca na barra de aplicação |
| Body | **0.875rem** | 400 | o tamanho dominante do sistema |
| Label | 0.75rem | 600 | rótulo de campo, cabeçalho de seção, badge (sem caixa alta) |

O corpo é 0.875rem e não 1rem — decisão de densidade operacional (Regra dos 14px,
`DESIGN.md`). Se um texto precisa de mais presença, mude o peso ou o tom, não o
tamanho.

Controles (botão, item de menu, ação da barra, skip link) usam peso **500**.

### Espaçamento e forma

```
container:  80rem (--width-content); card de login 24rem (--width-card-sm)
padding:    p-4 em cartão de listagem, p-6 em seção maior
gap:        gap-2 entre controles irmãos, gap-3/gap-4 em grade
rounded:    controle 0.375 / campo 0.5 / papel 0.75 / modal 1rem / pill
sombra:     shadow-sm só em papel; campo e botão não têm sombra
```

### Empilhamento (z-index)

Escala fechada, para que uma superfície nova não precise adivinhar um valor:

| Camada | z-index | Onde |
|---|---|---|
| Conteúdo da página | auto | padrão |
| Barra de ação fixa no rodapé | `z-10` | ações sticky de formulário no mobile |
| Popover ancorado | `z-20` | dropdown do `autocomplete.html` |
| Barra de aplicação / overlay de navegação | `z-30` | `.app-bar`, scrim do menu |
| Drawer de navegação | `z-40` | `.app-bar__menu-wrap` |
| Skip link | `z-50` | primeiro foco tabulável |
| Modal | top layer | `<dialog>` nativo, fora da escala |

A regra que importa: **a barra de ação fixa fica abaixo do popover**. Quando ela
subiu para `z-30` e empatou com a barra de aplicação, o dropdown de material
passou a ser pintado por baixo dela no celular, e a opção ativa do combobox
ficava encoberta (WCAG 2.4.11).

## Estados de UI

### Desabilitado (ação bloqueada por permissão ou estado)

`button.html` já entrega `opacity-60` e `cursor-not-allowed` nos dois estados
(`disabled:` e `aria-disabled:`), preservando a variante — o botão continua
reconhecível como a ação que é.

- Ação de **workflow** bloqueada: visível + motivo em texto, amarrado por
  `aria_describedby` ao parágrafo que explica. Com esse motivo presente,
  `button.html` emite `aria-disabled="true"` em vez de `disabled` nativo: o
  botão continua na ordem de tabulação, e quem navega por Tab chega até ele e
  ouve a descrição. A ativação é barrada por `core/js/acao-bloqueada.js`, em
  fase de captura, valendo também para submit, HTMX e `@click` do Alpine.
- Bloqueio **sem motivo a expor**: `disabled` nativo, que é o caso da paginação
  — "Anterior" na primeira página não tem o que explicar.
- Ação **administrativa** irrelevante: fora da marcação.

```django
{% if pode_autorizar %}
  {% include "components/button.html" with label="Autorizar" variant="primary" %}
{% else %}
  {% include "components/button.html" with label="Autorizar" variant="primary" disabled=True aria_describedby="motivo-bloqueio" %}
  <p id="motivo-bloqueio" class="text-sm text-text-tertiary">
    Disponível apenas para o chefe do setor do beneficiário.
  </p>
{% endif %}
```

### Carregando

`button.html` cobre um caminho só: `loading_label="Registrando…"`.
`form-submit.js` troca o texto do `[data-submit-text]`, aplica `aria-busy` e
libera tudo em `htmx:afterRequest` e na volta pelo bfcache.

Em form que envia por HTMX, o bloqueio real do duplo envio é
`hx-sync="this:drop"` no próprio `<form>`: o `preventDefault()` do
`form-submit.js` roda num listener em `document`, depois do listener que o HTMX
instala no elemento, e o HTMX não consulta `defaultPrevented`.

Não existe spinner de submit. Houve um vocabulário Alpine paralelo para isso
(`x_disabled`, `x_aria_busy`, `spinner_show`, `label_bind`), com implementação,
teste e documentação — e nenhuma tela que o usasse. Foi removido. Se um botão
precisar de estado reativo no cliente, ele volta junto com a tela que precisa.

### Readonly (campo preenchido, não editável)

`bg-bg-subtle`, borda neutra, cursor padrão. Nunca `disabled`, que impediria o
envio, e nunca `aria-disabled`, porque o campo não está semanticamente
desabilitado.

### Foco

Anel de foco em **todo** controle, sempre `focus-visible` e nunca `focus`:

```
focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-offset-1
```

`.campo` já traz o seu. Em ação destrutiva o anel é `danger-accent`. Remover
`outline` só é aceitável porque o anel o substitui.

**Exceção: alvo de foco programático não é controle.** Um elemento que só recebe
foco por `tabindex="-1"` mais `focus()` — sumário de erros, barra de resumo
depois de um upload — usa `focus:`, não `focus-visible:`. Depois de um POST
disparado por clique ou toque, a última interação não foi teclado e
`:focus-visible` não casa: o anel simplesmente não pinta, e quem navega por
teclado recebe o foco sem saber onde ele foi parar. A regra do `focus-visible`
continua valendo para tudo que o usuário aciona — botão, link, campo, âncora de
item dentro do próprio sumário.

Hoje a exceção tem dois consumidores: a caixa de
`components/error_summary.html` e a barra de estatísticas de
`estoque/preview_importacao_scpi.html`. As duas declaram o motivo no
`{% comment %}` logo acima, e `apps/core/tests/test_components.py` trava os dois
lados no sumário — caixa em `focus:`, âncora em `focus-visible:` — para que
"consertar" o elemento errado quebre um teste em vez de passar despercebido.

### Erro de formulário

Uma superfície, uma porta: **`{% erros_do_formulario %}`** (`core_tags`). Todo
formulário do sistema — login, formset longo, corpo de modal — abre com ela
logo depois do `{% csrf_token %}`, e nenhum outro lugar decide como um erro de
formulário aparece.

```django
{% erros_do_formulario form formset ancora_geral="sec-materiais" %}
{% erros_do_formulario cabecalho formset acao="registrar o atendimento" ancora_geral="sec-itens" %}
{% erros_do_formulario erro acao="recusar" id="confirmar-recusar-erro" focar=False %}
```

Fontes são Forms, FormSets e strings (a falha que a view já traduziu de uma
exceção de domínio); `None` é ignorado, então contexto opcional não precisa de
`{% if %}` na tela. `acao` é o verbo da frase-líder — "Não foi possível
{acao}: N problemas encontrados." — e a pluralização fica no componente. `id`
nomeia a caixa quando algo aponta para ela por `aria-describedby`. `focar=False`
só onde outro componente já governa o foco da região (hoje o modal, cujo
`modal.js` leva ao campo inválido).

**`ancora_geral` é obrigatório na prática.** Mensagem que não pertence a campo
nenhum — `non_form_errors`, `__all__`, string da view — não tem `id` de onde
derivar âncora, e sem alvo declarado sai do sumário como texto solto no meio de
uma lista de links: a caixa anuncia e conta, mas não leva. O alvo é de cada
tela (a seção que contém a falha, ou o campo por onde se começa a corrigi-la) e
precisa existir e ser focável — `href="#id"` sozinho rola até o elemento sem pôr
o foco nele, e o teclado chegaria ao destino com o foco ainda no sumário. Logo:
`id` + `tabindex="-1"` no alvo, com anel em `focus:` pela mesma exceção do
sumário. `ancora_geral` é destino, não identidade: duas mensagens sem campo
continuam sendo duas linhas apontando para o mesmo lugar.

Exceção: o corpo de modal não declara alvo. Ali `modal.js` já leva o foco ao
campo inválido, e a caixa fica a centímetros dele — não há para onde navegar.

A tag decide as três coisas que antes cada tela decidia sozinha:

- **o quê** entra — todos os erros de todas as fontes, achatados por
  `coletar_erros`, um item por alvo e sem repetição;
- **onde** aparece — sumário no topo do `<form>` com âncora por campo, e o erro
  inline no campo via `form_field.html` → `field_error.html`. Não é redundância:
  o sumário anuncia, conta e navega; o inline fica ao lado do controle enquanto
  a pessoa corrige;
- **como é anunciado** — `role="alert"` e foco programático no mount.

O texto vem sempre do Form, nunca hardcoded no componente.
`.campo[aria-invalid="true"]` pinta a borda em `danger-border-input`.

**Regra para quem escreve `clean()`**: um formset que anexa o erro ao campo
(`add_error`) **e** levanta `ValidationError` para abortar a validação precisa
usar **a mesma frase** nas duas pontas. `coletar_erros` casa mensagens
idênticas e deixa só a versão com âncora; com duas redações do mesmo problema,
o sumário lista dois itens e a contagem mente.

## Onde uma coisa mora

```
É estilo de campo?            -> .campo, em input.css
É uma ação clicável?          -> components/button.html (variante nova nasce lá)
Precisa de estado de domínio  -> partial de domínio em apps/<app>/templates/<app>/partials/
  (status="autorizada")?
Serve a 2+ telas, sem domínio -> componente global em apps/core/templates/components/
Usado 1 vez, fluxo instável   -> inline na tela, até estabilizar
```

### Componente global

Vive em `apps/core/templates/components/`. Conhece variantes visuais, estados e
ARIA. **Não** conhece semântica de domínio: recebe `variant` e `label` já
resolvidos.

### Partial de domínio

Vive em `apps/<app>/templates/<app>/partials/`. Conhece enums e regras do app, e
usa os componentes globais por dentro. É quem mapeia `EstadoRequisicao → variant`.

### Inline

Permitido para bloco usado uma vez, fluxo instável ou markup muito acoplada à
tela. Extrair quando for reutilizado 2+ vezes, quando o padrão visual estabilizar
ou quando uma mudança central precisar se refletir em vários lugares.

Estrutura **flat** em `components/`. Hierarquia só se passar de 30–40
componentes ou surgir uma família grande.

## Índice de componentes

23 componentes. A API de cada um está no `{% comment %}` do próprio arquivo —
esta tabela diz o que existe e para quê, não como se chama cada parâmetro.

### Ação e navegação

| Componente | Para quê |
|---|---|
| `button.html` | Toda ação do sistema. 9 variantes, `<a>` ou `<button>`, passthrough HTMX/Alpine/modal |
| `pagination.html` | Paginação server-side, preservando filtros ativos |
| `ordenacao_data.html` | Inverte a ordem por data/hora de uma listagem paginada |
| `page_header.html` | `<h1>` de tela principal, dentro do `<main>` |

### Formulário

| Componente | Para quê |
|---|---|
| `form_field.html` | Campo com label vinculada, ajuda, erro e fiação ARIA completa |
| `field_error.html` | Erro inline de um campo em `role="alert"`, com todos os erros do campo numa frase só. O texto vem do Form, nunca daqui |
| `error_summary.html` | Sumário de erros no topo do formulário (padrão GOV.UK, foco no mount). Montado só por `{% erros_do_formulario %}` — nunca incluído direto |
| `item_form_row.html` | Linha de formset de item, compartilhada entre requisição e saída excepcional |
| `autocomplete.html` | Combobox ARIA de busca de material |

### Filtro

Família `filter_*`, montada por composição explícita na tela chamadora.

| Componente | Para quê |
|---|---|
| `filter_shell.html` | Moldura: disclosure no mobile, `<form>` HTMX, grade de campos (`partialdef`) |
| `filter_busca.html` | Campo de busca textual |
| `filter_select.html` | Select com opção "Todos…" |
| `filter_data.html` | Campo de data único — chamar duas vezes para um par De/Até |
| `filter_checkbox_group.html` | Grupo multi-seleção em `fieldset`/`legend` |
| `filter_acoes.html` | "Aplicar filtros" + "Limpar filtros" condicional, com reemite OOB |

### Superfície e feedback

| Componente | Para quê |
|---|---|
| `table.html` | Chrome de listagem em cartões (`partialdef`). Não há renderização em tabela |
| `modal.html` | `<dialog>` nativo: foco contido pelo top layer de `showModal()`, rolagem de fundo travada por `modal.js`, e uma linha de identidade obrigatória que nomeia o registro sendo confirmado — componente-assinatura |
| `_modal_body.html` | Corpo compartilhado do modal (header, erro, corpo, rodapé) |
| `_modal_icon.html` | Ícone semântico do header de modal |
| `_icone_nivel.html` | Glifo de severidade em `currentColor`, compartilhado pelo banner e pelo painel de decisão |
| `alert.html` | Banner de aviso estático de página ou formulário: glifo de nível, mensagem e um `role` — `alert` em `warning`/`danger`, `status` em `info`/`success` — que o chamador pode sobrescrever. Faz só isso |
| `badge.html` | Pill de estado. 14 variantes visuais, zero conhecimento de domínio |
| `empty_state.html` | Estado vazio com causa distinguida, nível de cabeçalho parametrizável (`nivel_titulo`, default 2) e CTA opcional |

Fora de `components/`: `core/partials/_messages.html` (flash messages do Django) e
`core/partials/_side_nav.html` (navegação lateral em `lg:`).

### Paridade entre o banner e a faixa de flash

`components/alert.html` e a faixa de flash message
(`core/partials/_messages.html`, que delega a marcação a
`core/partials/_message_item.html`) desenham os mesmos quatro níveis de
severidade. **São dois arquivos de propósito, e continuam sendo.** O que eles
não podem é divergir na superfície.

| Nível | Raio | Padding | Fundo | Borda | Texto | Ícone | role |
|---|---|---|---|---|---|---|---|
| `info` | `rounded-lg` | `px-4 py-3` | `bg-primary-subtle` | `border-primary-border` | `text-primary-text-emphasis` | `currentColor` | `status` |
| `success` | `rounded-lg` | `px-4 py-3` | `bg-success-subtle` | `border-success-border` | `text-success-text-emphasis` | `currentColor` | `status` |
| `warning` | `rounded-lg` | `px-4 py-3` | `bg-warning-subtle` | `border-warning-border` | `text-warning-text` | `currentColor` | `alert` |
| `danger` | `rounded-lg` | `px-4 py-3` | `bg-danger-subtle` | `border-danger-border` | `text-danger-text-emphasis` | `currentColor` | `alert` |

`danger` e `error` são o mesmo nível com dois nomes: o componente segue o
vocabulário de variante de `button.html`, a faixa recebe o que o Django emite.

Três coisas que a tabela decide e que valem a pena dizer em voz alta:

- **`rounded-lg` porque alerta é campo, não controle.** Pela Regra do Raio
  Crescente, 0.375rem é raio de controle e nenhuma das duas superfícies é
  acionável como unidade. A faixa usava raio de controle e saiu dele.
- **O ícone herda a cor da caixa.** Sem classe de cor, `fill="currentColor"`
  pega o token de texto do nível. Com cor fixa da variante, o ícone de `warning`
  ficava em 2.07:1 sobre o próprio fundo e falhava a WCAG 1.4.11 (3:1 para
  componente gráfico) — justo no único sinal não-cromático de nível. Herdando,
  vai a 6.88:1, e quatro ramos condicionais deixam de existir.
- **Um degrau de texto só.** Os quatro níveis usam o shade 800. O nome do token
  muda porque `warning` é a exceção da escala de sufixos acima: nas outras três
  famílias o 800 se chama `-text-emphasis`; em âmbar, que tem `-text-subtle` e
  não tem `-text-emphasis`, o 800 se chama `-text`. Mesmo degrau, dois nomes.

O `alert.html` não tem mais exceção interna de raio. O cartão de decisão de
workflow, que era papel num componente de campo, virou
`requisicoes/partials/_painel_decisao.html` na #127 — ver §Painel de decisão de
workflow. Deste lado sobra a regra sem exceção, e
`apps/core/tests/test_paridade_feedback.py` falha se um `rounded-xl` reaparecer
aqui.

#### Por que não há um partial compartilhado

Os contratos ARIA são incompatíveis. O banner é estático: é anunciado uma vez,
no lugar onde está, e não desaparece. A faixa é uma fila com `role` no nó que
contém só o texto, ordenação por assertividade, dismiss por teclado, e timer de
8s em `success`/`info` e nunca em `warning`/`error` (WCAG 2.2.1). Fundir os dois
obrigaria o parâmetro a descrever comportamento em vez de aparência — o sinal,
pelo contrato de componente logo abaixo, de que a abstração está errada.

O que **não** é compartilhado, e não deve passar a ser: o dismiss e seu timer, a
ordenação por assertividade, `body_template` e o ramo de fallback de variante
desconhecida.

`apps/core/tests/test_paridade_feedback.py` lê esta tabela e compara com os dois
templates renderizados **e** com a expectativa aprovada no próprio teste. As
três pontas precisam concordar: mudar tabela e templates juntos não passa.

### Badge forte para desfecho oposto no varrimento

`badge.html` tem quatro variantes fortes — `blue-strong`, `amber-strong`,
`red-strong`, `teal-strong` — que sobem um degrau na escala de sufixos: fundo
`-muted-strong` (shade 200) e ring `-border-strong` (shade 300).

`teal-strong` nasceu na issue #157. No varrimento de uma listagem, o fundo
`-muted` (teal-100) de "Estornada" fica a ΔL 0,009 / ΔC 0,007 / Δh 24° do verde
`success-muted` (green-100) de "Atendida" — dois desfechos opostos do documento,
entrega feita e entrega revertida, com carimbo perceptualmente igual. Subir
"Estornada" para `teal-strong` (teal-200) leva o par a ΔL 0,052 / ΔC 0,052, com
o Δh de 24° preservado. Texto `return-text-strong` (teal-900) sobre teal-200
mede 7,5:1 — acima do piso de 4,5:1.

Os tokens `--color-return-muted-strong` (teal-200) e
`--color-return-border-strong` (teal-300) vivem em `input.css`, no mesmo molde
de `primary`/`warning`/`danger`. A variante é aplicada por
`requisicoes/partials/_estado_badge.html` (estado `estornada`) e
`estoque/partials/_estado_saida_badge.html` (estado `estornada` da saída
excepcional). A Regra da Reversão Não é Erro continua intacta: teal mais forte,
nunca vermelho.

O par `blue`/`blue-strong` de "Autorizada" vs "Pronta para retirada" na fila de
atendimento foi medido junto: ΔL 0,050 / ΔC 0,027, mesmo passo de lightness que
a correção de "Estornada", e já distinguível num relance — segue sem mudança.

### Vocabulário de severidade do ícone de modal

`_modal_icon.html` tem cinco variantes, todas obrigatórias em `icon_variant`
(#136). O parâmetro deixou de ser opcional: era opcional e o resultado era
ruído — a severidade de cada modal saía ao acaso de quem lembrou de passar o
parâmetro, e três dos oito consumidores reais não passavam nada.

| Variante | Glifo | Cor | Quando usar |
|---|---|---|---|
| `info` | círculo de informação | azul | ação neutra, sem consequência a destacar |
| `warning` | triângulo de atenção | âmbar | pede cuidado redobrado antes de confirmar |
| `danger` | círculo de alerta | vermelho | recusar/cancelar: encerram a requisição, mas a trilha é append-only |
| `descarte` | lixeira | vermelho | reservada à única operação que remove um registro sem rastro (descarte de rascunho sem número público) |
| `return` | seta de devolução | teal | devolução **e estorno** — reversão operacional, Regra da Reversão Não é Erro |

Todos os cinco glifos saem do registry `{% icon %}` (`core_tags.py`), nunca de
SVG inline — era assim que `_modal_icon.html` tinha dois mecanismos de ícone
no mesmo arquivo (`danger` no registry, `warning`/`info` inline).

Mapa por consumidor (os 8 reais, não o componente isolado):

| Modal | Variante | Por quê |
|---|---|---|
| descartar rascunho | `descarte` | única remoção sem rastro do sistema |
| cancelar rascunho/requisição | `danger` | encerra, preserva o número público |
| recusar requisição | `danger` | encerra, não reserva nem baixa estoque |
| estornar requisição / estornar saída excepcional | `return` | reversão operacional; grava movimentação reversora, nunca vermelho |
| registrar devolução | `return` | reversão operacional, nunca vermelho |
| enviar / separar para retirada / autorizar | `info` | fluxo neutro, sem consequência a destacar |
| retornar para rascunho | `warning` | pede ajuste, atenção redobrada |
| confirmar registro de retirada | `warning` | baixa estoque físico, "não pode ser desfeita" |
| confirmar importação SCPI | `danger` | única escrita irreversível declarada do sistema, sem aprovação humana depois |

**O estorno saiu de `danger` (Etapa 6, fase 2).** A tabela acima listava
"estornar" em `danger` enquanto a linha de `return`, duas células abaixo, dizia
que reversão operacional nunca usa o vocabulário de erro — e
`_estado_badge.html` já carimbava o estado resultante "Estornada" em
`teal-strong`, com a Regra da Reversão Não é Erro dizendo "nunca vermelho" sobre
esse mesmo carimbo. A ação e o seu efeito diziam coisas opostas, e a devolução
já havia feito esse mesmo caminho na #136. Painel, gatilho, ícone e botão de
confirmação do estorno passaram a teal; `classes_painel_decisao` ganhou a
variante `return` e `_icone_nivel.html` ganhou o glifo. O vermelho volta a
significar só negação, falha e divergência.

A regra vale para as duas reversões que a tabela lista, e não só para a
requisição: o estorno de requisição em `requisicoes/detalhe.html` e o estorno de
saída excepcional em `estoque/detalhe_saida_excepcional.html`, incluindo o
`confirm_variant` que cada view repassa ao re-render 422 — o modal que reabre
com erro é o mesmo modal, e a cor da ação é parte dele. A tela de saída
excepcional já saía em `text-return-*` no bloco "Dados do estorno" enquanto a
ação que o produz saía em vermelho; era a mesma operação com dois sistemas de
cor na mesma página.

Duas coisas que a tabela corrige em relação ao que existia antes da #136:

- **A lixeira não é mais o glifo de `danger` inteiro.** Cancelar, recusar e
  estornar diziam "isto vai para o lixo" sem que nenhuma das três apagasse
  algo — `CONTEXT.md` é explícito que cancelamento preserva o número público,
  estorno grava movimentação reversora e a trilha é append-only. A lixeira
  ficou só com o descarte, a única operação que de fato remove sem rastro.
- **O fio teal não morre mais na porta do modal.** O trigger de "Registrar
  devolução" já era `return-outline` (teal, pela Regra da Reversão Não é
  Erro); o modal confirmava em azul (`primary`) e sem ícone. `confirm_variant`
  da devolução passou a `return` (variante preenchida nova em
  `button.html`/`core_tags.py`), no mesmo tom do trigger.

Variante fora do catálogo cai na Decisão A-1, como em `alert.html` e
`badge.html`: fundo cheio de grito (`bg-danger`, não a lavagem `-muted`),
`role="alert"` e o valor cru em `data-modal-icon-variant`.

Verificado por `apps/core/tests/test_modal_icon.py`.

### Foco inicial do modal de confirmação

`modal.js` decide para onde o foco vai quando o `<dialog>` abre, e a ordem é
sempre a mesma — no render inicial e no re-render de 422:

1. `[aria-invalid="true"]` — o campo que voltou com erro;
2. o primeiro campo do DOM (`textarea`, `input` não-oculto, `select`) — a
   consulta é por ordem de documento e não olha visibilidade computada;
3. `[data-modal-dismiss]` — o botão de dispensa ("Voltar").

Não há quarta perna: sem botão de dispensa, `modal.js` não mexe no foco e a
resposta final é onde os passos nativos de `showModal()` o puseram. O
`[data-modal-body]` é `tabindex="-1"` para que esse lugar seja o corpo do
diálogo — conteúdo inerte, que anuncia título e descrição e não tem o que Enter
ative.

**O foco de abertura nunca vai para `[data-modal-confirm]`** (#132). Modal sem
campo é confirmação pura, e neste sistema esses são exatamente os que executam
operação irreversível — enviar, separar, autorizar, atender retirada, importar
SCPI. Quem aciona o trigger pelo teclado chega ao diálogo com o Enter ainda
pressionado, e o `keydown` repete no elemento que acabou de receber o foco: com
o foco no botão que executa, a porta abre com a mão já na maçaneta errada. A
WAI-ARIA APG manda o contrário — foco inicial na opção menos destrutiva. Por
isso o degrau 3 existe, e por isso `button.html` tem `data_modal_dismiss`: é o
par de `data_modal_confirm`, e diz qual botão o foco pode encostar sem executar
nada.

**O modal também não confirma por submissão implícita.** Enter num campo de
linha única submete o `<form>` sem passar pelo rodapé, que é onde a consequência
está escrita — e o modal de devolução abre com o foco num
`<input type="number">`. `modal.html` traz
`@keydown.enter="bloquearSubmitImplicito($event)"` **nos dois modos**: no
`<form>` interno do modo `action_url`, e no `<div>` envolvente do modo
`submit_form_id`, onde o `<dialog>` costuma ficar dentro do formulário que
confirma e um campo do corpo pertenceria a ele.

A trava barra `<input>` que não seja botão e `<select>` — os dois no seletor do
degrau 2. **As duas origens não têm o mesmo estatuto**, e a diferença importa
para quem for mexer nisso:

- `<input>` é a regra do HTML. A especificação lista os estados que governam a
  submissão implícita (Text, Search, URL, Telephone, Email, Password, Number e
  os de data/hora); é comportamento exigido, não conveniência de navegador.
- `<select>` **não** está nessa lista. Entra na trava por decisão deste
  componente, porque o degrau 2 pode pousar o foco num `select` e o navegador
  submete assim mesmo. Medido no Chromium: Enter com o select fechado dispara o
  submit do `<form>`, igual a um campo de texto.

Passam de propósito o `<textarea>` (onde Enter é quebra de linha) e os botões e
links (onde Enter é a ativação do próprio controle, e `preventDefault` mataria o
clique ou a navegação).

Verificado por `apps/core/tests/test_modal.py` (marcação do contrato) e por
`apps/requisicoes/tests/test_navegador_modal_foco.py` (comportamento em
Chromium, camada Navegador da ADR-0019).

### Desfechos do modal depois de confirmar

No modo `action_url`, confirmar dispara um POST por HTMX, e o componente tem que
ter uma resposta visível para **cada** desfecho possível — o rodapé descreve
essas ações como irreversíveis, e "a tela voltou ao normal" não é resposta
(#133). O modo `submit_form_id` submete o formulário externo, que hoje é POST
clássico: ali o desfecho é a navegação, e a tabela abaixo não se aplica.

| Desfecho | O que acontece |
|---|---|
| 204 + `HX-Redirect` | Navega. É o contrato PRG da ADR-0011, fechado pela #130 |
| 422 | `htmx:beforeSwap` liga o swap, `[data-modal-body]` volta com a caixa de erro, o foco vai ao `[aria-invalid]` |
| 5xx, 403, 404 | `htmx:responseError` clona o molde `servidor` para dentro do slot |
| Queda de conexão | `htmx:sendError` clona o molde `conexao` |

**A caixa de falha de transporte é renderizada pelo servidor, não montada em
JS.** `_modal_body.html` emite dois `<template data-modal-erro-transporte>` com
`{% erros_do_formulario %}` dentro, e `modal.js` só clona o que couber ao
desfecho para o `[data-modal-erro-transporte-slot]`. Montar markup de erro no JS
seria a quarta grafia de "o formulário falhou", que é a divergência que a tag
existe para fechar; e o texto é copy de produto em PT-BR, nunca o status code.
O slot fica **fora** da região rolável, entre cabeçalho e corpo, para estar na
tela mesmo com o formulário rolado.

**Nenhuma via de fechamento vale com a requisição em voo.** Fechar ali trocaria
o corpo de um `<dialog>` já fechado: a recusa não seria vista, e o `role="alert"`
da caixa de erro seria anunciado num nó que não está renderizado.

As vias não entram pela mesma porta, e a diferença importa para quem for mexer
nisto. Backdrop e "Voltar" passam por `fechar()`, que desiste enquanto existe
`form[data-submitting="1"][hx-post]` dentro do diálogo — ou envolvendo-o, no modo
`submit_form_id`. `Esc` passa por `fechar()` **só** quando o foco está dentro do
diálogo, que é quando o `@keydown.escape` de `modal.html` roda; fora disso quem
fecha é o caminho nativo, e a trava dele é o listener de `cancel`, que dá
`preventDefault()` sob a mesma condição.

O recorte por `hx-post` é deliberado, e as duas razões apontam para o mesmo
lugar. O dano que a trava evita é a resposta ser trocada dentro de um diálogo
fechado, e só um XHR troca alguma coisa; um POST clássico navega, e o diálogo
vai embora com a página. E `htmx:afterRequest` — que é quem apaga a marca — não
dispara em form clássico, então lá o `data-submitting` só cai com a navegação:
se ela for abortada, sem o recorte o diálogo ficaria trancado sem saída.
`requisicoes/atender_retirada.html` é exatamente esse form.

A segunda rota do `Esc` não é hipótese: é a que ocorre depois do clique em
confirmar. `form-submit.js` desabilita o botão acionado, o navegador solta o
foco dele, e o `keydown` deixa de ter alvo dentro do diálogo — sem o listener de
`cancel`, a trava não alcançaria o `Esc` no exato instante em que ela existe
para valer.

**A caixa de falha de transporte é limpa na abertura**, e não só no
`htmx:beforeRequest`. Reabrir o modal é tentar de novo; a mensagem descreve a
tentativa anterior, e deixá-la ali faria a abertura acusar um erro que ainda não
aconteceu.

**Fechar por backdrop exige `mousedown` e `mouseup` fora da caixa.** Só com
`@click`, uma seleção de texto que começa dentro do modal e termina fora chega
com `target` no `<dialog>` e era lida como "clicou fora" — apagando a
justificativa inteira. E, com texto digitado, o backdrop **não descarta**: é o
gesto mais fácil de disparar sem querer do componente, e justificativa de
estorno e de cancelamento é obrigatória e pode ter parágrafos. As duas saídas
deliberadas — `Esc` e "Voltar" — continuam de pé, e são elas que dizem que a
pessoa quis mesmo sair. "Preenchido" é `value !== defaultValue`: um campo com
default do servidor não trava nada.

**Recusar o gesto não pode ser mudo**, ou seria a mesma falha que esta seção
fecha nos outros três lugares — a pessoa age e nada acontece, sem explicação. O
foco vai para "Voltar": é a saída de verdade, o leitor de tela anuncia o botão,
e encostar nele não executa nada, porque `[data-modal-dismiss]` é `type="button"`
por contrato. Um `confirm()` nativo também resolveria e foi **descartado** — é
vocabulário que este design system não tem, e apareceria como artefato do
navegador por cima de um `<dialog>`.

Verificado por `apps/core/tests/test_modal.py` (slot, moldes, copy, `@mousedown`)
e por `apps/requisicoes/tests/test_navegador_modal_em_voo.py` (comportamento em
Chromium).

### O que o modal faz com a página atrás dele

**Nada em volta do diálogo é operável, e nada disso é feito à mão.**
`showModal()` põe o `<dialog>` no top layer e torna o resto do documento inerte
nativamente: o foco não sai, o clique não alcança, o leitor de tela não navega
para fora. O componente já teve `x-trap.inert.noscroll` declarado nos dois modos
e o diretivo **nunca ativou** — a expressão era `$refs.dialog.open`, que o
`effect` do Alpine não consegue rastrear (`$refs` é `mergeProxies`, não
`reactive()`, e `.open` é propriedade IDL nativa). Foi removido: os dois efeitos
que ele prometia sobre foco já vêm do navegador, e `aria-hidden` espalhado à mão
convive mal com o inert nativo (#134).

**A rolagem do fundo trava, e essa parte é explícita.** É o único efeito do
diretivo morto que fazia falta de verdade. `modal.js` grava `overflow: hidden`
no `<html>` com a compensação da barra de rolagem — o mesmo gesto do plugin de
foco, que continua governando o menu da barra de aplicação — e desfaz no evento
`close`, que cobre todas as saídas, inclusive o `Esc` nativo. Rolar o fundo
enquanto o modal pergunta se pode executar algo irreversível tira da tela o
registro sobre o qual a pergunta é feita.

> O valor global é um só, e tem dois donos sem contagem: esta trava e o
> `x-trap.noscroll` do menu da barra de aplicação. Desfazer em LIFO funciona;
> intercalar, não. Quem garante o LIFO hoje é o próprio menu, que fecha no
> `@click.outside` antes de qualquer trigger de modal ficar clicável.

**`overscroll-contain` mora na caixa que rola**, que é a região do corpo em
`_modal_body.html`, e não no `<dialog>` — o diálogo tem `max-h` e nunca ganha
barra própria, então lá o atributo não tinha o que conter.

**`abrir_ao_carregar` é server-side de verdade**: o template emite `open` no
`<dialog>`, e é essa marcação — não uma opção do `modalController` — a fonte
única de "este modal abre ao carregar". Sem JS o diálogo abre não-modal, no
fluxo da página, com a caixa de erro legível; com Alpine vivo o init o promove a
modal por `showModal()`. Antes, a abertura só existia no Alpine e o re-render
com erro voltava numa tela aparentemente intacta, com a recusa escondida dentro
de um diálogo `display: none`.

**`aria-modal` acompanha o que o diálogo é**, e não o que ele vai virar. O
template emite `false` junto com `open`, porque até a promoção o resto da página
está mesmo operável e o "Voltar" do rodapé (`@click="fechar()"`) está morto sem
Alpine — anunciar "modal" ali prenderia o leitor de tela num diálogo sem saída.
`modal.js` sobe o valor para `true` no mesmo passo do `showModal()`.

> Este não é o único caminho de erro sem JS do sistema, e os dois são válidos:
> requisições re-renderizam a página inteira com o modal aberto; o estorno de
> saída excepcional em `estoque` usa PRG com a mensagem no banner de topo. A
> escolha segue o que a view já faz com o desfecho, não o componente.
>
> O parâmetro exige **bool do contexto**. `erro|yesno:"true,false"` era o idioma
> certo enquanto o destino era uma expressão JavaScript e é veneno agora: a
> string `"false"` é verdadeira para o `{% if %}` e abriria todo modal, em
> silêncio. `validar_contrato_modal` recusa o render se ela chegar.

Verificado por `apps/core/tests/test_modal.py` (o atributo `open`, a recusa do
`|yesno`, o lugar do `overscroll-contain`), por
`apps/core/tests/test_components.py`
(`test_nenhum_x_trap_liga_a_propriedade_fora_do_escopo_alpine`, que impede a
forma morta de voltar em qualquer template) e por
`apps/requisicoes/tests/test_navegador_modal_scroll.py` (comportamento em
Chromium).

### Rodapé, corpo rolável e retorno de foco (#137)

**`role` do `<dialog>` é parametrizável**, default `"dialog"`. Todo consumidor
real recebe `role="alertdialog"`, exceto `confirmar-retornar` e `devolver` —
os dois caminhos que a Regra da Reversão Não é Erro trata como reversão de
workflow, tom neutro, não confirmação de dano. A #136 tornou essa distinção
explícita no vocabulário de ícone: `devolucao_copy['icon_variant']` é
`'return'` (teal), o mesmo fio do trigger `return-outline` — o modal não pode
confirmar essa ação em tom de alerta se o resto da tela já a trata como
operação normal. `alertdialog` é o que faz o leitor de tela anunciar o corpo
como alerta na abertura, não só o título; a APG recomenda o papel para todo
diálogo que notifica algo importante e pede uma decisão antes de prosseguir —
que é a descrição de qualquer outro modal deste componente.

**`aria-modal` continua escrito à mão**, e uma tentativa de removê-lo foi
revertida no mesmo PR que a introduziu. A exposição implícita de `<dialog>`
não bastaria: `getAttribute('aria-modal')` continua `null` mesmo depois de
`showModal()` — medido quebrando dois testes da camada Navegador que liam o
atributo para provar a promoção a modal
(`apps/requisicoes/tests/test_navegador_modal_scroll.py`). Sem o valor escrito
à mão, nada no HTML renderizado ou no DOM prova que o diálogo é modal.

**`loading_label` chega ao rodapé nos dois modos, e todo consumidor real
passa um valor.** Antes o parâmetro não existia no contrato do componente — o
rótulo só trocaria por acidente, via herança de contexto do `{% include %}`,
nunca de propósito. Hoje `modal.html`/`_modal_body.html` declaram o parâmetro
e os onze consumidores passam um verbo no gerúndio ("Cancelando…",
"Recusando…", "Estornando…" etc).

**O rodapé respeita `env(safe-area-inset-bottom)`**, mesma grafia de
`atender_retirada.html` e da `.app-bar`
(`pb-[calc(1rem+env(safe-area-inset-bottom))]`). Sem isso, um modal na altura
máxima — estorno com justificativa, teclado do celular aberto — deixava o
botão de confirmar embaixo do home indicator do iPhone.

> **`app.css` é versionado, e toda classe Tailwind nova no template precisa
> de `make css-build`** antes do commit — regra já registrada mais acima
> neste doc, e que esta issue violou na primeira volta: a classe do
> safe-area chegou ao template sem o build correspondente, e o padding não
> existia em produção até o build rodar.

**A região rolável do corpo tem `tabindex="0"` e `aria-labelledby` só quando
não há nenhum controle nativamente focável no corpo.**
`confirmar-importacao-scpi` é o único consumidor sem campo nenhum — sem o
atributo, o recap da importação ficava inalcançável pelas setas em viewport
curta (WCAG 2.1.1). Nos outros dez, que já têm `<textarea>`/`<input>` no
`form_body_template`, os dois atributos são suprimidos por
`corpo_com_campo_focavel=True` no chamador: escrevê-los ali seria uma parada
de tabulação extra e redundante antes do campo de verdade. `confirmar-cancelar`
é o caso dinâmico — a justificativa só renderiza quando
`cancelamento_requer_justificativa` é verdadeiro, e o parâmetro repassa essa
mesma variável em vez de um `True` fixo.

**A expressão de submit do modo `submit_form_id` virou método do
`modalController`** (`submeterFormExterno`), não mais uma string montada no
template. `getElementById(...)?.requestSubmit() ?? console.error(...)`
disparava o `console.error` sempre — `requestSubmit()` devolve `undefined`, e
`undefined ?? X` avalia `X` — e toda confirmação de retirada bem-sucedida
gravava um erro falso no console. O método não mexe em `aria-busy` nem no
rótulo: o botão de confirmar já tem `data-modal-confirm`, que está no seletor
de `alvosDoForm` de `form-submit.js`, e `requestSubmit()` dispara o `submit`
nativo que aquele listener escuta — duplicar a troca ali fazia os dois donos
brigarem pelo mesmo atributo (a primeira versão gravava `aria-busy="true"`
antes de `form-submit.js` capturar o valor "antes" para restaurar depois).

O bloqueio de duplo envio deste modo é próprio — antes só existia por acaso,
herdado do `<form>` externo ter `data-prevent-double-submit`. A trava vive no
próprio `<form>` (`data-submetendo-externo`), não numa propriedade do
componente Alpine: é o que permite ao listener de `pageshow`/`persisted` no
fim de `modal.js` desfazê-la depois de uma volta pelo bfcache sem precisar de
referência a cada instância — mesmo tratamento que `form-submit.js` já dá ao
`data-submitting` dele.

**`abrirSemTrigger` sem trigger no DOM não devolve o foco ao `<body>`.**
`modalController` aceita `focoFallbackSeletor` (opcional) — um seletor CSS de
alvo declarado da tela, promovido a `tabindex="-1"` se ainda não for focável —
usado quando `[data-modal-trigger]` não existe mais no documento (ação de
workflow que deixou de ser permitida entre a submissão que abriu o modal com
erro e o re-render). `requisicoes/partials/_confirmacao_acao.html` e o
`x-data` inline de `confirmar-cancelar` declaram `.app-bar__title`.

**Todo `.focus()` de `modal.js` usa `{ preventScroll: true }`** — sem isso,
focar um campo abaixo da dobra saltava o corpo do diálogo.

Verificado por `apps/core/tests/test_modal.py` (role, safe-area,
`loading_label`, `tabindex`/`aria-labelledby` condicional do corpo, ausência
da expressão antiga), por `apps/requisicoes/tests/test_views.py` (role,
`loading_label` e supressão do `tabindex` em consumidores reais — não só o
passthrough sintético do componente) e por
`apps/requisicoes/tests/test_navegador_modal_foco.py` e
`test_navegador_modal_submit_externo.py` (o `console.error` distinguindo os
dois casos, o bloqueio de duplo envio, a liberação por `pageshow`/bfcache, o
retorno de foco ao fallback — comportamento em Chromium).

### O modal nomeia o registro que está confirmando (#138)

**`registro` é obrigatório em todo modal**, no mesmo molde de `icon_variant`:
`validar_contrato_modal` recusa o render inicial sem ele e
`apps.core.modal.render_modal_erro` recusa o 422, os dois pela mesma função
(`validar_registro_modal`). É um mapa com `rotulo`, `identificador` e
`contexto` (opcional), renderizado como **linha fixa entre o `<h2>` e a
descrição** do cabeçalho.

Nenhum dos oito consumidores carregava número público, estado ou quantidade.
"Estornar requisição" — qual? "Confirmar recusa" — de quem? Em bloco de decisão
no desktop, que é a cena declarada do chefe de setor no `PRODUCT.md`, a pessoa
abre várias requisições em sequência e confirmava sem âncora nenhuma de qual
estava na frente. É o vetor clássico de executar a ação certa no documento
errado, e o sistema não tem desfazer.

**Obrigatório em todo modal, não só nos que movimentam estoque.** Um recorte por
tipo de ação exigiria uma lista de ids "que escrevem movimentação" mantida à mão
em sincronia com o domínio, e deixaria de fora o `confirmar-enviar` — que é onde
o número público nasce. O que cada consumidor tem a dizer varia; que ele diga
alguma coisa, não.

**O mapa é montado na apresentação de cada app, nunca no template.**
`registro_requisicao` (`apps/requisicoes/presentation.py`),
`registro_saida_excepcional` e `registro_arquivo_scpi`
(`apps/estoque/presentation.py`). Seis modais da mesma tela de detalhe
confirmam a mesma requisição: cada `{% include %}` redigindo a própria versão
de "qual documento é este" é a divergência que a #135 fechou para título e
descrição.

> **`identificador` nunca sai do `__str__` do model.** `str(requisicao)` devolve
> `Rascunho #<pk>`, e `docs/CONVENTIONS.md` §Identificadores na interface
> diz que PK interno não vaza para UI. O fallback é o literal `"Rascunho"`
> (requisição) ou `"Sem número"` (saída excepcional), e quem responde "qual
> documento?" nesse caso é o `contexto`. O `__str__` continua servindo admin e
> log, que é para onde ele foi escrito.

**O que cada consumidor mostra.** A linha de identidade responde "qual
documento"; o corpo responde "quanto isto move":

| Modal | Identidade | Corpo |
|---|---|---|
| `confirmar-autorizar`, `confirmar-recusar`, `confirmar-retornar`, `confirmar-cancelar`, `confirmar-enviar`, `confirmar-separar` | número público (ou "Rascunho") · beneficiário · setor | campo da ação, quando há |
| `estornar-modal` | idem | material e entregue líquida de cada item que volta ao saldo físico |
| `devolver-<item>` | idem | material e entregue líquida disponível (já existia) |
| `confirmar-atender-retirada` | idem | material, quantidade autorizada e a **entregue digitada agora** |
| `estornar-saida` | número da saída · estoque · quem registrou | justificativa |
| `confirmar-importacao-scpi` | nome do arquivo | novos, divergências e linhas lidas (já existia) |

**A quantidade da retirada é lida do campo, não do servidor.** Em
`atender_retirada.html` a pessoa digita item a item num formulário de até 15
linhas, e o modal dizia *"baixa estoque das quantidades entregues"* sem repetir
uma única quantidade. O corpo
(`requisicoes/partials/_modal_corpo_atender_retirada.html`) traz material e
autorizada renderizadas pelo servidor, e cada célula de "entregue" declara o
`id` do `<input>` de onde lê; `sincronizarResumo`, em `modal.js`, copia o valor
antes do `showModal()`. Imprimir o `initial` do formset ali mostraria o valor com
que a tela abriu — um número plausível e errado, que é pior que nenhum. Parear
por `id` e não por posição é o que sobrevive a uma mudança de ordem entre as
duas listas.

**A identidade entra no `aria-describedby` do `<dialog>`**, antes da
`descricao`. Sem isso, quem usa leitor de tela ouvia a ação e a consequência, e
a única resposta a "qual requisição?" ficava na tela atrás — justamente a parte
que `showModal()` torna inerte.

**`consequencia` é a frase de irreversibilidade, e não mora mais na
`descricao`.** Ela é renderizada no fim do corpo em `text-sm font-semibold
text-text-primary`; a descrição continua em `text-sm text-text-secondary`. No
cabeçalho a hierarquia estava invertida: no modal do SCPI, *"A gravação não pode
ser desfeita"* era secundária enquanto as três contagens logo abaixo saíam em
`text-base font-semibold` — a tipografia dizia que os números importavam mais
que o aviso de que eles são definitivos. Continua dita **uma vez só**: quem
ganhou `consequencia` teve a frase removida da `descricao`, e o painel de
decisão que resume a ação antes de abrir o modal concatena as duas. Só recebe
`consequencia` a ação que de fato não tem volta — retornar para rascunho e
devolução não recebem.

**O backdrop escurece e não desfoca.** `backdrop:bg-slate-900/60`, sem
`backdrop-blur`. Era a única superfície embaçada do sistema, e o `DESIGN.md`
recusa vidro fosco no north star; a exceção só se sustentava porque nada dentro
do diálogo dizia sobre qual documento a pergunta era feita. Borrar a tela de
origem apagava número público, beneficiário, itens e entregue líquida
exatamente no instante em que serviriam de âncora. `/60` e não `/50` porque,
sem o desfoque, o overlay sozinho responde por separar as duas camadas.

> O nome da classe removida não aparece escrito em nenhum template: o scanner
> do Tailwind lê o arquivo inteiro, comentário incluso, e recompilaria a regra
> morta a partir da própria explicação de por que ela morreu. `DESIGN.md` está
> na varredura pelo mesmo motivo — só `docs/` é excluído.

Verificado por `apps/core/tests/test_modal.py` (obrigatoriedade, dict
incompleto, tipo errado, ordem no cabeçalho, ênfase da consequência, backdrop
sem desfoque), `apps/core/tests/test_modal_erro.py` (as mesmas regras no 422),
`apps/core/tests/contrato_modal.py` (`assert_copy_nao_diverge` compara também a
identidade entre render inicial e 422) e pelos testes por consumidor em
`apps/requisicoes/tests/test_views.py` e `apps/estoque/tests/test_views.py`,
que leem o texto **de dentro de cada `<dialog>`** — buscar no documento inteiro
passaria só porque a tela atrás também mostra o número, que é exatamente a
situação que esta seção existe para consertar.

### Painel de decisão de workflow

`requisicoes/partials/_painel_decisao.html` é a superfície compartilhada das
decisões de fluxo da requisição — autorizar, recusar, retornar, cancelar,
estornar: título, descrição e o botão que abre o modal de confirmação. Dois
layouts — `card`, dentro do grid de decisão, e `banner`, seção de largura total.

O painel **não** implica um ator. Quem pode cada operação sai das policies e de
`docs/matriz-permissoes.md`, e varia por ator efetivo, setor, beneficiário e
estado atual — autorizar e recusar são do chefe do Setor do Beneficiário,
enquanto estornar é do chefe de Almoxarifado. A tela só renderiza o painel que
o `pode_*` correspondente liberou.

Ele já foi montado em cima do `alert.html`, de onde herdava só a lavagem de cor
por variante. A separação é da #127, e o que ela fixou vale para qualquer
superfície de decisão que venha depois:

- **É papel, não campo.** `rounded-xl`, `shadow-sm`, padding de seção. Um alerta
  é banner embutido no fluxo e leva raio de campo; um painel com ação
  persistente é papel. A Regra do Raio Crescente responde isso sozinha.
- **O nível é comunicado por mais do que cor.** Glifo de `_icone_nivel.html` em
  `currentColor`, o mesmo do banner. Sem ele, um painel `danger` e um `warning`
  se distinguiam só pela lavagem `-subtle` (L≈98%) e pela borda — cor como sinal
  único de estado, que a Regra do Sinal Único não permite para severidade.
- **Todo painel tem nome acessível.** O `card` é `role="group"` amarrado por
  `aria-labelledby` ao próprio `<h3>`; o `banner` é `<section>` nomeada pelo
  `<h2>`. `role="group"` anônimo faz três cards virarem "grupo, grupo, grupo" na
  navegação estrutural, apesar de cada um já ter um heading pronto.
- **O sufixo `-titulo` sobre o `modal_id` é do modal, não do painel** (#131).
  Quem emite `{{ modal_id }}-titulo` é o `<h2>` de `_modal_body.html`, alvo do
  `aria-labelledby` do `<dialog>`. O painel entra antes no DOM, então um `<h3>`
  com esse mesmo id duplicava o id e fazia o diálogo ser anunciado com o título
  do cartão que ficou atrás. O card usa `-painel-titulo`; o `heading_id` que o
  chamador passa ao `banner` também não pode terminar em `-titulo` sobre o
  `modal_id` daquele painel.
- **A descrição é corpo de 14px.** Ela sustenta uma decisão irreversível, lida em
  bloco. 12px é rótulo estrutural em caixa alta, pela Regra dos 14px.
- **O mapa variante→token vive em `classes_painel_decisao`** (`core_tags.py`),
  nunca reescrito no partial de domínio. Era exatamente essa duplicação —
  dois switches que precisavam concordar com o do componente, sem nada
  garantindo isso — que a extração fechou.
- **Variante desconhecida cai na Decisão A-1**, como no `alert.html` e no
  `badge.html`: `bg-danger` preenchido, "Aviso indisponível", `role="alert"` sem
  exceção e `data-painel-variant` cru — com a decisão ainda legível e acionável.
- **O painel não recebe classe do chamador.** `desc_class` e `bg_class`
  existiram e morreram: pela Regra do Chrome Sem Parâmetro, parâmetro que
  descreve conteúdo em vez de estrutura é sinal de abstração errada.
- **`aria-haspopup="dialog"` é do painel, não do chamador.** O botão abre um
  modal por definição — é isso que faz dele um painel de decisão. Como
  parâmetro opcional, só um dos cinco painéis declarava, e os outros quatro
  prometiam menos do que faziam.

Verificado por `apps/requisicoes/tests/test_painel_decisao.py`.

## Contrato de componente novo

```
[ ] Bloco {% comment %} de cabeçalho: parâmetros, obrigatoriedade, contrato
    ARIA e o motivo das decisões não óbvias
[ ] Só tokens semânticos — zero classe de paleta crua
[ ] Raio conforme a camada (controle / campo / papel / modal)
[ ] Elevação em um dos quatro degraus
[ ] Piso de 44px em qualquer coisa acionável
[ ] focus-visible:ring-2 com offset
[ ] Zero semântica de domínio — variante e label chegam resolvidos
[ ] Uma linha no índice acima
```

Se o componente precisa de um parâmetro que descreve **conteúdo** e não
estrutura, a abstração está errada. Parar e registrar, não generalizar.

## Borda de controle: medições vigentes

Onde a borda é a única delimitação do controle — botão de fundo branco —, a WCAG
1.4.11 pede 3:1. **Nenhuma variante está em exceção.** As quatro passam, medidas
sobre branco a partir do token, não do nome da classe:

| Variante | Token da borda | Medido |
|---|---|---|
| `secondary` | `border-control` (slate-500) | 4,77:1 |
| `danger-outline` | `danger-accent` (red-500) | 3,82:1 |
| `warning-outline` | `warning-text-subtle` (amber-700) | 5,05:1 |
| `return-outline` | `return` (teal-600) | 3,66:1 |

`warning-outline` chegou lá por um caminho diferente das irmãs, e é o que vale
registrar: a família âmbar **não tem token de borda** que passe — `amber-500`,
o mais escuro da escala de bordas, dá 2,15:1, e o âmbar claro o bastante para
continuar âmbar não alcança 3:1 sobre branco. Os únicos membros ≥3:1 da família
são os de texto, já alaranjados; daí a borda usar `warning-text-subtle`, que a
deixa na mesma família do texto do próprio botão.

Valores **históricos**, de antes da Etapa 6, quando as três variantes de
contorno viviam nos `-border-strong` — shades escolhidos para separar
superfícies, não para desenhar controles: `danger-outline` 1,92:1 (red-300),
`warning-outline` 1,45:1 (amber-300), `return-outline` 1,26:1 (teal-200).
Quatro dos cinco gatilhos de workflow da tela de detalhe usavam essas variantes,
ou seja, as ações destrutivas eram os controles menos visíveis da página.

`test_borda_de_controle_passa_em_1411` (`apps/core/tests/test_components.py`)
resolve o token até o `oklch` da paleta e calcula a razão de verdade, para toda
variante de fundo branco. Trocar um shade por outro que passe segue válido;
trocar por um que não passe fica vermelho. A tabela acima é registro; o teste é
o guarda.

## Checklist de revisão — acessibilidade

```
[ ] Contraste de texto ≥ 4.5:1; borda que identifica controle ≥ 3:1
    (medições vigentes: ver §Borda de controle: medições vigentes)
[ ] Todo controle interativo tem focus-visible
[ ] Botão em carregamento usa aria-busy
[ ] Campo com erro usa aria-invalid + aria-describedby
[ ] Readonly e disabled visualmente distintos
[ ] Modal e dropdown operáveis por teclado (Tab, Escape, Enter/Espaço)
[ ] Modal de confirmação abre no campo com erro, no primeiro campo, na ação
    menos destrutiva ou no corpo quando não há controle aplicável — nessa
    ordem, e nunca em [data-modal-confirm]
    (ver §Foco inicial do modal de confirmação)
[ ] Ação bloqueada tem motivo textual amarrado por aria-describedby
[ ] Atualização HTMX crítica tem aria-live ou feedback visível
[ ] Listagem filtrada por HTMX anuncia a CONTAGEM numa live region fora da
    lista — nunca a lista inteira (ver §Anúncio de listagem filtrada por HTMX)
[ ] Live region NÃO é o mecanismo depois de um POST full-page — conteúdo já
    presente no carregamento não é anunciado; o que funciona é foco programático
    (tabindex="-1" + foco no mount), com anel `focus:` e não `focus-visible:`
[ ] Ícone tem alternativa textual (aria-label, ou contexto que já o nomeia)
[ ] Badge de dado estático NÃO usa role="status" — 20 linhas virariam 20 live regions
```

## Exemplos de uso

Botão de navegação (só `href`, navegação nativa):

```django
{% include "components/button.html" with label="Ver detalhes" variant="secondary" href=url_detalhe aria_label="Ver detalhes da requisição REQ-2026-001" %}
```

Botão com HTMX — `hx_target` é literal, então quem chama manda o seletor pronto, com `#`:

```django
{% with seletor_alvo="#"|add:target_id %}
  {% include "components/button.html" with label="Limpar filtros" variant="secondary" href=action_url hx_get=action_url hx_target=seletor_alvo hx_push_url="true" %}
{% endwith %}
```

O `href` continua presente de propósito: sem JavaScript o link navega, e o HTMX é a
melhoria progressiva por cima. É o padrão de `components/filter_acoes.html`.

Campo de formulário:

```django
{% include "components/form_field.html" with field=form.observacao_geral %}
```

Campo fora de um Form Django (raro — prefira o Form):

```django
<input type="search" name="busca" class="campo" aria-label="Buscar material">
```

Badge de estado, via partial de domínio:

```django
{# em requisicoes/partials/_estado_badge.html #}
{% if requisicao.estado == "rascunho" %}
  {% include "components/badge.html" with variant="slate" label="Rascunho" prefixo_sr="Estado: " %}
{% elif requisicao.estado == "autorizada" %}
  {% include "components/badge.html" with variant="blue" label="Autorizada" prefixo_sr="Estado: " %}
{% endif %}
```

Listagem em cartões, com o fragmento de resultado pronto para swap HTMX:

```django
{% partialdef resultados %}
{% if lista %}
  {% include "components/table.html#cards_abertura" %}
    {% for item in lista %}
      {% include "components/table.html#card_abertura" %}
        <div class="flex items-start justify-between gap-3">
          <h2 class="break-words text-sm font-semibold text-text-primary">{{ item.titulo }}</h2>
          <span class="shrink-0">{% include "components/badge.html" with variant="blue" label="Autorizada" %}</span>
        </div>
      </article>
    {% endfor %}
  </div>
{% else %}
  {% include "components/empty_state.html" with icone="components/icons/_caixa_entrada.html" titulo="Nada por aqui" descricao="Os itens aparecem aqui assim que existirem." %}
{% endif %}
{% endpartialdef %}
{% partial resultados %}
```

O fragmento é sempre **GET-only**. Transição de estado de domínio continua
retornando `204` com `HX-Redirect` (`docs/CONVENTIONS.md`); este fragmento nunca
é alvo delas.

### Anúncio de listagem filtrada por HTMX

Uma listagem filtrada por HTMX troca de conteúdo sem navegação: sem anúncio,
quem filtrou não sabe se filtrou demais ou se a requisição travou. O que **não**
resolve é marcar o wrapper de resultados como live region — a cada ajuste de
filtro o leitor de tela releria as 25 linhas do começo, e uma região substituída
inteira não anuncia de forma confiável.

O padrão é anunciar o **tamanho** do resultado, não o resultado:

```django
{% comment %}
  Vazia no carregamento inicial: nada mudou ainda.
{% endcomment %}
<p id="resumo-listagem" class="sr-only" role="status"></p>

<div id="resultados-listagem">
  {% partialdef resultados %}
  ...
  {% if is_htmx %}
    <span hx-swap-oob="innerHTML:#resumo-listagem">{% if page_obj.paginator.count %}{{ page_obj.paginator.count }} it{{ page_obj.paginator.count|pluralize:"em,ens" }} encontrad{{ page_obj.paginator.count|pluralize:"o,os" }}.{% else %}Nenhum item encontrado.{% endif %}</span>
  {% endif %}
  {% endpartialdef %}
  {% partial resultados %}
</div>
```

Três coisas não são negociáveis aqui:

- **A região fica FORA do wrapper de swap.** Dentro dela seria substituída
  junto e perderia o `role`.
- **O swap é `innerHTML:`**, não out-of-band pelado. Sem o prefixo o elemento
  inteiro é trocado e a live region vai junto — o anúncio morre em silêncio,
  sem quebrar nada visível.
- **A contagem é `page_obj.paginator.count`**, o total do recorte filtrado.
  `object_list|length` anunciaria o tamanho da página: "25 encontrados" para um
  filtro que casou 300.

**O filtro corta a palavra onde a flexão começa.** `pluralize` acrescenta o
sufixo ao que vem antes dele, então o exemplo acima escreve `it` + `em`/`ens`, e
não `item` + algum sufixo — `item{{ n|pluralize:"ns" }}` produziria `itemns`. Em
PT-BR isso quase sempre significa cortar no meio da palavra, e a concordância
costuma exigir mais de um filtro na mesma frase: o substantivo troca a sílaba
tônica e o particípio concorda com ele.

```django
{{ n }} requisiç{{ n|pluralize:"ão,ões" }} encontrad{{ n|pluralize:"a,as" }}.
{{ n }} movimenta{{ n|pluralize:"ção,ções" }} encontrada{{ n|pluralize }}.
```

Cada listagem cobre **0, 1 e 2** em teste, casando a frase inteira e não só o
número. O caso 1 é o que impede "1 movimentações"; o caso 2 é o que impede "2
requisição encontrada". Uma asserção por substring de número passaria por cima
dos dois.

Implementado em `historico_requisicoes.html` e `historico_movimentacoes.html`.

Confirmação de ação irreversível:

```django
<div x-data="modalController({ id: 'confirmar-estorno' })">
  {% include "components/button.html" with variant="return-outline" label="Estornar" data_modal_trigger="confirmar-estorno" %}
  {% include "components/modal.html" with id="confirmar-estorno" titulo="Estornar requisição?" descricao="O estorno reverte toda a entregue líquida ao saldo físico do estoque e encerra a requisição." consequencia="Esta operação é irreversível." registro=registro action_url=url_estornar confirm_label="Confirmar estorno" confirm_variant="return" icon_variant="return" form_body_template="requisicoes/partials/_modal_form_estorno.html" %}
</div>
```

## Armadilhas do template Django

Duas que já custaram bug em produção de tela:

- **`{# … #}` não atravessa linha.** O lexer só casa comentário numa linha só;
  um `{#` multi-linha não vira comentário, e as tags de dentro são executadas.
  Para comentário de várias linhas use `{% comment %}`. Travado por
  `test_nenhum_template_usa_comentario_de_linha_em_varias_linhas`.
- **`{% with %}` fecha no mesmo bloco.** Não dá para abrir um `{% with %}` num
  ramo de `{% if %}` e usá-lo fora. Quando precisar de um valor condicional,
  resolva com filtro (`yesno`, `firstof`, `default`) antes do `with`.

## Quando aparecer identidade corporativa da SAEP

Se a SAEP trouxer guideline oficial (logo, cores, tipografia):

1. Atualizar os tokens em `input.css` e o frontmatter de `DESIGN.md`
2. Não alterar templates individuais
3. Rodar `npm run css:build`

Isso é possível porque componentes usam `variant="primary"` e `class="campo"`,
não `bg-blue-600` nem a string de campo copiada.

## Futuro — dark mode

Adiado; o sistema começa em light mode. Se virar requisito, os tokens `--color-*`
já são o ponto único de troca: basta redefini-los sob
`@media (prefers-color-scheme: dark)` e `:root[data-theme="dark"]`. Nenhum
componente precisa ser reescrito.
