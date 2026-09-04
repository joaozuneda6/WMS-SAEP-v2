"""Testes diretos de partials de badge de estoque (sem DB, sem view).

Mesma correção de `_estado_badge.html` (issue #122) para os três partials de
estoque que anulavam o fallback vermelho de `components/badge.html`: valor
não mapeado passa a gritar sob o prefixo `desconhecida:`, em vez de virar
uma cor plausível. Os dois que hoje passam `aria_label` (que o fallback do
badge.html propagaria literalmente, calando o grito para leitor de tela)
trocam para `prefixo_sr` só no ramo do grito.
"""

import re
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string

TIPOS_CANONICOS = {
    'reserva': 'blue',
    'liberacao': 'slate',
    'consumo': 'consumption',
    'saida_excepcional': 'red',
    'estorno_saida': 'amber',
    'devolucao': 'teal',
    'estorno_requisicao': 'reversal',
}


def _movimentacao(tipo, rotulo='Rótulo do tipo'):
    return SimpleNamespace(tipo=tipo, rotulo=rotulo)


def _render_tipo_movimentacao(tipo, rotulo='Rótulo do tipo'):
    mov = _movimentacao(tipo, rotulo)
    return render_to_string(
        'estoque/partials/_badge_tipo_movimentacao.html',
        {'tipo': mov.tipo, 'rotulo': mov.rotulo},
    )


def _saida(estado, label='Rótulo do estado'):
    return SimpleNamespace(estado=estado, get_estado_display=lambda: label)


def _render_saida(estado, label='Rótulo do estado'):
    return render_to_string(
        'estoque/partials/_estado_saida_badge.html',
        {'saida': _saida(estado, label)},
    )


# ─── _badge_tipo_movimentacao.html ─────────────────────────────────────────


def test_tipo_inexistente_renderiza_indisponivel_visivel():
    html = _render_tipo_movimentacao('tipo-que-nao-existe')
    assert 'Indisponível' in html


def test_tipo_inexistente_emite_data_badge_variant_prefixado():
    html = _render_tipo_movimentacao('tipo-que-nao-existe')
    assert 'data-badge-variant="desconhecida:tipo-que-nao-existe"' in html


def test_tipo_cancel_colide_mas_gruda_no_fallback():
    html = _render_tipo_movimentacao('cancel')
    assert 'Indisponível' in html
    assert 'bg-cancel-muted' not in html


def test_tipo_inexistente_preserva_rotulo_real():
    html = _render_tipo_movimentacao('tipo-que-nao-existe', rotulo='Reserva de saída')
    assert 'Reserva de saída' in html


def test_tipo_inexistente_nao_emite_aria_label():
    html = _render_tipo_movimentacao('tipo-que-nao-existe')
    assert 'aria-label=' not in html


def test_tipo_inexistente_nome_acessivel_contem_indisponivel_e_rotulo():
    html = _render_tipo_movimentacao('tipo-que-nao-existe', rotulo='Reserva de saída')
    assert 'Tipo de movimentação: ' in html
    assert 'Indisponível' in html
    assert 'Reserva de saída' in html


@pytest.mark.parametrize('tipo,variant_esperada', sorted(TIPOS_CANONICOS.items()))
def test_tipo_canonico_mantem_variante_de_hoje(tipo, variant_esperada):
    html = _render_tipo_movimentacao(tipo)
    marcadores = {
        'blue': 'bg-primary-muted ',
        'slate': 'bg-bg-subtle',
        'consumption': 'bg-consumption-muted',
        'red': 'bg-danger-muted ',
        'amber': 'bg-warning-muted ',
        'teal': 'bg-return-muted',
        'reversal': 'bg-reversal-muted',
    }[variant_esperada]
    assert marcadores in html
    # `prefixo_sr` e não `aria-label`+`role="status"`: badge de dado estático não
    # é live region (contrato escrito em components/badge.html), e no ledger eram
    # 25 delas por página. Texto `sr-only` é sempre exposto; `aria-label` num
    # <span> sem role, não — a spec ARIA não garante.
    assert '<span class="sr-only">Tipo de movimentação: </span>' in html
    assert 'role="status"' not in html
    assert 'aria-label=' not in html


