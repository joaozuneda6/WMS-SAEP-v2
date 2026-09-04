"""Testes diretos de components/badge.html (sem DB, sem view)."""

import pathlib
import re
import xml.etree.ElementTree as ET
from collections import Counter

import pytest
from django.template.loader import render_to_string

BASE_DIR = pathlib.Path(__file__).resolve().parents[3]
BADGE_TEMPLATE = BASE_DIR / 'apps' / 'core' / 'templates' / 'components' / 'badge.html'

VARIANTE_DESCONHECIDA = 'estado-que-nao-existe'

# Desde a #177, badge.html não tem mais nenhuma classe de paleta crua — as
# quatro variantes de catálogo (orange/indigo/violet/yellow) migraram para
# família de token semântico (cancel/consumption/reversal) ou foram
# substituídas por reuso direto de `amber`. Allowlist vazia no mesmo rigor de
# apps/core/tests/test_tokens_semanticos.py — qualquer cor crua nova quebra o
# teste.
CLASSES_DE_CATALOGO_PERMITIDAS = {}

CLASSE_DE_PALETA_RE = re.compile(r'(?:bg|text|border|ring|divide)-[a-z]+-\d+')

# Só a cadeia de variantes abre ramo. As condicionais internas de `role`,
# `aria_label`, `prefixo_sr` e `label` são `{% if %}` também, então contar tag
# genérica daria muito mais que 14 — e o primeiro `</span>` fecha um filho
# `sr-only`, não a raiz. Por isso a fatia é pelos marcadores da cadeia.
MARCADOR_DE_RAMO_RE = re.compile(r'\{%\s*(?:if|elif)\s+variant\s*==|\{%\s*else\s*%\}')

# O cabeçalho {% comment %} documenta o ramo `{% else %}` citando a tag por
# extenso. Prosa não é ramo: o bloco sai do texto antes da fatia, senão a
# documentação do componente derruba o teste que vigia o componente.
BLOCO_DE_COMENTARIO_RE = re.compile(
    r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', re.S
)

TOTAL_DE_RAMOS = 14

VARIANTES_CONHECIDAS = [
    'slate',
    'blue',
    'blue-strong',
    'amber',
    'amber-strong',
    'green',
    'red',
    'red-strong',
    'cancel',
    'teal',
    'teal-strong',
    'consumption',
    'reversal',
]


def _render(**ctx):
    ctx.setdefault('variant', 'slate')
    ctx.setdefault('label', 'Rótulo')
    return render_to_string('components/badge.html', ctx)


def _arvore(**ctx):
    """Renderiza e devolve o <span> raiz como árvore.

    O componente é um único elemento bem-formado, então `ElementTree` basta e
    não traz dependência nova. Asserção por árvore, e não por substring, é o
    que distingue "o texto está no HTML" de "o texto está no lugar certo, no
    elemento certo, na ordem certa" — a diferença que este arquivo precisa
    provar depois que o ramo de fallback passou a carregar `sr-only`.
    """
    return ET.fromstring(_render(**ctx).strip())


def _classes(elemento):
    return set((elemento.get('class') or '').split())


def _e_sr_only(elemento):
    return 'sr-only' in _classes(elemento)


def _tokens(raiz):
    """Pedaços de texto do badge em ordem de documento, marcados por visibilidade.

    Devolve `[(visivel, texto), ...]`. Serve para afirmar **ordem** entre o
    sinal visível e o texto só-leitor-de-tela sem depender de o sinal estar
    solto na raiz ou dentro de um `<span>` interno.
    """
    tokens = [(True, raiz.text or '')]
    for filho in raiz:
        tokens.append((not _e_sr_only(filho), ''.join(filho.itertext())))
        tokens.append((True, filho.tail or ''))
    return tokens


def _texto_visivel(raiz):
    """Texto que sobra na tela depois de descontar todo `sr-only`."""
    return ''.join(texto for visivel, texto in _tokens(raiz) if visivel)


