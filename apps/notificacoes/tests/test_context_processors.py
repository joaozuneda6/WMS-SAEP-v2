"""Testes do context processor que alimenta o sino.

O processor roda em toda página autenticada, então o que ele faz quando o
seletor levanta é decisão de produto, não detalhe: um fallback para zero é
indistinguível de "nada pendente" e desfaz por outro caminho a garantia da
#175 — que a conta do sino possa ser conferida contra a Fila de autorização
sem discordar dela (issue #183).
"""

import pytest
from django.db import OperationalError
from django.test import RequestFactory

from apps.notificacoes import context_processors
from apps.notificacoes.context_processors import notificacoes_ctx


@pytest.fixture
def request_de(chefe_obras):
    """Request autenticado, sem passar pela pilha de middleware."""
    request = RequestFactory().get('/')
    request.user = chefe_obras
    return request


@pytest.mark.django_db
def test_falha_de_banco_nao_finge_fila_vazia(monkeypatch, request_de):
    """Indisponibilidade do banco vira ``None``, nunca zero.

    Zero mente: afirma que o destinatário não tem nada a fazer. ``None`` diz
    "não sei", e o template omite o badge em vez de desenhar uma fila vazia
    que ninguém apurou.
    """

    def indisponivel(_destinatario_id):
        raise OperationalError('conexão perdida')

    monkeypatch.setattr(
        context_processors, 'contagem_de_notificacoes_pendentes', indisponivel
    )

    assert notificacoes_ctx(request_de) == {'notificacoes_pendentes': None}


@pytest.mark.django_db
def test_defeito_de_codigo_propaga(monkeypatch, request_de):
    """Bug no seletor derruba a página, como já derruba no vizinho.

    ``flags_de_papel`` (requisições) roda ``papel_efetivo`` sem defesa alguma e
    está registrado **antes** deste processor em ``TEMPLATES``. Uma regressão de
    código que quebrasse a resolução de papel já derrubaria a página ali. Engolir
    a mesma classe de erro aqui não protegeria requisição nenhuma — só trocaria
    o sintoma por silêncio.
    """

    def regressao(_destinatario_id):
        raise AttributeError('campo renomeado')

    monkeypatch.setattr(
        context_processors, 'contagem_de_notificacoes_pendentes', regressao
    )

    with pytest.raises(AttributeError):
        notificacoes_ctx(request_de)


def test_anonimo_conta_zero_de_verdade():
    """Para quem não está autenticado, zero é fato apurado, não fallback."""
    request = RequestFactory().get('/')
    request.user = None

    assert notificacoes_ctx(request) == {'notificacoes_pendentes': 0}


@pytest.mark.django_db
def test_sino_sem_contagem_apurada_omite_badge_e_sufixo_do_rotulo(
    monkeypatch, client, chefe_obras
):
    """O ``None`` não vaza para a tela por nenhuma das duas saídas.

    ``base_auth.html`` lê a variável em dois lugares — o sufixo do ``aria-label``
    e o badge — e ambos são ``{% if %}``. Trava as duas: sem contagem apurada, o
    rótulo do sino é só "Notificações" e nenhum número é desenhado.
    """

    def indisponivel(_destinatario_id):
        raise OperationalError('conexão perdida')

    monkeypatch.setattr(
        context_processors, 'contagem_de_notificacoes_pendentes', indisponivel
    )
    client.force_login(chefe_obras)

    resp = client.get('/notificacoes/')
    html = resp.content.decode()

    assert resp.status_code == 200
    assert 'aria-label="Notificações"' in html
    assert '>None<' not in html


@pytest.mark.django_db
def test_sino_com_contagem_apurada_desenha_numero_e_sufixo(
    monkeypatch, client, chefe_obras
):
    """Controle positivo: o par acima só vale se o caminho feliz ainda escrever."""
    monkeypatch.setattr(
        context_processors, 'contagem_de_notificacoes_pendentes', lambda _pk: 3
    )
    client.force_login(chefe_obras)

    resp = client.get('/notificacoes/')
    html = resp.content.decode()

    assert 'aria-label="Notificações — 3 pendentes"' in html
    assert '>3<' in html