# ─── _estado_saida_badge.html ──────────────────────────────────────────────


def test_saida_inexistente_renderiza_indisponivel_visivel():
    html = _render_saida('estado-que-nao-existe')
    assert 'Indisponível' in html


def test_saida_inexistente_emite_data_badge_variant_prefixado():
    html = _render_saida('estado-que-nao-existe')
    assert 'data-badge-variant="desconhecida:estado-que-nao-existe"' in html


def test_saida_cancel_colide_mas_gruda_no_fallback():
    html = _render_saida('cancel')
    assert 'Indisponível' in html
    assert 'bg-cancel-muted' not in html


def test_saida_inexistente_nao_emite_aria_label():
    html = _render_saida('estado-que-nao-existe')
    assert 'aria-label=' not in html


def test_saida_inexistente_nome_acessivel_contem_indisponivel_e_rotulo():
    html = _render_saida('estado-que-nao-existe', label='Registrada')
    assert 'Estado: ' in html
    assert 'Indisponível' in html
    assert 'Registrada' in html


def test_saida_registrada_mantem_blue_strong():
    html = _render_saida('registrada')
    assert 'bg-primary-muted-strong' in html


def test_saida_estornada_usa_teal_forte():
    """`estornada` tem ramo explícito próprio (senão o grito pintaria todo
    estorno de vermelho). Desde a issue #157 sobe para `teal-strong` — fundo
    shade 200 — para não empatar no varrimento com o verde de "Atendida".
    """
    html = _render_saida('estornada')
    assert 'bg-return-muted-strong' in html
    assert 'ring-return-border-strong' in html
    assert 'Indisponível' not in html


# ─── _alert_divergencias_corpo.html ────────────────────────────────────────


def _render_divergencias(divergencias=3):
    return render_to_string(
        'estoque/partials/_alert_divergencias_corpo.html',
        {'divergencias': divergencias},
    )


def test_alerta_de_divergencia_nomeia_quem_decide_e_a_proxima_acao():
    """Um âmbar mudo parece erro do sistema para quem confia no papel.

    O `DESIGN.md` define âmbar como "a decisão está com alguém"; a decisão do
    dono do produto (issue #123) diz que esse alguém é o chefe de almoxarifado,
    e que a ação é ajustar no SCPI. A copy antiga informava só o efeito técnico.
    """
    html = _render_divergencias()
    assert 'chefe de almoxarifado' in html
    assert 'ajustar no SCPI' in html


def test_alerta_de_divergencia_enquadra_a_divergencia_como_esperada():
    """`PRODUCT.md`: divergência entre WMS e SCPI é estado normal, não erro.

    O fluxo é reexecutado por gente que confia mais no papel do que no
    software. Sem dizer que é esperado, o âmbar lê como falha da importação.
    """
    html = _render_divergencias()
    assert 'estado esperado da coexistência com o SCPI' in html
    assert 'não é falha da importação' in html


def test_alerta_de_divergencia_nomeia_os_dois_lados_sem_jargao():
    """O WMS é a fonte do saldo; o SCPI informa uma quantidade em arquivo.

    "registradas como alerta" descreve o que o sistema fez consigo mesmo, não o
    que o usuário está vendo. `CONTEXT.md` define divergência como a diferença
    entre a quantidade do arquivo SCPI e o saldo do WMS — é esse par que a copy
    precisa nomear, preservando a garantia de que o saldo do WMS não muda.
    """
    html = _render_divergencias()
    assert 'saldo do WMS' in html
    assert 'quantidade informada no arquivo do SCPI' in html
    assert 'saldo do WMS não será alterado' in html
    assert 'registrada' not in html


# ─── _alert_novos_materiais_corpo.html ─────────────────────────────────────


