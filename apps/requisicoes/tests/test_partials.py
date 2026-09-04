"""Testes diretos de partials de badge de domínio (sem DB, sem view).

Cobre a Decisão A-1 da issue #122: `_estado_badge.html` para de anular o
fallback vermelho de `components/badge.html` — estado não mapeado passa a
gritar em vez de virar um badge cinza plausível.
"""

from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string

ESTADOS_CANONICOS = {
    'rascunho': 'slate',
    'aguardando_autorizacao': 'amber-strong',
    'autorizada': 'blue',
    'pronta_para_retirada': 'blue-strong',
    'atendida': 'green',
    'recusada': 'red-strong',
    'cancelada': 'cancel',
    'estornada': 'teal-strong',
}


def _requisicao(estado, label='Rótulo do estado'):
    return SimpleNamespace(estado=estado, get_estado_display=lambda: label)


def _render(estado, label='Rótulo do estado'):
    return render_to_string(
        'requisicoes/partials/_estado_badge.html',
        {'requisicao': _requisicao(estado, label)},
    )


def test_estado_inexistente_renderiza_indisponivel_visivel():
    html = _render('estado-que-nao-existe')
    assert 'Indisponível' in html


def test_estado_inexistente_emite_data_badge_variant_prefixado():
    html = _render('estado-que-nao-existe')
    assert 'data-badge-variant="desconhecida:estado-que-nao-existe"' in html


def test_estado_cancel_colide_com_variante_de_catalogo_mas_gruda_no_fallback():
    """`cancel` é nome de variante do badge.html — a colisão precisa ser impossível."""
    html = _render('cancel')
    assert 'Indisponível' in html
    assert 'bg-cancel-muted' not in html


def test_estado_inexistente_preserva_rotulo_real_em_sr_only():
    html = _render('estado-que-nao-existe', label='Aguardando autorização')
    assert 'Aguardando autorização' in html


@pytest.mark.parametrize('estado,variant_esperada', sorted(ESTADOS_CANONICOS.items()))
def test_estado_canonico_mantem_variante_de_hoje(estado, variant_esperada):
    html = _render(estado)
    marcadores = {
        'slate': 'bg-bg-subtle',
        'amber-strong': 'bg-warning-muted-strong',
        'blue': 'bg-primary-muted ',
        'blue-strong': 'bg-primary-muted-strong',
        'green': 'bg-success-muted',
        'red-strong': 'bg-danger-muted-strong',
        'cancel': 'bg-cancel-muted',
        'teal-strong': 'bg-return-muted-strong',
    }[variant_esperada]
    assert marcadores in html
