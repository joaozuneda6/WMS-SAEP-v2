"""Testes diretos de components/button.html (sem DB, sem view)."""

import math
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.template.loader import render_to_string

from apps.core.templatetags.core_tags import _VARIANTES_BOTAO, faixa_paginas
from apps.core.tests.marcacao import (
    TAGS_DJANGO,
    atributo,
    classes,
    elementos,
    pares,
)


def _render(**ctx):
    ctx.setdefault('label', 'Rótulo')
    return render_to_string('components/button.html', ctx)


def test_sem_href_renderiza_button():
    html = _render()
    assert '<button' in html
    assert '<a ' not in html and '<a\n' not in html


def test_com_href_renderiza_link():
    html = _render(href='/destino/')
    assert html.lstrip().startswith('<a')
    assert 'href="/destino/"' in html
    assert '<button' not in html


def test_type_default_button():
    html = _render()
    assert 'type="button"' in html


def test_type_submit():
    html = _render(type='submit')
    assert 'type="submit"' in html


def test_name_e_value_renderizam_atributos_no_button():
    html = _render(name='acao', value='enviar')
    assert 'name="acao"' in html
    assert 'value="enviar"' in html


def test_name_e_value_ausentes_por_padrao():
    html = _render()
    assert 'name=' not in html
    assert 'value=' not in html


def test_value_inteiro_zero_nao_e_tratado_como_ausente():
    html = _render(value=0)
    assert 'value="0"' in html


def test_disabled_aplica_atributo_boolean_na_tag():
    html = _render(disabled=True)
    abertura = html[: html.index('>') + 1]
    assert re.search(r'\bdisabled\b(?!:)', abertura)
    assert 'disabled:cursor-not-allowed' in html
    assert 'disabled:opacity-60' in html


def test_disabled_false_nao_aplica_atributo_na_tag():
    html = _render(disabled=False)
    abertura = html[: html.index('>') + 1]
    assert not re.search(r'\bdisabled\b(?!:)', abertura)


@pytest.mark.parametrize(
    'variant,classes_esperadas',
    [
        (
            'primary',
            ['bg-primary', 'hover:bg-primary-hover', 'active:bg-primary-active'],
        ),
        (
            'secondary',
            [
                'bg-surface',
                # border-control (slate-500), não border-strong (slate-300): num
                # botão secundário a borda é a única pista de que há um controle
                # ali, e slate-300 entregava 1.48:1 contra o papel branco.
                'border-border-control',
                'hover:bg-bg-page',
                'text-text-secondary',
            ],
        ),
        (
            'neutral',
            ['bg-text-secondary', 'text-text-on-primary', 'hover:bg-text-primary'],
        ),
        ('danger', ['bg-danger', 'hover:bg-danger-hover', 'active:bg-danger-active']),
        (
            'danger-outline',
            [
                'border-danger-accent',
                'text-danger-text',
                'hover:bg-danger-subtle',
            ],
        ),
        ('ghost', ['bg-transparent', 'hover:bg-bg-subtle', 'text-text-secondary']),
        ('link', ['bg-transparent', 'text-primary-text', 'hover:underline']),
    ],
)
def test_variant_produz_classes_de_cor_esperadas(variant, classes_esperadas):
    html = _render(variant=variant)
    for classe in classes_esperadas:
        assert classe in html


@pytest.mark.parametrize(
    'size,classes_esperadas',
    [
        ('sm', ['px-3 py-2 text-xs']),
        ('md', ['px-3 py-2 text-sm']),
    ],
)
def test_size_produz_padding_tipografia_esperados(size, classes_esperadas):
    html = _render(size=size)
    for classe in classes_esperadas:
        assert classe in html


def test_full_width_mobile_aplica_classes():
    html = _render(full_width_mobile=True)
    assert 'w-full sm:w-auto' in html


def test_full_width_mobile_ausente_nao_aplica_classes():
    html = _render()
    assert 'w-full sm:w-auto' not in html


def test_aria_label_sobrescreve_texto_acessivel_mantendo_label_visivel():
    html = _render(label='Ver', aria_label='Ver detalhes da requisição REQ-2026-001')
    assert 'aria-label="Ver detalhes da requisição REQ-2026-001"' in html
    assert '>Ver</' in html or '>Ver<' in html


def test_hx_get_renderiza_atributo_hifenizado():
    html = _render(hx_get='/parcial/')
    assert 'hx-get="/parcial/"' in html
    assert 'hx_get' not in html


def test_hx_post_renderiza_atributo_hifenizado():
    html = _render(hx_post='/acao/')
    assert 'hx-post="/acao/"' in html


def test_hx_target_e_hx_swap_renderizam_atributos_hifenizados():
    html = _render(hx_target='#alvo', hx_swap='outerHTML')
    assert 'hx-target="#alvo"' in html
    assert 'hx-swap="outerHTML"' in html


def test_hx_atributos_ausentes_por_padrao():
    html = _render()
    assert 'hx-get' not in html
    assert 'hx-post' not in html
    assert 'hx-target' not in html
    assert 'hx-swap' not in html


def test_class_passthrough_e_mesclado_nao_substitui_invariantes():
    html = _render(**{'class': 'meu-ajuste-customizado'})
    assert 'meu-ajuste-customizado' in html
    assert 'min-h-11' in html
    assert 'inline-flex' in html


def test_data_modal_trigger_renderiza_atributo():
    html = _render(data_modal_trigger='meu-modal')
    assert 'data-modal-trigger="meu-modal"' in html


def test_data_modal_trigger_renderiza_click_abrir_conforme_contrato_do_modal():
    html = _render(data_modal_trigger='meu-modal')
    assert '@click="abrir($event)"' in html


def test_data_modal_trigger_ausente_por_padrao():
    html = _render()
    assert 'data-modal-trigger' not in html
    assert '@click' not in html


def test_icon_template_incluido_antes_do_label():
    html = render_to_string(
        'components/button.html',
        {'label': 'Confirmar', 'icon_template': 'components/icons/confirmar.svg'},
    )
    icon_idx = html.index('aria-hidden="true"')
    label_idx = html.index('Confirmar')
    assert icon_idx < label_idx


def test_icon_template_ausente_por_padrao_nao_renderiza_span_icone():
    html = _render()
    assert 'aria-hidden="true"' not in html


def test_botao_somente_icone_usa_aria_label_como_nome_acessivel():
    html = render_to_string(
        'components/button.html',
        {
            'label': '',
            'aria_label': 'Fechar',
            'icon_template': 'components/icons/confirmar.svg',
        },
    )
    assert 'aria-label="Fechar"' in html
    assert 'aria-hidden="true"' in html


def test_label_e_aria_label_ausentes_nao_mascara_com_texto_generico():
    html = render_to_string('components/button.html', {})
    assert 'Botão' not in html
    assert 'aria-label' not in html
    assert 'button' in html.lower()


@pytest.mark.parametrize(
    'variant', ['primary', 'secondary', 'danger', 'danger-outline', 'ghost']
)
def test_invariantes_comuns_presentes_exceto_link(variant):
    html = _render(variant=variant)
    for classe in [
        'inline-flex',
        'items-center',
        'justify-center',
        'min-h-11',
        'rounded-md',
        'focus-visible:outline-none',
        'focus-visible:ring-2',
        'focus-visible:ring-offset-1',
    ]:
        assert classe in html


def test_link_nao_forca_min_h_11_nem_justify_center():
    html = _render(variant='link')
    assert 'min-h-11' not in html
    assert 'justify-center' not in html


def test_icon_class_chega_ao_icone_sem_vazar_class_do_botao():
    html = render_to_string(
        'components/button.html',
        {
            'label': 'Registrar',
            'icon_template': 'components/icons/confirmar.svg',
            'icon_class': 'h-5 w-5',
            'class': 'mt-4',
        },
    )
    assert 'class="h-5 w-5"' in html
    icon_svg = html[html.index('<svg') : html.index('</svg>') + len('</svg>')]
    assert 'mt-4' not in icon_svg


def test_icon_class_default_h4_w4_quando_nao_informado():
    html = render_to_string(
        'components/button.html',
        {'label': 'Registrar', 'icon_template': 'components/icons/confirmar.svg'},
    )
    assert 'class="h-4 w-4"' in html


def test_loading_label_gera_atributo_e_span_com_valor_exato():
    html = _render(loading_label='Enviando...')
    assert 'data-submit-loading-label="Enviando..."' in html
    assert '<span data-submit-text>Rótulo</span>' in html


def test_loading_label_ausente_por_padrao():
    html = _render()
    assert 'data-submit-loading-label' not in html
    assert 'data-submit-text' not in html


def test_label_mobile_junto_de_loading_label_gera_dois_spans_responsivos():
    html = _render(
        label='Criar e enviar para autorização',
        label_mobile='Enviar',
        loading_label='Enviando...',
    )
    assert 'data-submit-loading-label="Enviando..."' in html
    assert (
        '<span data-submit-text class="hidden sm:inline">Criar e enviar para autorização</span>'
        in html
    )
    assert '<span data-submit-text class="sm:hidden">Enviar</span>' in html
    assert '<span data-submit-text>Criar e enviar para autorização</span>' not in html


def test_label_mobile_sozinho_sem_loading_label_nao_ativa_spans_responsivos():
    html = _render(label='Criar e enviar para autorização', label_mobile='Enviar')
    assert 'data-submit-text' not in html
    assert 'hidden sm:inline' not in html


def test_href_setado_nao_renderiza_nenhum_param_dinamico_de_button():
    html = _render(
        href='/destino/',
        loading_label='Enviando...',
        label_mobile='Enviar',
    )
    for trecho in (
        'data-submit-loading-label',
        'data-submit-text',
    ):
        assert trecho not in html


def test_nenhum_template_usa_comentario_de_linha_em_varias_linhas():
    """`{# #}` é comentário de UMA linha; multi-linha vaza como texto na tela.

    Django não fecha `{# ... #}` que atravessa quebra de linha — o conteúdo é
    renderizado como conteúdo, visível para o usuário, e nenhum teste de
    presença de marcação pega isso porque o HTML continua válido. Comentário de
    mais de uma linha usa `{% comment %}`.
    """

    raiz = Path(__file__).resolve().parents[3]
    infratores: list[str] = []
    for caminho in (raiz / 'apps').rglob('*.html'):
        dentro = False
        for numero, linha in enumerate(caminho.read_text().splitlines(), 1):
            if dentro:
                if '#}' in linha:
                    dentro = False
                continue
            inicio = linha.find('{#')
            if inicio != -1 and '#}' not in linha[inicio:]:
                infratores.append(f'{caminho.relative_to(raiz)}:{numero}')
                dentro = True

    assert not infratores, (
        'Comentário {# #} atravessando linhas (vaza como texto renderizado); '
        f'use {{% comment %}}: {infratores}'
    )


# Bordas que *identificam* um controle. `border-border` fica de fora: é borda
# estrutural de papel, e o dropdown de autocomplete a usa legitimamente.
_BORDAS_DE_CONTROLE = (
    'border-border-strong',
    'border-border-control',
    'border-danger-border-input',
)

# `.campo` é a definição de campo de texto. Checkbox e radio seguem `size-5`
# dentro de uma label de 44px, e upload é outro controle — nenhum dos três
# passa por `.campo`, então não são infração.
_TIPOS_DE_TEXTO = frozenset(
    {
        '',
        'text',
        'search',
        'number',
        'email',
        'password',
        'tel',
        'url',
        'date',
        'datetime-local',
        'month',
        'week',
        'time',
    }
)


def _controles_de_texto(texto: str):
    """Devolve (tag, atributos, linha) de cada input/select/textarea de texto.

    A varredura respeita aspas (ver apps/core/tests/marcacao.py): um atributo
    pode conter `>` — o `@keydown.enter="if (ativo >= 0)"` de autocomplete.html
    contém —, e um `<[^>]*>` ingênuo truncaria o elemento no meio, justamente
    antes do `class`.
    """
    yield from elementos(texto, 'input', 'select', 'textarea')


def test_nenhum_template_escreve_campo_na_mao():
    """Campo tem uma definição só: `.campo`, em input.css.

    A string do campo já viveu copiada 19 vezes nos forms.py dos apps e nos
    componentes de filtro, e divergiu em silêncio — dois campos ficaram sem o
    piso de 44px e três com raio de controle em vez de raio de campo. Nada
    quebrava quando isso acontecia, que é exatamente por que aconteceu.

    A versão anterior deste teste procurava a assinatura contígua
    `border border-border-strong px-3 py-2`, e por isso era cega para o único
    infrator que existia: o input de autocomplete escrevia
    `border {% if com_erro %}...{% else %}border-border-strong{% endif %} px-3`,
    e a tag no meio quebrava a string. A regra tinha mecanismo e o mecanismo não
    alcançava o infrator — que ficou a 1.48:1 de contraste de borda, contra os
    3:1 da WCAG 1.4.11, pelo tempo em que ninguém olhou.

    Agora a varredura é por elemento, com as tags de template removidas antes da
    comparação, para que uma classe condicional não sirva de esconderijo.
    """

    raiz = Path(__file__).resolve().parents[3]
    infratores: list[str] = []
    for caminho in (raiz / 'apps').rglob('*.html'):
        texto = caminho.read_text()
        for tag, atributos, numero in _controles_de_texto(texto):
            limpo = TAGS_DJANGO.sub(' ', atributos)
            if 'class=' not in limpo or 'campo' in limpo:
                continue
            if tag == 'input':
                tipo = re.search(r'type="([^"]*)"', limpo)
                if (
                    tipo.group(1).strip().lower() if tipo else ''
                ) not in _TIPOS_DE_TEXTO:
                    continue
            escreveu_borda = any(b in limpo for b in _BORDAS_DE_CONTROLE)
            if escreveu_borda or 'px-3 py-2' in limpo:
                infratores.append(f'{caminho.relative_to(raiz)}:{numero}')

    assert not infratores, (
        'Campo escrito à mão; use class="campo" (definido em '
        f'assets/css/input.css): {infratores}'
    )


_INPUT_CSS = 'assets/css/input.css'

_COMENTARIO_CSS = re.compile(r'/\*.*?\*/', re.S)
# Os blocos são casados de dentro para fora: `[^{}]*` nunca atravessa uma chave,
# então uma regra dentro de `@media` sai com o at-rule grudado no seletor. Não
# atrapalha — o que se extrai do seletor é nome de classe, e `@media` não tem.
_BLOCO_CSS = re.compile(r'([^{}]*)\{([^{}]*)\}', re.S)
_ALTURA_DE_PISO = re.compile(r'(?<![-\w])(?:min-)?height:\s*var\(--size-touch-target\)')
# Nome de classe começa por letra, `_` ou `-`. Sem essa âncora, o `.5rem` de um
# `padding: 0.5rem` viraria uma classe chamada `5rem`.
_NOME_DE_CLASSE_CSS = re.compile(r'\.(-?[A-Za-z_][\w-]*)')