def _render_novos(novos=2):
    return render_to_string(
        'estoque/partials/_alert_novos_materiais_corpo.html',
        {'novos': novos},
    )


def test_alerta_de_materiais_novos_diz_quem_confere_o_catalogo():
    """O material novo entra no catálogo com uma unidade que ninguém escolheu.

    `confirmar_importacao_scpi` cria o material com `unidade=UNIDADE` fixa,
    porque o CSV do SCPI não informa unidade, e com o nome vindo da denominação
    do arquivo. Existe conferência humana pendente de fato — e ela é do mesmo
    dono que decide sobre a divergência.
    """
    html = _render_novos()
    assert 'unidade' in html
    assert 'chefe de almoxarifado' in html
    assert 'conferir' in html


# ─── Regra dos 14px nos dois corpos ────────────────────────────────────────


@pytest.mark.parametrize('render', [_render_divergencias, _render_novos])
def test_corpo_de_alerta_do_preview_usa_14px(render):
    """`DESIGN.md` reserva 12px a rótulo estrutural em caixa alta.

    Aqui é conteúdo numérico que sustenta a decisão do chefe de almoxarifado,
    renderizado no tamanho de metadado. "Se um texto precisa de mais presença,
    mude o peso ou o tom, não o tamanho" vale nos dois sentidos.
    """
    html = render()
    assert 'text-sm' in html
    assert 'text-xs' not in html


@pytest.mark.parametrize(
    'render,quantidade,esperado,proibido',
    [
        (_render_divergencias, 1, 'divergência', 'divergências'),
        (_render_divergencias, 2, 'divergências', None),
        (_render_novos, 1, 'material novo será criado', 'serão criados'),
        (_render_novos, 2, 'materiais novos serão criados', 'será criado'),
    ],
)
def test_corpo_de_alerta_flexiona_singular_e_plural(
    render, quantidade, esperado, proibido
):
    """A reescrita da copy não pode levar junto a flexão que já funcionava."""
    html = render(quantidade)
    assert esperado in html
    if proibido is not None:
        assert proibido not in html


@pytest.mark.parametrize('render', [_render_divergencias, _render_novos])
def test_corpo_de_alerta_do_preview_tem_linha_lider(render):
    """Os dois alertas do preview ganham linha-líder como os de desfecho (#164).

    `_alert_sucesso_importacao_corpo.html` e `_alert_erro_scpi_corpo.html` já
    abrem com um `<p class="font-semibold">`; sem isso, os alertas de antes da
    escrita irreversível — quando ainda há decisão — saíam mais planos que os de
    depois, invertendo a progressão.
    """
    html = render()
    assert re.search(r'<p[^>]*\bclass="[^"]*\bfont-semibold\b[^"]*"', html), html


# ─── Alertas do fluxo SCPI ─────────────────────────────────────────────────


def _render_alerta(variant, body_template, **contexto):
    """Renderiza o corpo dentro do `alert.html` de verdade.

    Renderizar o corpo isolado esconderia justamente o que estes testes
    verificam: o que a caixa já entrega e o corpo não deve repetir.
    """
    return render_to_string(
        'components/alert.html',
        {'variant': variant, 'body_template': body_template, **contexto},
    )


def _render_erro_scpi(titulo='Erro ao processar o arquivo', detalhe='Detalhe.'):
    return _render_alerta(
        'danger',
        'estoque/partials/_alert_erro_scpi_corpo.html',
        titulo=titulo,
        detalhe=detalhe,
    )


def test_alerta_de_erro_scpi_serve_as_duas_portas_de_falha():
    """Uma caixa, dois títulos — era o mesmo partial escrito duas vezes."""
    leitura = _render_erro_scpi('Erro ao processar o arquivo', 'CSV inválido.')
    gravacao = _render_erro_scpi('Erro ao confirmar importação', 'Já importado.')
    assert 'Erro ao processar o arquivo' in leitura
    assert 'CSV inválido.' in leitura
    assert 'Erro ao confirmar importação' in gravacao
    assert 'Já importado.' in gravacao


