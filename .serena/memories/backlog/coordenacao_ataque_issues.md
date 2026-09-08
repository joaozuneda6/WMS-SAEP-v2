# Coordenação do ataque às issues — backlog pós-Etapa 8

**Documento vivo.** Ponto de partida para quem entra no backlog e ferramenta de acompanhamento para quem já está nele. Visão macro: o detalhe técnico vive na issue, aqui vive a **ordem, a dependência e o estado**.

Última atualização: **2026-09-08, segunda passada** (ondas 4 e 5 **fechadas**: as PRs `joaozuneda6#70`, `#71`, `#72` e `#73` mergearam e as issues #167, #178, #181 e #182 foram fechadas manualmente — o fechamento que os corpos das PRs prometiam não tinha acontecido. A #183 está em PR (`joaozuneda6#75`). A #173 foi fatiada em **quatro**, não três: #184, #185, #186 e #187; a #187 vai na frente por ser bug de comportamento, não achado estético).

## Como usar

- Antes de pegar trabalho: leia o quadro de estado e a ordem de ataque; pegue o primeiro item desbloqueado.
- Ao fechar algo: mova a linha para "Concluído", atualize a onda e registre o que a conclusão desbloqueou.
- Não replique aqui o conteúdo da issue. Se você está copiando parágrafo de issue para cá, está no lugar errado.
- Issues e PRDs vivem em `JMZR-SAEP/WMS-SAEP-v2`; PRs e CodeRabbit no fork `joaozuneda6/WMS-SAEP-v2` (ver `project_git_remotes_topology`).

## Origem deste backlog

Tudo aqui nasceu da **Etapa 8** (auditoria de frontend do produto inteiro) e da sua remedição. Duas medições heurísticas, mesmo alvo, mesmo método dual-agent:

| Rodada | Data | Nota | P0 | P1 |
|---|---|---|---|---|
| Etapa 8, Fase 2 | 2026-09-01 | 21/40 | 1 | 3 |
| Remedição (#165) | 2026-09-03 | **27/40** | 2 | 2 |

Snapshots em `.impeccable/critique/` (diretório local, gitignored). O plano de origem é `docs/plans/audit-frontend-restante.md`, seção "Depois do plano".

**A tese central que a remedição revelou, e que organiza toda a ordem abaixo:** *as correções da Etapa 8 pararam no chamador, não desceram para o componente.* O `4,38:1` de contraste está diagnosticado por escrito no comentário do template que o corrigiu, e o componente que 7 telas incluem continua emitindo o par. Mesmo padrão no badge: 9 variantes migradas para token, 4 esquecidas na paleta crua. Por isso o eixo componente+guarda (#177 → `quantidade.html` → #166) tem prioridade alta apesar de nenhuma das suas peças ser P0.

## Quadro de estado

**Concluído**

| # | O quê | Como fechou |
|---|---|---|
| 165 | Remedir a baseline heurística | Segunda medição rodada em 2026-09-03: 21 → 27. Gerou #175, #176 e #177. |
| 175 | Notificação afirmava estado que nunca reconsultava (P0) | PR #61, merged 2026-09-04. Sino passou de 14 para 4 e passou a bater com a fila. Decisão de produto registrada: `/notificacoes/` é **diário**, não caixa de entrada — aviso vencido fica visível marcado "Resolvida" e sai só da contagem. |
| 176 | Laço `home()` → `/admin/` + dono da importação SCPI | PR #62 e PR #63, ambos merged. Issue fechada em 2026-09-04 com comentário linkando os PRs e os spinoffs. |
| 168 | `input.css` na árvore de estáticos, storage customizado | PR `joaozuneda6/WMS-SAEP-v2#65`, squash `c3f7fb1`, merged 2026-09-04. Issue fechada. |
| 177 | 4 variantes cruas de `badge.html` | PR `joaozuneda6/WMS-SAEP-v2#66`, squash `0ee1949`, merged 2026-09-04 (empilhada sobre a #65, retargetou pra `main` sozinha assim que a #65 mergeou). Issue fechada. Nomenclatura: `orange`→`cancel`, `indigo`→`consumption`, `violet`→`reversal`, `yellow`→reuso de `amber`. |
| — | `quantidade.html`: contraste da unidade + `tom` não propagava pra `referencia` | PR `joaozuneda6/WMS-SAEP-v2#68`, merge `421ce15`, merged 2026-09-04. Sem issue própria. |
| 166 | Varredura de contraste na lane Navegador (par pai/filho) | PR `joaozuneda6/WMS-SAEP-v2#69`, merge `95e8018`, merged 2026-09-04. Issue fechada. Emendou a ADR-0019: 4º critério de admissão ("cascade resolvida e pipeline de cor") e o gatilho de "~15 casos" deu lugar ao relógio. Deixa pendente uma extensão: `estoque:preview_importacao_scpi` ficou fora (upload multipart), então o guarda nasce cego para o `bg-primary-subtle` que originou o eixo. |

**Ondas 4 e 5 — mergeadas e fechadas em 2026-09-08**

| # | PR | Merge | O que entregou |
|---|---|---|---|
| 182 | `joaozuneda6#70` | `9e52881` | `listar_saidas_excepcionais` perdeu o `ator_id` morto. Levou nota normativa ao `CONVENTIONS.md`: `ator_id` em selector é reservado ao sufixo `_visiveis_para`. |
| 167 | `joaozuneda6#71` | `43b6dee` | Legenda do preview SCPI **removida**, não corrigida — ver decisão abaixo. |
| 178 | `joaozuneda6#72` | `f3dd967` | Marcador EST-07 restrito ao almoxarifado, com `pode_consultar_divergencias_criticas` nova e os operandos `Físico`/`Reservado` gated. Bullet de catálogo na matriz §5. |
| 181 | `joaozuneda6#73` | `4fdf1e0` | `marcar_lida_view` passou a consumir a policy; negativa vira `Http404`. Cláusula de atividade no selector, corrigindo o USR-01. Bullet de notificações na matriz §5. |

**Armadilha de processo, custou uma rodada inteira.** Os corpos das quatro PRs diziam "issue fechada manualmente após o merge, já que a issue vive no outro remote" — e ninguém fechou. O merge não fecha issue de outro remote, e `Closes #N` no corpo também não atravessa. **Fechar é passo manual explícito depois do merge**, não consequência dele. As quatro passaram quatro dias abertas dizendo que o trabalho estava por fazer.

**Em andamento**

| # | PR | O que entrega |
|---|---|---|
| 183 | `joaozuneda6#75` | Contagem do sino sai do `except Exception` com fallback zero: tolera só `django.db.Error` e devolve `None`. Sem mudança de template — os dois `{% if %}` de `base_auth.html` já tratam falsy. |

**Decisões desta rodada, que mudaram o escopo do que as issues pediam:**

1. **#167 fechou por remoção.** A issue pedia alinhar o shade dos swatches e acrescentar a linha do estado `OK`. Ao ler a tela inteira: são **três** cores por estado (cartão `-subtle`, badge `-muted`, swatch `-muted`), e o swatch batia com o badge, não com o cartão. Pior, acrescentar a linha `OK` sob o alinhamento pedido exigiria um swatch `bg-surface` — quadrado branco invisível, o mesmo modo de falha que a #164 diagnosticou. E a legenda **duplicava os chips**: explicava exatamente o par que `Só divergências` e `Só materiais novos` já nomeiam poucas linhas acima. Argumento que fechou: todo badge da tela é **texto**, e legenda existe para decodificar sinal não-textual.
2. **A L89 governa o marcador do catálogo, não um painel.** A observação da L89 ("Gestão do Almoxarifado/suporte") é o nome da L96, e a L96 nega ao auxiliar o que a L89 concede. Sob a leitura do painel, a L89 seria permissão morta para o auxiliar de almoxarifado — e nenhum painel existe no código. Decidido: é o marcador.
3. **#178 esconde o badge E os operandos.** EST-07 é `físico < reservado`, e o cartão imprimia os dois lados sem gate: esconder só o booleano removeria o rótulo, não a informação. `Disponível` fica para todos (L72), com resíduo declarado — num material divergente ele é negativo, e a L71 já bloqueia a seleção desse material por desenho.
4. **#181 mantém o 404, não adota o 403.** ADR-0010:118 (404 por não-enumeração) e ADR-0011 (`PermissaoNegada` → 403) colidem exatamente neste caso. Notificação de terceiro é objeto fora do escopo de visibilidade, então o 404 vence: um 403 confirmaria a existência da notificação a qualquer autenticado. Substituição explícita e comentada, que a emenda da ADR-0011 autoriza.
5. **Policy nova sem par `exigir_pode_*`, de propósito.** `pode_consultar_divergencias_criticas` não guarda endpoint — só decide escopo de conteúdo. Criar um `exigir_*` sem chamador plantaria de novo o defeito que a #181 existe para consertar.
6. **Estilo de selector escopado: `ator_id` + `papel_efetivo` interno.** O repo tem dois padrões vivos e nenhuma ADR decide. Escolhido o do vizinho direto (`movimentacoes_visiveis_para`), cujo padrão a matriz §5 L107 já ratifica. A nota nova do `CONVENTIONS.md` (PR #70) descreve esse padrão.

**Restrição de ambiente descoberta na rodada:** worktrees paralelos **não** servem aqui. O banco é PostgreSQL único e `make resetpostgres` apaga o schema `public`; duas suítes pytest simultâneas colidem em `test_<dbname>`, e migrations são gitignored, então worktree novo exige `make setup`, que reseta o banco compartilhado. Paralelismo vai na **análise** (read-only, sem branch, sem DB); implementação é sequencial.

**Decisões de domínio da #176 (2026-09-04).** A metade 2 não era divergência matriz↔código: `pode_visualizar_preview_scpi = eh_superusuario` batia com `docs/matriz-permissoes.md` L85-87. O conflito era matriz ↔ `PRODUCT.md:44` + `docs/processos-almoxarifado.md:88-96`. Resolvido:
1. Preview SCPI → **chefe de almoxarifado** (superusuário mantém override). Feito no #63.
2. Confirmar SCPI → **chefe também** (preview + confirmar + tela de sucesso). Feito no #63.
3. Matriz L89 "divergências críticas" = **invariante EST-07** (`físico < reservado`), não divergência SCPI → `divergente_calculado` (`selectors.py:324-328`) vaza o marcador para todo usuário ativo. Virou **#178**.
4. Inativar material → matriz L74/§3 já concede ao chefe, mas `pode_gerir_catalogo` só é consumida pelo admin do Django e não há UI de produto. **Tirado do #63** (mudar só a policy = código morto). Virou **#180**.
5. Matriz L83 "Estornar devolução" sem policy nem service → virou **#179**.

Nota factual: a policy real é `apps/estoque/policies.py:56`, não `apps/accounts/policies.py:56` como a issue diz.

**Spinoffs da #176 — triados, onda 5**

| # | O quê | Label | Bloqueio |
|---|---|---|---|
| 178 | `divergente_calculado` expõe o marcador EST-07 a solicitante/aux. setor/chefe setor (matriz L89) | `ready-for-agent` | — |
| 179 | `pode_estornar_devolucao` + service — linha de matriz (L83) sem implementação | `needs-info` | decisão de domínio: entra no MVP ou fica pra depois do piloto? |
| 180 | inativar material só existe pelo admin do Django; decidir UI de produto ou recuar a matriz | `needs-info` | decisão de domínio: UI de produto ou recuar a matriz L74/§3? |

**Spinoffs da #166 — triados, onda 5.** Achados pela auditoria de papéis que escolheu o usuário de cada tela do parametrize. Nenhum é vazamento de autorização hoje; os dois são defeito de contrato.

| # | O quê | Label | Bloqueio |
|---|---|---|---|
| 181 | `pode_ver_notificacao` é policy órfã: sem consumidor de produção, a regra vive no filtro de ORM da view (ADR-0011 existe para evitar as duas fontes) | `ready-for-agent` | — |
| 182 | `listar_saidas_excepcionais(ator_id)` ignora o parâmetro — assinatura simula recorte por papel que não existe | `ready-for-agent` | — |

**Spinoff da #181 — aberto 2026-09-08**

| # | O quê | Label | Bloqueio |
|---|---|---|---|
| 183 | contagem do sino em `except Exception` com fallback zero, em toda página autenticada — zero é indistinguível de "nada pendente". Mesma classe de defeito que a #175 consertou. | `ready-for-agent` | — |

**Aberto — todas triadas (nenhuma `needs-triage` restante). A onda 6 é a #173 fatiada em quatro**

| # | Onda | Label | Bloqueio |
|---|---|---|---|
| 183 | 5 | **em PR** (`joaozuneda6#75`) | — |
| 187 | 6 | `bug`, `ready-for-agent` — fatia (d) da #173 | — |
| 184 | 6 | `ready-for-agent` — fatia (a) da #173 | — |
| 185 | 6 | `ready-for-agent` — fatia (b) da #173 | — |
| 186 | 6 | `ready-for-agent` — fatia (c) da #173 | — |
| 173 | 6 | guarda-chuva, aberta até as quatro filhas fecharem | #184, #185, #186, #187 |
| 172 | 7 | `ready-for-human` (decisão de vocabulário visual) | **#185** documentar a gramática de formas |
| 170 | 8 | `needs-info` | resposta do chefe de almoxarifado |
| 171 | 9 | `needs-info` | export real do SCPI |
| 169 | 10 | `needs-info` | medição da rede do piloto |
| 174 | 11 | `ready-for-human` (decisão de contrato, maior item) | — |
| 179 | — | `needs-info` | decisão de domínio: entra no MVP? |
| 180 | — | `needs-info` | decisão de domínio: UI de produto ou recuar matriz? |

## Ordem de ataque

1. ~~**#176, metade barata** — `home()` para de rotear por `is_superuser`.~~ **Feito e fechada — PR #62.**
2. ~~**#168** — mover `input.css`, apagar `apps/core/staticfiles.py`.~~ **Feito e fechada — PR #65** (squash `c3f7fb1`).
3. ~~**#177** — 4 variantes cruas de `badge.html`.~~ **Feito e fechada — PR #66** (squash `0ee1949`, empilhada sobre a #65, retargetou pra `main` sozinha ao mergear a #65).
3b. ~~**`quantidade.html`**~~ **Feito e fechada — PR #68** (merge `421ce15`, sem CodeRabbit).
3c. ~~**#166**~~ **Feita e fechada — PR #69** (merge `95e8018`). Emendou a ADR-0019 no caminho.
4. ~~**#167**~~ **Feita e fechada — PR `joaozuneda6#71`** (merge `43b6dee`). Fechada por remoção da legenda. O bullet das pílulas do #173 **não** entrou: a premissa dele estava errada (ver "Candidatos"), e a colisão real precisa de mudança no componente global.
5. ~~**#178, #181, #182**~~ **Feitas e fechadas — PRs `joaozuneda6#72`, `#73`, `#70`.** Não houve conflito de hunk entre #178 e #182, apesar de editarem o mesmo `selectors.py`: as regiões eram disjuntas (20-27 vs 304-338; testes 9-78 vs 467-549). A #178 gerou a #183.
5b. **#183** — **em PR, `joaozuneda6#75`.**
6. ~~**#173, fatiada em 3**~~ **Fatiada em 4 e aberta: #184 (a), #185 (b), #186 (c), #187 (d).** A quarta fatia existe porque cinco dos candidatos anexados não eram achado estético e sim **defeito de comportamento** — diluí-los em (a)/(b)/(c) enterraria bug sob revisão de copy. **Ordem: #187 primeiro**, depois #185 (que destrava a #172), depois #184 e #186.
7. **#172** — depois que a **#185** documentar a gramática de formas.
8. ~~**#176, metade de permissão** — quem é o dono da importação SCPI.~~ **Feito e fechada — PR #63.** Domínio decidiu: chefe de almoxarifado. Gerou #178, #179, #180.
9. **#170** — quando o chefe de almoxarifado responder.
10. **#171** — quando o export real chegar. Cada quebra vira issue própria.
11. **#169** — medir a rede do piloto e decidir. `wontfix` consciente é o desfecho provável.
12. **#174** — a maior. Primeira a cortar do escopo se o piloto apertar.
13. **#179, #180** — `needs-info`, esperando decisão de domínio (ver "Disparar cedo"). Sem código antes da resposta.

## Dependências

- **#168 → #166, #177.** Os três editam `test_tokens_semanticos.py`. A #168 mexe na constante `INPUT_CSS`; as outras duas acrescentam cobertura. Fora de ordem = conflito garantido.
- **#177 ≡ #166 em forma.** Cor que existe, par que existe, guarda que não alcança — uma por paleta crua, outra por par pai/filho. Entender o guarda duas vezes é desperdício.
- ~~**#166 → #167, #173, #174.**~~ **Satisfeita.** A varredura está no lugar: toda mudança de markup daqui em diante nasce medida, nas 11 telas cobertas.
- ~~**#173 ⊃ #167.**~~ **Resolvida por medição**: o bullet das pílulas era falso (ver "Candidatos"), e a colisão real foi para a **#185**, que toca `filter_chips.html` — componente global que arrasta as 11 telas da varredura da #166.
- **#185 → #172.** Os bullets de `DESIGN.md` fixam a gramática que o triângulo vai estender. Documentar antes de acrescentar.
- **#187 antes de #184/#186.** Não é dependência de código, é de severidade: bug de comportamento não espera revisão de copy.
- **#176 se divide em duas metades independentes.** A do laço fechado é defeito puro e sai sozinha; a da policy espera decisão de domínio.
- **Sem dependência de código real entre as demais.** As dependências que importam neste backlog são de **informação** (respostas humanas) e de **contaminação de medição**, não de build.

## Trabalho sem issue própria

**Fechado e mergeado — PR `joaozuneda6/WMS-SAEP-v2#68`** (merge `421ce15`, sem CodeRabbit, merge manual do usuário). Os dois P1 vizinhos de `components/quantidade.html` (linha 60, `text-tertiary` reprovando contraste; linha 64, `tom` não propagava pra `referencia`) saíram no mesmo PR. Pull request criada com corpo corrompido por expansão de crase no shell (`` `tom` `` virou tentativa de comando) — corrigido via `gh pr edit --body-file`. Nota pra próxima vez: nunca passar `--body` inline com crases dentro de aspas duplas no bash; usar heredoc/arquivo.

## Candidatos do #173 — distribuídos em 2026-09-08

Todos os candidatos da remedição foram para uma fatia. Nada ficou sem dono:

| Candidato | Foi para |
|---|---|
| DELTA do SCPI sem unidade nas duas telas | **#187** — muda schema (`LinhaDivergenteSCPI`) |
| `motivo` gravado como slug no livro-razão imutável | **#187** |
| `Doação` num seletor que o `PRODUCT.md` declara fora de escopo | **#187** |
| `@drop` que submete sem revisão e mata o `data-prevent-double-submit` | **#187** |
| ordenação que exibe o inverso do que mostra | **#187** |
| `IntegerField` num material medido em metros | **#187**, por comentário — escapou do corpo no primeiro fatiamento |
| ordem de foco invertida (`flex-col-reverse`, WCAG 2.4.3) | **#186** |
| 12 links de navegação sem `focus-visible` autoral | **#186** |
| chip ativo × badge do cartão (achado da #167) | **#185** — `filter_chips.html` é global |
| heading ausente na região de resultados do preview (achado da #167) | **#186** |

**Duas peças de schema na #187**: a unidade do `LinhaDivergenteSCPI` e o `IntegerField`. Se a fatia crescer, elas se separam **juntas** — ambas mudam model e ambas exigem `make setup`.

**Correção de um bullet existente, medida na #167 (2026-09-08).** O bullet que diz que contadores (`5 linhas`) e filtros (`Só divergências`) vestem a mesma pílula a ~170px **não se sustenta**: os contadores são `rounded-lg` com `px-4 py-2.5` — retângulos, não pílulas — e os chips são `rounded-full`; já se distinguem por forma, e os três contadores se distinguem entre si por matiz. Os dois achados reais que o substituem:

- **Chip ativo × badge do cartão vestem a mesma pílula.** `filter_chips.html` no estado ativo usa `rounded-full border px-3 py-1.5 bg-primary-muted text-primary-text-strong`; `badge.html variant="blue"` usa `rounded-full bg-primary-muted px-2.5 py-0.5 text-primary-text-strong ring-1`. Mesma cor, mesma forma, diferindo só em tamanho. **Um é link que alterna filtro, o outro é marcador estático de estado** — é defeito de affordance, não de vocabulário. Ficou fora do escopo da #167 porque `filter_chips.html` é componente global (o ledger também o usa) e mexer nele arrasta as 11 telas da varredura de contraste da #166. Foi para a **#185**.
- **A região de resultados do preview SCPI não tem heading próprio.** Lacuna preexistente, não criada pela #167 — o `<h2 class="sr-only">` que saiu com a legenda nomeava a legenda, não os resultados. Um `<h2 class="sr-only">` para as linhas do arquivo daria a leitor de tela um alvo de salto para o conteúdo real da tela. Foi para a **#186**.

## Disparar cedo, fora da fila

Itens 8 e 9 têm lead time humano e **zero trabalho de código antes da resposta**. Mande os pedidos assim que a fila começar, e siga pelos itens 1 a 6 enquanto chegam:

- ~~**#176 metade 2** — quem é o dono da importação SCPI?~~ **Respondido: chefe de almoxarifado.** PR #63, issue fechada.
- **#170** — "recusa" e "cancelamento" diferem no vocabulário de auditoria do almoxarifado?
- **#171** — alguém com acesso ao SCPI produzir um export real.
- **#179** — estorno de devolução entra no MVP ou fica pra depois do piloto?
- **#180** — inativar material ganha UI de produto, ou a matriz L74/§3 recua pra só-superusuário (admin do Django)?

## Regras de coordenação

- **Não rode a próxima critique antes de fechar a onda 4.** Rodar no meio mistura o efeito dos P0 com o do eixo do componente — o erro de atribuição que a #165 existia justamente para não repetir.
- **Comparação de nota só é válida like-for-like**: mesmo alvo, mesmo slug (`apps`), sem alvo específico, e sem mostrar a pontuação anterior aos agentes. Calibração diferente entre rodadas vira falso progresso ou falsa regressão.
- ~~**#173 é guarda-chuva, não issue.**~~ **Fatiada em #184/#185/#186/#187.** Fica aberta como capa até as quatro fecharem.
- **Merge não fecha issue de outro remote.** Depois de cada merge, fechar a issue no `origin` é passo manual, com comentário linkando a PR e o commit de merge. Quatro issues ficaram abertas por quatro dias porque as PRs *afirmavam* o fechamento em vez de fazê-lo.
- **#169, #170 e #171 não são tarefas de código** — são uma medição, uma pergunta e um pedido. Não devem ocupar slot de implementação.
- **#174 é dívida declarada com produção correta.** Primeira a sair do escopo sob pressão de prazo. A #168 fica só porque é barata.
- Uma branch por issue, nunca commit direto na `main`; vocabulário de triagem em `docs/agents/triage-labels.md`.

## Manutenção desta memória

Atualize quando: uma issue fechar, uma onda concluir, uma decisão externa chegar (permissões, vocabulário de auditoria, export SCPI), ou uma nova rodada de critique mudar a ordem. Não registre progresso parcial de PR nem saída de teste — isso vive no PR.

Memórias vizinhas: `project_git_remotes_topology` (onde issue e PR moram), `project_css_build_gate` (classe nova exige `make css-build`), `frontend/etapa2_feedback_backlog` e `frontend/etapa3_overlay_backlog` (backlogs de etapas anteriores).
