"""Testes de regressão para #86 e #122 — tokens semânticos dentro dos templates.

Garante o que os critérios de aceite das duas issues pedem como "busca
automatizável":

1. Nenhuma classe de cor de paleta crua do Tailwind (qualquer uma das 22
   famílias padrão) aparece em `apps/**/*.html`, exceto na exceção
   declarada em `docs/design-system.md` ("Token, nunca shade"): o backdrop de
   `components/modal.html`. A exceção é por **classe exata com contagem**
   (Decisão B da issue #122) — não por família nem por arquivo inteiro, para
   que reaproveitar uma classe já isenta num ramo novo, ou colar um shade
   novo da mesma família, quebre o teste.
2. Os tokens novos do @theme realmente compilam pra CSS utilizável — roda
   `npm run css:build` e confere que as custom properties e as utilities
   usadas pelos templates existem no app.css gerado.
"""

import pathlib
import re
import shutil
import subprocess
from collections import Counter

import pytest

BASE_DIR = pathlib.Path(__file__).resolve().parents[3]
TAILWIND_CLI = BASE_DIR / 'node_modules' / '.bin' / 'tailwindcss'
APPS_DIR = BASE_DIR / 'apps'
INPUT_CSS = BASE_DIR / 'assets' / 'css' / 'input.css'
APP_CSS = BASE_DIR / 'apps' / 'core' / 'static' / 'core' / 'css' / 'app.css'

# As 22 famílias de paleta padrão do Tailwind v4 — não só as que já apareceram
# no repositório hoje, porque a Decisão B da issue #122 pede que uma família
# nova coladas amanhã (ex. `bg-lime-100`) quebre o teste, não só as que já
# existem.
FAMILIAS_TAILWIND = [
    'slate',
    'gray',
    'zinc',
    'neutral',
    'stone',
    'red',
    'orange',
    'amber',
    'yellow',
    'lime',
    'green',
    'emerald',
    'teal',
    'cyan',
    'sky',
    'blue',
    'indigo',
    'violet',
    'purple',
    'fuchsia',
    'pink',
    'rose',
]

# Prefixos de utility de cor do Tailwind — inclui as variantes direcionais de
# border (border-t/-r/-b/-l) e as de gradiente/SVG/decoração, que têm prefixo
# composto e escapavam do regex mesmo com a família presente (CodeRabbit).
PREFIXOS_DE_COR = [
    'bg',
    'text',
    'border',
    'border-t',
    'border-r',
    'border-b',
    'border-l',
    'ring',
    'divide',
    'outline',
    'fill',
    'stroke',
    'decoration',
    'accent',
    'from',
    'via',
    'to',
]

CLASSE_CRUA_RE = re.compile(
    r'(?:'
    + '|'.join(PREFIXOS_DE_COR)
    + r')-(?:'
    + '|'.join(FAMILIAS_TAILWIND)
    + r')-\d+(?:/\d+)?'
)


def _classe_sem_opacidade(classe):
    """`bg-slate-900/50` -> `bg-slate-900`: a isenção é da cor, não da opacidade."""
    return classe.split('/')[0]


# Allowlist por (caminho relativo a apps/) -> {classe exata: nº de ocorrências}.
# Comparação é de igualdade entre dicionários (ver test_allowlist_bate_exatamente
# abaixo), não de continência: reaproveitar uma classe isenta em ramo novo, um
# shade novo da mesma família, ou uma classe sumir do arquivo — tudo quebra.
ALLOWLIST_COR_CRUA = {
    'core/templates/components/modal.html': {
        # O backdrop do modal — segunda exceção declarada na mesma linha do
        # design system.
        'bg-slate-900': 1,
    },
}

TOKENS_NOVOS = [
    '--color-primary-muted-strong',
    '--color-primary-border-strong',
    '--color-primary-text-emphasis',
    '--color-primary-text-strong',
    '--color-danger-muted-strong',
    '--color-danger-border-strong',
    '--color-danger-border-input',
    '--color-danger-accent',
    '--color-danger-hover',
    '--color-danger-active',
    '--color-danger-text-emphasis',
    '--color-danger-text-strong',
    '--color-warning-muted-strong',
    '--color-warning-border-strong',
    '--color-warning-text-subtle',
    '--color-warning-text-strong',
    '--color-success-text-emphasis',
    '--color-success-text-strong',
    '--color-return-muted-strong',
    '--color-return-border-strong',
    '--color-return-text-strong',
    '--color-cancel-muted',
    '--color-cancel-border',
    '--color-cancel-text-strong',
    '--color-consumption-muted',
    '--color-consumption-border',
    '--color-consumption-text-strong',
    '--color-reversal-muted',
    '--color-reversal-border',
    '--color-reversal-text-strong',
]