def test_corpo_de_erro_scpi_nao_redeclara_o_token_da_caixa():
    """Cor de texto é da variante, e a variante é do chamador.

    Redeclarar `text-danger-text-emphasis` no corpo acopla o corpo à variante:
    um chamador que passasse outra teria a cor do texto brigando com a da
    caixa. O `alert.html` já entrega o token.
    """
    corpo = render_to_string(
        'estoque/partials/_alert_erro_scpi_corpo.html',
        {'titulo': 'T', 'detalhe': 'D'},
    )
    assert 'text-danger' not in corpo
    assert 'text-sm' not in corpo
    # …e a caixa continua entregando os dois.
    caixa = _render_erro_scpi()
    assert 'text-danger-text-emphasis' in caixa
    assert 'text-sm' in caixa


def _importacao(nome='SCPI_SALDOS_2026_08_31_ALMOXARIFADO_CENTRAL.csv'):
    from datetime import datetime

    return SimpleNamespace(
        total_linhas=7,
        total_novos=2,
        total_divergentes=2,
        arquivo_nome=nome,
        importado_em=datetime(2026, 8, 31, 9, 18),
    )


def _render_sucesso(**kwargs):
    return _render_alerta(
        'success',
        'estoque/partials/_alert_sucesso_importacao_corpo.html',
        importacao=_importacao(**kwargs),
    )


def test_alerta_de_sucesso_usa_a_grafia_de_data_do_sistema():
    """`historico_importacoes_scpi.html` imprime o mesmo campo como d/m/Y H:i.

    Sem o filtro, o `DateTimeField` caía na localização longa do Django —
    "31 de Agosto de 2026 às 09:18" — e as duas telas mostravam o mesmo
    instante em grafias diferentes. A de sucesso oferece "Ver histórico de
    importações" como primeira ação, ou seja, elas são percorridas em
    sequência.
    """
    html = _render_sucesso()
    assert '31/08/2026 09:18' in html
    assert 'de Agosto de' not in html


def test_nome_de_arquivo_do_alerta_de_sucesso_pode_quebrar():
    """Medido a 375px: o `<code>` estourava para 404,6px e rolava a página.

    Nome de arquivo do SCPI é uma palavra só de ~46 caracteres, sem espaço
    onde o navegador possa quebrar sozinho.
    """
    html = _render_sucesso()
    assert 'break-all' in html
    assert 'max-w-full' in html


# ─── _autocomplete_item_material.html — o rótulo do saldo ──────────────────


def _render_item_material():
    return render_to_string('estoque/partials/_autocomplete_item_material.html', {})


def test_item_de_material_nomeia_cada_saldo_pelo_que_ele_e():
    """As duas buscas devolvem grandezas diferentes, não a mesma com dois nomes.

    `requisicoes` manda `saldo_disponivel` (físico − reservado); `estoque`
    (saída excepcional) manda `saldo_fisico`, reservado incluído. O rótulo era
    `disp:` nos dois: quem registrava saída excepcional lia "disp: 44" com 10
    reservados para requisições já autorizadas.
    """
    html = _render_item_material()
    assert 'disponível: ' in html
    assert 'físico: ' in html
    assert 'disp:' not in html


def test_item_de_material_nao_deixa_rotulo_e_valor_se_desencontrarem():
    """Rótulo e valor têm de sair do mesmo lado do teste.

    Com `??`, o valor caía para `saldo_fisico` enquanto o rótulo continuava
    fixo em outra grandeza. A guarda é estrutural: cada nome de campo aparece
    exatamente uma vez, ao lado do próprio rótulo.
    """
    html = _render_item_material()
    assert html.count('item.saldo_disponivel + ') == 1
    assert html.count('item.saldo_fisico + ') == 1
    assert '??' not in html


def test_item_de_material_ramifica_por_presenca_e_nao_por_falsidade():
    """Saldo zero é resposta legítima e não pode cair no ramo errado."""
    assert 'item.saldo_disponivel !== undefined' in _render_item_material()