_COMENTARIO_DJANGO = re.compile(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', re.S)
_CONDICIONAL_DJANGO = re.compile(r'\{%\s*if\b.*?\{%\s*endif\s*%\}', re.S)
# O projeto escreve `{% include %}` com as duas aspas — `fila_atendimento.html`
# usa simples, `notificacoes/lista.html` usa duplas —, e a mesma liberdade vale
# para o valor de `variant`. Um guarda que só entende aspas duplas seria
# contornável por uma escolha de estilo, que é a definição de guarda decorativo.
# A aspa é capturada e conferida por retrovisor (`\1`), para que `"...'` não
# passe por par.
_INCLUDE_DE_BOTAO = re.compile(
    r'\{%\s*include\s+([\'"])components/button\.html\1(.*?)%\}', re.S
)
# `(?:[^%]|%(?!\}))*` casa os argumentos até o `%}` de fechamento sem parar num
# `%` de valor (`prefixo_sr="50%"`). `[^%]*` parava, e um `role=` depois do `%`
# escapava da guarda. Aspa capturada + retrovisor (`\1`) como no include de botão.
_INCLUDE_DE_BADGE = re.compile(
    r'\{%\s*include\s+([\'"])components/badge\.html\1(?:[^%]|%(?!\}))*%\}'
)
_VARIANTE_LINK = re.compile(r'variant=([\'"])link\1')

# Único arquivo em que a classe pode sair de `{% classes_botao %}`: é lá que
# `variant` é variável de runtime. Fora dele, chamar a tag à mão seria uma rota
# de fuga do piso — e o design system já diz que toda ação passa pelo componente.
_TEMPLATE_DE_BOTAO = 'apps/core/templates/components/button.html'

# Piso confirmado por varredura, para que o guarda não possa passar por não ter
# achado nada. Hoje são 30; o número é folgado de propósito, porque o custo de
# um falso vermelho aqui é alto e o de um teto baixo é zero.
_MINIMO_DE_CLICAVEIS_VARRIDOS = 25

# Exceção declarada em docs/design-system.md: a variante `link` de button.html é
# texto inline no meio de prosa, e uma caixa de 44px quebraria a linha (WCAG
# 2.5.8 isenta link em sentença).
#
# Nasce vazia de propósito. Não existe uso inline ainda, e exceção pré-aprovada
# para caso que não existe é a folga que vira esconderijo — foi assim que os dois
# controles de recuperação ficaram sem piso sem quebrar teste nenhum. O primeiro
# link inline de verdade entra aqui junto com a frase que o justifica.
#
# O mecanismo de exceção é exercitado por fixture sintética
# (`test_excecao_de_prosa_inline_isenta_o_ponto_de_chamada`), nunca por uma
# entrada real posta aqui só para ter teste.
#
# A chave é `(caminho, linha)` e não só o caminho: um arquivo pode ter os dois
# usos, e isentar o arquivo inteiro por causa de um link inline esconderia toda
# ação isolada sem piso que aparecesse depois nele. O número de linha envelhece
# — qualquer edição acima desloca o ponto de chamada e a exceção deixa de casar.
# É o lado certo de falhar: o guarda volta a cobrar o piso e alguém reescreve a
# exceção conferindo se ela ainda vale, em vez de ela seguir valendo sozinha.
EXCECOES_DE_PROSA_INLINE: dict[tuple[str, int], str] = {}


def _classes_com_piso_no_css(raiz: Path) -> frozenset[str]:
    """Classes cujo bloco em input.css declara altura de `--size-touch-target`.

    Derivada do CSS a cada execução, e não escrita à mão, porque uma lista fixa
    só conheceria o que existia no dia em que foi escrita — que é exatamente o
    defeito que este guarda existe para não repetir.
    """
    css = _COMENTARIO_CSS.sub(' ', (raiz / _INPUT_CSS).read_text())
    nomes: set[str] = set()
    for seletor, corpo in _BLOCO_CSS.findall(css):
        if _ALTURA_DE_PISO.search(corpo):
            nomes.update(_NOME_DE_CLASSE_CSS.findall(seletor))
    return frozenset(nomes)


def _classes_garantidas(atributos: str) -> set[str]:
    """Classes que valem em *qualquer* ramo do template.

    Difere de `classes()` de propósito. Aquele helper troca a tag Django por
    espaço e mantém o texto de dentro, porque os guardas dele perguntam "esta
    string aparece em algum ramo?". Aqui a pergunta é o contrário: piso que só
    existe quando a condição é verdadeira não é piso — do outro lado do `{% if %}`
    o alvo volta a ter 21px, e nenhuma varredura por presença notaria.
    """
    valor = atributo(atributos, 'class') or ''
    return set(TAGS_DJANGO.sub(' ', _CONDICIONAL_DJANGO.sub(' ', valor)).split())


def _sem_comentarios(texto: str) -> str:
    """Remove blocos `{% comment %}` preservando a numeração de linha.

    Markup dentro de comentário não é markup: os blocos de documentação de
    button.html, modal.html e pagination.html trazem exemplos de uso com
    `<button ...>` e `<a ...>` que nunca renderizam. Sem removê-los o guarda
    acusaria quatro falsos positivos, e a correção óbvia seria afrouxá-lo.
    """
    return _COMENTARIO_DJANGO.sub(lambda m: '\n' * m.group(0).count('\n'), texto)


def _tem_atributo(atributos: str, nome: str) -> bool:
    """`True` só se `nome` for um atributo exato do elemento.

    `atributo()` devolve `None` tanto para ausente quanto para presente-sem-valor
    (`data-cartao-link`), e `nome in atributos` casaria `data-cartao-link-extra`
    ou um `aria-describedby="data-cartao-link"`. O parser de pares resolve os
    dois.
    """
    procurado = nome.lower()
    return any(chave.lower() == procurado for chave, _ in pares(atributos))


def _faixas_de_cartao(texto: str) -> list[range]:
    """Faixas de linha que renderizam *dentro* de um cartão de listagem.

    `card_abertura` só emite `<article ...>`; o fechamento é literal na tela
    chamadora. Uma âncora `data-cartao-link` só é o alvo do cartão se estiver
    dentro dessa faixa — fora dela, é uma âncora de texto solta e a isenção do
    piso de 44px não vale.

    O corpo do cartão também pode viver num `{% partialdef %}` no mesmo arquivo
    (`fila_atendimento.html`) e ser incluído no `{% for %}`. Nesse caso a faixa
    do `partialdef` incluído de dentro do cartão também conta.
    """
    linhas = texto.splitlines()
    faixas: list[range] = []
    abertura: int | None = None
    for numero, linha in enumerate(linhas, 1):
        if 'components/table.html#card_abertura' in linha:
            abertura = numero
        elif abertura is not None and '</article>' in linha:
            faixas.append(range(abertura, numero + 1))
            abertura = None

    incluidos: set[str] = set()
    for numero, linha in enumerate(linhas, 1):
        if any(numero in faixa for faixa in faixas):
            incluidos.update(re.findall(r'\{%\s*include\s+"[^"]*#([\w-]+)"', linha))
    if incluidos:
        dentro: int | None = None
        for numero, linha in enumerate(linhas, 1):
            encontro = re.search(r'\{%\s*partialdef\s+([\w-]+)', linha)
            if encontro and encontro.group(1) in incluidos:
                dentro = numero
            elif dentro is not None and 'endpartialdef' in linha:
                faixas.append(range(dentro, numero + 1))
                dentro = None
    return faixas


def _clicaveis_sem_piso(
    caminho: str,
    texto: str,
    piso_css: frozenset[str],
    excecoes: Mapping[tuple[str, int], str],
) -> tuple[list[str], int]:
    """Infratores e total de clicáveis de um template.

    Um clicável tem piso comprovável de quatro formas:

    1. `min-h-11` literal na própria lista de classes, fora de `{% if %}`;
    2. uma classe cujo bloco em input.css declara `--size-touch-target`;
    3. classe vinda de `{% classes_botao %}` **dentro de components/button.html**
       — é lá que `variant` é variável de runtime e nenhuma varredura de markup
       pode saber o que o chamador vai pedir. A isenção é por arquivo, e não por
       aparecer a tag: escrita à mão em outro template, ela viraria rota de fuga
       do piso;
    4. para quem *inclui* button.html com `variant="link"` (em aspas simples ou
       duplas): `min-h-11` no `class`, salvo o **ponto de chamada** — a dupla
       `(caminho, linha)` — estar em `excecoes`. A chave é por chamada, e não
       por arquivo, porque um arquivo pode ter link inline e ação isolada, e
       isentar o arquivo inteiro esconderia a segunda.

    A forma 3 tira button.html da varredura; não dá quitação a quem o inclui. É
    a segunda metade da regra do design system — "`link` usado como ação isolada
    recebe `class="min-h-11"` explícito" — e apagá-la abriria, no mecanismo
    novo, um buraco do mesmo formato do que ele fecha.

    5. `data-cartao-link` **dentro de uma faixa `#card_abertura` … `</article>`**:
       o alvo efetivo do link não é a sua própria caixa de texto, é o
       `<article>` inteiro do cartão de listagem, que mede no mínimo 126px de
       altura. O piso existe para garantir área de toque, e aqui a área é maior
       justamente porque o link foi marcado — `card_abertura` reage a ele por
       `has-[a[data-cartao-link]]` e `core/js/cartao-alvo.js` encaminha o clique
       do cartão. Exigir `min-h-11` na âncora inflaria a caixa de linha do
       `<h2>` em cada cartão sem aumentar alvo nenhum.

       A isenção é estrutural, não pela presença do atributo: `_faixas_de_cartao`
       amarra a âncora ao cartão que a contém. Uma âncora `data-cartao-link`
       fora de um `<article>` de cartão continua devendo o piso. E não é
       gratuita: `test_link_de_cartao_tem_o_cartao_como_alvo` falha se a
       marcação existir sem o mecanismo que a sustenta.
    """
    limpo = _sem_comentarios(texto)
    faixas_cartao = _faixas_de_cartao(limpo)
    infratores: list[str] = []
    quantidade = 0

    for _, atributos, numero in elementos(limpo, 'a', 'button'):
        quantidade += 1
        if caminho == _TEMPLATE_DE_BOTAO and 'classes_botao' in (
            atributo(atributos, 'class') or ''
        ):
            continue
        if _tem_atributo(atributos, 'data-cartao-link') and any(
            numero in faixa for faixa in faixas_cartao
        ):
            continue
        nomes = _classes_garantidas(atributos)
        if 'min-h-11' in nomes or nomes & piso_css:
            continue
        infratores.append(f'{caminho}:{numero} clicável sem piso de 44px')

    for encontro in _INCLUDE_DE_BOTAO.finditer(limpo):
        argumentos = encontro.group(2)
        if not _VARIANTE_LINK.search(argumentos) or 'min-h-11' in argumentos:
            continue
        numero = limpo.count('\n', 0, encontro.start()) + 1
        if (caminho, numero) in excecoes:
            continue
        infratores.append(
            f'{caminho}:{numero} variant="link" como ação isolada, sem min-h-11'
        )

    return infratores, quantidade


def test_nenhum_controle_abaixo_do_piso_de_44px():
    """Todo clicável de apps/**/*.html tem piso de 44px comprovável.

    A versão anterior deste guarda procurava os literais `min-h-9`/`min-h-10`
    linha a linha. Ela pega quem escolheu conscientemente um número menor que
    `--size-touch-target` e é **cega para quem não escreveu piso nenhum** — que
    era o caso das âncoras de error_summary.html e do CTA secundário de
    empty_state.html, os dois exatamente na superfície de recuperação de erro,
    os dois passando em silêncio.

    As duas varreduras convivem porque cobrem coisas diferentes: a por linha
    alcança o número menor escrito em qualquer elemento, inclusive nos que não
    são `<a>` nem `<button>`; a por elemento alcança a ausência.

    A mesma tela é operada com o dedo, em pé no galpão, e com teclado no
    escritório.
    """
    raiz = Path(__file__).resolve().parents[3]
    piso_css = _classes_com_piso_no_css(raiz)
    infratores: list[str] = []
    clicaveis = 0

    for caminho in sorted((raiz / 'apps').rglob('*.html')):
        relativo = str(caminho.relative_to(raiz))
        texto = caminho.read_text()
        for numero, linha in enumerate(texto.splitlines(), 1):
            if 'min-h-9' in linha or 'min-h-10' in linha:
                infratores.append(f'{relativo}:{numero} número menor que o piso')
        achados, quantidade = _clicaveis_sem_piso(
            relativo, texto, piso_css, EXCECOES_DE_PROSA_INLINE
        )
        infratores.extend(achados)
        clicaveis += quantidade

    assert clicaveis >= _MINIMO_DE_CLICAVEIS_VARRIDOS, (
        f'A varredura achou só {clicaveis} clicáveis em apps/**/*.html — o '
        'guarda está passando por não enxergar, não por estar tudo certo'
    )
    assert not infratores, (
        f'Controle abaixo do piso de 44px; use min-h-11: {infratores}'
    )


class TestMecanismoDoPisoDe44px:
    """O guarda precisa provar que *detecta*, não que hoje não há infrator.

    Um guarda exercitado só pela árvore real é indistinguível de um guarda
    quebrado enquanto a árvore estiver limpa — e foi assim que a versão anterior
    passou verde por cima de dois controles sem piso. Cada forma de prova e cada
    cegueira conhecida tem aqui um caso sintético que deve falhar (ou passar) por
    conta própria.
    """

    PISO_CSS = frozenset({'skip-link'})

    def _infratores(self, texto, excecoes=None, caminho='sintetico.html'):
        achados, _ = _clicaveis_sem_piso(caminho, texto, self.PISO_CSS, excecoes or {})
        return achados

    def _quantidade(self, texto):
        _, quantidade = _clicaveis_sem_piso('sintetico.html', texto, self.PISO_CSS, {})
        return quantidade

    def test_ausencia_de_piso_e_detectada(self):
        """O caso que a versão anterior não via: nenhum piso escrito."""
        assert self._infratores('<a href="#x" class="underline">Erro</a>')

    def test_min_h_11_literal_passa(self):
        assert not self._infratores('<a href="#x" class="min-h-11">Erro</a>')

    def test_a_seguido_de_newline_e_detectado(self):
        """`<(a|button)[ >]` não casaria — e os dois infratores eram assim.

        As âncoras de error_summary.html e o CTA de empty_state.html quebram
        linha logo depois do nome da tag. Um guarda cego para essa grafia
        nasceria sem enxergar exatamente o que veio corrigir.
        """
        texto = '<a\n  href="#x"\n  class="underline"\n>Erro</a>'
        assert self._infratores(texto)

    def test_classe_condicional_nao_serve_de_esconderijo(self):
        """`min-h-11` dentro de `{% if %}` não conta como piso escrito."""
        texto = '<a href="#x" class="{% if x %}min-h-11{% endif %}">Erro</a>'
        assert self._infratores(texto)

    def test_piso_vindo_do_css_dispensa_min_h_11(self):
        assert not self._infratores('<a href="#x" class="skip-link">Pular</a>')

    def test_markup_dentro_de_comment_nao_e_markup(self):
        texto = '{% comment %}\n<a href="#x" class="underline">Exemplo</a>\n{% endcomment %}'
        assert not self._infratores(texto)
        assert self._quantidade(texto) == 0

    def test_comment_removido_preserva_a_numeracao_de_linha(self):
        texto = '{% comment %}\nexemplo\n{% endcomment %}\n<a href="#x" class="u">E</a>'
        assert self._infratores(texto) == ['sintetico.html:4 clicável sem piso de 44px']

    def test_classes_botao_delega_o_piso_ao_componente(self):
        """Em button.html `variant` é runtime; nenhuma varredura o resolve."""
        texto = '<a href="#x" class="{% classes_botao variant=variant %}">Ir</a>'
        assert not self._infratores(texto, caminho=_TEMPLATE_DE_BOTAO)

    def test_classes_botao_fora_de_button_html_nao_delega_nada(self):
        """A isenção é do arquivo, não da tag.

        Chamar `{% classes_botao %}` à mão numa tela seria rota de fuga do piso
        — e o design system já manda toda ação passar pelo componente.
        """
        texto = '<a href="#x" class="{% classes_botao variant=variant %}">Ir</a>'
        assert self._infratores(texto, caminho='requisicoes/tela.html')

    def test_include_de_variant_link_sem_min_h_11_e_detectado(self):
        """Delegar a classe ao componente não quita o chamador.

        `_FORMA_LINK` é a única forma sem piso, e o design system a isenta só
        para texto inline em prosa. Ação isolada com `variant="link"` carrega
        `class="min-h-11"` explícito.
        """
        texto = '{% include "components/button.html" with variant="link" label="Ir" %}'
        assert self._infratores(texto)

    def test_include_de_variant_link_com_min_h_11_passa(self):
        texto = (
            '{% include "components/button.html" with variant="link" '
            'label="Ir" class="min-h-11" %}'
        )
        assert not self._infratores(texto)

    def test_include_de_variant_link_com_aspas_simples_e_detectado(self):
        """Aspas simples são o estilo majoritário de include neste projeto.

        Um guarda que só entende aspas duplas é contornável por escolha de
        estilo — e um guarda contornável não é mecanismo, é sugestão.
        """
        texto = "{% include 'components/button.html' with variant='link' label='Ir' %}"
        assert self._infratores(texto)

    def test_include_com_aspas_desbalanceadas_nao_casa(self):
        """`"...'` não é par de aspas; o retrovisor `\\1` é o que garante isso."""
        texto = '{% include "components/button.html\' with variant="link" %}'
        assert not self._infratores(texto)

    def test_include_de_outra_variante_nao_exige_min_h_11_do_chamador(self):
        """`primary` já vem com piso de `_FORMA_BOTAO` — cobrar de novo seria ruído."""
        texto = (
            '{% include "components/button.html" with variant="primary" label="Ir" %}'
        )
        assert not self._infratores(texto)

    def test_excecao_de_prosa_inline_isenta_o_ponto_de_chamada(self):
        """Fixture sintética: o mecanismo existe antes de haver caso real.

        A lista real (`EXCECOES_DE_PROSA_INLINE`) continua vazia — ver o teste
        seguinte. Pôr uma entrada nela só para ter teste transformaria a exceção
        num desvio permanente da regra.
        """
        texto = '{% include "components/button.html" with variant="link" label="Ir" %}'
        excecoes = {('sintetico.html', 1): 'link inline no meio de uma frase'}
        assert not self._infratores(texto, excecoes)

    def test_excecao_isenta_uma_chamada_e_nao_o_arquivo_inteiro(self):
        """Um arquivo pode ter link inline *e* ação isolada.

        Com chave por caminho, a exceção do primeiro esconderia o segundo — e o
        buraco reapareceria exatamente onde este guarda foi posto para fechar.
        """
        chamada = (
            '{% include "components/button.html" with variant="link" label="Ir" %}'
        )
        texto = f'{chamada}\n{chamada}'
        excecoes = {('sintetico.html', 1): 'link inline no meio de uma frase'}

        assert self._infratores(texto, excecoes) == [
            'sintetico.html:2 variant="link" como ação isolada, sem min-h-11'
        ]

    def test_lista_real_de_excecoes_de_prosa_inline_esta_vazia(self):
        """Enquanto não houver link inline de verdade, ela não ganha entrada."""
        assert EXCECOES_DE_PROSA_INLINE == {}

    def test_classes_com_piso_saem_do_css_e_nao_de_lista_escrita_a_mao(self):
        raiz = Path(__file__).resolve().parents[3]
        derivadas = _classes_com_piso_no_css(raiz)

        assert {'campo', 'skip-link', 'app-bar__menu-item'} <= derivadas
        assert not any(nome[0].isdigit() for nome in derivadas), (
            f'`.5rem` de um padding virou nome de classe: {sorted(derivadas)}'
        )


class TestPisoDosControlesDeRecuperacao:
    """error_summary e empty_state: a superfície onde o usuário já falhou uma vez.

    São os dois controles que a issue #120 encontrou sem piso — e os dois estão
    justamente na recuperação de erro e na saída de estado vazio, operados com
    luva, no galpão, depois de a tela já ter dito não.
    """

    def _ancora_de_erro(self):
        html = render_to_string(
            'components/error_summary.html',
            {
                'erros': [
                    {'id': 'id_setor', 'rotulo': 'Setor', 'mensagem': 'Obrigatório.'}
                ]
            },
        )
        ((_, atributos, _),) = elementos(html, 'a')
        return classes(atributos)

    def _cta_secundario(self):
        html = render_to_string(
            'components/empty_state.html',
            {
                'titulo': 'Nenhum material',
                'cta_url': '/estoque/materiais/',
                'cta_label': 'Limpar busca',
                'cta_secundario': True,
            },
        )
        ((_, atributos, _),) = elementos(html, 'a')
        return classes(atributos)

    def test_ancora_de_erro_tem_alvo_de_44px(self):
        """`block` porque `min-height` não tem efeito em elemento inline.

        Num sumário de 4 erros, no celular, um alvo de ~21px leva o solicitante
        ao campo errado — no exato momento em que ele já errou uma vez.
        """
        assert {'block', 'min-h-11', 'py-2.5'} <= self._ancora_de_erro()

    def test_cta_secundario_tem_alvo_de_44px(self):
        """Única saída do estado vazio de busca de material."""
        assert {'inline-flex', 'items-center', 'min-h-11'} <= self._cta_secundario()

    def test_cta_secundario_nao_ganha_folga_horizontal(self):
        """A regra é de altura. `px-*` alargaria o alvo sem que nada peça."""
        assert not {c for c in self._cta_secundario() if c.startswith('px-')}

    @pytest.mark.parametrize(
        'template',
        (
            'components/error_summary.html',
            'components/empty_state.html',
        ),
    )
    def test_nenhum_raio_fora_da_escala(self, template):
        """`rounded` pelado é 0.25rem — degrau abaixo do menor da escala.

        A escala é controle 0.375 → campo 0.5 → papel 0.75 → modal 1rem → pill.
        Um raio intermediário inventado quebra a leitura de hierarquia por
        geometria.
        """
        raiz = Path(__file__).resolve().parents[3]
        texto = (raiz / 'apps/core/templates' / template).read_text()
        for _, atributos, numero in elementos(texto, 'a', 'button', 'div', 'ul', 'li'):
            assert 'rounded' not in classes(atributos), (
                f'{template}:{numero} usa `rounded` pelado; use a escala'
            )


_TEMPLATE_DO_ESTADO_VAZIO = 'components/empty_state.html'
_ASSINATURA_DO_ESTADO_VAZIO = frozenset({'border-dashed', 'border-border-strong'})
_INCLUDE_DO_ESTADO_VAZIO = re.compile(
    r'\{%\s*include\s+(["\'])components/empty_state\.html\1(?P<args>.*?)%\}', re.S
)
_MINIMO_DE_CHAMADORES_DO_ESTADO_VAZIO = 11
_FRAGMENTOS_DE_GRADE = ('cards_abertura', 'cards_abertura_denso')


def _clones_do_estado_vazio(caminho: str, texto: str) -> list[str]:
    """Elementos que replicam a assinatura visual do estado vazio à mão.

    A busca é por conjunto de tokens, não por substring: procurar a sequência
    literal `border-dashed border-border-strong` é guarda contornável por
    formatação — trocar a ordem das classes, quebrar a linha entre elas ou
    intercalar uma terceira já escaparia, e nenhuma das três muda um pixel do
    render.

    O dropzone da importação SCPI (`border-2 border-dashed border-border`, sem
    `-strong`) não casa, e é isso que separa "tracejado" de "estado vazio".

    A varredura cobre todo contêiner de bloco do sistema, não só `<div>`: um
    clone escrito em `<article>` ou `<aside>` renderiza exatamente igual, e uma
    guarda que depende da tag escolhida é contornável sem querer.
    """
    if caminho.endswith(_TEMPLATE_DO_ESTADO_VAZIO):
        return []
    infratores = []
    for _, atributos, numero in elementos(
        _sem_comentarios(texto), 'div', 'section', 'article', 'aside', 'p'
    ):
        if _ASSINATURA_DO_ESTADO_VAZIO <= classes(atributos):
            infratores.append(f'{caminho}:{numero} replica o estado vazio à mão')
    return infratores


def _chamadas_do_estado_vazio(texto: str):
    """Devolve (linha, argumentos) de cada `{% include %}` do componente."""
    limpo = _sem_comentarios(texto)
    for encontro in _INCLUDE_DO_ESTADO_VAZIO.finditer(limpo):
        numero = limpo.count('\n', 0, encontro.start()) + 1
        yield numero, encontro.group('args')


_ARGUMENTO_DE_INCLUDE = re.compile(
    r'(?P<nome>[\w-]+)=(?P<valor>"[^"]*"|\'[^\']*\'|[^\s]+)'
)


def _argumentos_do_include(argumentos: str) -> dict[str, str]:
    """Argumentos `nome=valor` com as aspas **preservadas**.

    `pares()` devolve o valor já sem aspas, e é isso que ele deve fazer para
    atributo HTML. Aqui a informação decisiva é justamente a que ele descarta:
    `titulo='Nada aqui'` é literal e `titulo=titulo_busca` é variável, e sem as
    aspas os dois chegam idênticos. Uma guarda que não distingue os dois ou não
    verifica nada, ou acusa toda variável de ter ponto final.
    """
    return {
        encontro.group('nome'): encontro.group('valor')
        for encontro in _ARGUMENTO_DE_INCLUDE.finditer(argumentos)
    }


def _e_literal(valor: str) -> bool:
    return len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in '"\''


def _sem_aspas(valor: str) -> str:
    return valor[1:-1] if _e_literal(valor) else valor


def _titulos_de_with(texto: str) -> dict[str, str]:
    """Literais atribuídos por `{% with nome=... %}` no próprio arquivo.

    `titulo=titulo_busca` não pode ser lido no ponto de chamada, mas a variável
    é montada no mesmo template. Resolver o `{% with %}` antes de desistir é o
    que impede que "título dinâmico" vire rota de fuga da regra de copy.
    """
    resolvidos: dict[str, str] = {}
    for encontro in re.finditer(r'\{%\s*with\s+(?P<args>.*?)%\}', texto, re.S):
        resolvidos.update(_argumentos_do_include(encontro.group('args')))
    return resolvidos


_TITULO_COM_TERMO = re.compile(
    r'\{%\s*titulo_com_termo\s+\S+\s+'
    r"(?P<prefixo>'[^']*'|\"[^\"]*\")\s*"
    r"(?P<sufixo>'[^']*'|\"[^\"]*\")?\s*"
    r'as\s+(?P<var>\w+)\s*%\}'
)


def _titulos_de_titulo_com_termo(texto: str) -> dict[str, str]:
    """Literais que `{% titulo_com_termo %}` monta pra `as <var>`.

    `titulo_com_termo` (apps/core/templatetags/core_tags.py) monta o título
    como `prefixo + '"' + termo + '"'` ou `prefixo + sufixo_generico` — nunca
    deixa `termo` (dinâmico, não dá pra verificar aqui) decidir se o título
    termina em ponto: só `prefixo`/`sufixo_generico`, os dois literais e
    capturados aqui, participam dessa borda. Resolver isso — em vez de jogar
    `titulo_busca` em `nao_verificaveis` — fecha o mesmo buraco que
    `_titulos_de_with` fecha pro `{% with %}` + `|add:` que esta tag substitui.
    """
    resolvidos: dict[str, str] = {}
    for encontro in _TITULO_COM_TERMO.finditer(texto):
        prefixo = _sem_aspas(encontro.group('prefixo'))
        sufixo = encontro.group('sufixo')
        partes = [prefixo] + ([_sem_aspas(sufixo)] if sufixo else [])
        resolvidos[encontro.group('var')] = "'" + ' '.join(partes) + "'"
    return resolvidos


def _desvios_de_copy_do_estado_vazio(caminho: str, texto: str):
    """Chamadas que fogem do padrão de copy, e as que não dá para verificar.

    Regra: título sem ponto final, ícone presente e descrição presente — os
    três com valor não vazio, porque chave presente não é contrato cumprido.
    """
    desvios, nao_verificaveis, quantidade = [], [], 0
    texto_limpo = _sem_comentarios(texto)
    com_with = _titulos_de_with(texto_limpo)
    com_with.update(_titulos_de_titulo_com_termo(texto_limpo))

    for numero, argumentos in _chamadas_do_estado_vazio(texto):
        quantidade += 1
        local = f'{caminho}:{numero}'
        args = _argumentos_do_include(argumentos)

        for nome in ('icone', 'descricao'):
            if not _sem_aspas(args.get(nome, '')).strip():
                desvios.append(f'{local} sem `{nome}` com valor')

        titulo = args.get('titulo')
        if titulo is None:
            desvios.append(f'{local} sem `titulo`')
            continue

        if not _e_literal(titulo):
            titulo = com_with.get(titulo, '')
        if not _e_literal(titulo):
            nao_verificaveis.append(local)
        elif _sem_aspas(titulo).strip().endswith('.'):
            desvios.append(f'{local} título com ponto final')

    return desvios, nao_verificaveis, quantidade


def test_nenhum_template_replica_a_marcacao_do_estado_vazio():
    """Uma implementação só de estado vazio, e o mecanismo que a mantém única.

    O clone que existia (importação SCPI) não recebia nenhuma correção do
    componente: ficou sem cabeçalho, sem ícone e com `text-text-disabled` num
    texto real (2.63:1 sobre branco, abaixo dos 4.5:1 da WCAG 1.4.3). Copiar
    classes é barato; o custo aparece na próxima correção, que passa longe da
    cópia.
    """
    raiz = Path(__file__).resolve().parents[3]
    infratores = []
    for caminho in sorted((raiz / 'apps').rglob('*.html')):
        relativo = str(caminho.relative_to(raiz))
        infratores.extend(_clones_do_estado_vazio(relativo, caminho.read_text()))

    assert not infratores, (
        f'Use components/empty_state.html em vez de replicar a caixa: {infratores}'
    )


def test_todo_chamador_do_estado_vazio_segue_a_copy():
    """Onze chamadores, um padrão de copy.

    Título sem ponto final, ícone e descrição sempre presentes. As exceções que
    existiam estavam no catálogo de materiais — a única tela em que o estado
    vazio era só um título, sem dizer o que aconteceu nem o que fazer.
    """
    raiz = Path(__file__).resolve().parents[3]
    desvios, nao_verificaveis, quantidade = [], [], 0
    for caminho in sorted((raiz / 'apps').rglob('*.html')):
        relativo = str(caminho.relative_to(raiz))
        achados, opacos, n = _desvios_de_copy_do_estado_vazio(
            relativo, caminho.read_text()
        )
        desvios.extend(achados)
        nao_verificaveis.extend(opacos)
        quantidade += n

    assert quantidade >= _MINIMO_DE_CHAMADORES_DO_ESTADO_VAZIO, (
        f'A varredura achou só {quantidade} chamadores do estado vazio — o '
        'guarda está passando por não enxergar, não por estar tudo certo'
    )
    assert not desvios, f'Copy fora do padrão do estado vazio: {desvios}'
    assert not nao_verificaveis, (
        'Título vindo de contexto de view não pode ser verificado aqui; se for '
        f'mesmo necessário, ele entra numa lista nomeada: {nao_verificaveis}'
    )


class TestMecanismoDasGuardasDoEstadoVazio:
    """As duas guardas precisam provar que *detectam*, não que hoje passa.

    Uma guarda exercitada só pela árvore real é indistinguível de uma guarda
    quebrada enquanto a árvore estiver limpa — foi assim que o piso de 44px
    passou verde por cima de dois controles sem piso (#120).
    """

    CLONE = '<div class="rounded-xl border border-dashed border-border-strong bg-surface">x</div>'

    def _clones(self, texto):
        return _clones_do_estado_vazio('sintetico.html', texto)

    def _desvios(self, texto):
        desvios, _, _ = _desvios_de_copy_do_estado_vazio('sintetico.html', texto)
        return desvios

    def _nao_verificaveis(self, texto):
        _, opacos, _ = _desvios_de_copy_do_estado_vazio('sintetico.html', texto)
        return opacos

    def test_clone_literal_e_detectado(self):
        assert self._clones(self.CLONE)

    def test_clone_com_classes_reordenadas_e_detectado(self):
        """Trocar a ordem das classes não muda um pixel do render."""
        texto = '<div class="border-border-strong bg-surface border-dashed">x</div>'
        assert self._clones(texto)

    def test_clone_quebrado_em_varias_linhas_e_detectado(self):
        texto = (
            '<div\n'
            '  class="rounded-xl border border-dashed\n'
            '         border-border-strong"\n'
            '>x</div>'
        )
        assert self._clones(texto)

    def test_clone_em_outra_tag_de_bloco_e_detectado(self):
        """`<article>` renderiza igual; a guarda não pode depender da tag."""
        texto = '<article class="border border-dashed border-border-strong">x</article>'
        assert self._clones(texto)

    def test_dropzone_tracejado_nao_e_estado_vazio(self):
        """`border-2 border-dashed border-border` é área de upload, não vazio."""
        texto = '<section class="border-2 border-dashed border-border bg-surface">x</section>'
        assert not self._clones(texto)

    def test_clone_dentro_de_comment_nao_e_clone(self):
        texto = f'{{% comment %}}\n{self.CLONE}\n{{% endcomment %}}'
        assert not self._clones(texto)

    def test_o_proprio_componente_nao_se_acusa(self):
        assert not _clones_do_estado_vazio(
            f'apps/core/templates/{_TEMPLATE_DO_ESTADO_VAZIO}', self.CLONE
        )

    def test_falta_de_icone_reprova(self):
        texto = (
            "{% include 'components/empty_state.html' with titulo='Nada aqui' "
            "descricao='Uma descrição.' %}"
        )
        assert self._desvios(texto)

    def test_icone_vazio_reprova_como_ausencia(self):
        """Chave presente não é contrato cumprido."""
        texto = (
            "{% include 'components/empty_state.html' with icone='' "
            "titulo='Nada aqui' descricao='Uma descrição.' %}"
        )
        assert self._desvios(texto)

    def test_descricao_vazia_reprova_como_ausencia(self):
        texto = (
            '{% include "components/empty_state.html" with icone="i.html" '
            'titulo="Nada aqui" descricao="" %}'
        )
        assert self._desvios(texto)

    def test_titulo_com_ponto_final_reprova(self):
        texto = (
            "{% include 'components/empty_state.html' with icone='i.html' "
            "titulo='Nada aqui.' descricao='Uma descrição.' %}"
        )
        assert self._desvios(texto)

    def test_chamada_completa_passa(self):
        texto = (
            "{% include 'components/empty_state.html' with icone='i.html' "
            "titulo='Nada aqui' descricao='Uma descrição.' %}"
        )
        assert not self._desvios(texto)

    def test_titulo_vindo_de_with_no_mesmo_arquivo_e_verificado(self):
        """`titulo=titulo_busca` não é ponto cego: o `{% with %}` mora ao lado."""
        texto = (
            "{% with titulo_busca='Nada encontrado.' %}"
            "{% include 'components/empty_state.html' with icone='i.html' "
            "titulo=titulo_busca descricao='Uma descrição.' %}"
            '{% endwith %}'
        )
        assert self._desvios(texto)

    def test_titulo_vindo_de_contexto_de_view_entra_na_lista_e_nao_some(self):
        """Uma isenção que ninguém consegue contar vira rota de fuga."""
        texto = (
            "{% include 'components/empty_state.html' with icone='i.html' "
            "titulo=titulo_da_view descricao='Uma descrição.' %}"
        )
        assert self._nao_verificaveis(texto)


class TestEmptyStateNivelDeTitulo:
    """O nível do cabeçalho do estado vazio é escolha da tela, não do componente.

    Até a #126 o `<h2>` era cravado. Coincidia com o nível dos títulos de cartão
    das listagens, então o outline não quebrava — mas o acoplamento não estava
    declarado em lugar nenhum, e a próxima tela que usasse o componente dentro de
    uma seção mais funda quebraria a hierarquia sem aviso.
    """

    def _render(self, **ctx):
        ctx.setdefault('titulo', 'Nenhum material')
        return render_to_string('components/empty_state.html', ctx)

    def test_titulo_usa_h2_por_padrao(self):
        """O default preserva os 11 chamadores que já existiam."""
        html = self._render()
        assert '<h2' in html and '</h2>' in html

    def test_nivel_titulo_parametriza_abertura_e_fechamento(self):
        """`<h3>…</h2>` não quebra render nenhum — quebra o outline em silêncio."""
        html = self._render(nivel_titulo=3)
        assert '<h3' in html and '</h3>' in html
        assert '<h2' not in html and '</h2>' not in html


class TestEmptyStateMedidaDaProsa:
    """Prosa centralizada ocupando os 80rem do container não é linha de leitura.

    `DESIGN.md` limita prosa longa a 65–75ch. A descrição do estado vazio era o
    único texto do componente sem limite de medida.
    """

    FAIXA_CH = (65, 75)

    def _descricao(self):
        html = render_to_string(
            'components/empty_state.html',
            {'titulo': 'Nenhum material', 'descricao': 'Uma descrição qualquer.'},
        )
        ((_, atributos, _),) = elementos(html, 'p')
        return classes(atributos)

    def _classe_de_medida(self):
        (medida,) = {c for c in self._descricao() if c.startswith('max-w-')}
        return medida

    def test_descricao_tem_limite_de_medida(self):
        assert self._classe_de_medida()

    def test_descricao_centralizada_nao_encosta_na_esquerda(self):
        """A caixa é `text-center`: sem `mx-auto` a coluna estreita vai pra esquerda."""
        assert 'mx-auto' in self._descricao()

    def test_medida_de_prosa_esta_compilada_no_app_css(self):
        """O passo de build que o AGENTS.md não menciona.

        Procurar o nome da classe no bundle não é asserção: o nome pode aparecer
        num seletor sem provar que ele declara a largura certa, e uma saída por
        valor arbitrário nem sequer contém a string. Esta guarda lê a declaração
        `max-width` do seletor e exige unidade `ch` dentro da faixa do DESIGN.md.
        Sem ela, esquecer `make css-build` deixa a classe inerte em produção com
        a suíte verde.
        """
        raiz = Path(__file__).resolve().parents[3]
        css = (raiz / 'apps/core/static/core/css/app.css').read_text()
        classe = self._classe_de_medida()
        seletor = '.' + re.sub(r'([.\[\]])', r'\\\1', classe)

        posicao = css.find(seletor + '{')
        assert posicao != -1, (
            f'`{classe}` não está compilada em app.css — rode `make css-build`'
        )

        bloco = css[posicao : css.index('}', posicao)]
        casamento = re.search(r'max-width:\s*([\d.]+)ch', bloco)
        assert casamento, f'`{classe}` não declara `max-width` em `ch`: {bloco}'

        piso, teto = self.FAIXA_CH
        assert piso <= float(casamento.group(1)) <= teto, (
            f'`{classe}` mede {casamento.group(1)}ch, fora da faixa {piso}–{teto}ch '
            'de DESIGN.md'
        )


class TestPaginationHref:
    """A paginação já navegou para lugar nenhum sem quebrar um teste.

    `add` é numérico primeiro: `add('?page=', 2)` tenta `int('?page=')`, falha,
    tenta `str + int`, falha de novo, e devolve string vazia em silêncio. Com
    href vazio, `button.html` cai no ramo <button> e os controles de página
    param de navegar — sem erro, sem log, sem teste vermelho.
    """

    CONTROLES = '<div class="flex flex-wrap items-center gap-2">'

    def _render(self, numero_pagina, *, total=30, por_pagina=10, **ctx):
        from django.core.paginator import Paginator
        from django.template.loader import render_to_string

        paginator = Paginator(list(range(total)), por_pagina)
        return render_to_string(
            'components/pagination.html',
            {
                'page_obj': paginator.page(numero_pagina),
                'rotulo_itens': 'itens',
                **ctx,
            },
        )

    def _hrefs(self, html):
        return re.findall(r'href="([^"]*)"', html)

    def _lista(self, html):
        """O bloco <ol> dos números, sem "Anterior"/"Próxima"."""
        return html.split('<ol ')[1].split('</ol>')[0]

    def _faixa(self, html):
        """Texto visível de cada item da faixa, na ordem do DOM."""
        return re.findall(r'>([^<>]+)</(?:a|span)>', self._lista(html))

    def test_href_carrega_o_numero_da_pagina(self):
        # 3 páginas, na 2: Anterior, número 1, número 3, Próxima — a 2 é o
        # marcador estático de página atual, e marcador não tem href.
        hrefs = self._hrefs(self._render(2))
        assert hrefs == ['?page=1', '?page=1', '?page=3', '?page=3']

    def test_href_preserva_filtros_ativos(self):
        html = self._render(2, querystring_filtros='texto=a+b&setor=1')
        hrefs = self._hrefs(html)
        assert len(hrefs) == 4
        for href in hrefs:
            assert 'texto=a+b' in href
            assert 'setor=1' in href

    def test_numero_de_pagina_carrega_a_querystring_de_filtros(self):
        """O número é o atalho novo; sem filtro no href ele desfaz o recorte.

        O guarda amarra o número visível ao `page=` do próprio href: um link
        rotulado "19" que aponta para outra página passaria em qualquer
        asserção de contagem.
        """
        import html as html_lib

        html = self._render(20, total=400, querystring_filtros='texto=a+b&setor=1')
        numeros = re.findall(r'<a\s+href="([^"]*)"[^>]*>(\d+)</a>', self._lista(html))
        assert [rotulo for _, rotulo in numeros] == ['1', '19', '21', '40']
        for href, rotulo in numeros:
            cru = html_lib.unescape(href)
            assert f'page={rotulo}' in cru
            assert 'texto=a+b' in cru and 'setor=1' in cru

    def test_pagina_atual_nao_e_link_e_carrega_aria_current(self):
        """Link para onde já se está é destino falso; e sem `aria-current` a
        faixa inteira é uma fileira de números sem "você está aqui".
        """
        html = self._render(20, total=400)
        assert html.count('aria-current="page"') == 1

        marcador = re.search(
            r'<span\s+aria-current="page"(.*?)>(\d+)</span>', html, re.S
        )
        assert marcador, html
        assert marcador.group(2) == '20'
        assert 'href' not in marcador.group(1)
        assert '?page=20' not in html

        # `bg-bg-subtle` é o hover da variante `ghost` dos outros números: usá-lo
        # aqui faria "em que página estou" ficar idêntico a "onde o ponteiro está".
        assert 'bg-text-secondary' in marcador.group(1)
        assert 'bg-bg-subtle' not in marcador.group(1)

    def test_reticencia_e_decorativa(self):
        """O `<li>` da lacuna sai da árvore junto com o `<span>`.

        Esconder só o `<span>` deixa o `<li>` de pé: o leitor de tela conta
        "lista, 7 itens" e anuncia dois itens vazios no meio da faixa. Com o
        `aria-hidden` no item, a contagem passa a ser a dos 5 alvos reais.
        """
        html = self._render(20, total=400)
        reticencias = re.findall(r'<span([^>]*)>…</span>', html)
        assert len(reticencias) == 2
        for atributos in reticencias:
            assert 'aria-hidden="true"' in atributos
            assert 'tabindex' not in atributos
            assert 'href' not in atributos
        assert '>…</a>' not in html

        itens = re.findall(r'<li([^>]*)>(.*?)</li>', self._lista(html), re.S)
        ocultos = [atributos for atributos, corpo in itens if '…' in corpo]
        visiveis = [atributos for atributos, corpo in itens if '…' not in corpo]
        assert len(ocultos) == 2 and len(visiveis) == 5
        for atributos in ocultos:
            assert 'aria-hidden="true"' in atributos
        for atributos in visiveis:
            assert 'aria-hidden' not in atributos

    def test_faixa_elidida_nao_explode_com_40_paginas(self):
        """Sete entradas no pior caso — cinco alvos de 44px e duas reticências.

        Com o default do Django (`on_each_side=3, on_ends=2`) seriam 13, que a
        375px viram três linhas de números empurrando "Próxima" para fora do
        alcance do polegar.
        """
        html = self._render(20, total=400)
        assert self._faixa(html) == ['1', '…', '19', '20', '21', '…', '40']

    def test_faixa_usa_a_pagina_corrente_e_nao_o_default_do_django(self):
        """`get_elided_page_range()` sem argumento pagina a partir da 1.

        O template não sabe passar argumento para método, então a chamada sem a
        tag resolveria para a faixa da página 1 — em toda página que não fosse a
        primeira, a faixa mostrada seria a de outra página, com a atual às vezes
        fora dela. Aqui a página 20 de 40 não pode trazer a vizinhança da 1.
        """
        from django.core.paginator import Paginator

        paginator = Paginator(list(range(400)), 10)
        faixa = faixa_paginas(paginator.page(20))
        assert [str(item) for item in faixa] == [
            '1',
            '…',
            '19',
            '20',
            '21',
            '…',
            '40',
        ]
        assert faixa != faixa_paginas(paginator.page(1))
        assert 20 in faixa

        html = self._render(20, total=400)
        assert '?page=2"' not in html

    def test_nome_acessivel_do_numero_diz_pagina(self):
        """ "7" sozinho é nome acessível pobre; e o rótulo tem de conter o texto
        visível, senão quebra o Label in Name (WCAG 2.5.3).
        """
        html = self._render(20, total=400)
        rotulos = re.findall(r'aria-label="([^"]*)"', self._lista(html))
        assert rotulos == ['Página 1', 'Página 19', 'Página 21', 'Página 40']
        for rotulo, visivel in zip(rotulos, ['1', '19', '21', '40'], strict=True):
            assert rotulo.endswith(visivel)

    def test_numero_respeita_o_piso_de_toque(self):
        """A varredura de markup isenta `button.html` (lá `variant` é runtime),
        então o piso dos números só se prova no render.
        """
        lista = self._lista(self._render(20, total=400))
        classes_dos_numeros = re.findall(r'<a[^>]*class="([^"]*)"', lista)
        assert len(classes_dos_numeros) == 4
        for valor in classes_dos_numeros:
            assert 'min-h-11' in valor
            assert 'min-w-11' in valor

    def test_ampersand_dos_filtros_nao_e_escapado_duas_vezes(self):
        """`&amp;amp;` faz o navegador ler um parâmetro chamado `amp;setor`.

        Ou seja: paginar perderia exatamente os filtros que o param existe para
        preservar. O escape duplo não quebra nada visível — o link continua
        clicável e a página continua carregando, só que sem filtro.
        """
        import html as html_lib
        from urllib.parse import parse_qs, urlparse

        html = self._render(2, querystring_filtros='texto=a+b&setor=1')
        assert '&amp;amp;' not in html

        for href in self._hrefs(html):
            params = parse_qs(urlparse(html_lib.unescape(href)).query)
            assert set(params) == {'texto', 'setor', 'page'}
            assert params['texto'] == ['a b']
            assert params['setor'] == ['1']

    def test_sem_filtros_nao_deixa_e_comercial_solto(self):
        for href in self._hrefs(self._render(2)):
            assert re.fullmatch(r'\?page=\d+', href), href

    def test_nome_acessivel_dos_controles_e_anterior_e_proxima(self):
        """O `aria_label` do include nomeia o <nav>, não os botões.

        `{% include %}` sem `only` repassa o contexto inteiro, e `button.html`
        emite `aria-label` quando encontra a variável. Sem zerar o parâmetro nos
        includes de botão, os dois controles anunciavam o rótulo do <nav> —
        "Paginação do histórico de requisições" — em vez de "Anterior" e
        "Próxima". O texto visível continuava certo; só quem usa leitor de tela
        perdia a única pista de qual controle avança e qual volta.

        Os números *têm* `aria-label`, o seu próprio ("Página 19"): o vazamento
        que este guarda persegue é o rótulo do <nav>, não a existência do
        atributo.
        """
        html = self._render(2, aria_label='Paginação do histórico de requisições')

        assert html.count('aria-label="Paginação do histórico de requisições"') == 1
        assert 'aria-label' in html.split(self.CONTROLES)[0]
        controles = html.split(self.CONTROLES)[1]
        assert 'Paginação do histórico de requisições' not in controles
        for rotulo in re.findall(r'aria-label="([^"]*)"', controles):
            assert rotulo.startswith('Página '), rotulo
        assert 'Anterior' in controles
        assert 'Próxima' in controles

    def test_nome_acessivel_tambem_nao_vaza_nos_extremos(self):
        """Nos extremos os controles são <button disabled>, mesmo caminho."""
        for numero in (1, 3):
            html = self._render(numero, aria_label='Paginação das movimentações')
            controles = html.split(self.CONTROLES)[1]
            assert 'Paginação das movimentações' not in controles

    def test_extremos_desabilitam_em_vez_de_gerar_href_vazio(self):
        primeira = self._render(1)
        ultima = self._render(3)
        # na 1: números 2 e 3 + "Próxima"; na 3: números 1 e 2 + "Anterior"
        assert self._hrefs(primeira) == ['?page=2', '?page=3', '?page=2']
        assert self._hrefs(ultima) == ['?page=2', '?page=1', '?page=2']
        assert 'href=""' not in primeira
        assert 'href=""' not in ultima
        assert primeira.count('aria-current="page"') == 1
        assert ultima.count('aria-current="page"') == 1


class TestOrdenacaoDataContagem:
    """Issue #156: a contagem do recorte sumia da linha de cima justamente
    quando havia paginação — `<span></span>` vazio no lugar e o número só
    reaparecia no rodapé de `pagination.html`. Agora aparece SEMPRE.
    """

    def _render(self, total, per_page):
        from django.core.paginator import Paginator
        from django.template.loader import render_to_string

        paginator = Paginator(list(range(total)), per_page)
        return render_to_string(
            'components/ordenacao_data.html',
            {
                'url_ordenacao': '?ordem=asc',
                'ordem': 'desc',
                'target_id': 'resultados-x',
                'page_obj': paginator.page(1),
                'rotulo_contagem': 'requisição,requisições',
            },
        )

    def test_sem_paginacao_mostra_o_tamanho_do_recorte(self):
        html = self._render(total=8, per_page=25)
        assert '<span class="font-medium tabular-nums">8</span> requisições' in html

    def test_com_paginacao_diz_pagina_de_recorte(self):
        html = self._render(total=60, per_page=25)
        assert (
            '<span class="font-medium tabular-nums">25</span> de '
            '<span class="font-medium tabular-nums">60</span> requisições'
        ) in html

    def test_sem_span_vazio_de_layout(self):
        assert '<span></span>' not in self._render(total=60, per_page=25)

    def test_contagem_e_sempre_o_primeiro_filho_da_linha(self):
        for total in (8, 60):
            corpo = self._render(total=total, per_page=25)
            corpo = corpo[corpo.index('justify-between') :]
            assert corpo.index('<p') < corpo.index('Mais antigas primeiro')


def test_todo_icon_template_de_button_honra_a_classe():
    """`button.html` dimensiona o ícone por `class`, a tag {% icon %} por `size`.

    Todo `.svg` do catálogo usa `class="{{ class }}"`; `voltar.svg` e
    `devolver.svg` aceitam `width="{{ size }}"` por cima, para a tag. Um SVG que
    dimensionasse **só** por `size` renderizaria `width=""` vindo de
    `icon_template` — o ícone estoura o botão, e nada quebra: sem erro, sem log,
    sem teste vermelho.
    """
    import re

    raiz = Path(__file__).resolve().parents[3]
    usados = set()
    for caminho in (raiz / 'apps').rglob('*.html'):
        usados.update(re.findall(r'icon_template="([^"]+)"', caminho.read_text()))

    incompativeis = []
    for relativo in sorted(usados):
        arquivo = raiz / 'apps/core/templates' / relativo
        if not arquivo.exists():
            incompativeis.append(f'{relativo} (arquivo não existe)')
        elif '{{ class' not in arquivo.read_text():
            incompativeis.append(f'{relativo} (não usa {{{{ class }}}})')

    assert not incompativeis, (
        f'icon_template precisa de um SVG que dimensione por class: {incompativeis}'
    )


def test_disabled_com_motivo_usa_aria_disabled_e_continua_focavel():
    """Botão `disabled` nativo sai da ordem de tabulação — e leva o motivo junto.

    O design system manda a ação de workflow bloqueada permanecer visível com o
    motivo em texto, amarrado por `aria-describedby`. Com `disabled` nativo, quem
    navega por Tab nunca chega ao botão e nunca ouve o motivo: o padrão só
    funcionava para quem lê a tela com os olhos.
    """
    html = _render(label='Estornar', disabled=True, aria_describedby='motivo-bloqueio')
    abertura = html[: html.index('>') + 1]
    assert 'aria-disabled="true"' in abertura
    assert 'aria-describedby="motivo-bloqueio"' in abertura
    assert not re.search(r'(?<![-:])\bdisabled\b(?![:=])', abertura)


def test_disabled_sem_motivo_continua_disabled_nativo():
    """Sem motivo declarado não há o que alcançar pelo foco.

    É o caso da paginação: "Anterior" na primeira página não tem explicação a
    dar, e um controle focável que não faz nada seria só ruído no Tab.
    """
    html = _render(label='Anterior', disabled=True)
    abertura = html[: html.index('>') + 1]
    assert re.search(r'(?<![-:])\bdisabled\b(?![:=])', abertura)
    # Atributo, não substring: as classes `aria-disabled:*` estão sempre no
    # `class`, porque a variante é estática e só o atributo é condicional.
    assert 'aria-disabled="true"' not in abertura


def test_aria_disabled_tem_tratamento_visual_de_desabilitado():
    """`aria-disabled` não herda o estilo de `:disabled` — precisa da variante."""
    html = _render(label='Estornar', disabled=True, aria_describedby='motivo-bloqueio')
    assert 'aria-disabled:opacity-60' in html
    assert 'aria-disabled:cursor-not-allowed' in html


def test_mecanismo_de_campo_enxerga_classe_condicional():
    """Teste do teste: a varredura acima não pode voltar a ser cega.

    O infrator real não era um campo escrito numa string limpa — era um campo
    cuja borda vinha de `{% if %}`. Se alguém trocar a varredura por busca de
    substring contígua de novo, isto quebra antes de o furo voltar a existir.
    """
    marcacao = (
        '<input\n'
        '  type="search"\n'
        '  @keydown.enter="if (ativo >= 0) { confirmar(); }"\n'
        '  class="w-full min-h-11 rounded-lg border '
        '{% if com_erro %}border-danger-border-input'
        '{% else %}border-border-strong{% endif %} px-3 py-2 text-sm"\n'
        '>'
    )
    controles = list(_controles_de_texto(marcacao))
    assert len(controles) == 1, 'o `>` dentro do atributo truncou o elemento'

    _, atributos, _ = controles[0]
    limpo = TAGS_DJANGO.sub(' ', atributos)
    assert 'campo' not in limpo
    assert any(borda in limpo for borda in _BORDAS_DE_CONTROLE)


def _oklch_para_srgb(L: float, C: float, h_graus: float) -> tuple[float, float, float]:
    """Converte oklch para sRGB com gama, na mesma matemática que o navegador usa."""

    h = math.radians(h_graus)
    a, b = C * math.cos(h), C * math.sin(h)
    longa = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    media = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    curta = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lineares = (
        4.0767416621 * longa - 3.3077115913 * media + 0.2309699292 * curta,
        -1.2684380046 * longa + 2.6097574011 * media - 0.3413193965 * curta,
        -0.0041960863 * longa - 0.7034186147 * media + 1.7076147010 * curta,
    )

    def codificar(u: float) -> float:
        u = max(0.0, min(1.0, u))
        return 12.92 * u if u <= 0.0031308 else 1.055 * u ** (1 / 2.4) - 0.055

    return tuple(codificar(x) for x in lineares)


def _luminancia(rgb: tuple[float, float, float]) -> float:
    def linearizar(u: float) -> float:
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    r, g, b = (linearizar(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _razao_sobre_branco(rgb: tuple[float, float, float]) -> float:
    return 1.05 / (_luminancia(rgb) + 0.05)


def _resolver_cor(token: str) -> tuple[float, float, float]:
    """Resolve `--color-<token>` até o oklch da paleta.

    O alias mora em `input.css` (`--color-danger-accent: var(--color-red-500)`)
    e o valor concreto só existe no `app.css` compilado, que é onde o Tailwind
    emite a paleta. Por isso o teste lê os dois arquivos.
    """

    raiz = Path(__file__).resolve().parents[3]
    fonte = (raiz / _INPUT_CSS).read_text()
    compilado = (raiz / 'apps/core/static/core/css/app.css').read_text()

    alias = re.search(rf'--color-{re.escape(token)}:\s*var\(--([\w-]+)\)', fonte)
    nome = alias.group(1) if alias else f'color-{token}'
    valor = re.search(rf'--{re.escape(nome)}:\s*oklch\(([^)]+)\)', compilado)
    assert valor, f'não achei o oklch de --{nome} no app.css'

    partes = valor.group(1).replace('%', '').split()
    L = float(partes[0]) / 100
    C = float(partes[1])
    h = float(partes[2])
    return _oklch_para_srgb(L, C, h)


def test_borda_de_controle_passa_em_1411():
    """Botão de fundo branco tem a borda como única delimitação — 3:1 (WCAG 1.4.11).

    É a mesma regra que `DESIGN.md` justifica nominalmente para `border-control`
    (slate-500, 4,77:1): onde a borda é a única pista de que existe um controle,
    ela precisa dos 3:1 de contraste não-textual.

    As variantes de contorno viviam nos `-border-strong`, que são shades 200/300
    escolhidos para separar superfícies, não para desenhar controles: medidos
    sobre branco davam 1,92:1 (red-300), 1,45:1 (amber-300) e 1,26:1 (teal-200).
    Como quatro dos cinco gatilhos de workflow da tela de detalhe usam estas
    variantes, as ações destrutivas eram os controles menos visíveis da página.

    O teste calcula o contraste de verdade a partir do token, em vez de fixar o
    nome da classe: trocar `border-danger-accent` por outro shade que também
    passe continua válido, e trocar por um que não passe quebra aqui.
    """

    raiz = Path(__file__).resolve().parents[3]
    fonte = (raiz / 'apps/core/templatetags/core_tags.py').read_text()
    bloco = fonte[fonte.index('_VARIANTES_BOTAO') : fonte.index('_TAMANHOS_BOTAO')]

    reprovadas: list[str] = []
    verificadas = 0
    for nome, classes_da_variante in re.findall(
        r"'([\w-]+)': \(\s*((?:'[^']*'\s*)+)\)", bloco
    ):
        texto = ' '.join(re.findall(r"'([^']*)'", classes_da_variante))
        if 'bg-surface' not in texto:
            continue
        borda = re.search(r'\bborder-([\w-]+)', texto)
        if not borda:
            continue
        verificadas += 1
        razao = _razao_sobre_branco(_resolver_cor(borda.group(1)))
        if razao < 3.0:
            reprovadas.append(f'{nome}: border-{borda.group(1)} = {razao:.2f}:1')

    assert verificadas >= 4, (
        f'esperava ao menos 4 variantes de fundo branco, achei {verificadas} — '
        'a varredura provavelmente parou de casar com o formato do dicionário'
    )
    assert not reprovadas, (
        'Borda de controle abaixo dos 3:1 da WCAG 1.4.11 sobre bg-surface. '
        'Onde a borda é a única delimitação do controle, ela precisa ser vista: '
        f'{reprovadas}'
    )


def test_nenhum_rotulo_de_campo_escrito_a_mao():
    """Rótulo de campo tem uma definição só: `.rotulo-campo`, em input.css.

    Ela carrega também o espaço até o campo — que antes vivia em quatro lugares
    e três valores: `mb-1` na label, `mt-1` no campo (família filter_*), `mt-2`
    na classe do widget em accounts/forms.py, e coisa nenhuma nos quatro
    chamadores de form_field.html que aceitavam o `label_class` padrão, onde o
    rótulo encostava no campo.

    Só `<label>` é varrido: a mesma tipografia é usada legitimamente em `<dt>`
    de lista de dados, que é termo de definição e não rótulo de controle.

    O critério é "a label declara tipografia própria", e não "a label copiou
    exatamente as classes de `.rotulo-campo`". A primeira versão exigia as três
    classes `text-xs`, `font-medium` e `uppercase` juntas, e os cinco corpos de
    modal de `requisicoes/partials/` passavam por baixo: quatro traziam
    `text-sm font-medium text-text-primary` (nenhuma das três) e o de devolução
    trazia `font-semibold` no lugar de `font-medium` — uma letra de diferença
    para a regra sumir. O teste passava verde com a régua quebrada em cinco
    arquivos.

    Uma label de campo legítima ou tem `rotulo-campo`, ou tem `sr-only` (caso em
    que o rótulo não aparece e não há tipografia a herdar), ou não declara
    tipografia nenhuma. Qualquer classe de fonte, tamanho ou caixa fora disso é
    a régua voltando a não ter dono.

    Rótulo de **opção** fica de fora, e o marcador é `flex`/`inline-flex`: ali a
    label embrulha o próprio controle numa linha de 44px (checkbox de filtro,
    radio de modo de criação). Ela não é o rótulo acima de um campo, e a caixa
    alta de bloco de `.rotulo-campo` estaria errada. É a mesma exceção que o
    parágrafo do `<dt>` acima descreve, por um motivo diferente.
    """

    raiz = Path(__file__).resolve().parents[3]
    prefixos_de_tipografia = ('text-', 'font-', 'uppercase', 'tracking-', 'leading-')
    # `text-left/center/right` alinham, não tipografam.
    alinhamento = {'text-left', 'text-center', 'text-right', 'text-justify'}
    # A lista de exceção da Etapa 7 fechou: `preview_importacao_scpi.html` e
    # `_modal_form_estorno_saida.html` eram os últimos rótulos escritos à mão,
    # e os dois passaram para `.rotulo-campo`. O guarda vale para `apps/`
    # inteiro, sem escotilha — que era a condição que o comentário anterior
    # anunciava ("some quando a Etapa 7 fechar").
    infratores: list[str] = []
    for caminho in (raiz / 'apps').rglob('*.html'):
        relativo = str(caminho.relative_to(raiz))
        texto = caminho.read_text()
        for _, atributos, numero in elementos(texto, 'label'):
            presentes = classes(atributos)
            if presentes & {'rotulo-campo', 'sr-only', 'flex', 'inline-flex'}:
                continue
            tipografia = {
                classe
                for classe in presentes
                if classe.startswith(prefixos_de_tipografia)
                and classe not in alinhamento
            }
            if tipografia:
                infratores.append(f'{relativo}:{numero} ({sorted(tipografia)})')

    assert not infratores, (
        'Rótulo de campo escrito à mão; use class="rotulo-campo" (definido em '
        f'assets/css/input.css): {infratores}'
    )


def test_dt_repetido_por_registro_nao_veste_tipografia_de_label():
    """Rótulo repetido por registro (issue #158) fica inline em caixa normal.

    `DESIGN.md` §A Regra da Caixa Alta Estrutural reserva `uppercase` a rótulo
    de estrutura impresso uma vez — `<th>`, `<label>`, cabeçalho de menu. O
    `<dt>` de um `<dl>` dentro de um cartão de listagem reimprime o mesmo texto
    a cada cartão da página: não é cabeçalho de coluna e não sobe para caixa
    alta. Semântica `<dl>/<dt>/<dd>` preservada; só a apresentação muda.
    """

    raiz = Path(__file__).resolve().parents[3]
    telas = (
        'apps/requisicoes/templates/requisicoes/historico_requisicoes.html',
        'apps/requisicoes/templates/requisicoes/lista_minhas.html',
        'apps/requisicoes/templates/requisicoes/fila_autorizacao.html',
        'apps/requisicoes/templates/requisicoes/fila_atendimento.html',
        'apps/estoque/templates/estoque/historico_movimentacoes.html',
        'apps/estoque/templates/estoque/lista_saidas_excepcionais.html',
        'apps/estoque/templates/estoque/lista_materiais.html',
        'apps/estoque/templates/estoque/historico_importacoes_scpi.html',
    )
    infratores: list[str] = []
    for rel in telas:
        texto = (raiz / rel).read_text()
        for _, atributos, numero in elementos(texto, 'dt'):
            if 'uppercase' in classes(atributos):
                infratores.append(f'{rel}:{numero}')

    assert not infratores, (
        '`<dt>` repetido por registro em caixa alta; rebaixe para rótulo inline '
        f'(DESIGN.md §A Regra da Caixa Alta Estrutural): {infratores}'
    )


def test_nenhum_widget_carrega_margem_de_rotulo():
    """A régua entre rótulo e campo não pertence ao Python.

    `accounts/forms.py` compensava a falta de margem da label escrevendo
    `campo mt-2` na classe do widget — espaçamento de layout decidido na camada
    que valida, e divergente dos 4px que o resto do sistema usava.
    """

    raiz = Path(__file__).resolve().parents[3]
    # A chave e o valor aceitam qualquer uma das duas aspas, e o valor pode
    # atravessar linhas — a varredura procura o literal, não uma grafia dele.
    padrao = re.compile(r'["\']class["\']\s*:\s*(["\'])(?P<valor>.*?)\1', re.S)
    margem = re.compile(r'\b(mt|mb)-\d')
    infratores: list[str] = []
    for caminho in (raiz / 'apps').rglob('forms.py'):
        texto = caminho.read_text()
        for encontro in padrao.finditer(texto):
            if margem.search(encontro.group('valor')):
                numero = texto.count('\n', 0, encontro.start()) + 1
                infratores.append(f'{caminho.relative_to(raiz)}:{numero}')

    assert not infratores, (
        'Margem vertical na classe do widget; o espaço entre rótulo e campo vem '
        f'de `.rotulo-campo`: {infratores}'
    )


def _classes(**ctx):
    marcacao = _render(**ctx)
    return set(marcacao.split('class="')[1].split('"')[0].split())


def test_ramos_a_e_button_compartilham_a_mesma_classe_de_variante():
    """A expressão de classe vivia duplicada entre os dois ramos, e já divergira.

    `cursor-pointer` e os estados `disabled:` existiam só no ramo `<button>`, e
    nada comparava as duas cópias — variante nova precisava ser escrita em dois
    lugares para não sair torta em um deles. Agora as duas saem de
    `{% classes_botao %}`, e a única diferença legítima é o que um link não tem:
    estado desabilitado e cursor de ponteiro.
    """
    so_do_botao = {
        'cursor-pointer',
        'disabled:cursor-not-allowed',
        'disabled:opacity-60',
        'aria-disabled:cursor-not-allowed',
        'aria-disabled:opacity-60',
    }
    for variante in _VARIANTES_BOTAO:
        link = _classes(variant=variante, href='/x/')
        botao = _classes(variant=variante)
        assert botao - link == so_do_botao, f'variante {variante}: {botao - link}'
        assert not link - botao, (
            f'variante {variante}: link tem classe que o botão não tem'
        )


def test_params_dinamicos_removidos_nao_voltam_por_engano():
    """O vocabulário Alpine de loading foi removido por não ter consumidor.

    Se alguém reintroduzir um deles no corpo do template sem uma tela que
    precise, isto quebra — a alternativa é ele voltar a ser documentado, testado
    e não usado, que foi exatamente como ele viveu até aqui.
    """

    raiz = Path(__file__).resolve().parents[3]
    marcacao = (raiz / 'apps/core/templates/components/button.html').read_text()
    corpo = marcacao[marcacao.index('{% endcomment %}') :]
    for param in ('spinner_show', 'label_bind', 'x_disabled', 'x_aria_busy'):
        assert param not in corpo, f'`{param}` voltou ao corpo de button.html'


class TestMessagesDismiss:
    """O contrato de dismiss de docs/CONVENTIONS.md, §Níveis e ARIA.

    O contrato foi decidido, documentado e nunca implementado — e dois
    documentos passaram a afirmar que existia. Estes testes são o mecanismo que
    faltava: `docs/design-system.md` avisa que regra sem mecanismo vira sugestão,
    e neste conjunto de arquivos isso já aconteceu três vezes.
    """

    NIVEIS = ('error', 'warning', 'success', 'info')

    def _render(self, *niveis, texto=None):
        from django.contrib import messages as django_messages
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get('/')
        request.session = {}
        request._messages = FallbackStorage(request)
        for indice, nivel in enumerate(niveis):
            getattr(django_messages, nivel)(
                request, texto or f'Mensagem {nivel} {indice}'
            )
        return render_to_string('core/partials/_messages.html', request=request)

    def _itens(self, html):
        """Elementos que carregam `x-data` — um por mensagem renderizada."""
        return [
            (attrs, linha)
            for _, attrs, linha in elementos(html, 'div')
            if atributo(attrs, 'x-data')
        ]

    @pytest.mark.parametrize('nivel', NIVEIS)
    def test_botao_de_fechar_presente_no_nivel(self, nivel):
        html = self._render(nivel)
        rotulos = [
            atributo(attrs, 'aria-label') for _, attrs, _ in elementos(html, 'button')
        ]
        assert rotulos == ['Fechar mensagem']

    @pytest.mark.parametrize('nivel', NIVEIS)
    def test_botao_de_fechar_respeita_o_piso_de_44px(self, nivel):
        html = self._render(nivel)
        (attrs,) = [attrs for _, attrs, _ in elementos(html, 'button')]
        assert {'min-h-11', 'min-w-11'} <= classes(attrs)

    @pytest.mark.parametrize('nivel', NIVEIS)
    def test_dismiss_e_um_button_nativo(self, nivel):
        """`<div @click>` não é focável nem responde a Enter/Espaço.

        O critério "dispensável só pelo teclado" é satisfeito pela escolha do
        elemento, não por handler de teclado — então é o elemento que o teste
        protege.
        """
        html = self._render(nivel)
        (attrs,) = [attrs for _, attrs, _ in elementos(html, 'button')]
        assert atributo(attrs, 'type') == 'button'

    @pytest.mark.parametrize('nivel', NIVEIS)
    def test_botao_fica_fora_do_no_que_carrega_o_role(self, nivel):
        """Botão irmão do texto dentro do nó com role entra no anúncio.

        O leitor de tela leria "Erro tal — Fechar mensagem, botão". O role vive
        num wrapper que contém só o texto.
        """
        html = self._render(nivel)
        for _, attrs, linha in elementos(html, 'div'):
            if atributo(attrs, 'role') not in {'alert', 'status'}:
                continue
            fim = html.index('</div>', html.index(attrs) + len(attrs))
            assert '<button' not in html[html.index(attrs) + len(attrs) : fim], (
                f'botão dentro da live region na linha {linha}'
            )

    def test_contagem_de_role_permanece_uma_por_mensagem(self):
        """Espelha apps/requisicoes/tests/test_views.py:2713, que não muda."""
        html = self._render('error', 'success')
        assert html.count('role="alert"') == 1
        assert html.count('role="status"') == 1
        assert 'aria-live=' not in html

    @pytest.mark.parametrize('nivel', ('success', 'info'))
    def test_success_e_info_pedem_auto_dismiss(self, nivel):
        html = self._render(nivel)
        ((attrs, _),) = self._itens(html)
        assert 'auto: true' in atributo(attrs, 'x-data')

    @pytest.mark.parametrize('nivel', ('warning', 'error'))
    def test_warning_e_error_declaram_auto_false(self, nivel):
        """Asserção positiva, não de ausência.

        Procurar por "não tem auto" passaria vacuamente se o atributo mudasse de
        nome, sumisse, ou o item deixasse de renderizar — o mesmo buraco de
        `test_nenhum_controle_abaixo_do_piso_de_44px`, que procura `min-h-9` e
        `min-h-10` e por isso não enxerga piso nenhum.
        """
        html = self._render(nivel)
        ((attrs, _),) = self._itens(html)
        assert 'auto: false' in atributo(attrs, 'x-data')

    @pytest.mark.parametrize('nivel', ('warning', 'error'))
    def test_warning_e_error_mantem_dismiss_manual(self, nivel):
        """Não ter timer não pode virar não ter saída."""
        html = self._render(nivel)
        assert 'Fechar mensagem' in html

    @pytest.mark.parametrize('nivel', ('success', 'info'))
    def test_timer_pausa_em_hover_e_em_foco(self, nivel):
        html = self._render(nivel)
        ((attrs, _),) = self._itens(html)
        for evento in ('@mouseenter', '@mouseleave', '@focusin', '@focusout'):
            assert atributo(attrs, evento), f'{evento} ausente'

    def test_motivo_da_assimetria_esta_registrado_no_template(self):
        """WCAG 2.2.1 é a razão de warning/error não terem timer.

        Sem o motivo no arquivo, a próxima pessoa "uniformiza" o comportamento.
        """

        raiz = Path(__file__).resolve().parents[3]
        texto = (raiz / 'apps/core/templates/core/partials/_messages.html').read_text()
        assert '2.2.1' in texto

    def test_debug_nao_chega_ao_usuario_final(self):
        html = self._render('debug')
        assert 'Mensagem debug' not in html
        assert self._itens(html) == []

    def test_sem_mensagens_visiveis_nao_sobra_wrapper(self):
        """`{% if messages %}` seria verdadeiro com um storage só de debug."""
        assert self._render('debug').strip() == ''

    def test_um_mecanismo_de_espacamento_so(self):
        """`space-y-2` no wrapper e `mb-2` nos filhos dobravam o respiro."""

        raiz = Path(__file__).resolve().parents[3]
        texto = (raiz / 'apps/core/templates/core/partials/_messages.html').read_text()
        assert not ('space-y-2' in texto and 'mb-2' in texto)

    def test_assertivas_precedem_polidas_no_dom(self):
        html = self._render('success', 'error')
        assert html.index('Mensagem error') < html.index('Mensagem success')


class TestMensagensNasTelasDeAuth:
    """Depois do logout, "Sessão encerrada." precisa ser vista.

    `login.html` incluía `_messages.html` antes do wrapper de 100vh: no celular
    o usuário via só o card e nunca a confirmação. `login_bloqueado.html` não
    incluía o partial, então qualquer mensagem enfileirada antes do 429 do axes
    sumia sem rastro.
    """

    def _render(self, template, nivel='info', texto='Sessão encerrada.', **ctx):
        from datetime import timedelta

        from django.contrib import messages as django_messages
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        from apps.accounts.forms import MatriculaAuthenticationForm

        # O axes sempre injeta este contexto na tela de bloqueio. Sem ele, o
        # `minutos_totais` estoura antes de o teste chegar ao que interessa.
        ctx.setdefault('cooloff_timedelta', timedelta(minutes=30))
        # Pelo mesmo motivo, o `form`: desde que o login passou a desenhar os
        # campos pelo components/form_field.html, um contexto sem form derruba
        # o template em `field.help_text` antes de chegar à faixa de mensagem.
        # A view sempre entrega um — o teste não pode ser mais pobre que ela.
        ctx.setdefault('form', MatriculaAuthenticationForm())
        request = RequestFactory().get('/')
        request.session = {}
        request._messages = FallbackStorage(request)
        getattr(django_messages, nivel)(request, texto)
        return render_to_string(template, ctx, request=request)

    def test_login_renderiza_a_faixa_uma_vez(self):
        html = self._render('accounts/login.html')
        assert html.count('Sessão encerrada.') == 1

    def test_login_renderiza_a_faixa_dentro_do_bloco_centralizado(self):
        """Fora dele, a mensagem fica acima de uma dobra de 100vh."""
        html = self._render('accounts/login.html')
        assert html.index('min-h-screen') < html.index('Sessão encerrada.')

    def test_login_bloqueado_renderiza_a_faixa_uma_vez(self):
        html = self._render('accounts/login_bloqueado.html')
        assert html.count('Sessão encerrada.') == 1

    def test_login_bloqueado_conta_a_faixa_e_nao_o_alerta_fixo(self):
        """O alerta de bloqueio é components/alert.html, não flash message.

        Contá-lo mascararia justamente o caso de a faixa estar ausente.
        """
        html = self._render('accounts/login_bloqueado.html')
        assert 'Tentativas de acesso demais' in html
        assert 'Fechar mensagem' in html

    @pytest.mark.parametrize(
        'template',
        ('base_auth.html', 'accounts/login.html', 'accounts/login_bloqueado.html'),
    )
    def test_ancora_de_foco_existe_nos_tres_layouts(self, template):
        """Destino do foco depois do dismiss por teclado.

        `login_bloqueado.html` não tem nenhum outro elemento focável no card —
        é só texto —, então sem a âncora o foco cairia no body justamente na
        tela que mais precisa dela.
        """
        html = self._render(template)
        (attrs,) = [
            attrs
            for _, attrs, _ in elementos(html, 'main')
            if atributo(attrs, 'id') == 'conteudo'
        ]
        assert atributo(attrs, 'tabindex') == '-1'


class TestSumarioDeErros:
    """`error_summary.html` fora do caminho feliz — a issue #125.

    O componente promete três coisas: anunciar que falhou, dizer quantos
    problemas e levar ao campo por link. Cinco dos seis defeitos que a #125
    encontrou eram ele falhando fora do caminho feliz — anel que não pinta,
    foco que depende inteiramente do Alpine, contagem que mente.
    """

    ERROS = [
        {'id': 'id_setor', 'rotulo': 'Setor', 'mensagem': 'Obrigatório.'},
        {'id': 'id_motivo', 'rotulo': 'Motivo', 'mensagem': 'Obrigatório.'},
    ]

    def _render(self, **ctx):
        ctx.setdefault('erros', self.ERROS)
        return render_to_string('components/error_summary.html', ctx)

    def _caixa(self, html):
        ((_, attrs, _),) = [
            (tag, attrs, linha)
            for tag, attrs, linha in elementos(html, 'div')
            if atributo(attrs, 'role') == 'alert'
        ]
        return attrs

    def test_anel_de_foco_usa_focus_e_nao_focus_visible(self):
        """O foco aqui é programático, e `:focus-visible` não casa nele.

        Depois de um POST full-page a última interação do usuário foi o clique
        ou o toque no botão de enviar. O foco vai para a caixa por
        `tabindex="-1"`, e um anel declarado em `focus-visible:` simplesmente
        não pinta — o usuário de teclado recebe o foco sem nenhuma indicação
        de onde ele está.
        """
        caixa = classes(self._caixa(self._render()))
        assert {'focus:ring-2', 'focus:outline-none'} <= caixa
        assert not {c for c in caixa if c.startswith('focus-visible:')}

    def test_ancora_do_item_mantem_focus_visible(self):
        """A âncora é o caso contrário, e o guarda existe para não confundi-los.

        Ela recebe foco por teclado, que é exatamente o que `:focus-visible`
        casa. Trocar as duas de lugar "consertaria" o elemento errado.
        """
        html = self._render()
        ((_, attrs, _), *_) = elementos(html, 'a')
        anel = classes(attrs)
        assert 'focus-visible:ring-2' in anel
        assert 'focus:ring-2' not in anel

    def test_foco_nao_depende_do_alpine(self):
        """`autofocus` é o caminho que sobra quando o Alpine não carregou.

        Rede institucional, celular antigo, `defer` que falhou: sem fallback a
        tela volta "aparentemente intacta", que é a falha descrita no cabeçalho
        do próprio componente. `autofocus` é atributo global de HTML e vale em
        elemento focável por `tabindex`.
        """
        attrs = self._caixa(self._render())
        assert atributo(attrs, 'tabindex') == '-1'
        assert 'autofocus' in {chave.lower() for chave, _ in pares(attrs)}

    def test_contagem_conta_alvos(self):
        """Dois alvos, dois problemas — e o plural acompanha."""
        html = self._render()
        assert '2 problemas encontrados' in html

    def test_contagem_singular(self):
        html = self._render(erros=self.ERROS[:1])
        assert '1 problema encontrado' in html
        assert 'problemas' not in html

    def test_frase_lider_default_fala_em_salvar(self):
        assert 'Não foi possível salvar:' in self._render()

    def test_frase_lider_e_parametrizavel(self):
        """A tela que não salva não pode dizer que não salvou.

        `atender_retirada.html` registra uma retirada; "não foi possível
        salvar" descreve uma ação que aquela tela não tem.
        """
        html = self._render(acao='registrar o atendimento')
        assert 'Não foi possível registrar o atendimento:' in html
        assert 'salvar' not in html

    def test_acao_vazia_cai_no_default(self):
        """Tela que passa string vazia não pode produzir "Não foi possível :"."""
        assert 'Não foi possível salvar:' in self._render(acao='')

    def test_titulo_e_cabecalho(self):
        """`<p>` não entra no outline nem na navegação por cabeçalhos.

        Procurar "onde está o erro" saltando de cabeçalho em cabeçalho é como
        um usuário de leitor de tela navega. O padrão GOV.UK, que o componente
        diz seguir, usa `<h2>`.
        """
        tags = {tag for tag, _, _ in elementos(self._render(), 'h2', 'p')}
        assert tags == {'h2'}

    def test_mensagem_longa_quebra_dentro_da_ancora(self):
        """Mensagens agregadas ficam longas, e o alvo é celular de 375px.

        Com a agregação por alvo, um campo com três erros vira uma âncora com
        três frases. Sem quebra, um rótulo comprido empurra a caixa para fora
        da viewport e a rolagem horizontal come a tela inteira.
        """
        html = self._render()
        ((_, attrs, _), *_) = elementos(html, 'a')
        assert 'break-words' in classes(attrs)

    def test_sem_erros_nao_renderiza_nada(self):
        assert self._render(erros=[]).strip() == ''

    def test_nao_tem_dismiss_nem_auto_ocultacao(self):
        """O contrato de dismiss é o das flash messages, não o do sumário.

        `docs/CONVENTIONS.md` §Níveis e ARIA governa `_messages.html`. Aqui
        fechar a caixa seria dano: os erros continuam no formulário e o usuário
        perderia a única navegação até eles. A asserção é sobre o conjunto de
        mecanismos, não sobre uma grafia — checar só `mensagemFlash` deixaria
        passar um timer escrito de outro jeito.
        """
        html = self._render()
        assert not list(elementos(html, 'button'))
        for mecanismo in (
            'mensagemFlash',
            'setTimeout',
            'x-show',
            'x-if',
            'x-transition',
            'hidden',
        ):
            assert mecanismo not in html


class TestAdocaoDoSumarioNasTelasDeFormsetLongo:
    """As três telas longas de formset tratadas do mesmo jeito — a #125.

    Antes: `atender_retirada` e `rascunho_form` tinham o sumário,
    `nova_saida_excepcional` não tinha nenhum, e `rascunho_form` tinha o erro de
    formset duas vezes. Três telas com o mesmo problema e três tratamentos
    diferentes.
    """

    TELAS = (
        'apps/estoque/templates/estoque/nova_saida_excepcional.html',
        'apps/requisicoes/templates/requisicoes/rascunho_form.html',
        'apps/requisicoes/templates/requisicoes/atender_retirada.html',
    )

    PARTIAIS_REMOVIDOS = (
        'apps/estoque/templates/estoque/partials/_alert_erros_formset.html',
        'apps/requisicoes/templates/requisicoes/partials/_alert_erros_formset.html',
    )

    def _raiz(self):
        return Path(__file__).resolve().parents[3]

    @pytest.mark.parametrize('tela', TELAS)
    def test_tela_monta_e_inclui_o_sumario(self, tela):
        texto = (self._raiz() / tela).read_text()
        assert '{% erros_do_formulario' in texto

    @pytest.mark.parametrize('tela', TELAS)
    def test_nenhum_include_e_alimentado_por_erro_de_formset(self, tela):
        """A borda pode ler `non_form_errors`; uma segunda caixa de texto, não.

        O sumário já coleta `formset.non_form_errors()`. O que pode sobrar na
        tela é marcador de *onde* — a borda da seção —, nunca a mensagem
        repetida a várias roladas de distância.

        A asserção varre as tags `{% include %}` e exige que nenhuma seja
        alimentada por erro de formset. Proibir `body_template` em bloco seria
        errado: `rascunho_form.html` tem um legítimo, o de itens inelegíveis.
        E uma asserção sobre a ausência do partial removido seria **vácua** —
        ele já não existe, então passaria sem olhar nada. É o buraco do guarda
        de 44px (#120) reproduzido: teste que não pode falhar não é guarda.
        """
        texto = (self._raiz() / tela).read_text()
        includes = re.findall(r'\{%\s*include\s.*?%\}', texto, re.S)
        assert includes, f'{tela}: nenhum include encontrado — regex quebrou?'
        alimentados = [
            include
            for include in includes
            if 'non_form_errors' in include or 'erros_formset' in include
        ]
        assert alimentados == [], (
            f'{tela}: include alimentado por erro de formset — o sumário já '
            f'mostra essa mensagem: {alimentados}'
        )

    def test_partiais_orfaos_sairam(self):
        for caminho in self.PARTIAIS_REMOVIDOS:
            assert not (self._raiz() / caminho).exists(), (
                f'{caminho} continua no repositório sem consumidor'
            )

    def test_nenhuma_referencia_residual_ao_partial_removido(self):
        """Arquivo ausente não é guarda suficiente.

        Um `{% include %}` sobrevivente vira `TemplateDoesNotExist` em produção,
        na tela de erro, para o chefe de almoxarifado. O guarda que só olha o
        arquivo passaria feliz.
        """
        # Este arquivo cita o nome do partial para poder procurá-lo, então é o
        # único excluído da varredura. Qualquer outro arquivo — template, view
        # ou outro módulo de teste — continua sendo pego.
        eu = Path(__file__).resolve()
        residuais = [
            str(arquivo.relative_to(self._raiz()))
            for arquivo in (self._raiz() / 'apps').rglob('*')
            if arquivo.is_file()
            and arquivo.suffix in {'.html', '.py'}
            and arquivo.resolve() != eu
            and '_alert_erros_formset' in arquivo.read_text(errors='ignore')
        ]
        assert residuais == [], f'referência a partial removido: {residuais}'


class TestSuperficieUnicaDeErroDeFormulario:
    """Uma porta só para erro de formulário: `{% erros_do_formulario %}`.

    O sumário existia desde a #125, mas cada tela ainda decidia sozinha o quê
    coletar, em que ordem e onde incluir o componente — e três superfícies
    conviviam: o sumário nas telas de formset, uma caixa de `non_field_errors`
    montada com `alert.html` no login, e uma terceira caixa desenhada à mão
    dentro de `_modal_body.html`. Guardar só o comportamento do componente não
    impede a quarta grafia: o que este bloco guarda é a *porta*.
    """

    TELAS_DE_FORMULARIO = (
        'apps/estoque/templates/estoque/nova_saida_excepcional.html',
        'apps/requisicoes/templates/requisicoes/rascunho_form.html',
        'apps/requisicoes/templates/requisicoes/atender_retirada.html',
        'apps/accounts/templates/accounts/login.html',
        'apps/core/templates/components/_modal_body.html',
    )

    def _raiz(self):
        return Path(__file__).resolve().parents[3]

    def _templates(self):
        return [
            arquivo
            for arquivo in (self._raiz() / 'apps').rglob('*.html')
            if arquivo.is_file()
        ]

    @pytest.mark.parametrize('tela', TELAS_DE_FORMULARIO)
    def test_toda_tela_com_formulario_usa_a_tag(self, tela):
        texto = (self._raiz() / tela).read_text()
        assert '{% erros_do_formulario' in texto, (
            f'{tela}: formulário sem a superfície canônica de erro'
        )

    def test_nenhum_template_inclui_o_sumario_direto(self):
        """`{% include "components/error_summary.html" %}` é a porta dos fundos.

        Incluir o componente à mão devolve à tela a escolha de o quê coletar —
        exatamente a decisão que a tag centraliza. O componente continua
        renderizável em teste (é o que este arquivo faz acima); o que não pode
        é um *template* chamá-lo sem passar pela tag.
        """
        eu = Path(__file__).resolve()
        infratores = [
            str(arquivo.relative_to(self._raiz()))
            for arquivo in self._templates()
            if arquivo.resolve() != eu
            and re.search(
                r'\{%\s*include\s+["\']components/error_summary\.html',
                arquivo.read_text(errors='ignore'),
            )
        ]
        assert infratores == [], (
            f'include direto do sumário; use {{% erros_do_formulario %}}: {infratores}'
        )

    def test_coletar_erros_nao_e_mais_tag_de_template(self):
        """A coleta é peça interna da tag, não uma segunda porta.

        Enquanto `{% coletar_erros %}` existia, a tela montava a lista numa
        variável e depois decidia se — e onde — desenhá-la. São duas decisões
        onde deve haver zero.
        """
        from apps.core.templatetags.core_tags import register

        assert 'coletar_erros' not in register.tags
        assert 'erros_do_formulario' in register.tags

        infratores = [
            str(arquivo.relative_to(self._raiz()))
            for arquivo in self._templates()
            if '{% coletar_erros' in arquivo.read_text(errors='ignore')
        ]
        assert infratores == [], f'{{% coletar_erros %}} não existe mais: {infratores}'

    def test_erro_de_campo_a_mao_nao_volta_pelo_login(self):
        """O login escrevia rótulo, widget e erro campo a campo.

        Três blocos de markup para o que `components/form_field.html` já faz,
        com ids de erro próprios (`username-error`) que só existiam ali — e que
        o `accounts/forms.py` tinha de conhecer para montar o `aria-describedby`
        na mão. A mesma decisão em dois arquivos, com o Form perdendo calado
        quando o componente mudasse.
        """
        texto = (
            self._raiz() / 'apps/accounts/templates/accounts/login.html'
        ).read_text()
        assert 'components/form_field.html' in texto
        assert 'field_error.html' not in texto
        assert 'username-error' not in texto
        assert 'password-error' not in texto


class TestAncoraDosErrosSemCampo:
    """ "A saída precisa ter ao menos um item." precisa levar a algum lugar.

    O sumário promete três coisas — anunciar, contar e levar. A terceira valia
    só para erro de campo: o que vem de `non_form_errors` não tinha `id`, virava
    texto morto no meio de uma lista de links, e quem clicava em volta não
    entendia por que aquele não respondia. `ancora_geral` dá a esses itens o
    alvo que falta, e o alvo precisa ser real e focável — âncora para `id` que
    não existe rola para lugar nenhum, e sem `tabindex="-1"` o foco não pousa.
    """

    TELAS = (
        'apps/estoque/templates/estoque/nova_saida_excepcional.html',
        'apps/requisicoes/templates/requisicoes/rascunho_form.html',
        'apps/requisicoes/templates/requisicoes/atender_retirada.html',
    )

    def _raiz(self):
        return Path(__file__).resolve().parents[3]

    @pytest.mark.parametrize('tela', TELAS)
    def test_ancora_geral_existe_e_e_focavel(self, tela):
        texto = (self._raiz() / tela).read_text()
        (alvo,) = re.findall(r'ancora_geral="([\w-]+)"', texto)

        assert f'id="{alvo}"' in texto, (
            f'{tela}: ancora_geral="{alvo}" não tem elemento correspondente — '
            f'a âncora rola para lugar nenhum'
        )
        elemento = texto[texto.index(f'id="{alvo}"') :]
        elemento = elemento[: elemento.index('>')]
        assert 'tabindex="-1"' in elemento, (
            f'{tela}: alvo "{alvo}" não é focável — o teclado chega ao destino '
            f'com o foco ainda no sumário'
        )


# Portas de saída do escopo Alpine para o DOM cru. Nenhuma delas produz valor
# rastreável: `$refs` é `mergeProxies` e não `reactive()`, e `document`/`window`
# nunca foram proxy de nada.
_FUGAS_DO_ESCOPO_ALPINE = ('$refs', '$el', '$root', 'document.', 'window.')


# Busca por atributo e não por elemento: `x-trap` não pertence a nenhuma tag em
# particular, e um guarda com lista de tags fechada é cego para a tag de fora
# da lista — que é exatamente a forma como o defeito volta.
_X_TRAP = re.compile(
    r"""x-trap[\w.]*\s*=\s*(?:(["'])(?P<citado>.*?)\1|(?P<cru>[^\s"'>]+))""",
    re.S,
)


def _x_trap_sem_reatividade(caminho: str, texto: str) -> list[str]:
    """Acha `x-trap` cuja expressão o `effect` do Alpine não consegue rastrear."""
    infratores: list[str] = []
    limpo = _sem_comentarios(texto)
    for encontro in _X_TRAP.finditer(limpo):
        # Valor sem aspas é HTML válido, e um guarda que só enxerga o citado é
        # cego para a única grafia que ninguém pensa em escrever de propósito.
        valor = encontro.group('citado')
        if valor is None:
            valor = encontro.group('cru')
        fuga = next((f for f in _FUGAS_DO_ESCOPO_ALPINE if f in valor), None)
        if fuga:
            linha = limpo.count('\n', 0, encontro.start()) + 1
            infratores.append(f'{caminho}:{linha} x-trap="{valor}" usa {fuga}')
    return infratores


def test_nenhum_x_trap_liga_a_propriedade_fora_do_escopo_alpine():
    """`x-trap` só ativa se a expressão for dado reativo do Alpine (#134).

    `x-trap.inert.noscroll="$refs.dialog.open"` viveu meses em
    `components/modal.html` sem nunca ativar: `$refs` é `mergeProxies`, não
    `reactive()`, e `.open` é propriedade IDL nativa de `HTMLDialogElement` — o
    `effect` do plugin não rastreava nada, rodava uma vez no init com o diálogo
    fechado e não voltava mais.

    É a classe de defeito mais cara que este front tem: nada quebra, o atributo
    está lá, a documentação descreve o comportamento, e o efeito simplesmente
    não existe. Nenhuma asserção sobre HTML renderizado o alcança, porque o
    HTML renderizado está correto — o que está errado é o que ele significa.
    """
    raiz = Path(__file__).resolve().parents[3]
    infratores: list[str] = []
    for caminho in sorted((raiz / 'apps').rglob('*.html')):
        infratores.extend(
            _x_trap_sem_reatividade(str(caminho.relative_to(raiz)), caminho.read_text())
        )

    assert not infratores, (
        'x-trap ligado a valor não rastreável — o diretivo nunca reavalia e o '
        f'efeito inteiro é código morto: {infratores}'
    )


class TestMecanismoDoGuardaDeXTrap:
    """O guarda tem que provar que detecta, e não que a árvore está limpa hoje."""

    def test_expressao_com_refs_e_detectada(self):
        assert _x_trap_sem_reatividade(
            'sintetico.html', '<div x-trap.noscroll="$refs.dialog.open"></div>'
        )

    def test_dado_alpine_passa(self):
        assert not _x_trap_sem_reatividade(
            'sintetico.html', '<div x-trap.inert.noscroll="menuOpen"></div>'
        )

    def test_modificadores_nao_escondem_a_fuga(self):
        assert _x_trap_sem_reatividade(
            'sintetico.html', '<div x-trap="document.body.dataset.aberto"></div>'
        )

    def test_valor_sem_aspas_nao_escapa_do_guarda(self):
        assert _x_trap_sem_reatividade(
            'sintetico.html', '<div x-trap.noscroll=$refs.dialog.open></div>'
        )

    def test_exemplo_dentro_de_comment_nao_e_markup(self):
        assert not _x_trap_sem_reatividade(
            'sintetico.html',
            '{% comment %}<div x-trap="$refs.d.open"></div>{% endcomment %}',
        )


class TestAutocompleteEstadosECombobox:
    """components/autocomplete.html — contrato ARIA e estados da busca.

    Achados da Etapa 4 (`docs/plans/audit-frontend-restante.md`), todos
    reproduzidos no navegador antes da correção.
    """

    def _fonte(self) -> str:
        raiz = Path(__file__).resolve().parents[3]
        return (
            raiz / 'apps' / 'core' / 'templates' / 'components' / 'autocomplete.html'
        ).read_text()

    def _js(self) -> str:
        raiz = Path(__file__).resolve().parents[3]
        return (
            raiz / 'apps' / 'core' / 'static' / 'core' / 'js' / 'autocomplete.js'
        ).read_text()

    def test_activedescendant_so_aponta_com_o_popup_aberto(self):
        """Referência para opção invisível é referência quebrada.

        Depois de selecionar, o dropdown fecha mas `resultados` continua em
        memória. A seta para baixo apontava `aria-activedescendant` para uma
        <li> dentro de um <ul> em `display:none`.
        """
        assert 'aberto && ativo >= 0' in self._fonte()

    def test_seta_para_baixo_reabre_o_popup_fechado(self):
        js = self._js()
        assert '!this.aberto && this.resultados.length > 0' in js
        # Nas duas direções — a APG manda abrir em ambas.
        assert js.count('!this.aberto && this.resultados.length > 0') == 2

    def test_busca_expoe_estado_ocupado(self):
        assert ':aria-busy="buscando"' in self._fonte()

    def test_haspopup_redundante_saiu_do_combobox(self):
        """`aria-haspopup="listbox"` é o valor padrão de `role="combobox"` em
        ARIA 1.2 — emiti-lo é só ruído no HTML (#149)."""
        assert 'aria-haspopup' not in self._fonte()

    def test_borda_do_listbox_documenta_a_decisao_de_nao_escalar(self):
        """`ul[role="listbox"]` mantém `border-border` (1.23:1) em vez de subir
        para `border-control`: decisão consciente, presa no comentário adjacente
        para não ser "corrigida" no automático (#149).

        Verifica o comentário imediatamente antes da tag, não a fonte inteira:
        `border-border` não mudou e `1.4.11` aparece em outros comentários do
        arquivo, então asserção sobre o arquivo todo passaria sem a decisão.
        """
        fonte = self._fonte()
        ul = fonte.index('role="listbox"')
        comentario = fonte[fonte.rindex('{% comment %}', 0, ul) : ul]
        assert 'border-border' in comentario
        assert 'border-control' in comentario
        assert '1.4.11' in comentario
        assert 'decisão consciente' in comentario

    def test_contagem_de_resultados_e_anunciada(self):
        """Sem isto só o caso "nenhum resultado" falava.

        O spinner é `aria-hidden` e abrir o listbox não anuncia nada sozinho,
        então uma busca bem-sucedida era silenciosa no leitor de tela.
        """
        fonte = self._fonte()
        assert 'anuncioResultados()' in fonte
        assert 'role="status"' in fonte
        assert 'resultados disponíveis.' in self._js()

    def test_erro_de_busca_e_distinto_de_zero_resultados(self):
        """403/500/queda de rede caíam no texto de "nada encontrado", ou em nada.

        Um 403 devolve JSON sem a chave `resultados` — virava lista vazia e a
        tela dizia que a busca não achou nada. Um 500 devolve HTML e estourava
        no parse: o spinner sumia e o componente ficava mudo.
        """
        js = self._js()
        assert 'if (!res.ok) throw' in js
        assert 'this.erro = true' in js
        fonte = self._fonte()
        assert 'aberto && erro' in fonte
        assert 'data-erro-busca' in fonte

    def test_erro_nao_e_pintado_por_resposta_fora_de_ordem(self):
        """Uma busca velha que falha não pode sujar o estado da busca corrente."""
        js = self._js()
        trecho = js[js.index('} catch (e) {') :]
        trecho = trecho[: trecho.index('} finally {')]
        assert 'this._abortController !== controller' in trecho

    def test_mensagem_vazia_respeita_piso_zero(self):
        """Com `minChars: 0`, busca de campo vazio sem resultados abria uma
        caixa vazia: o piso virava 1 por causa de `Math.max(minChars, 1)`."""
        js = self._js()
        assert 'Math.max(this.minChars, 1)' not in js
        assert 'this.query.length >= this.minChars' in js

    def test_opcao_respeita_o_piso_de_toque(self):
        """A <li> tinha 36px. É o alvo que o almoxarifado toca em pé, no galpão."""
        fonte = self._fonte()
        trecho = fonte[fonte.index('role="option"') :]
        trecho = trecho[: trecho.index('</li>')]
        assert 'min-h-11' in trecho

    def test_opcao_ativa_nao_depende_so_do_fundo(self):
        """`bg-primary-subtle` sozinho dá 1.09:1 contra o branco — a WCAG
        1.4.11 pede 3:1 para identificar estado, e este é o único sinal de
        onde as setas do teclado estão."""
        fonte = self._fonte()
        assert 'ring-2 ring-inset ring-primary' in fonte

    def test_nenhuma_cor_abaixo_do_piso_dentro_de_option(self):
        """Piso de cor dentro de `role="option"`: text-text-secondary.

        `text-text-disabled` mede 2.63:1 no branco e 2.42:1 no fundo da opção
        ativa; `text-text-tertiary` passa em repouso (4.76:1) e cai para
        4.38:1 sobre a opção ativa. Os dois carregavam informação de decisão
        (saldo do material, setor do beneficiário).
        """
        raiz = Path(__file__).resolve().parents[3]
        proibidas = {'text-text-disabled', 'text-text-tertiary'}
        infratores = []
        for caminho in (raiz / 'apps').rglob('_autocomplete_item_*.html'):
            texto = caminho.read_text()
            # Pelos elementos, não pelo texto cru: o `{% comment %}` de cada
            # partial cita os tokens reprovados para explicar por que saíram.
            for _, atributos, numero in elementos(texto, 'span'):
                for cor in classes(atributos) & proibidas:
                    infratores.append(f'{caminho.relative_to(raiz)}:{numero}: {cor}')
        assert not infratores, (
            f'Cor abaixo do piso dentro de role="option": {infratores}'
        )

    # ── #151: estado "vinculado" vs "digitado e vinculado a nada" ──────────

    def test_vinculado_deriva_do_hidden_input_sem_estado_paralelo(self):
        """A fonte única de verdade é `hiddenInput.value`.

        `vinculado` é cache reativo (Alpine não observa escrita direta em nó do
        DOM), mas nunca recebe um literal: só o resultado de
        `!!this.$refs.hiddenInput?.value`, via `_sincronizarVinculo()`.
        """
        js = self._js()
        assert 'this.vinculado = !!this.$refs.hiddenInput?.value' in js
        assert '_sincronizarVinculo()' in js
        # Nunca ligado/desligado por literal — a única atribuição a `vinculado`
        # é a derivação acima.
        assert 'this.vinculado = true' not in js
        assert 'this.vinculado = false' not in js

    def test_marca_de_vinculado_e_a_borda_estao_no_template(self):
        fonte = self._fonte()
        assert "'campo--vinculado': vinculado" in fonte
        assert 'x-show="vinculado && !buscando"' in fonte
        assert 'text-success' in fonte
        # Espaço à direita para o ícone absoluto não ser encoberto por rótulo longo.
        assert "'pr-10': vinculado || buscando" in fonte

    def test_borda_de_vinculado_compilada_no_app_css(self):
        """O passo `make css-build` que o AGENTS.md não menciona.

        `.campo--vinculado` vive em input.css; sem recompilar, a classe fica
        inerte em produção com a suíte verde.
        """
        raiz = Path(__file__).resolve().parents[3]
        css = (raiz / 'apps/core/static/core/css/app.css').read_text()
        casamento = re.search(r'\.campo--vinculado\{([^}]*)\}', css)
        assert casamento, (
            '`.campo--vinculado` não está em app.css — rode `make css-build`'
        )
        assert 'border-color' in casamento.group(1)

    def test_marca_some_no_mesmo_gesto_que_zera_o_hidden(self):
        """`buscarComDebounce()` zera o hidden e ressincroniza `vinculado` na
        mesma chamada — o delta visual acontece na tecla, não no roundtrip."""
        js = self._js()
        trecho = js[js.index('buscarComDebounce()') :]
        trecho = trecho[: trecho.index('buscarTodos')]
        assert "this.$refs.hiddenInput.value = ''" in trecho
        assert '_sincronizarVinculo()' in trecho

    def test_mudanca_de_vinculo_passa_pela_regiao_live(self):
        """vinculado -> desvinculado é anunciado pela região `role="status"`
        que já existe, via `anuncioResultados()`."""
        js = self._js()
        assert (
            "this._anuncioVinculo = 'Seleção desfeita. Escolha um item da lista.'" in js
        )
        assert 'if (this._anuncioVinculo) return this._anuncioVinculo;' in js
        # Só na transição: `tinhaVinculo` é lido antes de zerar o hidden.
        assert 'const tinhaVinculo = !!this.$refs.hiddenInput?.value;' in js
        assert 'if (tinhaVinculo) {' in js
        fonte = self._fonte()
        assert 'role="status" aria-live="polite" x-text="anuncioResultados()"' in fonte

    def test_gate_de_submit_bloqueia_texto_sem_vinculo_no_cliente(self):
        js = self._js()
        # Listener de submit em captura (`true`), para correr antes do HTMX e
        # do guard de duplo-submit.
        listener = js[js.index("addEventListener(\n    'submit',") :]
        listener = listener[: listener.index('\n  );') + len('\n  );')]
        assert listener.endswith('true\n  );')
        assert 'event.preventDefault();' in js
        assert 'event.stopPropagation();' in js
        assert "combo.value.trim() !== '' && hidden.value.trim() === ''" in js
        assert 'input[x-ref="hiddenInput"]' in js
        assert 'sinalizarGate()' in js

    def test_gate_identifica_a_linha_culpada_no_formset(self):
        """Percorre todos os comboboxes visíveis e para no primeiro culpado,
        pondo o foco nele."""
        js = self._js()
        assert 'form.querySelectorAll(\'input[role="combobox"]\')' in js
        assert 'combo.offsetParent === null' in js
        assert 'this.$refs.displayInput?.focus();' in js

    def test_gate_nao_e_erro_de_campo_do_form(self):
        """A mensagem do gate carrega `data-erro-gate` (some na próxima tecla);
        a autoridade do erro persistente segue no `clean()` do servidor."""
        fonte = self._fonte()
        assert 'data-erro-gate' in fonte
        assert 'x-show="erroGateVisivel"' in fonte
        js = self._js()
        assert 'this.erroGateVisivel = false;' in js

    def test_mensagem_do_gate_e_associada_ao_combobox(self):
        """`aria-describedby` amarra a causa do bloqueio ao input enquanto o
        gate está ativo, preservando o id do erro de servidor
        (docs/design-system.md — "campo com erro usa aria-invalid +
        aria-describedby")."""
        fonte = self._fonte()
        assert ':id="idBase + \'-erro-gate\'"' in fonte
        # A ligação dinâmica adiciona o id do gate e mantém o erro de servidor.
        assert "erroGateVisivel ? idBase + '-erro-gate' : null" in fonte
        assert "{% if com_erro and erro_id %}'{{ erro_id }}', {% endif %}" in fonte
        # Fallback estático sem JS continua lá.
        assert 'aria-describedby="{{ erro_id }}"' in fonte


class TestFilterShellDisclosure:
    """components/filter_shell.html — o disclosure de mobile."""

    def _fonte(self) -> str:
        raiz = Path(__file__).resolve().parents[3]
        return (
            raiz / 'apps' / 'core' / 'templates' / 'components' / 'filter_shell.html'
        ).read_text()

    def test_disclosure_reabre_ao_cruzar_o_breakpoint(self):
        """Fechar os filtros no celular e chegar a >=640px escondia o
        formulário inteiro E o `<summary>` que o reabria (`sm:hidden`): 12
        campos inalcançáveis até recarregar a página.

        `sm:block!` não resolve — um `<details>` fechado esconde pelo slot do
        próprio elemento, não por `display` no filho.
        """
        fonte = self._fonte()
        assert 'matchMedia' in fonte
        assert '$el.open = true' in fonte

    def test_glifo_acompanha_o_estado(self):
        """Parado, apontava para baixo aberto e fechado."""
        assert 'group-open:rotate-180' in self._fonte()

    def test_open_do_html_nao_depende_de_tem_filtro_ativo(self):
        """O `<details>` server-rendered nasce SEMPRE fechado no mobile, com ou
        sem filtro ativo (issue #155): sem filtro é a entrada padrão e a que
        mais paga em espaço abaixo da dobra. Quem reabre no desktop é o
        `x-init`; o `<summary>` mantém o resumo do recorte com o painel fechado.
        """
        fonte = self._fonte()
        abertura = fonte[fonte.index('{% partialdef abertura %}') :]
        abertura = abertura[: abertura.index('{% endpartialdef %}')]
        tag = abertura[abertura.index('<details') :]
        tag = tag[: tag.index('\n>') + 2]
        assert ' open' not in tag
        assert 'tem_filtro_ativo' not in tag


# ---------------------------------------------------------------------------
# Gate #152: todo template que empurra URL nova via HTMX (`hx-push-url`) reemite
# o estado que vive FORA do alvo do swap como `hx-swap-oob`. A dessincronia da
# #143 foi ter sobrado superfície não coberta — convenção não quebra a suíte,
# gate quebra.
# ---------------------------------------------------------------------------

# `hx-push-url` no markup, ou `hx_push_url=` repassado a um componente
# passthrough. Comentários `{% comment %}` são removidos antes da varredura.
_EMITE_PUSH_URL = re.compile(r'hx-push-url|hx_push_url\s*=')
_REEMITE_OOB = 'hx-swap-oob'

# Templates que emitem push-url mas não carregam o reemite OOB — cada um com o
# motivo pelo qual a regra não se aplica a eles.
_ISENTOS_DO_REEMITE_OOB: dict[str, str] = {
    # button.html é passthrough puro (não conhece domínio): só emite
    # `hx-push-url` quando o chamador passa `hx_push_url=`. A superfície é quem
    # chama, e é lá que o reemite OOB tem que estar.
    'apps/core/templates/components/button.html': (
        'passthrough — quem inclui o botão é a superfície'
    ),
    # ordenacao_data.html é renderizado DENTRO de `{% partialdef resultados %}`,
    # ou seja, dentro do próprio alvo do swap: volta inteiro em toda resposta
    # HTMX. Não vive fora do alvo como o form e o chip, então reemitir a si
    # mesmo via OOB só duplicaria id.
    'apps/core/templates/components/ordenacao_data.html': (
        'vive dentro do alvo do swap — trocado inteiro, sem OOB'
    ),
    # filter_presets_periodo.html (issue #153) é renderizado DENTRO do partial
    # `campos` do filtro, que já volta inteiro via `oob_campos` em toda resposta
    # HTMX. Reemitir a si mesmo via OOB só duplicaria o bloco.
    'apps/core/templates/components/filter_presets_periodo.html': (
        'vive dentro do partial `campos` — reemitido inteiro via oob_campos'
    ),
}

_MINIMO_DE_SUPERFICIES_COM_PUSH_URL = 3


def _superficies_com_push_url(raiz: Path):
    """(caminho_relativo, reemite_oob) de cada apps/**/*.html que emite push-url."""
    for caminho in sorted((raiz / 'apps').rglob('*.html')):
        limpo = _sem_comentarios(caminho.read_text())
        if not _EMITE_PUSH_URL.search(limpo):
            continue
        yield str(caminho.relative_to(raiz)), _REEMITE_OOB in limpo


def test_todo_template_com_push_url_reemite_oob():
    """`components/filter_acoes.html` já dizia em prosa ("o painel não pode
    discordar da URL"), e três superfícies já reemitiam à mão. Vira gate: a
    próxima superfície com `hx-push-url` sem `hx-swap-oob` quebra a suíte.
    """
    raiz = Path(__file__).resolve().parents[3]
    superficies = list(_superficies_com_push_url(raiz))

    assert len(superficies) >= _MINIMO_DE_SUPERFICIES_COM_PUSH_URL, (
        f'A varredura achou só {len(superficies)} templates com push-url — o '
        'gate está passando por não enxergar, não por estar tudo certo'
    )

    infratores = [
        caminho
        for caminho, reemite in superficies
        if not reemite and caminho not in _ISENTOS_DO_REEMITE_OOB
    ]
    assert not infratores, (
        'Template empurra URL nova via HTMX sem reemitir o estado fora do alvo '
        f'do swap via hx-swap-oob (regressão #143): {infratores}'
    )


class TestMecanismoDoGateDePushUrl:
    """O gate precisa provar que detecta, não que hoje a árvore está limpa."""

    def _emite(self, texto: str) -> bool:
        return bool(_EMITE_PUSH_URL.search(_sem_comentarios(texto)))

    def _reemite(self, texto: str) -> bool:
        return _REEMITE_OOB in _sem_comentarios(texto)

    def test_push_url_sem_oob_e_detectado(self):
        texto = '<a hx-get="/x" hx-push-url="true">ir</a>'
        assert self._emite(texto) and not self._reemite(texto)

    def test_push_url_com_oob_passa(self):
        texto = (
            '<a hx-get="/x" hx-push-url="true">ir</a>'
            '<div id="fora" hx-swap-oob="true">estado</div>'
        )
        assert self._emite(texto) and self._reemite(texto)

    def test_push_url_dentro_de_comment_nao_conta(self):
        texto = '{% comment %}\n<a hx-push-url="true">exemplo</a>\n{% endcomment %}'
        assert not self._emite(texto)

    def test_hx_push_url_como_param_passthrough_e_detectado(self):
        texto = '{% include "components/button.html" with hx_push_url="true" %}'
        assert self._emite(texto)

    def test_toda_isencao_tem_motivo_escrito(self):
        assert all(_ISENTOS_DO_REEMITE_OOB.values())


# ---------------------------------------------------------------------------
# Gate #152 (call site): o reemite OOB de uma barra de filtros pertence ao
# template CHAMADOR, não a filter_shell.html. O gate acima vê cada arquivo
# isolado — filter_shell.html tem `hx-swap-oob` nos próprios partials e passa —,
# mas um novo chamador de `#abertura` que esqueça de reemitir os campos ficaria
# invisível. Esta varredura cobre o call site: toda tela que abre a barra
# reemite todos os slots que vivem fora do alvo do swap.
# ---------------------------------------------------------------------------

_ABERTURA_DA_BARRA = 'components/filter_shell.html#abertura'

# (token que o chamador precisa conter, descrição do slot). "campos" e "resumo"
# vivem em filter_shell.html, "Limpar" em filter_acoes.html — os três fora de
# `#{{ target_id }}`, logo os três precisam de reemite OOB no partial de
# resultados de cada tela.
_SLOTS_OOB_OBRIGATORIOS = (
    ('oob_campos', 'reemite dos campos do filtro (filter_shell#campos_abertura)'),
    ('oob_resumo', 'reemite do resumo em <summary> (filter_shell#resumo)'),
    ('filter_acoes.html#limpar', 'reemite do slot "Limpar" (filter_acoes#limpar)'),
)

# Slot condicional: só quem também renderiza os chips de recorte precisa
# reemiti-los (issue #153 — chip por papel genérico em components/).
_CHIP_FILTRO = 'components/filter_chips.html'

_MINIMO_DE_BARRAS_DE_FILTRO = 2


def _slots_oob_faltando(texto: str) -> list[str] | None:
    """Slots OOB não reemitidos por uma tela que abre a barra de filtros.

    Devolve `None` se o template não abre barra nenhuma; `[]` se abre e cobre
    todos os slots.
    """
    limpo = _sem_comentarios(texto)
    if _ABERTURA_DA_BARRA not in limpo:
        return None
    faltando = [desc for token, desc in _SLOTS_OOB_OBRIGATORIOS if token not in limpo]
    if _CHIP_FILTRO in limpo and 'oob_chips' not in limpo:
        faltando.append('reemite dos chips de recorte (filter_chips)')
    return faltando


def test_toda_barra_de_filtros_reemite_todos_os_slots_oob():
    """O call site, não filter_shell.html, é dono do reemite (regressão #143)."""
    raiz = Path(__file__).resolve().parents[3]
    barras = {
        str(caminho.relative_to(raiz)): faltando
        for caminho in sorted((raiz / 'apps').rglob('*.html'))
        if (faltando := _slots_oob_faltando(caminho.read_text())) is not None
    }

    assert len(barras) >= _MINIMO_DE_BARRAS_DE_FILTRO, (
        f'A varredura achou só {len(barras)} barras de filtro — o gate está '
        'passando por não enxergar, não por estar tudo certo'
    )

    infratores = {caminho: faltando for caminho, faltando in barras.items() if faltando}
    assert not infratores, (
        'Tela abre a barra de filtros sem reemitir via OOB todos os slots que '
        f'vivem fora do alvo do swap (regressão #143): {infratores}'
    )


class TestMecanismoDaBarraDeFiltros:
    """O gate de call site precisa provar que detecta chamador incompleto."""

    BARRA_COMPLETA = (
        '{% include "components/filter_shell.html#abertura" %}'
        '{% if is_htmx %}{% with oob_campos=True %}x{% endwith %}'
        '{% include "components/filter_shell.html#resumo" with oob_resumo=True %}'
        '{% include "components/filter_acoes.html#limpar" with oob=True %}{% endif %}'
    )

    def test_barra_completa_passa(self):
        assert _slots_oob_faltando(self.BARRA_COMPLETA) == []

    def test_arquivo_que_nao_abre_a_barra_e_ignorado(self):
        assert _slots_oob_faltando('<div>sem barra</div>') is None

    def test_sem_reemite_de_campos_e_detectado(self):
        assert _slots_oob_faltando(self.BARRA_COMPLETA.replace('oob_campos=True', ''))

    def test_sem_reemite_de_limpar_e_detectado(self):
        texto = self.BARRA_COMPLETA.replace(
            'filter_acoes.html#limpar', 'filter_acoes.html'
        )
        assert _slots_oob_faltando(texto)

    def test_reemite_dentro_de_comment_nao_conta(self):
        texto = (
            '{% include "components/filter_shell.html#abertura" %}'
            '{% comment %}oob_campos oob_resumo filter_acoes.html#limpar{% endcomment %}'
        )
        assert len(_slots_oob_faltando(texto)) == 3

    def test_chip_sem_reemite_e_detectado_so_quando_o_chip_e_renderizado(self):
        com_chip = (
            self.BARRA_COMPLETA
            + '{% include "components/filter_chips.html" with chips=chips_filtro %}'
        )
        assert _slots_oob_faltando(com_chip) == [
            'reemite dos chips de recorte (filter_chips)'
        ]
        assert _slots_oob_faltando(self.BARRA_COMPLETA) == []


def _checkboxes_por_label_com_piso(html: str) -> tuple[int, list[str]]:
    """Percorre `html` e devolve (nº de checkboxes, valores sem piso herdado).

    Um checkbox "com piso" é o que tem, entre seus ancestrais abertos, uma
    `<label>` cujo `class` declara `min-h-11`. `<input>` é elemento vazio e o
    template não o fecha, então a pilha é montada só com as tags de abertura e
    fechamento das demais — `HTMLParser` já entrega `handle_startendtag` à parte
    caso o template passe a usar `/>`.
    """

    class _Sonda(HTMLParser):
        def __init__(self):
            super().__init__()
            self.pilha: list[tuple[str, str]] = []
            self.total = 0
            self.sem_piso: list[str] = []

        def _visitar_input(self, attrs):
            atributos = dict(attrs)
            if atributos.get('type') != 'checkbox':
                return
            self.total += 1
            tem_piso = any(
                tag == 'label' and 'min-h-11' in (classe or '').split()
                for tag, classe in self.pilha
            )
            if not tem_piso:
                self.sem_piso.append(atributos.get('value', '<sem value>'))

        def handle_starttag(self, tag, attrs):
            if tag == 'input':
                self._visitar_input(attrs)
                return
            self.pilha.append((tag, dict(attrs).get('class', '')))

        def handle_startendtag(self, tag, attrs):
            if tag == 'input':
                self._visitar_input(attrs)

        def handle_endtag(self, tag):
            for indice in range(len(self.pilha) - 1, -1, -1):
                if self.pilha[indice][0] == tag:
                    del self.pilha[indice:]
                    return

    sonda = _Sonda()
    sonda.feed(html)
    return sonda.total, sonda.sem_piso


class TestFilterCheckboxGroupAgrupado:
    """components/filter_checkbox_group.html: suporte a grupos opcionais sem
    quebrar o uso plano (issue #154)."""

    ESTADOS = [
        ('rascunho', 'Rascunho'),
        ('aguardando_autorizacao', 'Aguardando autorização'),
        ('recusada', 'Recusada'),
        ('autorizada', 'Autorizada'),
        ('pronta_para_retirada', 'Pronta para retirada'),
        ('atendida', 'Atendida'),
        ('cancelada', 'Cancelada'),
        ('estornada', 'Estornada'),
    ]
    EM_ANDAMENTO = 'rascunho aguardando_autorizacao autorizada pronta_para_retirada'
    ENCERRADAS = 'recusada atendida cancelada estornada'

    def _grupos(self):
        from apps.core.templatetags.core_tags import agrupar_opcoes

        return agrupar_opcoes(
            self.ESTADOS,
            'Em andamento',
            self.EM_ANDAMENTO,
            'Encerradas',
            self.ENCERRADAS,
        )

    def _render_plano(self):
        return render_to_string(
            'components/filter_checkbox_group.html',
            {
                'legend': 'Tipo',
                'name': 'tipos',
                'opcoes': [('entrada', 'Entrada'), ('saida', 'Saída')],
                'selecionados': ['saida'],
            },
        )

    def _render_agrupado(self):
        return render_to_string(
            'components/filter_checkbox_group.html',
            {
                'legend': 'Estado',
                'name': 'estados',
                'grupos': self._grupos(),
                'selecionados': ['autorizada'],
            },
        )

    def test_uso_plano_gera_um_unico_fieldset(self):
        html = self._render_plano()
        assert html.count('<fieldset') == 1
        assert html.count('<legend') == 1
        assert 'value="entrada"' in html
        assert 'value="saida"' in html
        assert html.count('name="tipos"') == 2

    def test_uso_plano_preserva_alvo_de_toque(self):
        html = self._render_plano()
        assert html.count('min-h-11') == 2

    def test_uso_plano_respeita_selecao(self):
        html = self._render_plano()
        marcado = html[
            html.index('value="saida"') : html.index('>', html.index('value="saida"'))
            + 1
        ]
        assert 'checked' in marcado

    def test_uso_agrupado_gera_dois_fieldsets_aninhados(self):
        html = self._render_agrupado()
        # 1 externo ("Estado") + 2 internos ("Em andamento" / "Encerradas").
        assert html.count('<fieldset') == 3
        assert html.count('<legend') == 3
        assert '>Estado<' in html
        assert '>Em andamento<' in html
        assert '>Encerradas<' in html

    def test_uso_agrupado_mantem_as_8_caixas_e_os_8_valores(self):
        html = self._render_agrupado()
        for valor, _ in self.ESTADOS:
            assert f'value="{valor}"' in html
        assert html.count('type="checkbox"') == 8
        assert html.count('name="estados"') == 8

    def test_uso_agrupado_preserva_alvo_de_toque(self):
        assert self._render_agrupado().count('min-h-11') == 8

    @pytest.mark.parametrize('modo', ['plano', 'agrupado'])
    def test_todo_checkbox_esta_dentro_da_label_que_carrega_o_piso(self, modo):
        """O `min-h-11` fica na label que *embrulha* o input, não solto na tela.

        Os dois testes acima contam ocorrências de `min-h-11`, e contagem não
        prova aninhamento: um piso declarado num irmão da label passaria por
        eles com o alvo real ainda em 20px. A auditoria da Etapa 5 levantou
        exatamente essa dúvida — "o padrão documentado é `size-5` dentro de uma
        label de 44px, e a label cumpre o piso, mas o alvo do `input` em si não;
        vale confirmar se a label realmente embrulha a área toda" (issue #160).

        Confirmado por medição no navegador, com o `app.css` compilado: a label
        renderiza 44px de altura e 80 a 184px de largura conforme o rótulo, o
        input renderiza 20×20px, e as oito sondas por label (quatro cantos,
        acima e abaixo do input, o vão do `gap-2` e o centro) resolvem todas
        para a label — em 15 labels, 120 sondas, zero fora. Clique sintético em
        cada uma das 120 alterna o checkbox. O piso não estava só no papel: a
        caixa de 44px inteira é área clicável, porque `elementFromPoint` dentro
        dela devolve a própria label e a label ativa o controle que embrulha.

        O que este guarda trava é o aninhamento, que é o que a medição depende:
        se alguém tirar o input de dentro da label (`for=`/`id=` em vez de
        embrulhar), a contagem de `min-h-11` continua igual e o alvo cai para
        20px sem ruído.
        """
        html = self._render_plano() if modo == 'plano' else self._render_agrupado()
        checkboxes, sem_piso = _checkboxes_por_label_com_piso(html)
        assert checkboxes > 0
        assert sem_piso == []

    def test_agrupar_opcoes_particiona_preservando_rotulos(self):
        grupos = self._grupos()
        assert [legenda for legenda, _ in grupos] == ['Em andamento', 'Encerradas']
        assert grupos[0][1] == [
            ('rascunho', 'Rascunho'),
            ('aguardando_autorizacao', 'Aguardando autorização'),
            ('autorizada', 'Autorizada'),
            ('pronta_para_retirada', 'Pronta para retirada'),
        ]
        assert [v for v, _ in grupos[1][1]] == self.ENCERRADAS.split()

    def test_agrupar_opcoes_erra_alto_quando_falta_valor(self):
        from django.core.exceptions import ImproperlyConfigured

        from apps.core.templatetags.core_tags import agrupar_opcoes

        with pytest.raises(ImproperlyConfigured):
            agrupar_opcoes(self.ESTADOS, 'Parcial', self.EM_ANDAMENTO)

    def test_agrupar_opcoes_erra_alto_com_valor_desconhecido(self):
        from django.core.exceptions import ImproperlyConfigured

        from apps.core.templatetags.core_tags import agrupar_opcoes

        with pytest.raises(ImproperlyConfigured):
            agrupar_opcoes(
                self.ESTADOS,
                'Em andamento',
                self.EM_ANDAMENTO + ' inexistente',
                'Encerradas',
                self.ENCERRADAS,
            )

    def test_agrupar_opcoes_erra_alto_com_especificacao_impar(self):
        from django.core.exceptions import ImproperlyConfigured

        from apps.core.templatetags.core_tags import agrupar_opcoes

        with pytest.raises(ImproperlyConfigured):
            agrupar_opcoes(self.ESTADOS, 'Em andamento')

    def test_grupos_do_historico_batem_com_estadorequisicao(self):
        """A partição escrita no template cobre exatamente os 8 estados
        canônicos — muda `EstadoRequisicao`, o `agrupar_opcoes` erra alto."""
        from apps.requisicoes.models import EstadoRequisicao
        from apps.core.templatetags.core_tags import agrupar_opcoes

        grupos = agrupar_opcoes(
            EstadoRequisicao.choices,
            'Em andamento',
            self.EM_ANDAMENTO,
            'Encerradas',
            self.ENCERRADAS,
        )
        assert [len(pares) for _, pares in grupos] == [4, 4]


def test_nenhum_badge_de_dado_estatico_declara_live_region():
    """`badge.html` escreveu a proibição e dois partials de domínio a violavam.

    O contrato do componente é explícito: "NÃO usar `status`/`alert` em badge
    de dado estático: são live regions, e uma listagem de 20 linhas viraria 20
    live regions." `_badge_tipo_movimentacao.html` e `_estado_saida_badge.html`
    passavam `role="status"` em toda variante mapeada — no ledger, 25 live
    regions por página, todas dentro de cartões, para dado que nunca muda em
    resposta a ação nenhuma.

    O contexto que o `role` carregava vive em `prefixo_sr`, que é texto
    `sr-only` e portanto sempre exposto.
    """
    raiz = Path(__file__).resolve().parents[3]
    infratores = []
    for template in (raiz / 'apps').rglob('*.html'):
        for encontro in _INCLUDE_DE_BADGE.finditer(template.read_text()):
            trecho = encontro.group(0)
            if 'role=' in trecho:
                infratores.append(f'{template.relative_to(raiz)}: {trecho.strip()}')

    assert not infratores, (
        f'badge de dado estático não declara live region; use prefixo_sr: {infratores}'
    )


def test_link_de_cartao_tem_o_cartao_como_alvo():
    """A isenção de `data-cartao-link` no piso de 44px tem que ser verdade.

    O link do título é uma âncora de texto: sozinho, ele é menor que 44px. O que
    o torna aceitável é o alvo efetivo ser o `<article>` inteiro — e isso depende
    de duas peças que este guarda amarra:

    - `card_abertura` reage à presença do link (`has-[a[data-cartao-link]]`), o
      que dá cursor, hover e anel de foco ao cartão;
    - `core/js/cartao-alvo.js` encaminha o clique do cartão para o link.

    Sem qualquer uma das duas, a isenção vira rota de fuga do piso e o cartão
    volta a ter como alvo real uma âncora de 7 caracteres.
    """
    raiz = Path(__file__).resolve().parents[3]

    chrome = (raiz / 'apps/core/templates/components/table.html').read_text()
    assert 'has-[a[data-cartao-link]]:cursor-pointer' in chrome
    assert 'hover:has-[a[data-cartao-link]]:bg-bg-page' in chrome
    assert 'has-[a[data-cartao-link]:focus-visible]:ring-2' in chrome

    js = (raiz / 'apps/core/static/core/js/cartao-alvo.js').read_text()
    assert 'a[data-cartao-link]' in js
    # As duas guardas que fazem o alargamento não atropelar o usuário.
    assert 'getSelection' in js
    assert 'closest(JA_INTERATIVO)' in js

    base = (raiz / 'apps/core/templates/base.html').read_text()
    assert 'core/js/cartao-alvo.js' in base

    # O CSS compilado precisa ter os seletores: `has-[]` com colchetes aninhados
    # é a construção mais frágil da varredura do Tailwind, e sem o `make
    # css-build` o cartão fica sem cursor e sem anel de foco em silêncio.
    css = (raiz / 'apps/core/static/core/css/app.css').read_text()
    assert 'has(:is(a[data-cartao-link]))' in css
    assert 'has(:is(a[data-cartao-link]:focus-visible))' in css

    # E a marcação só existe em tela que usa o chrome de cartão. O
    # `(?![-\w\]:])` separa o atributo exato das ocorrências dentro dos seletores
    # `has-[...]` do próprio chrome e de nomes parecidos (`data-cartao-link-x`),
    # que casariam o nome sem serem a marcação.
    import re

    atributo_marcador = re.compile(r'data-cartao-link(?![-\w\]:])')
    chrome_relativo = 'apps/core/templates/components/table.html'

    telas_marcadas = []
    for caminho in sorted((raiz / 'apps').rglob('*.html')):
        relativo = str(caminho.relative_to(raiz))
        if relativo == chrome_relativo:
            continue
        # `_sem_comentarios` ANTES de contar, e não só depois: um
        # `{% comment %}` que explica por que a tela NÃO usa o marcador
        # contém o nome do atributo e fazia o guarda acusar prosa como
        # marcação. O mesmo texto limpo alimenta as duas checagens abaixo.
        conteudo = _sem_comentarios(caminho.read_text())
        ocorrencias = len(atributo_marcador.findall(conteudo))
        if not ocorrencias:
            continue
        telas_marcadas.append(relativo)
        assert 'components/table.html#card_abertura' in conteudo, (
            f'{relativo} marca data-cartao-link sem usar o chrome de cartão'
        )
        # Presença do include não basta: cada âncora marcada tem que morar
        # dentro de uma faixa `#card_abertura` … `</article>`, senão o alvo real
        # volta a ser a âncora de texto e a isenção do piso de 44px fica sem
        # lastro (mesma faixa que `_clicaveis_sem_piso` usa).
        limpo = conteudo
        faixas = _faixas_de_cartao(limpo)
        for _, atributos, numero in elementos(limpo, 'a'):
            if not _tem_atributo(atributos, 'data-cartao-link'):
                continue
            assert any(numero in faixa for faixa in faixas), (
                f'{relativo}:{numero} data-cartao-link fora de um cartão'
            )

    # As oito listagens navegáveis. O histórico de importações entrou na #161,
    # quando a importação ganhou detalhe: até ali a única ação do cartão era um
    # download, que não é navegação. O botão de download continua explícito ao
    # lado — é o alvo do cartão que passou a ser o detalhe.
    #
    # O LEDGER entrou na Etapa 8. A justificativa anterior — "não tem detalhe
    # para onde ir" — não se sustentava: `Origem: REQ-2026-000005` já É a
    # identidade do documento que causou o lançamento, e imprimi-la como texto
    # obrigava a guardar o número e digitá-lo em outra tela. O alvo do cartão é
    # esse documento; quando é uma saída excepcional e o ator não tem a policy
    # do destino, o cartão fica inerte em vez de levar a um 403.
    #
    # O CATÁLOGO continua fora, e por um motivo estrutural, não por falta de
    # destino: o `<article>` de lá é literal, porque a borda depende de estado
    # de domínio (divergência crítica) e `#card_abertura` é string fixa por
    # contrato da #83. Sem o chrome não há alvo de cartão a herdar, então ele
    # ganhou um link explícito com piso de 44px para o ledger filtrado.
    #
    # AS NOTIFICAÇÕES entraram junto. Era a única das oito listagens fora do
    # sistema de cartões — `<ul class="divide-y">` de linhas — e com a
    # afordância invertida: o link para a requisição vinha em 12px cinza sem
    # sublinhado, idêntico ao carimbo de data logo abaixo, enquanto treze
    # `Marcar como lida` idênticos ocupavam a borda direita. O descarte parecia
    # o link e o link parecia metadado.
    assert len(telas_marcadas) == 8, telas_marcadas


def test_isencao_de_cartao_so_vale_para_o_atributo_exato():
    """`data-cartao-link-extra` e `aria-describedby="data-cartao-link"` não são a
    marcação — o seletor do chrome exige `a[data-cartao-link]`. A isenção do
    piso de 44px não pode alcançá-los por casamento de substring.
    """
    markup = (
        '{% include "components/table.html#card_abertura" %}\n'
        '  <a href="/x" data-cartao-link class="rounded-sm">REQ-1</a>\n'
        '</article>\n'
        '<a href="/y" data-cartao-link-extra class="rounded-sm">solto</a>\n'
        '<a href="/z" aria-describedby="data-cartao-link" class="rounded-sm">outro</a>\n'
    )
    infratores, _ = _clicaveis_sem_piso('t.html', markup, frozenset(), {})
    # a âncora real dentro do cartão é isentada; as duas parecidas, não
    assert infratores == [
        't.html:4 clicável sem piso de 44px',
        't.html:5 clicável sem piso de 44px',
    ]


def test_include_de_badge_detecta_role_depois_de_percent_no_argumento():
    """`prefixo_sr="50%"` não pode cegar a guarda de live region: o `%` no valor
    de um argumento antes de `role=` fazia o padrão antigo (`[^%]*`) não casar o
    include inteiro.
    """
    trecho = (
        '{% include \'components/badge.html\' with label="x" '
        'prefixo_sr="50% cheio" role="status" %}'
    )
    encontro = _INCLUDE_DE_BADGE.search(trecho)
    assert encontro is not None
    assert 'role=' in encontro.group(0)


def _corpo_do_chrome(nome: str) -> str:
    """Corpo de um `{% partialdef %}` de components/table.html, sem espaço em volta."""
    raiz = Path(__file__).resolve().parents[3]
    chrome = (raiz / 'apps/core/templates/components/table.html').read_text()
    abertura = '{% partialdef ' + nome + ' %}'
    inicio = chrome.index(abertura) + len(abertura)
    return chrome[inicio : chrome.index('{% endpartialdef %}', inicio)].strip()


def test_cards_abertura_denso_e_estrutura_pura_e_de_uso_restrito():
    """`#cards_abertura_denso` (issue #159) é fragmento irmão de estrutura pura.

    A variante densa antecipa a 3ª coluna para `xl` (1280px) numa listagem
    comprovadamente densa. Este guarda amarra o que a decisão prometeu:

    - o fragmento existe e diverge do `#cards_abertura` só no breakpoint da 3ª
      coluna (`xl` em vez de `2xl`) — nada mais;
    - continua string de classe fixa: nenhuma variável de template no corpo,
      senão vira o parâmetro que a Regra do Chrome Sem Parâmetro proíbe;
    - o CSS compilado tem a variante `xl:grid-cols-3` (sem `make css-build` a
      3ª coluna some em silêncio);
    - só uma listagem o usa. Uma segunda entra no mesmo fragmento pelo critério
      de DESIGN.md; um terceiro fragmento, não.
    """
    raiz = Path(__file__).resolve().parents[3]

    denso = _corpo_do_chrome('cards_abertura_denso')
    normal = _corpo_do_chrome('cards_abertura')

    assert denso == '<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">'
    assert normal.replace('2xl:grid-cols-3', 'xl:grid-cols-3') == denso
    assert '{{' not in denso and '{%' not in denso

    css = (raiz / 'apps/core/static/core/css/app.css').read_text()
    assert 'xl\\:grid-cols-3' in css or '.xl\\:grid-cols-3' in css

    usos = [
        str(p.relative_to(raiz))
        for p in sorted((raiz / 'apps').rglob('*.html'))
        if '#cards_abertura_denso' in p.read_text()
    ]
    assert usos == ['apps/estoque/templates/estoque/lista_materiais.html'], usos


def test_grade_de_cartoes_alinha_a_base_em_vez_do_topo():
    """Item 4 da issue #160: os fragmentos de grade não carregam `items-start`.

    Com `items-start`, cartões de alturas diferentes na mesma linha não alinham
    embaixo — 256 a 276px de variação medidos no histórico a 375px, porque a
    subline do material só aparece quando a requisição tem um item só. Um degrau
    de 20px entre dois cartões vizinhos não é lido como "este tem menos
    conteúdo", é lido como desalinho. Sem a classe, a grade volta ao `stretch`
    padrão: mesma altura por linha, base alinhada, e a folga sobrando no rodapé
    do cartão mais curto — o conteúdo não se redistribui porque o `<article>`
    não é flex column.

    O guarda existe para a decisão não voltar em silêncio, e vale só para os
    dois containers de grade: `items-start` dentro dos cartões (containers
    `flex`) é outra coisa e continua correto.
    """
    grades = {nome: _corpo_do_chrome(nome) for nome in _FRAGMENTOS_DE_GRADE}

    for nome, corpo in grades.items():
        assert corpo.startswith('<div class="grid '), f'{nome} deixou de ser grade'
        assert 'items-start' not in corpo, (
            f'{nome} voltou a alinhar pelo topo; a base rasgada foi decidida '
            'contra na issue #160'
        )

    denso, normal = grades['cards_abertura_denso'], grades['cards_abertura']
    assert normal == '<div class="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">'
    assert normal.replace('2xl:grid-cols-3', 'xl:grid-cols-3') == denso


# ---------------------------------------------------------------------------
# components/quantidade.html (Etapa 8, backlog da critique)
# ---------------------------------------------------------------------------


class TestComponenteQuantidade:
    """A quantidade é o dado que este produto existe para controlar.

    Antes deste componente ela recebia tratamento tipográfico em um lugar só —
    o modal de retirada — e em todo o resto era corpo de 14px igual ao rótulo
    ao lado, com a unidade ora colada, ora numa linha própria, ora ausente.
    """

    def _render(self, **contexto):
        from decimal import Decimal

        from django.template.loader import render_to_string

        base = {'valor': Decimal('820.000'), 'unidade': 'un'}
        base.update(contexto)
        return render_to_string('components/quantidade.html', base)

    def test_numero_e_unidade_saem_juntos(self):
        html = self._render()
        assert '820' in html
        assert 'un' in html

    def test_precisao_vem_da_unidade(self):
        from decimal import Decimal

        assert '820,0' in self._render(valor=Decimal('820.000'), unidade='m')
        assert '820,0' not in self._render(valor=Decimal('820.000'), unidade='un')

    def test_separador_e_virgula(self):
        from decimal import Decimal

        html = self._render(valor=Decimal('1250.500'), unidade='m')
        assert '1250,5' in html
        assert '1250.5' not in html

    def test_numero_forma_coluna(self):
        """`tabular-nums` alinha dígito com dígito, não parágrafo com parágrafo.

        O slot do número é alinhado à direita e não quebra; é isso que faz três
        linhas de rótulos com larguras diferentes terminarem os números no mesmo
        x, que era o defeito medido no catálogo (x=330, x=361, x=360).
        """
        html = self._render()
        assert 'tabular-nums' in html
        assert 'text-right' in html
        assert 'whitespace-nowrap' in html

    def test_unidade_tem_piso_de_largura_para_comecar_no_mesmo_x(self):
        assert 'min-w-8' in self._render()

    def test_valor_ausente_vira_travessao(self):
        assert '—' in self._render(valor=None)

    def test_tom_pinta_apenas_o_numero(self):
        assert 'text-warning-text' in self._render(tom='warning')
        assert 'text-danger-text' in self._render(tom='danger')
        assert 'text-text-primary' in self._render()

    def test_referencia_sai_abaixo_em_menor(self):
        html = self._render(referencia='de 150 autorizada')
        assert 'de 150 autorizada' in html
        assert 'text-xs' in html

    def test_nao_e_traduzido_automaticamente(self):
        """Número com unidade traduzido automaticamente vira outro número."""
        assert 'translate="no"' in self._render()

    def test_destaque_reservado_ao_momento_de_confirmacao(self):
        assert 'text-base' in self._render(destaque=True)
        assert 'text-base' not in self._render()


def test_cabecalho_de_cartao_nao_vira_linha_antes_de_xl():
    """A âncora de varredura tem posição fixa dentro do cartão.

    O `flex-wrap` da Etapa 8 consertou o número público partido em duas linhas a
    375px e comprou outro defeito: `Cancelada` cabia na linha do título e
    `Aguardando autorização` — o carimbo mais largo do produto, 192px — descia
    para baixo da data. O carimbo ocupava a linha 1 em uns cartões e a linha 3
    em outros, e uma âncora que muda de lugar entre vizinhos é pior que uma
    âncora deslocada.

    O ponto de virada é `xl` por medição, não por gosto: 192 (carimbo) + 12
    (gap) + 132 (número) + 32 (padding) = 368px de cartão, que em grade de 2
    colunas só existe a partir de ~1036px de viewport. `sm` põe a mesma
    instabilidade um breakpoint adiante.
    """
    raiz = Path(__file__).resolve().parents[3]
    cabecalho = re.compile(r'class="flex[^"]*items-start[^"]*justify-between[^"]*"')
    # O cartão do ledger é a exceção, e por estrutura: ali o carimbo de tipo é o
    # PRIMEIRO elemento do cabeçalho — quem fica na ponta direita é a data, e o
    # material é um `<h2>` abaixo dos dois. A âncora de varredura já nasce no
    # canto superior esquerdo e não se desloca, então empilhar só faria o cartão
    # crescer. A regra protege a posição do carimbo, não a classe.
    isento = 'apps/estoque/templates/estoque/historico_movimentacoes.html'
    infratores = []
    for caminho in sorted((raiz / 'apps').rglob('*.html')):
        if str(caminho.relative_to(raiz)) == isento:
            continue
        conteudo = _sem_comentarios(caminho.read_text())
        if 'components/table.html#card_abertura' not in conteudo:
            continue
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            achado = cabecalho.search(linha)
            if not achado:
                continue
            classes = achado.group(0)
            if 'xl:flex-row' in classes and 'flex-col' in classes:
                continue
            infratores.append(f'{caminho.relative_to(raiz)}:{numero}')
    assert infratores == [], (
        'cabeçalho de cartão em linha antes de `xl` — o carimbo de estado muda '
        f'de posição entre cartões vizinhos. Ver DESIGN.md: {infratores}'
    )