@pytest.mark.parametrize(
    'variant,classes_esperadas',
    [
        ('slate', ['bg-bg-subtle', 'text-text-primary', 'ring-border']),
        (
            'blue',
            ['bg-primary-muted', 'text-primary-text-strong', 'ring-primary-border'],
        ),
        (
            'blue-strong',
            [
                'bg-primary-muted-strong',
                'text-primary-text-strong',
                'ring-primary-border-strong',
            ],
        ),
        (
            'amber',
            ['bg-warning-muted', 'text-warning-text-strong', 'ring-warning-border'],
        ),
        (
            'amber-strong',
            [
                'bg-warning-muted-strong',
                'text-warning-text-strong',
                'ring-warning-border-strong',
            ],
        ),
        (
            'green',
            ['bg-success-muted', 'text-success-text-strong', 'ring-success-border'],
        ),
        ('red', ['bg-danger-muted', 'text-danger-text-strong', 'ring-danger-border']),
        (
            'red-strong',
            [
                'bg-danger-muted-strong',
                'text-danger-text-strong',
                'ring-danger-border-strong',
            ],
        ),
        ('teal', ['bg-return-muted', 'text-return-text-strong', 'ring-return-border']),
        (
            'teal-strong',
            [
                'bg-return-muted-strong',
                'text-return-text-strong',
                'ring-return-border-strong',
            ],
        ),
        # Famílias de token dedicadas (issue #177) — cancel/consumption/reversal.
        (
            'cancel',
            ['bg-cancel-muted', 'text-cancel-text-strong', 'ring-cancel-border'],
        ),
        (
            'consumption',
            [
                'bg-consumption-muted',
                'text-consumption-text-strong',
                'ring-consumption-border',
            ],
        ),
        (
            'reversal',
            [
                'bg-reversal-muted',
                'text-reversal-text-strong',
                'ring-reversal-border',
            ],
        ),
    ],
)
def test_variant_produz_classes_de_cor_esperadas(variant, classes_esperadas):
    html = _render(variant=variant)
    for classe in classes_esperadas:
        assert classe in html


def test_label_e_renderizado():
    html = _render(label='Autorizada')
    assert 'Autorizada' in html


def test_variant_desconhecida_cai_no_fallback_indisponivel():
    html = _render(variant='estado-que-nao-existe')
    assert 'bg-danger' in html
    assert 'ring-danger-hover' in html
    assert 'Indisponível' in html


def test_role_e_propagado_literalmente():
    html = _render(variant='blue', role='status')
    assert 'role="status"' in html


def test_role_ausente_por_padrao():
    html = _render()
    assert 'role=' not in html


def test_aria_label_e_propagado_literalmente():
    html = _render(variant='red', aria_label='Estado: Recusada')
    assert 'aria-label="Estado: Recusada"' in html


def test_aria_label_ausente_por_padrao():
    html = _render()
    assert 'aria-label=' not in html


def test_todas_as_variantes_de_marca_mantem_rounded_full_pill():
    for variant in ['slate', 'blue', 'amber', 'green', 'red', 'teal']:
        html = _render(variant=variant)
        assert 'rounded-full' in html


# ─── Ramo de fallback: preserva o que hoje descarta (issue #121) ──────────


def test_fallback_emite_prefixo_sr_dentro_de_sr_only():
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA, prefixo_sr='Estado: ')
    primeiro = list(raiz)[0]
    assert _e_sr_only(primeiro), (
        'o prefixo do leitor de tela precisa ser o primeiro filho do badge'
    )
    assert primeiro.text == 'Estado: '


def test_fallback_mantem_indisponivel_como_texto_visivel():
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA, label='Aguardando autorização')
    assert 'Indisponível' in _texto_visivel(raiz)


def test_fallback_preserva_label_em_sr_only_depois_do_sinal():
    tokens = _tokens(
        _arvore(variant=VARIANTE_DESCONHECIDA, label='Aguardando autorização')
    )

    posicao_sinal = [
        i
        for i, (visivel, texto) in enumerate(tokens)
        if visivel and 'Indisponível' in texto
    ]
    posicao_label = [
        i
        for i, (visivel, texto) in enumerate(tokens)
        if not visivel and '(Aguardando autorização)' in texto
    ]

    assert posicao_sinal, 'o sinal "Indisponível" sumiu do texto visível'
    assert posicao_label, (
        'o label recebido não foi preservado em sr-only entre parênteses'
    )
    assert min(posicao_label) > max(posicao_sinal), (
        'o label precisa vir depois do sinal, não no lugar dele'
    )