def test_item_de_material_respeita_o_piso_de_cor_da_opcao():
    """`text-text-disabled` mede 2.63:1 no branco e 2.42:1 na opção ativa.

    O saldo é o número que decide a escolha; não pode ficar abaixo do piso.
    """
    assert 'text-text-disabled' not in _render_item_material()


# ─── _delta_movimentacao.html — precisão por unidade ───────────────────────


def _render_delta(valor, unidade='un'):
    return render_to_string(
        'estoque/partials/_delta_movimentacao.html',
        {'valor': Decimal(valor), 'unidade': unidade},
    )


@pytest.mark.parametrize(
    'valor,unidade,esperado',
    [
        ('1.000', 'un', '+1'),
        ('-3.000', 'un', '−3'),
        ('15.000', 'un', '+15'),
        ('2.500', 'kg', '+2,5'),
        ('-2.500', 'kg', '−2,5'),
        ('1.000', 'kg', '+1,0'),
    ],
)
def test_delta_usa_a_precisao_da_unidade(valor, unidade, esperado):
    """O Decimal do banco carrega três casas; a unidade decide quantas valem.

    Sem o filtro, um delta de 1 saía `+1,000` — em pt-BR isso se lê *mil*, e é
    exatamente o erro que `apps/core/quantidades.py` foi criado para matar em
    `atender_retirada`. Aqui o número é lido em pé, no galpão, ao lado do
    material físico.

    O negativo casa `−` (U+2212), não `-` (U+002D): é o sinal que a issue #163
    pediu para casar a largura do `+`.

    A asserção fecha nas duas bordas do valor: `in` sozinho passaria com
    `+2.5000`, que é justamente a casa a mais que o filtro existe para tirar.
    """
    html = _render_delta(valor, unidade).replace(' ', '')
    assert f'>{esperado}<' in html


@pytest.mark.parametrize('valor', ['1.000', '-3.000', '47.000'])
def test_delta_nunca_imprime_as_tres_casas_cruas(valor):
    """Guarda de regressão: o `,000` é o defeito, não o formato.

    Vale a grafia com ponto também — se alguém trocar o filtro por um
    `floatformat` fixo, o zero à direita volta por outra porta.
    """
    html = _render_delta(valor)
    assert ',000' not in html
    assert '.000' not in html


def test_delta_zero_nao_ganha_casa_decimal_da_unidade():
    """Zero é ausência de movimento, não quantidade medida.

    Em `kg` o filtro devolveria `0.0`; o literal `0` mantém a coluna curta e
    diz a coisa certa.
    """
    html = _render_delta('0.000', 'kg')
    assert '>0<' in html.replace(' ', '')
    assert '0.0' not in html


def test_delta_sem_unidade_ainda_degrada_para_o_numero_certo():
    """Chamador que esquecer a unidade não pode reintroduzir o `1,000`."""
    html = render_to_string(
        'estoque/partials/_delta_movimentacao.html', {'valor': Decimal('1.000')}
    )
    assert '+1<' in html.replace(' ', '')
    assert ',000' not in html


# ─── _delta_movimentacao.html — grafia do sinal e da direção (issue #163) ──


def test_delta_negativo_usa_minus_sign_e_nao_hifen():
    """`−` (U+2212) casa a largura do `+`; `-` (U+002D) tem ~4px.

    `formatar_quantidade` devolve o número com U+002D — o átomo tem de removê-lo
    e repor o U+2212, senão a direção fica pendurada no glifo mais fraco.
    """
    html = _render_delta('-3.000', 'un')
    assert '−' in html
    assert '−3' in html.replace(' ', '')
    # O hífen-menos não pode sobrar em nenhum lugar do valor renderizado.
    assert '-3' not in html
    assert '>-' not in html.replace(' ', '')