# Amostra de utilities consumidas pelos templates que precisam ter sido
# realmente geradas pelo build (nome errado/typo no @theme não quebra o
# grep de cor crua, só a ausência da utility no app.css).
UTILITIES_ESPERADAS = [
    'bg-primary-muted-strong',
    'bg-danger-muted-strong',
    'bg-warning-muted-strong',
    'bg-return-muted-strong',
    'ring-return-border-strong',
    'text-primary-text-strong',
    'text-danger-text-strong',
    'text-warning-text-strong',
    'text-success-text-strong',
    'text-return-text-strong',
    'text-text-on-primary',
    'text-return-text',
    'border-danger-border-strong',
    'focus-visible:ring-danger-accent',
    # A caixa do error_summary.html é a exceção declarada da regra do anel:
    # foco programático não casa `:focus-visible`, então lá a utility é `focus:`.
    # As âncoras do mesmo componente seguem em `focus-visible:` — as duas
    # precisam existir no build, e é por isso que as duas estão nesta lista.
    'focus:ring-danger-accent',
    'bg-warning-subtle',
    'bg-cancel-muted',
    'text-cancel-text-strong',
    'ring-cancel-border',
    'bg-consumption-muted',
    'text-consumption-text-strong',
    'ring-consumption-border',
    'bg-reversal-muted',
    'text-reversal-text-strong',
    'ring-reversal-border',
]

# Tokens declarados no @theme mas sem consumidor real em nenhum template
# hoje (toda a família info-*, usada só pelo alert/messages "info" que na
# verdade consome primary-*). Não devem ter utility compilada — se
# aparecerem, algo (doc, teste) vazou pro scan.
#
# `text-success-text` entrou nesta lista na Etapa 7: o único consumidor era o
# delta positivo do preview do SCPI, pintado de verde. Verde ali dizia "bom"
# sobre uma divergência, que o PRODUCT.md declara "estado normal e esperado" —
# a cor saiu e o token ficou sem uso. As famílias `-emphasis` e `-strong` do
# mesmo verde continuam consumidas.
UTILITIES_DORMANTES = [
    '.text-success-text{',
    '.bg-info{',
    '.bg-info-subtle{',
    '.bg-info-muted{',
    '.border-info-border{',
    '.text-info-text{',
]


def _arquivos_alvo():
    return sorted(APPS_DIR.rglob('*.html'))


def _chave_relativa(arquivo):
    return str(arquivo.relative_to(APPS_DIR))


def _ocorrencias_de_cor_crua(conteudo):
    return dict(
        Counter(
            _classe_sem_opacidade(classe) for classe in CLASSE_CRUA_RE.findall(conteudo)
        )
    )


def _bate_com_allowlist(chave, conteudo):
    """Função pura de checagem — testável com conteúdo sintético, sem tocar disco."""
    return _ocorrencias_de_cor_crua(conteudo) == ALLOWLIST_COR_CRUA.get(chave, {})


@pytest.mark.parametrize(
    'arquivo', _arquivos_alvo(), ids=lambda p: str(p.relative_to(APPS_DIR))
)
def test_cor_crua_de_marca_bate_exatamente_com_a_allowlist(arquivo):
    conteudo = arquivo.read_text(encoding='utf-8')
    chave = _chave_relativa(arquivo)
    ocorrencias = _ocorrencias_de_cor_crua(conteudo)
    permitidas = ALLOWLIST_COR_CRUA.get(chave, {})
    assert ocorrencias == permitidas, (
        f'{chave}: cor crua não bate com a exceção declarada em '
        f'ALLOWLIST_COR_CRUA. Encontrado={ocorrencias} Permitido={permitidas}'
    )


# ─── Mecanismo exercitado por entrada sintética, não por sujeira real ─────
# (issue #122) — nunca escrever cor crua num template de verdade só para
# provar que o guard morde: o próprio teste viraria o vazamento que deveria
# pegar.

CHAVE_MODAL = 'core/templates/components/modal.html'


def _conteudo_real(chave):
    return (APPS_DIR / chave).read_text(encoding='utf-8')


def test_entrada_sintetica_familia_nova_em_arquivo_nao_isento_e_reprovada():
    assert not _bate_com_allowlist(
        'requisicoes/templates/requisicoes/exemplo_sintetico.html',
        '<span class="bg-violet-100"></span>',
    )