def test_fallback_forca_role_alert_ignorando_role_do_chamador():
    """Falha alta é role="alert" (Decisão A-1, issue #122) — o fallback não
    pode ser rebaixado a "status" por um chamador que não sabia que ia
    gritar (ex. _badge_tipo_movimentacao.html passa role="status" nos ramos
    conhecidos).
    """
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA, role='status')
    assert raiz.get('role') == 'alert'


def test_fallback_ignora_aria_label_do_chamador():
    """`aria_label` do fallback do badge.html propagado literalmente
    substituiria o nome acessível "Indisponível (rótulo)" pelo texto que o
    chamador escreveu para o ramo conhecido — calando o grito para quem usa
    leitor de tela.
    """
    raiz = _arvore(
        variant=VARIANTE_DESCONHECIDA,
        aria_label='Estado: Recusada',
        label='Recusada',
    )
    assert raiz.get('aria-label') is None
    assert 'Recusada' in ''.join(raiz.itertext())


def test_fallback_expoe_variant_crua_para_depuracao():
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA)
    assert raiz.get('data-badge-variant') == VARIANTE_DESCONHECIDA


def test_fallback_sem_label_nao_emite_parenteses_vazios():
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA, label='')
    assert '()' not in ''.join(raiz.itertext())


def test_fallback_sem_prefixo_sr_tem_um_unico_sr_only_o_do_label():
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA, label='Autorizada')
    sr_only = [filho for filho in raiz if _e_sr_only(filho)]
    assert len(sr_only) == 1
    assert 'Autorizada' in ''.join(sr_only[0].itertext())


# ─── Hardening: entradas extremas (issue #122, /impeccable harden) ────────


def test_variant_vazia_cai_no_fallback_de_grito():
    """`variant` é obrigatório e sem default — string vazia não casa com
    nenhum ramo nomeado e precisa gritar como qualquer outra variante
    desconhecida, não renderizar um pill quebrado.
    """
    html = _render(variant='')
    assert 'Indisponível' in html
    assert 'role="alert"' in html


def test_label_extremamente_longo_nao_e_truncado():
    label_longo = 'Aguardando autorização ' * 20  # 480+ caracteres
    raiz = _arvore(variant='blue', label=label_longo)
    assert label_longo in _texto_visivel(raiz)
    assert 'max-w-48' in _classes(raiz)


def test_label_extremamente_longo_no_fallback_nao_e_truncado():
    label_longo = 'Estado corrompido pela integração legada ' * 15
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA, label=label_longo)
    assert label_longo in ''.join(raiz.itertext())


def test_label_com_emoji_e_acentuacao_renderiza_integralmente():
    label = 'Requisição atrasada ⚠️ 🚨 — pátio nº 3 (São João)'
    html = _render(variant='amber', label=label)
    assert label in html


def test_label_com_caracteres_html_e_escapado():
    """Label vem de `get_estado_display()`/dado de domínio controlado, mas o
    componente não deve confiar nisso: autoescape do Django precisa segurar
    a barreira mesmo se um rótulo carregar marcação.
    """
    html = _render(variant='blue', label='<script>alert(1)</script>')
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


def test_variant_cru_e_escapado_no_atributo_data_badge_variant():
    """`desconhecida:<valor>` carrega dado de domínio no atributo de depuração
    — se o valor algum dia contiver aspas, não pode quebrar o atributo.
    """
    html = _render(variant='desconhecida:"><img src=x>')
    assert '<img src=x>' not in html
    assert 'data-badge-variant="desconhecida:&quot;&gt;&lt;img src=x&gt;"' in html


# ─── Token no lugar da última cor crua (issue #121) ───────────────────────


def test_fallback_usa_token_semantico_e_nao_text_white():
    raiz = _arvore(variant=VARIANTE_DESCONHECIDA)
    classes = _classes(raiz)
    assert 'text-text-on-primary' in classes
    assert 'text-white' not in classes


def test_badge_nao_tem_nenhuma_cor_crua():
    conteudo = BADGE_TEMPLATE.read_text(encoding='utf-8')
    ocorrencias = dict(Counter(CLASSE_DE_PALETA_RE.findall(conteudo)))
    assert ocorrencias == CLASSES_DE_CATALOGO_PERMITIDAS, (
        'cor crua de badge.html não bate com a exceção declarada em '
        f'CLASSES_DE_CATALOGO_PERMITIDAS. Encontrado={ocorrencias} '
        f'Permitido={CLASSES_DE_CATALOGO_PERMITIDAS}'
    )