def test_delta_direcao_tem_triangulo_aria_hidden_e_sinal_em_texto():
    """`▲`/`▼` são decoração; o portador acessível da direção é o sinal.

    O leitor de tela lia o nome Unicode do triângulo antes do número — por isso
    ele é `aria-hidden` e o `+`/`−` fica fora de qualquer `aria-hidden`.
    """
    positivo = _render_delta('5.000', 'un').replace(' ', '')
    assert '<spanaria-hidden="true">▲</span>+5' in positivo

    negativo = _render_delta('-5.000', 'un').replace(' ', '')
    assert '<spanaria-hidden="true">▼</span>−5' in negativo


def test_delta_valor_sai_em_font_mono_um_degrau_acima_dos_vizinhos():
    """`font-mono` para formar coluna; `font-medium` para pesar mais que
    `Origem:`/`Ator:` (400). O zero não pesa — nada aconteceu."""
    assert 'font-mono' in _render_delta('5.000', 'un')
    assert 'font-medium' in _render_delta('5.000', 'un')
    assert 'font-medium' in _render_delta('-5.000', 'un')
    assert 'font-medium' not in _render_delta('0.000', 'un')


def test_delta_zero_continua_font_mono_para_nao_quebrar_a_coluna():
    html = _render_delta('0.000', 'un')
    assert 'font-mono' in html
    assert '>0<' in html.replace(' ', '')


@pytest.mark.parametrize(
    'template',
    [
        'estoque/preview_importacao_scpi.html',
        'estoque/historico_movimentacoes.html',
        'estoque/partials/_cartoes_divergencias_scpi.html',
    ],
)
def test_as_tres_superficies_do_delta_incluem_o_mesmo_atomo(template):
    """Uma grafia só para a mesma grandeza (issue #163): ledger, preview do SCPI
    e lista de divergências renderizam o delta pelo mesmo partial."""
    from pathlib import Path

    fonte = (
        Path(__file__).resolve().parent.parent / 'templates' / template
    ).read_text()
    assert 'estoque/partials/_delta_movimentacao.html' in fonte


# ---------------------------------------------------------------------------
# Etapa 8 — regressão: precisão de quantidade na lista de divergências
# ---------------------------------------------------------------------------


def _render_cartoes_divergencias(saldo_wms, saldo_scpi, delta):
    """Renderiza `_cartoes_divergencias_scpi.html` com uma linha só.

    O partial espera um iterável de `LinhaDivergenteSCPI`; um objeto simples com
    os mesmos atributos basta e evita tocar o banco.
    """
    linha = SimpleNamespace(
        cadpro='001.001.001',
        denominacao='ELETRODUTO RIGIDO ROSCAVEL 3/4',
        saldo_wms=Decimal(saldo_wms),
        saldo_scpi=Decimal(saldo_scpi),
        delta=Decimal(delta),
    )
    return render_to_string(
        'estoque/partials/_cartoes_divergencias_scpi.html',
        {'divergencias': [linha]},
    )


def test_saldos_da_divergencia_passam_pela_politica_de_precisao():
    """`820,000` em pt-BR se lê *oitocentos e vinte mil*.

    `DecimalField(decimal_places=3)` impresso cru chega ao HTML como `820.000` e
    a localização pt-BR do Django o renderiza com vírgula. É o bug que
    `apps/core/quantidades.py` existe para matar, na tela cuja função inteira é
    comparar dois saldos — e o delta ao lado, no mesmo cartão, já obedecia.
    """
    html = _render_cartoes_divergencias('820.000', '750.000', '-70.000')
    assert '820,000' not in html
    assert '750,000' not in html
    assert '>820<' in html.replace(' ', '').replace('\n', '')
    assert '>750<' in html.replace(' ', '').replace('\n', '')


def test_saldo_fracionario_da_divergencia_mantem_a_casa_significativa():
    """Sem unidade (o CSV do SCPI não a informa) a política degrada para casa
    significativa — o mesmo caminho do átomo do delta."""
    html = _render_cartoes_divergencias('18.750', '18.500', '-0.250')
    assert '18,75' in html
    assert '18,750' not in html
    # Notação pt-BR: nunca o ponto, que aqui seria lido como separador de milhar.
    assert '18.75' not in html