def test_entrada_sintetica_familia_nova_dentro_do_modal_e_reprovada():
    """`badge.html` graduou da allowlist na #177 — não sobra nenhuma classe
    isenta lá pra este caso (família nova dentro de arquivo isento) exercitar.
    O `modal.html` é a única exceção viva restante."""
    conteudo = _conteudo_real(CHAVE_MODAL) + '<span class="bg-lime-100"></span>'
    assert not _bate_com_allowlist(CHAVE_MODAL, conteudo)


def test_entrada_sintetica_classe_isenta_reusada_no_modal_e_reprovada():
    conteudo = _conteudo_real(CHAVE_MODAL) + '<span class="bg-slate-900"></span>'
    assert not _bate_com_allowlist(CHAVE_MODAL, conteudo)


# Shade novo da mesma família isenta (bg-slate-800 dentro do modal) já é
# coberto por test_entrada_sintetica_classe_errada_no_modal_e_reprovada logo
# abaixo — badge.html perdeu a última classe isenta na #177 e não sobrou uma
# segunda exceção para exercitar esse caso sem duplicar o teste existente.


def test_entrada_sintetica_classe_errada_no_modal_e_reprovada():
    conteudo = _conteudo_real(CHAVE_MODAL) + '<span class="bg-slate-800"></span>'
    assert not _bate_com_allowlist(CHAVE_MODAL, conteudo)


def test_entrada_sintetica_classe_faltante_no_modal_e_reprovada():
    conteudo = _conteudo_real(CHAVE_MODAL).replace('bg-slate-900', '', 1)
    assert not _bate_com_allowlist(CHAVE_MODAL, conteudo)


@pytest.mark.parametrize(
    'classe',
    [
        'border-t-red-500',
        'border-r-red-500',
        'border-b-red-500',
        'border-l-red-500',
        'outline-red-500',
        'fill-red-500',
        'stroke-red-500',
        'from-red-500',
        'via-red-500',
        'to-red-500',
        'decoration-red-500',
        'accent-red-500',
    ],
)
def test_entrada_sintetica_prefixo_direcional_ou_de_gradiente_e_reprovada(classe):
    """CodeRabbit: border-t/outline/fill/stroke/from (e primos) escapavam do
    regex por terem prefixo composto — a família batia, mas o prefixo não.
    """
    assert not _bate_com_allowlist(
        'requisicoes/templates/requisicoes/exemplo_sintetico.html',
        f'<span class="{classe}"></span>',
    )


def test_todo_arquivo_da_allowlist_ainda_existe():
    """Exceção que sobrevive ao arquivo é como a regra vira sugestão de novo."""
    for chave in ALLOWLIST_COR_CRUA:
        assert (APPS_DIR / chave).exists(), (
            f'{chave} não existe mais — remova da allowlist'
        )


def test_tokens_novos_documentados_existem_no_input_css():
    conteudo = INPUT_CSS.read_text(encoding='utf-8')
    faltando = [token for token in TOKENS_NOVOS if token not in conteudo]
    assert faltando == [], f'Tokens ausentes em input.css: {faltando}'