def test_badge_nao_usa_cor_crua_sem_shade():
    """`text-white` não tem dígito e escapa do regex de família — cobre à parte."""
    conteudo = BADGE_TEMPLATE.read_text(encoding='utf-8')
    assert 'text-white' not in conteudo
    assert 'bg-white' not in conteudo


# ─── `:` é delimitador reservado do vocabulário de variant (issue #122) ───

# Aspas simples ou duplas, com ou sem espaço em volta de `==`/`in` — não um
# padrão textual fixo, senão uma variante declarada com aspas diferentes
# escaparia da varredura.
VARIANTE_LITERAL_RE = re.compile(r'variant\s*(?:==|in)\s*[\'\"]([^\'\"]+)[\'\"]')


def test_nenhuma_variante_de_catalogo_contem_dois_pontos():
    conteudo = BADGE_TEMPLATE.read_text(encoding='utf-8')
    literais = VARIANTE_LITERAL_RE.findall(conteudo)
    assert literais, 'a extração não achou nenhum literal — regex quebrou'
    com_dois_pontos = [v for v in literais if ':' in v]
    assert com_dois_pontos == [], (
        f'variante(s) de catálogo contendo o delimitador reservado ":": {com_dois_pontos}'
    )


# ─── Guarda de rótulo longo nos 14 ramos (issue #121) ─────────────────────


def _fatias_por_ramo(conteudo):
    """Corta o template nos marcadores da cadeia de variantes."""
    conteudo = BLOCO_DE_COMENTARIO_RE.sub('', conteudo)
    inicios = [m.start() for m in MARCADOR_DE_RAMO_RE.finditer(conteudo)]
    limites = inicios + [len(conteudo)]
    return [conteudo[inicio:fim] for inicio, fim in zip(inicios, limites[1:])]


@pytest.mark.parametrize('variant', [*VARIANTES_CONHECIDAS, VARIANTE_DESCONHECIDA])
def test_todo_ramo_renderiza_a_guarda_de_rotulo_longo(variant):
    raiz = _arvore(variant=variant, label='Aguardando autorização')

    assert 'max-w-48' in _classes(raiz), (
        f'variante {variant!r} sem largura máxima: rótulo comprido estoura o cartão'
    )

    guardas = [filho for filho in raiz if {'min-w-0', 'break-words'} <= _classes(filho)]
    assert len(guardas) == 1, (
        f'variante {variant!r} precisa de exatamente um invólucro de quebra '
        f'em volta do texto visível, encontrado(s) {len(guardas)}'
    )


@pytest.mark.parametrize('variant', [*VARIANTES_CONHECIDAS, VARIANTE_DESCONHECIDA])
def test_a_guarda_nao_engole_o_rotulo(variant):
    """Largura máxima não pode virar o descarte de dado que a issue #121 fecha."""
    raiz = _arvore(variant=variant, label='Aguardando autorização')
    if variant == VARIANTE_DESCONHECIDA:
        assert 'Aguardando autorização' in ''.join(raiz.itertext())
    else:
        assert 'Aguardando autorização' in _texto_visivel(raiz)


def test_guarda_de_rotulo_longo_em_todos_os_ramos_do_arquivo():
    """Vale também para o ramo que ainda não foi escrito.

    A asserção é por fatia, não por total: dois `min-w-0` num ramo compensariam
    zero em outro e um teste de contagem global passaria feliz.
    """
    fatias = _fatias_por_ramo(BADGE_TEMPLATE.read_text(encoding='utf-8'))

    assert len(fatias) == TOTAL_DE_RAMOS, (
        f'esperado {TOTAL_DE_RAMOS} ramos na cadeia de variantes, '
        f'encontrado {len(fatias)}'
    )

    for indice, fatia in enumerate(fatias):
        assert fatia.count('max-w-48') == 1, (
            f'ramo {indice} sem largura máxima (ou com mais de uma)'
        )
        assert fatia.count('min-w-0') == 1, (
            f'ramo {indice} sem invólucro de quebra (ou com mais de um)'
        )
        assert fatia.count('break-words') == 1, (
            f'ramo {indice} sem quebra de palavra longa (ou com mais de uma)'
        )