@pytest.mark.skipif(
    not TAILWIND_CLI.exists() and shutil.which('tailwindcss') is None,
    reason=(
        'Tailwind CLI não instalado (node_modules ausente) — ambiente sem '
        '`npm install`, ex. job de CI só-Python. Rodar localmente após '
        '`npm install` para validar o build.'
    ),
)
def test_css_build_gera_tokens_e_utilities_novas():
    resultado = subprocess.run(
        ['npm', 'run', 'css:build'],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, (
        f'npm run css:build falhou:\nstdout={resultado.stdout}\nstderr={resultado.stderr}'
    )

    app_css = APP_CSS.read_text(encoding='utf-8')

    tokens_faltando = [token for token in TOKENS_NOVOS if token not in app_css]
    assert tokens_faltando == [], (
        f'Tokens novos não aparecem no app.css compilado (typo ou @theme '
        f'não reconhecido): {tokens_faltando}'
    )

    def _utility_compilada(nome):
        # Seletor real: classe com ':' de variante escapado (\:), seguido de
        # '{' (regra própria) ou ':' (pseudo-classe, ex. :focus-visible) —
        # nunca um sufixo de identificador (ex. '-strong'), pra não casar
        # por substring dentro de uma utility maior (#88).
        seletor = re.escape('.' + nome.replace(':', '\\:'))
        return re.search(seletor + r'[{:]', app_css) is not None

    utilities_faltando = [u for u in UTILITIES_ESPERADAS if not _utility_compilada(u)]
    assert utilities_faltando == [], (
        f'Utilities esperadas ausentes no app.css — Tailwind não gerou a '
        f'classe (nome errado no template ou token não usado): {utilities_faltando}'
    )

    utilities_dormantes_vazadas = [
        seletor for seletor in UTILITIES_DORMANTES if seletor in app_css
    ]
    assert utilities_dormantes_vazadas == [], (
        f'Utility de token dormente (sem consumidor real em templates) '
        f'apareceu no app.css — provável vazamento do content scan do '
        f'Tailwind (ex. exemplo de classe escrito por extenso em docs/*.md '
        f'ou apps/*/tests/*.py, não excluído via @source not em '
        f'input.css): {utilities_dormantes_vazadas}'
    )


# ---------------------------------------------------------------------------
# Etapa 8 — pares de cor medidos, não tokens isolados
# ---------------------------------------------------------------------------

# Medido no navegador durante o passe de regressão da Etapa 8 (registrado em
# DESIGN.md §A Regra do Cinza Medido):
#
#   | sobre →          | bg-subtle | surface | bg-page |
#   | text-tertiary    |   4,35 ✗  |  4,76   |  4,55   |
#   | danger-accent    |   3,48 ✗  |  3,81 ✗ |  3,64 ✗ |
#
# O piso do cinza de metadado do DESIGN.md foi medido só contra branco, então o
# token passava no papel e reprovava sobre `bg-subtle`. `danger-accent`
# (red-500) reprova o 4,5:1 em toda superfície do sistema e só é legítimo como
# anel de foco / borda de campo, onde o mínimo é o 3:1 da WCAG 1.4.11.

PARES_DE_COR_PROIBIDOS = [
    (
        'text-text-tertiary',
        'bg-bg-subtle',
        'cinza de metadado sobre papel frio sombreado mede 4,35:1 — abaixo do '
        '4,5:1 da WCAG 1.4.3. Use text-text-secondary (9,45:1).',
    ),
    (
        'text-text-tertiary',
        'bg-primary-subtle',
        'cinza de metadado sobre papel azulado mede 4,38:1 — abaixo do 4,5:1 '
        'da WCAG 1.4.3. Use text-text-secondary (9,51:1).',
    ),
]

# `text-danger-accent` como cor de TEXTO. As demais utilities do mesmo token
# (`ring-danger-accent`, `border-danger-accent`, `focus-visible:ring-...`)
# continuam válidas: ali o mínimo é 3:1 e o token passa.
CLASSE_TEXTO_DANGER_ACCENT = re.compile(r'(?<![\w:-])text-danger-accent(?![\w-])')


def _templates():
    return sorted(APPS_DIR.rglob('*.html'))


def test_nenhum_template_pinta_texto_com_danger_accent():
    """Vermelho de ênfase é anel de foco e borda, nunca texto.

    O asterisco de campo obrigatório usava `text-danger-accent` — o único
    indicador visual de obrigatoriedade do produto, a 3,81:1 sobre papel branco.
    """
    infratores = []
    for caminho in _templates():
        conteudo = caminho.read_text(encoding='utf-8')
        # A menção dentro de um {% comment %} explicando a regra não conta.
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            if CLASSE_TEXTO_DANGER_ACCENT.search(linha) and 'class=' in linha:
                infratores.append(f'{caminho.relative_to(BASE_DIR)}:{numero}')
    assert infratores == [], (
        'text-danger-accent mede 3,48:1 a 3,81:1 nas três superfícies do '
        'sistema e reprova a WCAG 1.4.3. Texto de perigo é text-danger-text '
        f'(6,42:1 no branco). Ver DESIGN.md §A Regra do Cinza Medido: {infratores}'
    )


@pytest.mark.parametrize(('cor', 'fundo', 'motivo'), PARES_DE_COR_PROIBIDOS)
def test_nenhum_elemento_combina_par_de_cor_reprovado(cor, fundo, motivo):
    """O contraste é do par, não do token — o mesmo cinza passa no branco e
    reprova no papel frio sombreado.

    Limite conhecido: o guarda vê par no **mesmo elemento**. O caso do
    cabeçalho de `atender_retirada.html` — `bg-bg-subtle` no `<div>` e
    `text-text-tertiary` nos `<span>` filhos — passa por aqui e só apareceu na
    medição no navegador. A varredura de contraste da lane Navegador (ADR-0019)
    é o lugar de fechar isso; este teste tranca a recorrência literal.
    """
    infratores = []
    for caminho in _templates():
        for numero, linha in enumerate(
            caminho.read_text(encoding='utf-8').splitlines(), start=1
        ):
            if 'class=' not in linha:
                continue
            for atributo in re.findall(r'class="([^"]*)"', linha):
                classes = set(atributo.split())
                if cor in classes and fundo in classes:
                    infratores.append(f'{caminho.relative_to(BASE_DIR)}:{numero}')
    assert infratores == [], f'{motivo} Infratores: {infratores}'
