"""Testes de contrato HTTP para views de rascunho (ADR-0010).

Verifica: auth, status codes, redirects, mutations mínimas, presença de messages.
Sem testar HTML detalhado ou texto completo de mensagens.
"""

import re
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.contrato_modal import assert_copy_nao_diverge
from apps.core.tests.documento import (
    assert_dialogo_nomeado_pelo_proprio_titulo,
    assert_html_balanceado,
    assert_sem_id_duplicado,
    ids_do_documento,
)
from apps.requisicoes import views
from apps.requisicoes.models import (
    CancelamentoVariant,
    EstadoRequisicao,
    EventoTimeline,
    ItemRequisicao,
    Requisicao,
    TimelineRequisicao,
)
from apps.requisicoes.services import criar_requisicao


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, user):
    # `force_login` e não `client.login`: com o lockout do axes ativo
    # (ADR-0018), `AxesStandaloneBackend` recusa autenticar sem um `request`,
    # que o test client não repassa. `force_login` é o idioma do resto da
    # suíte e monta a sessão direto, que é o que estes testes de view querem.
    client.force_login(user)


class _AberturaDosDialogos(HTMLParser):
    """Para cada `<dialog>`, se ele veio com o atributo `open` (#134)."""

    def __init__(self):
        super().__init__()
        self.abertura = {}

    def handle_starttag(self, tag, attrs):
        if tag != 'dialog':
            return
        atributos = dict(attrs)
        self.abertura[atributos.get('id')] = 'open' in atributos


def _dialogos_abertos(html):
    parser = _AberturaDosDialogos()
    parser.feed(html)
    return parser.abertura


def _formset_post(material_id, quantidade='5', extra=None):
    data = {
        'observacao_geral': '',
        'itens-TOTAL_FORMS': '1',
        'itens-INITIAL_FORMS': '0',
        'itens-MIN_NUM_FORMS': '0',
        'itens-MAX_NUM_FORMS': '1000',
        'itens-0-material_id': str(material_id),
        'itens-0-material_label': 'Material Teste',
        'itens-0-quantidade_solicitada': quantidade,
    }
    if extra:
        data.update(extra)
    return data


# ---------------------------------------------------------------------------
# GET /requisicoes/nova/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_nova_requisicao_get_sem_login(client):
    url = reverse('requisicoes:nova_requisicao')
    resp = client.get(url)
    assert resp.status_code == 302
    assert '/login' in resp['Location'] or 'accounts' in resp['Location']


@pytest.mark.django_db
def test_nova_requisicao_get_com_login(client, solicitante):
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:nova_requisicao'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_nova_requisicao_get_container_itens_usa_factory_alpine(client, solicitante):
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:nova_requisicao'))
    html = resp.content.decode()
    assert 'id="itens-container"' in html
    # A factory passa a receber o prefixo do formset para ler o TOTAL_FORMS,
    # que é a fonte única do índice da próxima linha.
    assert 'x-data="itensFormset({ prefixo: \'itens\' })"' in html
    assert 'data-itens-container' in html


@pytest.mark.django_db
def test_nova_requisicao_get_botao_remover_usa_click_alpine_sem_onclick(
    client, solicitante
):
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:nova_requisicao'))
    html = resp.content.decode()
    assert '@click="removerLinha($event)"' in html
    assert 'onclick=' not in html


# ---------------------------------------------------------------------------
# POST /requisicoes/nova/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_nova_requisicao_post_valido_cria_e_redireciona(
    client, solicitante, material_disponivel
):
    _login(client, solicitante)
    data = _formset_post(material_disponivel.pk)
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)

    req = Requisicao.objects.filter(criador=solicitante).first()
    assert req is not None
    assert req.estado == EstadoRequisicao.RASCUNHO
    assert resp.status_code == 302
    assert reverse('requisicoes:detalhe', kwargs={'pk': req.pk}) in resp['Location']


@pytest.mark.django_db
def test_nova_requisicao_post_acao_enviar_cria_e_envia(
    client, solicitante, chefe_obras, material_disponivel
):
    """Botão 'Criar e enviar' cria rascunho + envia para autorização atomicamente."""
    _login(client, solicitante)
    data = _formset_post(material_disponivel.pk, extra={'acao': 'enviar'})
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)

    req = Requisicao.objects.filter(criador=solicitante).first()
    assert req is not None
    assert req.estado == EstadoRequisicao.AGUARDANDO_AUTORIZACAO
    assert req.numero_publico is not None
    assert resp.status_code == 302
    assert reverse('requisicoes:detalhe', kwargs={'pk': req.pk}) in resp['Location']

    eventos = list(req.eventos.values_list('evento', flat=True))
    assert 'criacao' in eventos
    assert 'envio_autorizacao' in eventos


@pytest.mark.django_db
def test_nova_requisicao_acao_enviar_setor_sem_autorizador_nao_cria_nada(
    client, solicitante, material_disponivel
):
    """Guard de #103 no fluxo composto: formulário volta com warning, nada persistido."""
    from django.contrib.messages import constants as message_constants

    _login(client, solicitante)
    data = _formset_post(material_disponivel.pk, extra={'acao': 'enviar'})
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)

    assert resp.status_code == 200
    assert not Requisicao.objects.exists()
    assert not TimelineRequisicao.objects.exists()

    msgs = list(resp.context['messages'])
    assert any(
        m.level == message_constants.WARNING and 'chefe ativo' in str(m) for m in msgs
    )


@pytest.mark.django_db
def test_nova_requisicao_post_acao_rascunho_explicito(
    client, solicitante, material_disponivel
):
    """acao='rascunho' redireciona para o detalhe do rascunho criado."""
    _login(client, solicitante)
    data = _formset_post(material_disponivel.pk, extra={'acao': 'rascunho'})
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)

    req = Requisicao.objects.filter(criador=solicitante).first()
    assert req.estado == EstadoRequisicao.RASCUNHO
    assert req.numero_publico is None
    assert resp.status_code == 302
    assert reverse('requisicoes:detalhe', kwargs={'pk': req.pk}) in resp['Location']


@pytest.mark.django_db
def test_nova_requisicao_post_sem_acao_default_eh_rascunho(
    client, solicitante, material_disponivel
):
    """Enter em campo → POST sem 'acao' → default seguro = rascunho.

    Guarda contra regressão: 'Criar e enviar' NÃO pode ser o default ao
    pressionar Enter em um input. View deve cair no ramo rascunho.
    """
    _login(client, solicitante)
    data = _formset_post(material_disponivel.pk)
    assert 'acao' not in data
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)

    req = Requisicao.objects.filter(criador=solicitante).first()
    assert req.estado == EstadoRequisicao.RASCUNHO
    assert req.numero_publico is None
    assert resp.status_code == 302
    assert reverse('requisicoes:detalhe', kwargs={'pk': req.pk}) in resp['Location']


@pytest.mark.django_db
def test_nova_requisicao_post_sem_itens_retorna_form(client, solicitante):
    _login(client, solicitante)
    data = {
        'observacao_geral': '',
        'itens-TOTAL_FORMS': '1',
        'itens-INITIAL_FORMS': '0',
        'itens-MIN_NUM_FORMS': '0',
        'itens-MAX_NUM_FORMS': '1000',
        'itens-0-material_id': '',
        'itens-0-material_label': '',
        'itens-0-quantidade_solicitada': '',
    }
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)
    assert resp.status_code == 200
    assert not Requisicao.objects.filter(criador=solicitante).exists()


@pytest.mark.django_db
def test_nova_requisicao_post_forjado_beneficiario_fora_escopo(
    client, solicitante, usuario_ti, material_disponivel
):
    """Solicitante com modo='proprio' não pode forjar beneficiario_id via POST.

    O form em modo 'proprio' remove os campos modo_criacao e beneficiario_id, de
    forma que dados extra no payload são silenciosamente ignorados. A view cria a
    requisição para o próprio solicitante e redireciona normalmente (302).
    """
    _login(client, solicitante)
    data = _formset_post(
        material_disponivel.pk,
        extra={
            'modo_criacao': 'outro',
            'beneficiario_id': str(usuario_ti.pk),
        },
    )
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)
    assert resp.status_code == 302
    req = Requisicao.objects.get(criador=solicitante)
    assert req.beneficiario_id == solicitante.pk


@pytest.mark.django_db
def test_nova_requisicao_post_chefe_cria_para_outro_setor_falha(
    client, chefe_obras, usuario_ti, material_disponivel
):
    """Chefe de setor não pode criar para usuário de outro setor.

    O beneficiário fora do escopo é rejeitado no ChoiceField do form (não está nas
    choices geradas pelo escopo). O form fica inválido → re-renderiza com 200 e erros.
    Não há message pois o service não chegou a ser chamado.
    """
    _login(client, chefe_obras)
    data = _formset_post(
        material_disponivel.pk,
        extra={
            'modo_criacao': 'outro',
            'beneficiario_id': str(usuario_ti.pk),
        },
    )
    resp = client.post(reverse('requisicoes:nova_requisicao'), data)
    # Form inválido (beneficiário fora do escopo) → 200 sem redirect
    assert resp.status_code == 200
    assert not Requisicao.objects.filter(criador=chefe_obras).exists()


# drift 1: PermissaoNegada no escopo de criação deve virar 403, não messages+redirect
@pytest.mark.django_db
def test_nova_requisicao_permissao_negada_retorna_403(client, solicitante):
    """Drift 1 (canônico): PermissaoNegada em resolver_escopo_criacao_requisicao deve
    retornar 403, nunca messages.error + redirect."""
    from unittest.mock import patch

    from apps.core.exceptions import PermissaoNegada

    _login(client, solicitante)
    with patch(
        'apps.requisicoes.views.resolver_escopo_criacao_requisicao',
        side_effect=PermissaoNegada('Sem papel de solicitante'),
    ):
        resp = client.get(reverse('requisicoes:nova_requisicao'))

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /requisicoes/<pk>/editar/
# ---------------------------------------------------------------------------


@pytest.fixture
def rascunho_solicitante(db, solicitante, material_disponivel):
    return criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('3'),
            }
        ],
    )


@pytest.mark.django_db
def test_editar_rascunho_get_sem_login(client, rascunho_solicitante):
    url = reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk})
    resp = client.get(url)
    assert resp.status_code == 302
    assert '/login' in resp['Location'] or 'accounts' in resp['Location']


@pytest.mark.django_db
def test_editar_rascunho_get_fora_do_escopo_retorna_404(
    client, outro_usuario_obras, rascunho_solicitante
):
    """Rascunho de terceiro está fora do escopo de visibilidade → 404, não 403.

    ADR-0010: objeto fora do escopo do ator devolve 404 para não revelar
    existência. Um 403 aqui permitiria probing de pk em
    ``/requisicoes/<pk>/editar/`` (#117).
    """
    _login(client, outro_usuario_obras)
    resp = client.get(
        reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk})
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_editar_rascunho_get_estado_diferente_retorna_403(
    client, solicitante, setor_obras
):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-000099',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:editar_rascunho', kwargs={'pk': req.pk}))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_editar_rascunho_get_visivel_nao_criador_retorna_403(
    client, solicitante, outro_usuario_obras, setor_obras
):
    """Objeto visível + ação proibida → 403, e não 404 (#117).

    O beneficiário enxerga a requisição fora de rascunho, então a fronteira do
    ADR-0010 não se aplica: o que barra é a policy de ator
    (``exigir_pode_editar_rascunho``), que exige criador ou superusuário.
    """
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-000117',
        criador=solicitante,
        beneficiario=outro_usuario_obras,
        setor_beneficiario=setor_obras,
    )
    _login(client, outro_usuario_obras)
    resp = client.get(reverse('requisicoes:editar_rascunho', kwargs={'pk': req.pk}))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_editar_rascunho_get_pk_inexistente_retorna_404(client, solicitante):
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:editar_rascunho', kwargs={'pk': 99999}))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_editar_rascunho_get_criador_retorna_200(
    client, solicitante, rascunho_solicitante
):
    _login(client, solicitante)
    resp = client.get(
        reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk})
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_editar_rascunho_get_container_itens_usa_factory_alpine(
    client, solicitante, rascunho_solicitante
):
    _login(client, solicitante)
    resp = client.get(
        reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk})
    )
    html = resp.content.decode()
    assert 'id="itens-container"' in html
    # A factory passa a receber o prefixo do formset para ler o TOTAL_FORMS,
    # que é a fonte única do índice da próxima linha.
    assert 'x-data="itensFormset({ prefixo: \'itens\' })"' in html
    assert 'data-itens-container' in html


@pytest.mark.django_db
def test_editar_rascunho_get_botao_remover_usa_click_alpine_sem_onclick(
    client, solicitante, rascunho_solicitante
):
    _login(client, solicitante)
    resp = client.get(
        reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk})
    )
    html = resp.content.decode()
    assert '@click="removerLinha($event)"' in html
    assert 'onclick=' not in html


# ---------------------------------------------------------------------------
# POST /requisicoes/<pk>/editar/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_editar_rascunho_post_valido_salva_e_redireciona(
    client, solicitante, rascunho_solicitante, material_disponivel
):
    _login(client, solicitante)
    data = _formset_post(
        material_disponivel.pk,
        quantidade='10',
        extra={'observacao_geral': 'Obs editada'},
    )
    resp = client.post(
        reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk}),
        data,
    )
    assert resp.status_code == 302
    assert resp['Location'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': rascunho_solicitante.pk}
    )
    rascunho_solicitante.refresh_from_db()
    assert rascunho_solicitante.observacao_geral == 'Obs editada'


@pytest.mark.django_db
def test_editar_rascunho_post_material_inativo_retorna_200_com_erro(
    client, solicitante, rascunho_solicitante, material_inativo
):
    _login(client, solicitante)
    data = _formset_post(material_inativo.pk)
    resp = client.post(
        reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk}),
        data,
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_editar_rascunho_post_fora_do_escopo_retorna_404(
    client, outro_usuario_obras, rascunho_solicitante, material_disponivel
):
    """A fronteira do ADR-0010 vale para POST, não só para GET (#117).

    ``get_object_or_404`` roda antes do ramo de POST, e a view aceita os dois
    verbos — sem este teste, uma regressão que reintroduzisse o queryset cru no
    caminho de escrita passaria despercebida.
    """
    _login(client, outro_usuario_obras)
    resp = client.post(
        reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk}),
        _formset_post(material_disponivel.pk),
    )
    assert resp.status_code == 404


# drift 2: EstadoInvalido no editar_rascunho deve ser warning, não error
@pytest.mark.django_db
def test_editar_rascunho_estado_invalido_mostra_warning(
    client, solicitante, rascunho_solicitante, material_disponivel
):
    """Drift 2 (canônico): EstadoInvalido em editar_rascunho deve gerar
    messages.warning, nunca messages.error."""
    from unittest.mock import patch

    from django.contrib.messages import constants as message_constants

    from apps.core.exceptions import EstadoInvalido

    _login(client, solicitante)
    url = reverse('requisicoes:editar_rascunho', kwargs={'pk': rascunho_solicitante.pk})
    with patch(
        'apps.requisicoes.views.editar_rascunho',
        side_effect=EstadoInvalido('Rascunho não pode ser editado neste estado'),
    ):
        resp = client.post(
            url,
            _formset_post(material_disponivel.pk),
            follow=True,
        )

    assert resp.status_code == 200
    msgs = list(resp.context['messages'])
    assert any(m.level == message_constants.WARNING for m in msgs)
    assert not any(m.level == message_constants.ERROR for m in msgs)


# ---------------------------------------------------------------------------
# GET /requisicoes/materiais/busca/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_buscar_materiais_sem_login(client):
    resp = client.get(reverse('requisicoes:buscar_materiais'))
    assert resp.status_code == 302


@pytest.mark.django_db
def test_buscar_materiais_retorna_json(client, solicitante, material_disponivel):
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:buscar_materiais'), {'q': 'Para'})
    assert resp.status_code == 200
    data = resp.json()
    assert 'resultados' in data


@pytest.mark.django_db
def test_buscar_materiais_shape(client, solicitante, material_disponivel):
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:buscar_materiais'), {'q': 'Para'})
    assert resp.status_code == 200
    data = resp.json()
    assert 'resultados' in data
    assert len(data['resultados']) > 0
    for r in data['resultados']:
        assert 'id' in r
        assert 'nome' in r
        assert 'codigo' in r
        assert 'saldo_disponivel' in r


# opt-out: PermissaoNegada → JsonResponse 403 (não messages+redirect)
@pytest.mark.django_db
def test_buscar_materiais_permissao_negada_retorna_json_403(client, solicitante):
    """Opt-out de buscar_materiais: PermissaoNegada deve retornar JsonResponse 403,
    não redirect com messages (ADR-0011 emenda 2026-06-26)."""
    from unittest.mock import patch

    from apps.core.exceptions import PermissaoNegada

    _login(client, solicitante)
    with patch(
        'apps.requisicoes.views.resolver_escopo_criacao_requisicao',
        side_effect=PermissaoNegada(),
    ):
        resp = client.get(reverse('requisicoes:buscar_materiais'))

    assert resp.status_code == 403
    assert resp['Content-Type'].startswith('application/json')
    assert 'error' in resp.json()


# ---------------------------------------------------------------------------
# buscar_beneficiarios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_buscar_beneficiarios_sem_login(client):
    resp = client.get(reverse('requisicoes:buscar_beneficiarios'))
    assert resp.status_code == 302


@pytest.mark.django_db
def test_buscar_beneficiarios_chefe_setor_retorna_usuarios_do_setor(
    client, chefe_obras, outro_usuario_obras, usuario_ti
):
    _login(client, chefe_obras)
    resp = client.get(reverse('requisicoes:buscar_beneficiarios'), {'q': ''})
    assert resp.status_code == 200
    data = resp.json()
    ids = [r['id'] for r in data['resultados']]
    assert outro_usuario_obras.pk in ids
    assert usuario_ti.pk not in ids


@pytest.mark.django_db
def test_buscar_beneficiarios_filtra_por_nome(client, chefe_obras, outro_usuario_obras):
    _login(client, chefe_obras)
    resp = client.get(reverse('requisicoes:buscar_beneficiarios'), {'q': 'Maria'})
    assert resp.status_code == 200
    data = resp.json()
    nomes = [r['nome'] for r in data['resultados']]
    assert 'Maria Obras' in nomes


@pytest.mark.django_db
def test_buscar_beneficiarios_solicitante_puro_retorna_vazio(client, solicitante):
    _login(client, solicitante)
    resp = client.get(reverse('requisicoes:buscar_beneficiarios'), {'q': ''})
    assert resp.status_code == 200
    data = resp.json()
    assert data['resultados'] == []


@pytest.mark.django_db
def test_buscar_beneficiarios_shape(client, chefe_obras, outro_usuario_obras):
    _login(client, chefe_obras)
    resp = client.get(reverse('requisicoes:buscar_beneficiarios'), {'q': ''})
    assert resp.status_code == 200
    data = resp.json()
    assert 'resultados' in data
    for r in data['resultados']:
        assert 'id' in r
        assert 'nome' in r
        assert 'matricula' in r
        assert 'label' in r


# ---------------------------------------------------------------------------
# Minhas requisições — lista
# ---------------------------------------------------------------------------


@pytest.fixture
def req_rascunho_solicitante(db, solicitante, setor_obras):
    return Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )


@pytest.fixture
def req_enviada_solicitante(db, solicitante, setor_obras):
    return Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-0010',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )


@pytest.fixture
def req_enviada_beneficiario(db, solicitante, outro_usuario_obras, setor_obras):
    return Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-0012',
        criador=solicitante,
        beneficiario=outro_usuario_obras,
        setor_beneficiario=setor_obras,
    )


@pytest.fixture
def req_rascunho_aux_para_solicitante(db, aux_obras, solicitante, setor_obras):
    return Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=aux_obras,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )


@pytest.fixture
def req_outro_setor_view(db, usuario_ti, setor_ti):
    return Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-0011',
        criador=usuario_ti,
        beneficiario=usuario_ti,
        setor_beneficiario=setor_ti,
    )


@pytest.mark.django_db
def test_minhas_get_sem_login_redireciona(client):
    response = client.get(reverse('requisicoes:minhas'))
    assert response.status_code == 302
    assert '/entrar' in response['Location'] or '/login' in response['Location']


@pytest.mark.django_db
def test_minhas_get_autenticado_200(client, solicitante, req_enviada_solicitante):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    assert response.status_code == 200
    requisicoes = list(response.context['requisicoes'])
    assert req_enviada_solicitante in requisicoes
    html = response.content.decode('utf-8')
    menu_html = html[
        html.index('aria-label="Navegação"') : html.index('app-bar__menu-divider')
    ]
    assert reverse('requisicoes:minhas') in menu_html
    assert 'aria-current="page"' in menu_html


@pytest.mark.django_db
def test_minhas_exibe_autorizacoes_para_chefe_ativo(client, chefe_obras):
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:minhas'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert reverse('requisicoes:autorizacoes') in html


@pytest.mark.django_db
def test_minhas_oculta_autorizacoes_para_chefe_inativo(client, chefe_obras):
    chefe_obras.setor.ativo = False
    chefe_obras.setor.save(update_fields=['ativo'])

    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:minhas'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert reverse('requisicoes:autorizacoes') not in html


@pytest.mark.django_db
def test_minhas_exclui_rascunho_de_terceiro(
    client, solicitante, req_rascunho_aux_para_solicitante
):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    assert response.status_code == 200
    assert req_rascunho_aux_para_solicitante not in list(
        response.context['requisicoes']
    )


@pytest.mark.django_db
def test_minhas_renderiza_numero_publico_e_fallback_rascunho(
    client, solicitante, req_rascunho_solicitante, req_enviada_solicitante
):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    html = response.content.decode()
    assert 'REQ-2026-0010' in html
    assert 'Rascunho' in html


@pytest.mark.django_db
def test_minhas_botao_ver_detalhes_corrige_drift_a11y(
    client, solicitante, req_enviada_solicitante
):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    html = response.content.decode()
    aria_label = 'Ver detalhes da requisição REQ-2026-0010'
    marker = f'aria-label="{aria_label}"'
    assert html.count(marker) == 1, 'sem tabela, o nome acessível aparece uma vez'
    tag = html[
        html.rindex('<a', 0, html.index(marker)) : html.index('>', html.index(marker))
        + 1
    ]
    # O alvo deixou de ser o botão de 109×44px e passou a ser o cartão inteiro:
    # o piso de 44px é do <article>, não desta âncora de texto, e o anel de foco
    # vem do chrome via `has-[a[data-cartao-link]:focus-visible]`. O guarda
    # `test_link_de_cartao_tem_o_cartao_como_alvo` amarra as duas peças.
    assert 'data-cartao-link' in tag
    assert 'min-h-11' not in tag
    assert 'py-1.5' not in tag


@pytest.mark.django_db
def test_minhas_botao_ver_detalhes_rascunho_preserva_aria_label(
    client, solicitante, req_rascunho_solicitante
):
    """Rascunho não tem número público; o nome acessível o distingue pelo
    beneficiário e pela data/hora de criação, nunca pela PK — que é dado de
    infraestrutura. O `aria-label` do único filho vira o nome acessível do
    heading, então o beneficiário precisa estar nele (PR #40).
    """
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    html = response.content.decode()
    criada_em = timezone.localtime(req_rascunho_solicitante.criado_em).strftime(
        '%d/%m/%Y %H:%M'
    )
    beneficiario = req_rascunho_solicitante.beneficiario.nome
    aria_label = f'Ver detalhes do rascunho de {beneficiario} criado em {criada_em}'
    assert html.count(f'aria-label="{aria_label}"') == 1
    assert f'Rascunho #{req_rascunho_solicitante.pk}' not in html


@pytest.mark.django_db
def test_minhas_renderiza_um_cartao_por_requisicao(
    client, solicitante, req_enviada_solicitante
):
    """Sem tabela, o cartão é a única renderização: um <article> por registro,
    dentro do grid do chrome compartilhado.
    """
    _login(client, solicitante)
    conteudo = client.get(reverse('requisicoes:minhas')).content.decode()
    assert '<div class="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">' in conteudo
    assert (
        conteudo.count('<article class="relative rounded-xl border border-border') == 1
    )
    assert req_enviada_solicitante.numero_publico in conteudo


@pytest.mark.django_db
def test_minhas_vazia_exibe_empty_state_com_cta_canonico(client, solicitante):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    html = response.content.decode()
    assert 'border-dashed border-border-strong' in html
    titulo_idx = html.index('Nenhuma requisição ainda')
    match = re.search(r'<a\b[^>]*>', html[titulo_idx:])
    assert match is not None
    tag = match.group()
    assert re.search(r'href="[^"]*"', tag)
    assert 'min-h-11' in tag
    assert 'focus-visible:ring-border-focus' in tag
    assert 'justify-center' in tag
    assert 'focus-visible:ring-offset-1' in tag
    assert 'ring-offset-2' not in tag


# ---------------------------------------------------------------------------
# Detalhe da requisição
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_detalhe_sem_login_redireciona(client, req_enviada_solicitante):
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_detalhe_criador_200(client, solicitante, req_enviada_solicitante):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    assert response.status_code == 200
    assert response.context['requisicao'].pk == req_enviada_solicitante.pk


@pytest.mark.django_db
def test_detalhe_rascunho_de_terceiro_para_beneficiario_404(
    client, solicitante, req_rascunho_aux_para_solicitante
):
    _login(client, solicitante)
    response = client.get(
        reverse(
            'requisicoes:detalhe',
            kwargs={'pk': req_rascunho_aux_para_solicitante.pk},
        )
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_detalhe_outro_setor_sem_papel_404(client, solicitante, req_outro_setor_view):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_outro_setor_view.pk})
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_detalhe_chefe_setor_ve_requisicao_do_setor(
    client, chefe_obras, req_enviada_solicitante
):
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_detalhe_chefe_setor_nao_ve_rascunho_de_terceiro(
    client, chefe_obras, req_rascunho_solicitante
):
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_rascunho_solicitante.pk})
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_detalhe_almox_ve_outro_setor(client, aux_almoxarifado, req_outro_setor_view):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_outro_setor_view.pk})
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_detalhe_renderiza_timeline_e_itens(
    client, solicitante, material_disponivel, setor_obras
):
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('3'),
            }
        ],
    )
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert list(response.context['itens'])
    assert list(response.context['eventos'])


# ---------------------------------------------------------------------------
# Enviar rascunho — TR-005
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_enviar_rascunho_get_retorna_405(client, solicitante, setor_obras):
    _login(client, solicitante)
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    response = client.get(reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk}))
    assert response.status_code == 405


@pytest.mark.django_db
def test_enviar_rascunho_post_sem_login_redireciona(client, solicitante, setor_obras):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    response = client.post(
        reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk})
    )
    assert response.status_code == 302
    assert '/login' in response.url or '/accounts/login' in response.url


@pytest.mark.django_db
def test_enviar_rascunho_post_nao_criador_retorna_403(
    client, solicitante, outro_usuario_obras, setor_obras
):
    _login(client, outro_usuario_obras)
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    response = client.post(
        reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk})
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_enviar_rascunho_post_criador_redireciona_detalhe(
    client, solicitante, chefe_obras, material_disponivel
):
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    response = client.post(
        reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk})
    )
    assert response.status_code == 302
    assert response.url == reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
    req.refresh_from_db()
    assert req.estado == EstadoRequisicao.AGUARDANDO_AUTORIZACAO
    assert req.numero_publico is not None


@pytest.mark.django_db
def test_enviar_rascunho_post_estado_invalido_mostra_warning(
    client, solicitante, setor_obras, material_disponivel
):
    """EstadoInvalido vira messages.warning (contrato de mensagens)."""
    from django.contrib.messages import constants as message_constants

    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    req.estado = EstadoRequisicao.AGUARDANDO_AUTORIZACAO
    req.numero_publico = 'REQ-2026-000777'
    req.save(update_fields=['estado', 'numero_publico'])

    response = client.post(
        reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk}),
        follow=True,
    )
    assert response.status_code == 200
    msgs = list(response.context['messages'])
    assert any(
        m.level == message_constants.WARNING and 'não é permitida' in str(m)
        for m in msgs
    )


@pytest.mark.django_db
def test_enviar_rascunho_htmx_retorna_hx_redirect(
    client, solicitante, chefe_obras, material_disponivel
):
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    response = client.post(
        reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk}),
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': req.pk}
    )


@pytest.mark.django_db
def test_enviar_rascunho_setor_sem_autorizador_mostra_warning(
    client, solicitante, material_disponivel
):
    """ConflitoDominio de #103 vira messages.warning + PRG, não 500."""
    from django.contrib.messages import constants as message_constants

    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )

    response = client.post(
        reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk})
    )
    assert response.status_code == 302
    assert response['Location'] == reverse('requisicoes:detalhe', kwargs={'pk': req.pk})

    req.refresh_from_db()
    assert req.estado == EstadoRequisicao.RASCUNHO
    assert req.numero_publico is None

    msgs = list(client.get(response['Location']).context['messages'])
    assert any(
        m.level == message_constants.WARNING and 'chefe ativo' in str(m) for m in msgs
    )


@pytest.mark.django_db
def test_enviar_rascunho_setor_sem_autorizador_htmx_retorna_hx_redirect(
    client, solicitante, material_disponivel
):
    """Sob HTMX o mesmo conflito vira 204 + HX-Redirect (contrato de mensagens)."""
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )

    response = client.post(
        reverse('requisicoes:enviar_rascunho', kwargs={'pk': req.pk}),
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': req.pk}
    )

    req.refresh_from_db()
    assert req.estado == EstadoRequisicao.RASCUNHO


@pytest.mark.django_db
def test_detalhe_exibe_botao_enviar_para_criador_em_rascunho(
    client, solicitante, material_disponivel
):
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert response.context['pode_enviar'] is True
    assert 'Enviar para autorização' in response.content.decode('utf-8')


@pytest.mark.django_db
def test_detalhe_nao_exibe_botao_enviar_em_estado_nao_rascunho(
    client, solicitante, material_disponivel
):
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    req.estado = EstadoRequisicao.AGUARDANDO_AUTORIZACAO
    req.numero_publico = 'REQ-2026-000888'
    req.save(update_fields=['estado', 'numero_publico'])

    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert response.context['pode_enviar'] is False


@pytest.mark.django_db
def test_detalhe_exibe_link_editar_para_criador_em_rascunho(
    client, solicitante, material_disponivel
):
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert response.context['pode_editar'] is True
    url_editar = reverse('requisicoes:editar_rascunho', kwargs={'pk': req.pk})
    assert url_editar in response.content.decode('utf-8')


@pytest.mark.django_db
def test_detalhe_nao_exibe_link_editar_para_nao_criador(
    client, solicitante, outro_usuario_obras, material_disponivel, setor_obras
):
    """Outro usuário do mesmo setor não vê rascunho de terceiro — nem o link."""
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    _login(client, outro_usuario_obras)
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    # rascunho de terceiro → 404 (selector unifica visibilidade)
    assert response.status_code == 404


@pytest.mark.django_db
def test_detalhe_nao_exibe_link_editar_em_estado_nao_rascunho(
    client, solicitante, material_disponivel
):
    _login(client, solicitante)
    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    req.estado = EstadoRequisicao.AGUARDANDO_AUTORIZACAO
    req.numero_publico = 'REQ-2026-000555'
    req.save(update_fields=['estado', 'numero_publico'])

    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert response.context['pode_editar'] is False


# ---------------------------------------------------------------------------
# Fila de autorização, retorno e recusa — TR-006 / TR-011
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fila_autorizacao_sem_login_redireciona(client):
    response = client.get(reverse('requisicoes:autorizacoes'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_fila_autorizacao_chefe_renderiza_apenas_setor(
    client, chefe_obras, req_enviada_solicitante, req_outro_setor_view
):
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:autorizacoes'))

    assert response.status_code == 200
    requisicoes = list(response.context['requisicoes'])
    assert req_enviada_solicitante in requisicoes
    assert req_outro_setor_view not in requisicoes
    html = response.content.decode('utf-8')
    assert 'Fila de autorização' in html
    assert 'Analisar' in html
    # A linha "Enviada em" não é asserida aqui: `req_enviada_solicitante` é
    # montada por ORM direto, sem o evento `envio_autorizacao` que alimenta a
    # anotação. O rótulo tem cobertura própria em
    # `test_fila_autorizacao_coluna_enviada_em` (issue #160).
    assert (
        f'aria-label="Analisar requisição {req_enviada_solicitante.numero_publico}"'
        in html
    )


@pytest.mark.django_db
def test_fila_autorizacao_superuser_ve_todos_setores(
    client, superuser, req_enviada_solicitante, req_outro_setor_view
):
    _login(client, superuser)
    response = client.get(reverse('requisicoes:autorizacoes'))

    assert response.status_code == 200
    requisicoes = list(response.context['requisicoes'])
    assert req_enviada_solicitante in requisicoes
    assert req_outro_setor_view in requisicoes
    html = response.content.decode('utf-8')
    assert 'Fila de autorização' in html
    assert 'Analisar' in html


@pytest.mark.django_db
def test_fila_autorizacao_ator_sem_permissao_retorna_403(client, solicitante):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:autorizacoes'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_retornar_rascunho_post_criador_redireciona_e_muda_estado(
    client, solicitante, req_enviada_solicitante
):
    _login(client, solicitante)
    response = client.post(
        reverse(
            'requisicoes:retornar_rascunho', kwargs={'pk': req_enviada_solicitante.pk}
        ),
        {'observacao': 'Corrigir item.'},
    )

    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk}
    )
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.RASCUNHO


@pytest.mark.django_db
def test_retornar_rascunho_post_respeita_next_seguro(
    client, outro_usuario_obras, req_enviada_beneficiario
):
    _login(client, outro_usuario_obras)
    response = client.post(
        reverse(
            'requisicoes:retornar_rascunho', kwargs={'pk': req_enviada_beneficiario.pk}
        ),
        {
            'observacao': 'Corrigir item.',
            'next': reverse('requisicoes:minhas'),
        },
    )

    assert response.status_code == 302
    assert response.url == reverse('requisicoes:minhas')
    req_enviada_beneficiario.refresh_from_db()
    assert req_enviada_beneficiario.estado == EstadoRequisicao.RASCUNHO


@pytest.mark.django_db
def test_retornar_rascunho_beneficiario_redireciona_e_muda_estado(
    client, outro_usuario_obras, req_enviada_beneficiario
):
    _login(client, outro_usuario_obras)
    response = client.post(
        reverse(
            'requisicoes:retornar_rascunho', kwargs={'pk': req_enviada_beneficiario.pk}
        ),
        {'observacao': 'Corrigir item.'},
    )

    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_beneficiario.pk}
    )
    req_enviada_beneficiario.refresh_from_db()
    assert req_enviada_beneficiario.estado == EstadoRequisicao.RASCUNHO


@pytest.mark.django_db
def test_retornar_rascunho_chefe_do_setor_pode_devolver(
    client, chefe_obras, req_enviada_solicitante
):
    """Entrou na Etapa 8, por um beco medido no fluxo.

    O chefe autoriza sem ver saldo, a reserva falha, e sem esta porta as únicas
    saídas eram deixar a requisição parada na fila ou recusar — encerrar em
    definitivo o pedido de alguém porque a quantidade digitada não cabia no
    estoque. Devolver para rascunho descreve o que de fato aconteceu.
    """
    _login(client, chefe_obras)
    response = client.post(
        reverse(
            'requisicoes:retornar_rascunho', kwargs={'pk': req_enviada_solicitante.pk}
        )
    )
    # O POST não manda `HX-Request`, então `htmx_redirect` faz `redirect(url)` e
    # o status é sempre 302. Aceitar 204 deixava uma regressão trocar o PRG
    # nativo por uma resposta sem `Location` sem ficar vermelha.
    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk}
    )
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.RASCUNHO


@pytest.mark.django_db
def test_retornar_rascunho_chefe_de_outro_setor_nao_pode(
    client, chefe_obras, setor_ti, req_enviada_solicitante
):
    """A condição do chefe é a mesma de recusar: chefiar o setor do
    beneficiário. Não abre alcance novo."""
    req_enviada_solicitante.setor_beneficiario = setor_ti
    req_enviada_solicitante.save(update_fields=['setor_beneficiario'])
    _login(client, chefe_obras)
    response = client.post(
        reverse(
            'requisicoes:retornar_rascunho', kwargs={'pk': req_enviada_solicitante.pk}
        )
    )
    assert response.status_code == 403
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.AGUARDANDO_AUTORIZACAO


@pytest.mark.django_db
def test_retornar_rascunho_post_superuser_redireciona_e_muda_estado(
    client, superuser, req_enviada_solicitante
):
    _login(client, superuser)
    response = client.post(
        reverse(
            'requisicoes:retornar_rascunho', kwargs={'pk': req_enviada_solicitante.pk}
        ),
        {'observacao': 'Corrigir item.'},
    )

    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk}
    )
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.RASCUNHO


@pytest.mark.django_db
def test_recusar_requisicao_post_chefe_redireciona_e_muda_estado(
    client, chefe_obras, req_enviada_solicitante
):
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': 'Necessário revisar quantidades.'},
    )

    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk}
    )
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.RECUSADA


@pytest.mark.django_db
def test_recusar_requisicao_post_respeita_next_seguro(
    client, chefe_obras, req_enviada_solicitante
):
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {
            'motivo': 'Necessário revisar quantidades.',
            'next': reverse('requisicoes:autorizacoes'),
        },
    )

    assert response.status_code == 302
    assert response.url == reverse('requisicoes:autorizacoes')
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.RECUSADA


@pytest.mark.django_db
def test_recusar_requisicao_post_superuser_redireciona_e_muda_estado(
    client, superuser, req_enviada_solicitante
):
    _login(client, superuser)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': 'Necessário revisar quantidades.'},
    )

    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk}
    )
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.RECUSADA


@pytest.mark.django_db
def test_recusar_requisicao_sem_motivo_retorna_erro_inline(
    client, chefe_obras, req_enviada_solicitante
):
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': ' '},
    )

    assert response.status_code == 200
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.AGUARDANDO_AUTORIZACAO
    html = response.content.decode('utf-8')
    assert 'modal-recusar-motivo' in html
    assert 'aria-invalid="true"' in html
    assert 'Informe o motivo da recusa.' in html


@pytest.mark.django_db
def test_recusar_sem_motivo_sem_htmx_devolve_o_dialogo_ja_aberto(
    client, chefe_obras, req_enviada_solicitante
):
    """Sem htmx a resposta é a página inteira, e o modal tem que vir com `open`.

    É o caminho de quem está sem JS ou com o Alpine fora do ar (#134): a caixa
    de erro já vinha no HTML, mas dentro de um `<dialog>` fechado — ou seja,
    `display: none`. A tela voltava aparentemente intacta e a pessoa não ficava
    sabendo que a recusa tinha sido rejeitada.

    Os outros diálogos da mesma página continuam fechados: `open` é a marca de
    qual modal falhou, e abrir todos diria a coisa errada.
    """
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': ' '},
    )

    abertura = _dialogos_abertos(response.content.decode('utf-8'))
    assert abertura.get('confirmar-recusar') is True, (
        'O modal que falhou voltou fechado — a recusa some da tela sem aviso.'
    )
    assert [modal for modal, aberto in abertura.items() if aberto] == [
        'confirmar-recusar'
    ]


@pytest.mark.django_db
def test_detalhe_sem_erro_nao_abre_nenhum_dialogo(
    client, chefe_obras, req_enviada_solicitante
):
    """`open` é exceção: um GET normal não pode chegar com modal aberto (#134)."""
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )

    abertura = _dialogos_abertos(response.content.decode('utf-8'))
    assert abertura, 'página de detalhe renderizada sem nenhum <dialog>'
    assert not any(abertura.values())


@pytest.mark.django_db
def test_recusar_requisicao_sem_motivo_via_htmx_retorna_422_fragment(
    client, chefe_obras, req_enviada_solicitante
):
    """HTMX request com motivo vazio retorna 422 + fragment do modal."""
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': ' '},
        HTTP_HX_REQUEST='true',
    )

    assert response.status_code == 422
    html = response.content.decode('utf-8')
    assert 'data-modal-body="confirmar-recusar"' in html
    assert 'data-modal-erro' in html
    assert 'Informe o motivo da recusa.' in html
    assert 'modal-recusar-motivo' in html
    assert '<!DOCTYPE html>' not in html
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.AGUARDANDO_AUTORIZACAO


@pytest.mark.django_db
def test_recusar_requisicao_sucesso_via_htmx_retorna_hx_redirect(
    client, chefe_obras, req_enviada_solicitante
):
    """HTMX request com motivo válido retorna 204 + HX-Redirect."""
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': 'Sem orçamento aprovado.'},
        HTTP_HX_REQUEST='true',
    )

    assert response.status_code == 204
    assert 'HX-Redirect' in response.headers
    req_enviada_solicitante.refresh_from_db()
    assert req_enviada_solicitante.estado == EstadoRequisicao.RECUSADA


@pytest.mark.django_db
def test_recusar_requisicao_outro_setor_retorna_403(
    client, chefe_almoxarifado, req_enviada_solicitante
):
    _login(client, chefe_almoxarifado)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': 'Não aprovado.'},
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_detalhe_exibe_recusa_e_retorno_para_chefe(
    client, chefe_obras, req_enviada_solicitante
):
    """O painel de decisão do chefe passa a ter a saída não-terminal."""
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    html = response.content.decode('utf-8')

    assert response.status_code == 200
    assert response.context['pode_recusar'] is True
    assert response.context['pode_retornar'] is True
    assert 'Confirmar recusa' in html
    assert 'Confirmar retorno' in html
    assert 'data-modal-trigger="confirmar-recusar"' in html
    assert 'window.confirm' not in html
    assert html.count('id="decisao-autorizacao-titulo"') == 1


@pytest.mark.django_db
def test_detalhe_com_painel_de_decisao_nao_repete_nenhum_id(
    client, chefe_obras, req_enviada_solicitante
):
    """#131: o card do painel derivava `{{ modal_id }}-titulo`, o mesmo id do
    `<h2>` do modal que ele abre. Id duplicado é HTML inválido e torna qualquer
    `getElementById` imprevisível."""
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    html = response.content.decode('utf-8')

    assert_sem_id_duplicado(html)
    assert 'confirmar-recusar-painel-titulo' in ids_do_documento(html)


@pytest.mark.django_db
def test_dialog_e_nomeado_pelo_titulo_do_proprio_modal(
    client, chefe_obras, req_enviada_solicitante
):
    """O nome acessível do `<dialog>` tem que ser o `<h2>` do corpo do modal.
    Com o id duplicado, `aria-labelledby` resolvia para o `<h3>` do cartão que
    ficou atrás: via-se "Recusar requisição?" e ouvia-se "Recusar requisição"."""
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    html = response.content.decode('utf-8')

    assert_dialogo_nomeado_pelo_proprio_titulo(html)


@pytest.mark.django_db
def test_detalhe_exibe_autorizar_para_chefe_e_nao_exibe_para_outro_papel(
    client, chefe_obras, aux_almoxarifado, material_disponivel
):
    from apps.requisicoes.services import enviar_para_autorizacao

    _login(client, chefe_obras)
    req = criar_requisicao(
        ator_id=chefe_obras.pk,
        beneficiario_id=chefe_obras.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('2'),
            }
        ],
    )
    req = enviar_para_autorizacao(ator_id=chefe_obras.pk, requisicao_id=req.pk)

    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    html = response.content.decode('utf-8')

    assert response.status_code == 200
    assert response.context['pode_autorizar'] is True
    assert 'Autorizar' in html
    assert 'Analisar' not in html

    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    html = response.content.decode('utf-8')

    assert response.status_code == 200
    assert response.context['pode_autorizar'] is False
    assert 'Autorizar' not in html
    assert 'Analisar' not in html


@pytest.mark.django_db
def test_autorizar_requisicao_post_chefe_redireciona_e_muda_estado(
    client, chefe_obras, material_disponivel
):
    from apps.requisicoes.services import enviar_para_autorizacao

    _login(client, chefe_obras)
    req = criar_requisicao(
        ator_id=chefe_obras.pk,
        beneficiario_id=chefe_obras.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('2'),
            }
        ],
    )
    req = enviar_para_autorizacao(ator_id=chefe_obras.pk, requisicao_id=req.pk)

    response = client.post(reverse('requisicoes:autorizar', kwargs={'pk': req.pk}))

    assert response.status_code == 302
    assert response.url == reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
    req.refresh_from_db()
    item = req.itens.get()
    assert req.estado == EstadoRequisicao.AUTORIZADA
    assert item.quantidade_autorizada == item.quantidade_solicitada


@pytest.mark.django_db
def test_autorizar_requisicao_htmx_retorna_hx_redirect(
    client, chefe_obras, material_disponivel
):
    from apps.requisicoes.services import enviar_para_autorizacao

    _login(client, chefe_obras)
    req = criar_requisicao(
        ator_id=chefe_obras.pk,
        beneficiario_id=chefe_obras.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('2'),
            }
        ],
    )
    req = enviar_para_autorizacao(ator_id=chefe_obras.pk, requisicao_id=req.pk)

    response = client.post(
        reverse('requisicoes:autorizar', kwargs={'pk': req.pk}),
        HTTP_HX_REQUEST='true',
    )

    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': req.pk}
    )


@pytest.mark.django_db
def test_autorizar_requisicao_post_estado_invalido_redireciona(
    client, chefe_obras, material_disponivel
):
    _login(client, chefe_obras)
    req = criar_requisicao(
        ator_id=chefe_obras.pk,
        beneficiario_id=chefe_obras.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('2'),
            }
        ],
    )

    response = client.post(reverse('requisicoes:autorizar', kwargs={'pk': req.pk}))

    assert response.status_code == 302
    assert response.url == reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
    req.refresh_from_db()
    assert req.estado == EstadoRequisicao.RASCUNHO


@pytest.mark.django_db
def test_autorizar_requisicao_post_sem_permissao_retorna_403(
    client, chefe_almoxarifado, req_enviada_solicitante
):
    _login(client, chefe_almoxarifado)
    response = client.post(
        reverse('requisicoes:autorizar', kwargs={'pk': req_enviada_solicitante.pk})
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_detalhe_exibe_retorno_para_criador_e_nao_exibe_recusa(
    client, solicitante, req_enviada_solicitante
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    html = response.content.decode('utf-8')

    assert response.status_code == 200
    assert response.context['pode_retornar'] is True
    assert response.context['pode_recusar'] is False
    assert 'Confirmar retorno' in html
    assert 'Confirmar recusa' not in html


@pytest.mark.django_db
def test_detalhe_autorizar_card_e_modal_tem_copy_diferenciada(
    client, chefe_obras, req_enviada_solicitante
):
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    html = response.content.decode('utf-8')

    modal_copy = (
        'Reserva o saldo necessário para todos os itens sem alterar o saldo físico.'
    )

    assert response.context['pode_autorizar'] is True
    assert html.count(modal_copy) == 1


@pytest.mark.django_db
def test_detalhe_exibe_descartar_rascunho_para_criador_em_rascunho(
    client, solicitante, rascunho_solicitante
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': rascunho_solicitante.pk})
    )
    html = response.content.decode('utf-8')

    assert response.status_code == 200
    assert response.context['pode_cancelar'] is True
    assert (
        response.context['cancelamento_info'].variante == CancelamentoVariant.DESCARTE
    )
    assert response.context['cancelamento_requer_justificativa'] is False
    assert 'role="alertdialog"' in html
    assert 'Descartar rascunho' in html
    # `cancelamento_requer_justificativa=False`: o corpo não tem campo, então
    # a região rolável (quando existir) ainda pode precisar de `tabindex="0"`.
    # Aqui ela nem renderiza (sem `erro`), então o atributo não aparece de
    # qualquer forma — o que importa é que não foi suprimido por engano.
    assert 'data-submit-loading-label="Cancelando…"' in html


@pytest.mark.django_db
def test_detalhe_exibe_cancelar_com_justificativa_para_autorizada(
    client, solicitante, req_autorizada_view
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_autorizada_view.pk})
    )
    html = response.content.decode('utf-8')

    assert response.status_code == 200
    assert response.context['pode_cancelar'] is True
    assert (
        response.context['cancelamento_info'].variante
        == CancelamentoVariant.CANCELAMENTO
    )
    assert response.context['cancelamento_requer_justificativa'] is True
    assert 'Justificativa do cancelamento' in html
    assert 'role="alertdialog"' in html
    assert 'data-submit-loading-label="Cancelando…"' in html
    # `cancelamento_requer_justificativa=True` aqui: o corpo já tem a
    # textarea, então a região rolável não pode ganhar `tabindex="0"` extra.
    assert 'tabindex="0"' not in html


@pytest.mark.django_db
def test_descartar_rascunho_post_redireciona_para_lista(
    client, solicitante, rascunho_solicitante
):
    _login(client, solicitante)
    response = client.post(
        reverse('requisicoes:cancelar', kwargs={'pk': rascunho_solicitante.pk})
    )

    assert response.status_code == 302
    assert response.url == reverse('requisicoes:minhas')
    assert not Requisicao.objects.filter(pk=rascunho_solicitante.pk).exists()


@pytest.mark.django_db
def test_cancelar_requisicao_post_autorizada_sem_justificativa_renderiza_modal_com_erro(
    client, solicitante, req_autorizada_view
):
    _login(client, solicitante)
    response = client.post(
        reverse('requisicoes:cancelar', kwargs={'pk': req_autorizada_view.pk}),
        {'justificativa': ' '},
    )

    assert response.status_code == 200
    assert response.context['cancelamento_modal_aberto'] is True
    assert (
        response.context['cancelamento_erro']
        == 'Informe a justificativa do cancelamento.'
    )
    assert response.context['cancelamento_requer_justificativa'] is True
    req_autorizada_view.refresh_from_db()
    assert req_autorizada_view.estado == EstadoRequisicao.AUTORIZADA
    html = response.content.decode('utf-8')
    assert 'modal-cancelar-justificativa' in html
    assert 'aria-invalid="true"' in html


@pytest.mark.django_db
def test_cancelar_requisicao_sem_justificativa_via_htmx_retorna_422_fragment(
    client, solicitante, req_autorizada_view
):
    """HTMX request com justificativa vazia em autorizada retorna 422 + fragment."""
    _login(client, solicitante)
    response = client.post(
        reverse('requisicoes:cancelar', kwargs={'pk': req_autorizada_view.pk}),
        {'justificativa': ' '},
        HTTP_HX_REQUEST='true',
    )

    assert response.status_code == 422
    html = response.content.decode('utf-8')
    assert 'data-modal-body="confirmar-cancelar"' in html
    assert 'data-modal-erro' in html
    assert 'Informe a justificativa do cancelamento.' in html
    assert 'modal-cancelar-justificativa' in html
    assert '<!DOCTYPE html>' not in html
    req_autorizada_view.refresh_from_db()
    assert req_autorizada_view.estado == EstadoRequisicao.AUTORIZADA


@pytest.mark.django_db
def test_cancelar_copy_do_422_nao_diverge_do_render_inicial(
    client, solicitante, req_autorizada_view
):
    """Título e descrição do modal de cancelamento não podem mudar no 422 (#135)."""
    _login(client, solicitante)
    detalhe_url = reverse('requisicoes:detalhe', kwargs={'pk': req_autorizada_view.pk})
    inicial = client.get(detalhe_url)

    erro = client.post(
        reverse('requisicoes:cancelar', kwargs={'pk': req_autorizada_view.pk}),
        {'justificativa': ' '},
        HTTP_HX_REQUEST='true',
    )

    assert erro.status_code == 422
    assert_copy_nao_diverge(
        erro,
        html_inicial=inicial.content.decode('utf-8'),
        modal_id='confirmar-cancelar',
    )


@pytest.mark.django_db
def test_cancelar_requisicao_post_autorizada_403_para_nao_autorizado(
    client, chefe_obras, req_autorizada_view
):
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:cancelar', kwargs={'pk': req_autorizada_view.pk})
    )

    assert response.status_code == 403
    req_autorizada_view.refresh_from_db()
    assert req_autorizada_view.estado == EstadoRequisicao.AUTORIZADA
    assert req_autorizada_view.numero_publico == 'REQ-2026-9001'


@pytest.mark.django_db
def test_cancelar_requisicao_post_autorizada_redireciona_e_muda_estado(
    client, solicitante, chefe_obras, material_disponivel
):
    from apps.requisicoes.services import (
        autorizar_requisicao,
        criar_requisicao,
        enviar_para_autorizacao,
    )

    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('2'),
            }
        ],
    )
    req = enviar_para_autorizacao(
        ator_id=solicitante.pk,
        requisicao_id=req.pk,
    )
    req = autorizar_requisicao(
        ator_id=chefe_obras.pk,
        requisicao_id=req.pk,
    )

    _login(client, solicitante)
    response = client.post(
        reverse('requisicoes:cancelar', kwargs={'pk': req.pk}),
        {'justificativa': 'Revisão interna do pedido.'},
    )

    assert response.status_code == 302
    assert response.url == reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
    req.refresh_from_db()
    assert req.estado == EstadoRequisicao.CANCELADA


@pytest.mark.django_db
def test_recusar_requisicao_htmx_retorna_hx_redirect(
    client, chefe_obras, req_enviada_solicitante
):
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': 'Não aprovado.'},
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk}
    )


@pytest.mark.django_db
def test_recusar_requisicao_htmx_superuser_retorna_hx_redirect(
    client, superuser, req_enviada_solicitante
):
    _login(client, superuser)
    response = client.post(
        reverse('requisicoes:recusar', kwargs={'pk': req_enviada_solicitante.pk}),
        {'motivo': 'Não aprovado.'},
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk}
    )


# ---------------------------------------------------------------------------
# Fila de atendimento + separar para retirada (TR-009)
# ---------------------------------------------------------------------------


@pytest.fixture
def req_autorizada_view(db, solicitante, setor_obras, material_disponivel):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AUTORIZADA,
        numero_publico='REQ-2026-9001',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req,
        material=material_disponivel,
        quantidade_solicitada=1,
        quantidade_autorizada=1,
    )
    return req


@pytest.fixture
def req_pronta_view(db, solicitante, setor_obras):
    return Requisicao.objects.create(
        estado=EstadoRequisicao.PRONTA_PARA_RETIRADA,
        numero_publico='REQ-2026-9002',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )


@pytest.mark.django_db
def test_fila_atendimento_sem_login_redireciona(client):
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 302
    assert response.url.startswith(reverse('accounts:login'))


@pytest.mark.django_db
def test_fila_atendimento_aux_almox_renderiza_autorizada_e_pronta(
    client, aux_almoxarifado, req_autorizada_view, req_pronta_view
):
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))

    assert response.status_code == 200
    requisicoes = list(response.context['requisicoes'])
    assert req_autorizada_view in requisicoes
    assert req_pronta_view in requisicoes
    html = response.content.decode('utf-8')
    assert 'Fila de atendimento' in html
    # O verbo sai do estado: separar material e entregá-lo a quem retira são
    # operações diferentes, e o cartão dizia "Atender" nas duas.
    assert 'Separar' in html
    assert 'Entregar' in html
    assert 'Atender' not in html


@pytest.mark.django_db
def test_fila_atendimento_link_do_cartao_nomeia_o_verbo_do_estado(
    client, aux_almoxarifado, req_autorizada_view
):
    """O nome acessível carrega o verbo: o número público sozinho não diz o que
    o link faz, e o verbo visível é `aria-hidden` justamente para não duplicar.
    """
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    html = response.content.decode('utf-8')
    assert (
        f'aria-label="Separar requisição {req_autorizada_view.numero_publico}"' in html
    )
    assert 'data-cartao-link' in html


@pytest.mark.django_db
def test_fila_atendimento_chefe_almox_200(
    client, chefe_almoxarifado, req_autorizada_view
):
    _login(client, chefe_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    assert req_autorizada_view in list(response.context['requisicoes'])


@pytest.mark.django_db
def test_fila_atendimento_superuser_200(
    client, superuser, req_autorizada_view, req_pronta_view
):
    _login(client, superuser)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    requisicoes = list(response.context['requisicoes'])
    assert req_autorizada_view in requisicoes
    assert req_pronta_view in requisicoes


@pytest.mark.django_db
def test_fila_atendimento_chefe_setor_403(client, chefe_obras):
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_fila_atendimento_solicitante_403(client, solicitante):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_fila_atendimento_vazia_renderiza_empty_state(client, aux_almoxarifado):
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Nenhuma requisição aguardando atendimento' in html


@pytest.mark.django_db
def test_separar_retirada_post_aux_almox_redireciona_e_muda_estado(
    client, aux_almoxarifado, req_autorizada_view
):
    _login(client, aux_almoxarifado)
    response = client.post(
        reverse('requisicoes:separar_retirada', kwargs={'pk': req_autorizada_view.pk})
    )

    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_autorizada_view.pk}
    )
    req_autorizada_view.refresh_from_db()
    assert req_autorizada_view.estado == EstadoRequisicao.PRONTA_PARA_RETIRADA


@pytest.mark.django_db
def test_separar_retirada_post_mensagem_sucesso_com_numero(
    client, aux_almoxarifado, req_autorizada_view
):
    _login(client, aux_almoxarifado)
    response = client.post(
        reverse('requisicoes:separar_retirada', kwargs={'pk': req_autorizada_view.pk}),
        follow=True,
    )

    mensagens = [str(m) for m in response.context['messages']]
    assert any('REQ-2026-9001' in m and 'pronta para retirada' in m for m in mensagens)


@pytest.mark.django_db
def test_separar_retirada_htmx_retorna_hx_redirect(
    client, aux_almoxarifado, req_autorizada_view
):
    _login(client, aux_almoxarifado)
    response = client.post(
        reverse('requisicoes:separar_retirada', kwargs={'pk': req_autorizada_view.pk}),
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_autorizada_view.pk}
    )


@pytest.mark.django_db
def test_separar_retirada_get_retorna_405(
    client, aux_almoxarifado, req_autorizada_view
):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:separar_retirada', kwargs={'pk': req_autorizada_view.pk})
    )
    assert response.status_code == 405


@pytest.mark.django_db
def test_separar_retirada_chefe_setor_403(client, chefe_obras, req_autorizada_view):
    _login(client, chefe_obras)
    response = client.post(
        reverse('requisicoes:separar_retirada', kwargs={'pk': req_autorizada_view.pk})
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_separar_retirada_estado_invalido_avisa(
    client, aux_almoxarifado, req_pronta_view
):
    _login(client, aux_almoxarifado)
    url = reverse('requisicoes:separar_retirada', kwargs={'pk': req_pronta_view.pk})
    # PRG: sem follow, deve retornar 302 para o detalhe
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == reverse('requisicoes:detalhe', args=[req_pronta_view.pk])
    # Follow e verificar mensagem de warning com texto do EstadoInvalido
    response = client.post(url, follow=True)
    assert response.status_code == 200
    messages_list = list(response.context['messages'])
    assert any('warning' in m.tags and 'autorizada' in m.message for m in messages_list)


@pytest.mark.django_db
def test_separar_retirada_rascunho_404_pois_fora_de_escopo(
    client, aux_almoxarifado, solicitante, setor_obras
):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        numero_publico=None,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    _login(client, aux_almoxarifado)
    response = client.post(
        reverse('requisicoes:separar_retirada', kwargs={'pk': req.pk})
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_detalhe_exibe_botao_separar_para_aux_almox(
    client, aux_almoxarifado, req_autorizada_view
):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_autorizada_view.pk})
    )
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Separar para retirada' in html
    textos = _texto_dos_dialogos(html)
    assert 'confirmar-separar' in textos
    assert req_autorizada_view.numero_publico in textos['confirmar-separar']
    assert req_autorizada_view.beneficiario.nome in textos['confirmar-separar']
    assert response.context['pode_separar_retirada'] is True


@pytest.mark.django_db
def test_detalhe_nao_exibe_botao_separar_para_solicitante(
    client, solicitante, req_autorizada_view
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_autorizada_view.pk})
    )
    assert response.status_code == 200
    assert response.context['pode_separar_retirada'] is False
    html = response.content.decode('utf-8')
    assert 'Separar para retirada' not in html


@pytest.mark.django_db
def test_topbar_exibe_link_atendimento_para_almox(client, aux_almoxarifado):
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:minhas'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Atendimento' in html


@pytest.mark.django_db
def test_topbar_nao_exibe_link_atendimento_para_solicitante(client, solicitante):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Fila de Atendimento' not in html


# ---------------------------------------------------------------------------
# registrar_atendimento_view (TR-016/017/018)
# ---------------------------------------------------------------------------


@pytest.fixture
def req_pronta_view_com_itens(db, solicitante, setor_obras, material_disponivel):
    from apps.estoque.models import SaldoEstoque

    req = Requisicao.objects.create(
        estado=EstadoRequisicao.PRONTA_PARA_RETIRADA,
        numero_publico='REQ-2026-9100',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req,
        material=material_disponivel,
        quantidade_solicitada=Decimal('2'),
        quantidade_autorizada=Decimal('2'),
    )
    saldo = SaldoEstoque.objects.get(material=material_disponivel)
    saldo.saldo_reservado = (saldo.saldo_reservado or 0) + Decimal('2')
    saldo.save(update_fields=['saldo_reservado'])
    return req


def _post_atendimento(
    client, req, *, entregue, justificativa='', retirante='Carlos', observacao=''
):
    item = req.itens.first()
    return client.post(
        reverse('requisicoes:registrar_atendimento', kwargs={'pk': req.pk}),
        data={
            'itens-TOTAL_FORMS': '1',
            'itens-INITIAL_FORMS': '1',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-item_id': str(item.id),
            'itens-0-quantidade_entregue': str(entregue),
            'itens-0-justificativa': justificativa,
            'retirante_nome': retirante,
            'observacao': observacao,
        },
    )


@pytest.mark.django_db
def test_atender_get_sem_login_redireciona(client, req_pronta_view_com_itens):
    response = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_atender_get_aux_almox_renderiza_form(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    )
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Registrar atendimento' in html
    assert 'Retirante' in html


@pytest.mark.django_db
def test_atender_get_dialog_confirmar_usa_modal_componente(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """Dialog de confirmação migrado para components/modal.html (issue #78)."""
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    )
    html = response.content.decode('utf-8')
    assert 'data-modal-trigger="confirmar-atender-retirada"' in html
    assert 'data-modal-confirm' in html
    assert "submeterFormExterno('form-atender-retirada')" in html
    assert 'data-submit-loading-label="Confirmando…"' in html
    dialog_inicio = html.index('id="confirmar-atender-retirada"')
    dialog_fim = html.index('</dialog>', dialog_inicio)
    dialog_html = html[dialog_inicio:dialog_fim]
    assert 'hx-post' not in dialog_html


@pytest.mark.django_db
def test_atender_get_prepreenche_quantidade_decimal_com_ponto(
    client, aux_almoxarifado, solicitante, setor_obras, material_disponivel
):
    from apps.estoque.models import SaldoEstoque

    req = Requisicao.objects.create(
        estado=EstadoRequisicao.PRONTA_PARA_RETIRADA,
        numero_publico='REQ-2026-9101',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req,
        material=material_disponivel,
        quantidade_solicitada=Decimal('5.500'),
        quantidade_autorizada=Decimal('5.500'),
    )
    saldo = SaldoEstoque.objects.get(material=material_disponivel)
    saldo.saldo_reservado = (saldo.saldo_reservado or 0) + Decimal('5.500')
    saldo.save(update_fields=['saldo_reservado'])

    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:registrar_atendimento', kwargs={'pk': req.pk})
    )
    html = response.content.decode('utf-8')
    # Ponto, nunca vírgula: `5,500` seria lido como cinco mil e quinhentos.
    # E sem os zeros à direita que o DecimalField carrega do banco — mas sem
    # arredondar 5,5 para 6, que faria confirmar mais do que foi autorizado.
    assert 'value="5.5"' in html
    assert 'value="5,5"' not in html
    assert 'value="5.500"' not in html


@pytest.mark.django_db
def test_atender_get_solicitante_403(client, solicitante, req_pronta_view_com_itens):
    _login(client, solicitante)
    response = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_atender_post_total_redireciona_e_muda_estado(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = _post_atendimento(
        client, req_pronta_view_com_itens, entregue=Decimal('2')
    )
    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk}
    )
    req_pronta_view_com_itens.refresh_from_db()
    assert req_pronta_view_com_itens.estado == EstadoRequisicao.ATENDIDA


@pytest.mark.django_db
def test_atender_post_total_mensagem_sucesso(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = _post_atendimento(
        client, req_pronta_view_com_itens, entregue=Decimal('2')
    )
    response = client.get(response.url)
    mensagens = [str(m) for m in response.context['messages']]
    assert any(
        'REQ-2026-9100' in m and 'registrada com sucesso' in m for m in mensagens
    )


@pytest.mark.django_db
def test_atender_post_parcial_com_justificativa_ok(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = _post_atendimento(
        client,
        req_pronta_view_com_itens,
        entregue=Decimal('1'),
        justificativa='Falta de material no carrinho.',
    )
    assert response.status_code == 302
    req_pronta_view_com_itens.refresh_from_db()
    assert req_pronta_view_com_itens.estado == EstadoRequisicao.ATENDIDA


@pytest.mark.django_db
def test_atender_post_sem_entrega_avisa(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = _post_atendimento(
        client,
        req_pronta_view_com_itens,
        entregue=Decimal('0'),
        justificativa='Não compareceu',
    )
    assert response.status_code == 302
    req_pronta_view_com_itens.refresh_from_db()
    assert req_pronta_view_com_itens.estado == EstadoRequisicao.PRONTA_PARA_RETIRADA
    response = client.get(response.url)
    mensagens = [str(m) for m in response.context['messages']]
    assert any('entregue maior que zero' in m for m in mensagens)


@pytest.mark.django_db
def test_atender_post_estado_origem_invalido_avisa(
    client, aux_almoxarifado, req_autorizada_view
):
    _login(client, aux_almoxarifado)
    response = client.post(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_autorizada_view.pk},
        ),
        data={
            'itens-TOTAL_FORMS': '0',
            'itens-INITIAL_FORMS': '0',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'retirante_nome': 'X',
        },
    )
    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_autorizada_view.pk}
    )


@pytest.mark.django_db
def test_atender_post_chefe_setor_403(client, chefe_obras, req_pronta_view_com_itens):
    _login(client, chefe_obras)
    response = client.post(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        ),
        data={
            'itens-TOTAL_FORMS': '0',
            'itens-INITIAL_FORMS': '0',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'retirante_nome': 'X',
        },
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_atender_post_form_invalido_renderiza_400(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """Retirante vazio dispara cabecalho.is_valid()=False."""
    _login(client, aux_almoxarifado)
    item = req_pronta_view_com_itens.itens.first()
    response = client.post(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        ),
        data={
            'itens-TOTAL_FORMS': '1',
            'itens-INITIAL_FORMS': '1',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-item_id': str(item.id),
            'itens-0-quantidade_entregue': '2',
            'itens-0-justificativa': '',
            'retirante_nome': '',
        },
    )
    assert response.status_code == 400
    html = response.content.decode('utf-8')
    assert 'Corrija os campos destacados' in html or 'obrigatório' in html.lower()


@pytest.mark.django_db
def test_atender_post_htmx_retorna_hx_redirect(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    item = req_pronta_view_com_itens.itens.first()
    response = client.post(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        ),
        data={
            'itens-TOTAL_FORMS': '1',
            'itens-INITIAL_FORMS': '1',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-item_id': str(item.id),
            'itens-0-quantidade_entregue': '2',
            'itens-0-justificativa': '',
            'retirante_nome': 'Carlos',
            'observacao': '',
        },
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk}
    )


@pytest.mark.django_db
def test_detalhe_exibe_botao_registrar_retirada_para_aux_almox(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk})
    )
    assert response.status_code == 200
    assert response.context['pode_atender_retirada'] is True
    html = response.content.decode('utf-8')
    assert 'Registrar retirada' in html


@pytest.mark.django_db
def test_detalhe_nao_exibe_botao_registrar_retirada_para_solicitante(
    client, solicitante, req_pronta_view_com_itens
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk})
    )
    assert response.status_code == 200
    assert response.context['pode_atender_retirada'] is False
    html = response.content.decode('utf-8')
    assert 'Registrar retirada' not in html


# ---------------------------------------------------------------------------
# Issue #9 — Cabeçalho, colunas de data, botão primário, a11y (Batch D)
# ---------------------------------------------------------------------------


@pytest.fixture
def req_enviada_com_timeline(db, solicitante, setor_obras):
    """Requisição em aguardando_autorizacao com evento ENVIO_AUTORIZACAO na timeline."""
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-D001',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    TimelineRequisicao.objects.create(
        requisicao=req,
        evento=EventoTimeline.ENVIO_AUTORIZACAO,
        ator=solicitante,
        estado_resultante=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
    )
    return req


@pytest.fixture
def req_autorizada_com_timeline(db, solicitante, setor_obras, material_disponivel):
    """Requisição autorizada com eventos ENVIO_AUTORIZACAO e AUTORIZACAO_TOTAL."""
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AUTORIZADA,
        numero_publico='REQ-2026-D002',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req,
        material=material_disponivel,
        quantidade_solicitada=1,
        quantidade_autorizada=1,
    )
    TimelineRequisicao.objects.create(
        requisicao=req,
        evento=EventoTimeline.ENVIO_AUTORIZACAO,
        ator=solicitante,
        estado_resultante=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
    )
    TimelineRequisicao.objects.create(
        requisicao=req,
        evento=EventoTimeline.AUTORIZACAO_TOTAL,
        ator=solicitante,
        estado_resultante=EstadoRequisicao.AUTORIZADA,
    )
    return req


@pytest.mark.django_db
def test_detalhe_exibe_enviada_em_em_aguardando_autorizacao(
    client, solicitante, req_enviada_com_timeline
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_com_timeline.pk})
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_detalhe_nao_exibe_enviada_em_em_rascunho(client, solicitante, setor_obras):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert response.context['enviada_em'] is None


@pytest.mark.django_db
def test_detalhe_nao_exibe_enviada_em_em_rascunho_retornado(
    client, solicitante, setor_obras
):
    """Rascunho com ENVIO_AUTORIZACAO na timeline (enviado e retornado) não exibe 'Enviada em'."""
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        numero_publico='REQ-2026-D099',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    TimelineRequisicao.objects.create(
        requisicao=req,
        evento=EventoTimeline.ENVIO_AUTORIZACAO,
        ator=solicitante,
        estado_resultante=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
    )
    TimelineRequisicao.objects.create(
        requisicao=req,
        evento=EventoTimeline.RETORNO_RASCUNHO,
        ator=solicitante,
        estado_resultante=EstadoRequisicao.RASCUNHO,
    )
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert response.context['enviada_em'] is None


@pytest.mark.django_db
def test_detalhe_titulo_rascunho_sem_pk(client, solicitante, setor_obras):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Rascunho' in html
    assert f'Rascunho #{req.pk}' not in html


@pytest.mark.django_db
def test_fila_autorizacao_coluna_enviada_em(
    client, chefe_obras, req_enviada_com_timeline
):
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:autorizacoes'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Enviada em' in html
    assert 'Atualizada em' not in html


@pytest.mark.django_db
def test_fila_atendimento_coluna_autorizada_em(
    client, aux_almoxarifado, req_autorizada_com_timeline
):
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Autorizada em' in html
    assert 'Atualizada em' not in html


# ---------------------------------------------------------------------------
# Issue #160 — a linha de data some inteira quando a data não existe
#
# `enviada_em`/`autorizada_em` não são campos de `Requisicao`: são anotações
# dos selectors `fila_autorizacao`/`fila_atendimento` sobre os eventos
# `envio_autorizacao`/`autorizacao_total` da timeline. Dentro do recorte de
# cada fila a data nunca falta em dado consistente — TR-005 é a única porta
# para `aguardando_autorizacao`, TR-008 para `autorizada`, e `autorizada` é a
# única origem de `pronta_para_retirada` (TR-009). A guarda no template é
# defensiva: se a data faltar, some o `<p>` inteiro, e não só o valor — um
# "Enviada em —" ocuparia a segunda posição de leitura do cartão sem informar
# nada.
#
# Os cenários negativos são montados por ORM direto porque não há caminho de
# service que os produza: todo service que leva a requisição a estes estados
# grava o evento na mesma transação.
# ---------------------------------------------------------------------------

#: O `<p>` de metadado do cartão das duas filas. Nenhuma das duas telas tem
#: formulário de filtro, então esta é a única ocorrência da classe na página —
#: dá para asserir a ausência do elemento, não só a do texto.
_P_METADADO_CARTAO = '<p class="mt-1 text-xs text-text-tertiary">'


@pytest.mark.django_db
def test_fila_autorizacao_enviada_em_traz_data_formatada(
    client, chefe_obras, req_enviada_com_timeline
):
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:autorizacoes'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    envio = TimelineRequisicao.objects.get(
        requisicao=req_enviada_com_timeline,
        evento=EventoTimeline.ENVIO_AUTORIZACAO,
    )
    enviada_em = timezone.localtime(envio.criado_em).strftime('%d/%m/%Y %H:%M')
    assert f'{_P_METADADO_CARTAO}Enviada em {enviada_em}</p>' in html


@pytest.mark.django_db
def test_fila_autorizacao_sem_evento_de_envio_omite_a_linha_inteira(
    client, chefe_obras, req_enviada_solicitante
):
    """Sem `envio_autorizacao` na timeline, não sobra rótulo nem travessão.

    `req_enviada_solicitante` nasce por ORM direto em `aguardando_autorizacao`,
    sem evento — o cenário que nenhum service produz, e o único em que a
    anotação `enviada_em` chega `None`.
    """
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:autorizacoes'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    # O cartão está lá: o que sumiu é a linha da data, não a requisição.
    assert req_enviada_solicitante.numero_publico in html
    assert 'Enviada em' not in html
    assert 'Enviada em —' not in html
    assert _P_METADADO_CARTAO not in html


@pytest.mark.django_db
def test_fila_atendimento_autorizada_em_traz_data_formatada(
    client, aux_almoxarifado, req_autorizada_com_timeline
):
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    autorizacao = TimelineRequisicao.objects.get(
        requisicao=req_autorizada_com_timeline,
        evento=EventoTimeline.AUTORIZACAO_TOTAL,
    )
    autorizada_em = timezone.localtime(autorizacao.criado_em).strftime('%d/%m/%Y %H:%M')
    assert f'{_P_METADADO_CARTAO}Autorizada em {autorizada_em}</p>' in html


@pytest.mark.django_db
def test_fila_atendimento_sem_evento_de_autorizacao_omite_a_linha_inteira(
    client, aux_almoxarifado, req_autorizada_view
):
    """Sem `autorizacao_total` na timeline, não sobra rótulo nem travessão.

    `req_autorizada_view` nasce por ORM direto em `autorizada`, sem evento — o
    cenário que nenhum service produz, e o único em que a anotação
    `autorizada_em` chega `None`.
    """
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    # O cartão está lá: o que sumiu é a linha da data, não a requisição.
    assert req_autorizada_view.numero_publico in html
    assert 'Autorizada em' not in html
    assert 'Autorizada em —' not in html
    assert _P_METADADO_CARTAO not in html


@pytest.mark.django_db
def test_fila_atendimento_pronta_para_retirada_sem_evento_omite_a_linha_inteira(
    client, aux_almoxarifado, req_pronta_view
):
    """Mesma guarda no outro estado que a fila lista (`pronta_para_retirada`).

    A tela renderiza o cartão pelo ramo "Entregar", que passa pelo mesmo
    `partialdef corpo_cartao` — o ramo do verbo não pode reintroduzir o rótulo
    órfão.
    """
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert req_pronta_view.numero_publico in html
    assert 'Entregar' in html
    assert 'Autorizada em' not in html
    assert _P_METADADO_CARTAO not in html


@pytest.mark.django_db
def test_fila_atendimento_renderiza_cartoes(
    client, aux_almoxarifado, req_autorizada_view
):
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert '<div class="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">' in html
    assert html.count('<article class="relative rounded-xl border border-border') == 1
    assert 'Separar' in html


@pytest.mark.django_db
def test_fila_autorizacao_renderiza_cartoes(
    client, chefe_obras, req_enviada_solicitante
):
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:autorizacoes'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert '<div class="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">' in html
    assert html.count('<article class="relative rounded-xl border border-border') == 1
    assert 'Analisar' in html


@pytest.mark.django_db
def test_detalhe_registrar_retirada_botao_azul(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk})
    )
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert '>Registrar retirada</a>' in html
    assert 'bg-primary' in html
    assert 'bg-emerald-600' not in html


def test_messages_html_declara_live_region_uma_vez_por_mensagem():
    """A live region vive no item, não no container.

    `role="alert"` já implica aria-live assertivo e `role="status"` implica
    polite; declarar aria-live também no wrapper faria o leitor de tela anunciar
    a mesma mensagem duas vezes.
    """
    from django.contrib import messages as django_messages
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.template.loader import render_to_string
    from django.test import RequestFactory

    rf = RequestFactory()
    request = rf.get('/')
    request.session = {}
    storage = FallbackStorage(request)
    request._messages = storage
    django_messages.error(request, 'Erro de teste')
    django_messages.success(request, 'Sucesso de teste')

    html = render_to_string('core/partials/_messages.html', request=request)
    assert 'aria-live=' not in html
    # Contagem, não presença: uma mensagem duplicada passaria num `in`.
    assert html.count('role="alert"') == 1
    assert html.count('role="status"') == 1
    assert html.count('Erro de teste') == 1
    assert html.count('Sucesso de teste') == 1
    # Erro (assertivo) precede sucesso (polite) na ordem do DOM.
    assert html.index('Erro de teste') < html.index('Sucesso de teste')


# ---------------------------------------------------------------------------
# copiar_requisicao_view
# ---------------------------------------------------------------------------


@pytest.fixture
def req_recusada_view(solicitante, material_disponivel, chefe_obras):
    from apps.requisicoes.services import enviar_para_autorizacao, recusar_requisicao

    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('3'),
            }
        ],
    )
    req = enviar_para_autorizacao(ator_id=solicitante.pk, requisicao_id=req.pk)
    return recusar_requisicao(
        ator_id=chefe_obras.pk,
        requisicao_id=req.pk,
        motivo='Sem orçamento.',
    )


@pytest.mark.django_db
def test_copiar_requisicao_view_get_retorna_confirmacao(
    client, solicitante, req_recusada_view
):
    _login(client, solicitante)
    url = reverse('requisicoes:copiar', kwargs={'pk': req_recusada_view.pk})
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_copiar_requisicao_view_nota_usa_components_alert_sem_role_note(
    client, solicitante, req_recusada_view
):
    _login(client, solicitante)
    url = reverse('requisicoes:copiar', kwargs={'pk': req_recusada_view.pk})
    response = client.get(url)
    conteudo = response.content.decode()

    assert 'role="note"' not in conteudo
    assert 'role="alert"' in conteudo
    assert 'border-warning-border' in conteudo
    assert 'bg-warning-subtle' in conteudo


@pytest.mark.django_db
def test_copiar_requisicao_view_post_cria_rascunho_e_redireciona(
    client, solicitante, req_recusada_view
):
    from django.urls import resolve

    _login(client, solicitante)
    url = reverse('requisicoes:copiar', kwargs={'pk': req_recusada_view.pk})
    response = client.post(url, follow=True)

    assert response.redirect_chain
    redirect_url = response.redirect_chain[0][0]
    novo_pk = resolve(redirect_url).kwargs['pk']
    novo = Requisicao.objects.get(pk=novo_pk)
    assert novo.estado == EstadoRequisicao.RASCUNHO
    assert novo.itens.count() == req_recusada_view.itens.count()
    mensagens = [str(m) for m in response.context['messages']]
    assert any('Rascunho criado' in m for m in mensagens)


@pytest.mark.django_db
def test_copiar_requisicao_view_post_sem_login_redireciona(client, req_recusada_view):
    url = reverse('requisicoes:copiar', kwargs={'pk': req_recusada_view.pk})
    response = client.post(url)
    assert response.status_code == 302
    assert '/login/' in response['Location'] or 'next=' in response['Location']


@pytest.mark.django_db
def test_copiar_requisicao_view_post_estado_invalido_exibe_erro(
    client, solicitante, material_disponivel
):
    req_rascunho = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    _login(client, solicitante)
    url = reverse('requisicoes:copiar', kwargs={'pk': req_rascunho.pk})
    response = client.post(url)
    assert response.status_code == 200
    mensagens = [str(m) for m in response.context['messages']]
    assert any('atendidas ou recusadas' in m for m in mensagens)


# drift 3a: PermissaoNegada em copiar deve virar 403, não messages.error
@pytest.mark.django_db
def test_copiar_requisicao_view_permissao_negada_retorna_403(
    client, solicitante, material_disponivel
):
    """Drift 3a (canônico): PermissaoNegada em copiar_requisicao deve retornar 403."""
    from unittest.mock import patch

    from apps.core.exceptions import PermissaoNegada

    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    _login(client, solicitante)
    with patch(
        'apps.requisicoes.views.copiar_requisicao',
        side_effect=PermissaoNegada('Sem permissão'),
    ):
        resp = client.post(reverse('requisicoes:copiar', kwargs={'pk': req.pk}))

    assert resp.status_code == 403


# drift 3b: EstadoInvalido em copiar deve ser warning, não error
@pytest.mark.django_db
def test_copiar_requisicao_view_estado_invalido_mostra_warning(
    client, solicitante, material_disponivel
):
    """Drift 3b (canônico): EstadoInvalido em copiar_requisicao deve gerar
    messages.warning, nunca messages.error."""
    from unittest.mock import patch

    from django.contrib.messages import constants as message_constants

    from apps.core.exceptions import EstadoInvalido

    req = criar_requisicao(
        ator_id=solicitante.pk,
        beneficiario_id=solicitante.pk,
        itens=[
            {
                'material_id': material_disponivel.pk,
                'quantidade_solicitada': Decimal('1'),
            }
        ],
    )
    _login(client, solicitante)
    with patch(
        'apps.requisicoes.views.copiar_requisicao',
        side_effect=EstadoInvalido('Estado inválido para cópia'),
    ):
        resp = client.post(
            reverse('requisicoes:copiar', kwargs={'pk': req.pk}),
            follow=True,
        )

    assert resp.status_code == 200
    msgs = list(resp.context['messages'])
    assert any(m.level == message_constants.WARNING for m in msgs)
    assert not any(m.level == message_constants.ERROR for m in msgs)


# ---------------------------------------------------------------------------
# registrar_devolucao_view (TR-020)
# ---------------------------------------------------------------------------


@pytest.fixture
def req_atendida_view(
    db, solicitante, setor_obras, material_disponivel, aux_almoxarifado
):
    from apps.estoque.models import SaldoEstoque
    from apps.requisicoes.services import registrar_atendimento
    from apps.requisicoes.types import LinhaAtendimento

    req = Requisicao.objects.create(
        estado=EstadoRequisicao.PRONTA_PARA_RETIRADA,
        numero_publico='REQ-2026-9200',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    item = ItemRequisicao.objects.create(
        requisicao=req,
        material=material_disponivel,
        quantidade_solicitada=Decimal('5'),
        quantidade_autorizada=Decimal('5'),
    )
    saldo = SaldoEstoque.objects.get(material=material_disponivel)
    saldo.saldo_reservado = (saldo.saldo_reservado or Decimal('0')) + Decimal('5')
    saldo.save(update_fields=['saldo_reservado'])
    return registrar_atendimento(
        ator_id=aux_almoxarifado.pk,
        requisicao_id=req.pk,
        itens=[
            LinhaAtendimento(
                item_id=item.pk,
                quantidade_entregue=Decimal('5'),
                justificativa='',
            )
        ],
        retirante_nome='Carlos',
    )


@pytest.mark.django_db
def test_registrar_devolucao_view_post_valido_redireciona(
    client, aux_almoxarifado, req_atendida_view
):
    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    response = client.post(url, {'quantidade': '1.000'}, follow=True)
    assert response.status_code == 200
    mensagens = [str(m) for m in response.context['messages']]
    assert any('sucesso' in m.lower() for m in mensagens)


@pytest.mark.django_db
def test_registrar_devolucao_view_htmx_retorna_hx_redirect(
    client, aux_almoxarifado, req_atendida_view
):
    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    response = client.post(url, {'quantidade': '1.000'}, HTTP_HX_REQUEST='true')
    assert response.status_code == 204
    assert response['HX-Redirect'] == reverse(
        'requisicoes:detalhe', args=[req_atendida_view.pk]
    )


@pytest.mark.django_db
def test_registrar_devolucao_view_quantidade_excede_avisa(
    client, aux_almoxarifado, req_atendida_view
):
    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    response = client.post(url, {'quantidade': '999.000'}, follow=True)
    mensagens = [str(m) for m in response.context['messages']]
    assert any('excede' in m for m in mensagens)


# drift 4: DadosInvalidos em devolucao deve ser error, não warning
@pytest.mark.django_db
def test_registrar_devolucao_view_dados_invalidos_mostra_error(
    client, aux_almoxarifado, req_atendida_view
):
    """Drift 4 (canônico): DadosInvalidos em registrar_devolucao deve gerar
    messages.error, nunca messages.warning."""
    from unittest.mock import patch

    from django.contrib.messages import constants as message_constants

    from apps.core.exceptions import DadosInvalidos

    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    with patch(
        'apps.requisicoes.views.registrar_devolucao',
        side_effect=DadosInvalidos('Quantidade inválida'),
    ):
        resp = client.post(url, {'quantidade': '1.000'}, follow=True)

    assert resp.status_code == 200
    msgs = list(resp.context['messages'])
    assert any(m.level == message_constants.ERROR for m in msgs)
    assert not any(m.level == message_constants.WARNING for m in msgs)


@pytest.mark.django_db
def test_registrar_devolucao_htmx_form_invalido_devolve_422_do_modal(
    client, aux_almoxarifado, req_atendida_view
):
    """Form inválido via HTMX reabre o modal com erro, não derruba a página.

    `form.errors.as_text()` numa mensagem levava o dump do Django à tela — com
    o asterisco de formatação de log — e trocava o modal por uma navegação de
    página inteira.
    """
    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    response = client.post(url, {'quantidade': ''}, HTTP_HX_REQUEST='true')

    assert response.status_code == 422
    conteudo = response.content.decode()
    assert f'data-modal-body="devolver-{item.pk}"' in conteudo
    assert 'data-modal-erro' in conteudo
    assert '<html' not in conteudo
    # O texto vem do Form, sem o asterisco de `as_text()`.
    assert 'obrigat' in conteudo.lower()
    assert '* quantidade' not in conteudo


@pytest.mark.django_db
def test_registrar_devolucao_copy_do_422_nao_diverge_do_render_inicial(
    client, aux_almoxarifado, req_atendida_view
):
    """Título e descrição do modal de devolução não podem mudar no 422 (#135)."""
    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    detalhe_url = reverse('requisicoes:detalhe', kwargs={'pk': req_atendida_view.pk})
    inicial = client.get(detalhe_url)

    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    erro = client.post(url, {'quantidade': ''}, HTTP_HX_REQUEST='true')

    assert erro.status_code == 422
    assert_copy_nao_diverge(
        erro,
        html_inicial=inicial.content.decode('utf-8'),
        modal_id=f'devolver-{item.pk}',
    )


@pytest.mark.django_db
def test_registrar_devolucao_htmx_item_obsoleto_devolve_422_nao_404(
    client, aux_almoxarifado, req_atendida_view, solicitante, setor_obras
):
    """Item que não é da requisição cai no 422, não numa página 404.

    Um 404 aqui devolveria página inteira a um `hx-post` que faz `outerHTML`
    em `[data-modal-body]` — o defeito desta issue, reintroduzido pelo ramo de
    erro do próprio conserto. E seria assimétrico: com o form válido o mesmo
    `item_pk` vira `DadosInvalidos` do service, e a pessoa é informada.

    Gatilho real: modal aberto numa aba, item alterado em outra.
    """
    outra = Requisicao.objects.create(
        estado=EstadoRequisicao.RASCUNHO,
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    item_de_fora = ItemRequisicao.objects.create(
        requisicao=outra,
        material=req_atendida_view.itens.first().material,
        quantidade_solicitada=Decimal('1'),
    )
    _login(client, aux_almoxarifado)
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item_de_fora.pk},
    )
    response = client.post(url, {'quantidade': ''}, HTTP_HX_REQUEST='true')

    assert response.status_code == 422
    conteudo = response.content.decode()
    assert f'data-modal-body="devolver-{item_de_fora.pk}"' in conteudo
    assert '<html' not in conteudo


@pytest.mark.django_db
def test_registrar_devolucao_sem_htmx_nao_usa_dump_do_as_text(
    client, aux_almoxarifado, req_atendida_view
):
    """Fallback sem HTMX segue redirecionando, mas com texto do Form."""
    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    entregue_antes = item.quantidade_entregue
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    response = client.post(url, {'quantidade': ''}, follow=True)

    assert response.status_code == 200
    mensagens = [str(m) for m in response.context['messages']]
    assert mensagens
    assert not any('*' in m for m in mensagens)
    # O positivo, e não só o negativo: uma regressão que devolvesse só o nome
    # do campo ("quantidade") passaria na asserção de asterisco sozinha.
    assert any('obrigat' in m.lower() for m in mensagens)
    # E o rótulo do campo sobrevive: a frase chega depois do redirect, numa
    # tela sem formulário, onde "Este campo é obrigatório." não diz qual.
    assert any('uantidade' in m for m in mensagens)
    # Form inválido não pode ter gravado devolução nenhuma.
    item.refresh_from_db()
    assert item.quantidade_entregue == entregue_antes


@pytest.mark.django_db
def test_estornar_htmx_form_invalido_devolve_422_do_modal(
    client, chefe_almoxarifado, req_atendida_view
):
    _login(client, chefe_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    response = client.post(url, {'justificativa': ''}, HTTP_HX_REQUEST='true')

    assert response.status_code == 422
    conteudo = response.content.decode()
    assert 'data-modal-body="estornar-modal"' in conteudo
    assert 'data-modal-erro' in conteudo
    assert '<html' not in conteudo
    assert '* justificativa' not in conteudo
    req_atendida_view.refresh_from_db()
    assert req_atendida_view.estado == EstadoRequisicao.ATENDIDA


@pytest.mark.django_db
def test_estornar_sem_htmx_nao_usa_dump_do_as_text(
    client, chefe_almoxarifado, req_atendida_view
):
    _login(client, chefe_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    response = client.post(url, {'justificativa': ''}, follow=True)

    assert response.status_code == 200
    mensagens = [str(m) for m in response.context['messages']]
    assert mensagens
    assert not any('*' in m for m in mensagens)
    assert any('obrigat' in m.lower() for m in mensagens)
    assert any('ustificativa' in m for m in mensagens)
    req_atendida_view.refresh_from_db()
    assert req_atendida_view.estado == EstadoRequisicao.ATENDIDA


@pytest.mark.django_db
def test_registrar_devolucao_view_sem_permissao_403(
    client, solicitante, req_atendida_view
):
    _login(client, solicitante)
    item = req_atendida_view.itens.first()
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    response = client.post(url, {'quantidade': '1.000'})
    assert response.status_code == 403


@pytest.mark.django_db
def test_registrar_devolucao_view_get_retorna_405(
    client, aux_almoxarifado, req_atendida_view
):
    _login(client, aux_almoxarifado)
    item = req_atendida_view.itens.first()
    url = reverse(
        'requisicoes:registrar_devolucao',
        kwargs={'pk': req_atendida_view.pk, 'item_pk': item.pk},
    )
    response = client.get(url)
    assert response.status_code == 405


@pytest.mark.django_db
def test_detalhe_modal_devolucao_max_renderiza_float_valido(
    client, aux_almoxarifado, req_atendida_view
):
    """max="{{ entregue_liquida }}" deve renderizar número válido de HTML5
    (`5.000`), não localizado (`5,000`), senão o browser descarta o atributo
    e o limite de quantidade some do formulário."""
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:detalhe', args=[req_atendida_view.pk]))
    assert response.status_code == 200
    conteudo = response.content.decode()
    match = re.search(r'name="quantidade"[^>]*max="([^"]+)"', conteudo)
    assert match, 'input de quantidade sem atributo max'
    assert float(match.group(1)) == 5.0


# ---------------------------------------------------------------------------
# estornar_requisicao_view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_estornar_view_sucesso_redireciona(
    client, chefe_almoxarifado, req_atendida_view
):
    """POST válido → redirect para detalhe + mensagem success."""
    _login(client, chefe_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    response = client.post(url, {'justificativa': 'Estorno por teste.'})
    assert response.status_code == 302
    assert response['Location'] == reverse(
        'requisicoes:detalhe', args=[req_atendida_view.pk]
    )
    req_atendida_view.refresh_from_db()
    assert req_atendida_view.estado == EstadoRequisicao.ESTORNADA


@pytest.mark.django_db
def test_estornar_view_htmx_retorna_hx_redirect(
    client, chefe_almoxarifado, req_atendida_view
):
    """HTMX POST → 204 + HX-Redirect."""
    _login(client, chefe_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    response = client.post(
        url,
        {'justificativa': 'Estorno HTMX.'},
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 204
    assert 'HX-Redirect' in response


@pytest.mark.django_db
def test_estornar_view_sem_justificativa_exibe_warning(
    client, chefe_almoxarifado, req_atendida_view
):
    """POST sem justificativa → redirect + mensagem warning (form inválido)."""
    _login(client, chefe_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    response = client.post(url, {'justificativa': ''}, follow=True)
    assert response.status_code == 200
    msgs = [str(m) for m in response.context['messages']]
    assert any('justificativa' in m.lower() or 'obrigat' in m.lower() for m in msgs)
    req_atendida_view.refresh_from_db()
    assert req_atendida_view.estado == EstadoRequisicao.ATENDIDA


# drift 5: DadosInvalidos em estorno deve ser error, não warning
@pytest.mark.django_db
def test_estornar_view_dados_invalidos_mostra_error(
    client, chefe_almoxarifado, req_atendida_view
):
    """Drift 5 (canônico): DadosInvalidos em estornar_requisicao deve gerar
    messages.error, nunca messages.warning."""
    from unittest.mock import patch

    from django.contrib.messages import constants as message_constants

    from apps.core.exceptions import DadosInvalidos

    _login(client, chefe_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    with patch(
        'apps.requisicoes.views.estornar_requisicao',
        side_effect=DadosInvalidos('Justificativa insuficiente'),
    ):
        resp = client.post(url, {'justificativa': 'motivo'}, follow=True)

    assert resp.status_code == 200
    msgs = list(resp.context['messages'])
    assert any(m.level == message_constants.ERROR for m in msgs)
    assert not any(m.level == message_constants.WARNING for m in msgs)


@pytest.mark.django_db
def test_estornar_view_sem_permissao_retorna_403(
    client, aux_almoxarifado, req_atendida_view
):
    """Auxiliar almox → 403."""
    _login(client, aux_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    response = client.post(url, {'justificativa': 'Tentativa.'})
    assert response.status_code == 403


@pytest.mark.django_db
def test_estornar_view_get_nao_permitido(client, chefe_almoxarifado, req_atendida_view):
    """GET → 405."""
    _login(client, chefe_almoxarifado)
    url = reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk})
    response = client.get(url)
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# historico_requisicoes_view
# ---------------------------------------------------------------------------

URL_HISTORICO_REQUISICOES = reverse('requisicoes:historico')


class TestSeteListagensNomeiamOMaterial:
    """As sete listagens contam a mesma história (Etapa 8).

    "Minhas requisições" não dizia nada do conteúdo — número, data e estado — e
    a fila de autorização dizia só "Itens: N". As duas telas de decisão do
    fluxo (o solicitante conferindo o que pediu, o chefe autorizando) eram as
    que menos informavam. A grafia canônica é a da fila de atendimento: nome do
    primeiro material e, quando há mais de um, "e mais N".
    """

    def _com_dois_itens(self, requisicao, material_a, material_b):
        requisicao.itens.create(material=material_a, quantidade_solicitada=1)
        requisicao.itens.create(material=material_b, quantidade_solicitada=2)
        return requisicao

    def test_minhas_requisicoes_nomeia_o_material(
        self,
        client,
        solicitante,
        setor_obras,
        material_disponivel,
        material_disponivel_2,
    ):
        req = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-E801',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        self._com_dois_itens(req, material_disponivel, material_disponivel_2)
        _login(client, solicitante)
        html = client.get(reverse('requisicoes:minhas')).content.decode('utf-8')
        assert material_disponivel.nome in html
        assert 'e mais 1' in html

    def test_minhas_requisicoes_item_unico_sai_sem_contagem(
        self, client, solicitante, setor_obras, material_disponivel
    ):
        req = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-E802',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        req.itens.create(material=material_disponivel, quantidade_solicitada=1)
        _login(client, solicitante)
        html = client.get(reverse('requisicoes:minhas')).content.decode('utf-8')
        assert material_disponivel.nome in html
        assert 'e mais 1' not in html

    def test_fila_autorizacao_nomeia_o_material(
        self,
        client,
        chefe_obras,
        solicitante,
        setor_obras,
        material_disponivel,
        material_disponivel_2,
    ):
        req = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-E803',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        self._com_dois_itens(req, material_disponivel, material_disponivel_2)
        _login(client, chefe_obras)
        html = client.get(reverse('requisicoes:autorizacoes')).content.decode('utf-8')
        assert material_disponivel.nome in html
        assert 'e mais 1' in html
        # "Itens: N" era o que a tela dizia antes, e o dígito sozinho não basta.
        assert 'Itens:' not in html


class TestHistoricoRequisicoesView:
    def test_chefe_almox_acessa(self, client, chefe_almoxarifado):
        _login(client, chefe_almoxarifado)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.status_code == 200

    def test_superuser_acessa(self, client, superuser):
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.status_code == 200

    def test_chefe_setor_acessa(self, client, chefe_obras):
        _login(client, chefe_obras)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.status_code == 200

    def test_solicitante_recebe_403(self, client, solicitante):
        _login(client, solicitante)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.status_code == 403

    def test_aux_setor_acessa_sem_ver_requisicao_de_terceiro(
        self, client, aux_obras, req_historico_obras
    ):
        """Aux entra na página (200, não 403) e não lista o que o detalhe nega (#106)."""
        _login(client, aux_obras)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.status_code == 200
        pks = {req.pk for req in response.context['page_obj']}
        assert req_historico_obras.pk not in pks

    def test_anonimo_redirecionado_para_login(self, client):
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_contexto_tem_page_obj(self, client, superuser):
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert 'page_obj' in response.context

    def test_view_alimenta_page_obj_com_selector_escopado(
        self, client, chefe_obras, req_historico_obras, req_historico_ti
    ):
        from apps.requisicoes.selectors import historico_requisicoes_visiveis_para

        _login(client, chefe_obras)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.status_code == 200
        assert 'requisicoes/historico_requisicoes.html' in {
            t.name for t in response.templates
        }
        esperado = historico_requisicoes_visiveis_para(chefe_obras.pk).count()
        assert response.context['page_obj'].paginator.count == esperado

    def test_paginacao_server_side(self, client, superuser, setor_obras, solicitante):
        for i in range(30):
            Requisicao.objects.create(
                estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
                numero_publico=f'REQ-2026-1{i:03d}',
                criador=solicitante,
                beneficiario=solicitante,
                setor_beneficiario=setor_obras,
            )
        _login(client, superuser)
        page1 = client.get(URL_HISTORICO_REQUISICOES)
        assert len(page1.context['page_obj'].object_list) == 25
        assert page1.context['page_obj'].has_next() is True
        page2 = client.get(URL_HISTORICO_REQUISICOES, {'page': 2})
        assert page2.status_code == 200
        assert len(page2.context['page_obj'].object_list) >= 1

    def test_botao_ver_detalhes_com_href_e_classes_esperadas(
        self, client, chefe_obras, req_historico_obras
    ):
        from django.template.defaultfilters import urlencode as tpl_urlencode

        _login(client, chefe_obras)
        response = client.get(URL_HISTORICO_REQUISICOES)
        html = response.content.decode('utf-8')
        href_esperado = (
            reverse('requisicoes:detalhe', kwargs={'pk': req_historico_obras.pk})
            + '?next='
            + tpl_urlencode(URL_HISTORICO_REQUISICOES)
        )
        marker = f'href="{href_esperado}"'
        assert marker in html
        idx = html.index(marker)
        tag = html[html.rindex('<a', 0, idx) : html.index('>', idx) + 1]
        # Alvo e foco são do cartão agora, não desta âncora — ver
        # `test_link_de_cartao_tem_o_cartao_como_alvo`.
        assert 'data-cartao-link' in tag
        assert 'min-h-11' not in tag

    def test_empty_state_quando_historico_vazio(self, client, chefe_almoxarifado):
        _login(client, chefe_almoxarifado)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert response.context['page_obj'].paginator.count == 0
        assert b'Nenhuma requisi' in response.content

    def test_paginacao_usa_componente_com_rotulo_e_aria_label_proprios(
        self, client, superuser, setor_obras, solicitante
    ):
        for i in range(30):
            Requisicao.objects.create(
                estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
                numero_publico=f'REQ-2026-2{i:03d}',
                criador=solicitante,
                beneficiario=solicitante,
                setor_beneficiario=setor_obras,
            )
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES)
        total = response.context['page_obj'].paginator.count
        assert (
            'aria-label="Paginação do histórico de requisições"'.encode()
            in response.content
        )
        esperado = f'<span class="tabular-nums">{total}</span> requisições'
        assert esperado.encode() in response.content

    def test_rascunho_de_terceiro_nao_expoe_pk_para_superuser(
        self, client, superuser, solicitante, setor_obras
    ):
        rascunho = Requisicao.objects.create(
            estado=EstadoRequisicao.RASCUNHO,
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert f'#{rascunho.pk}'.encode() not in response.content
        assert b'Rascunho' in response.content

    def test_requisicao_htmx_devolve_so_partial(self, client, superuser):
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES, HTTP_HX_REQUEST='true')
        assert response.status_code == 200
        assert any(
            t.name == 'resultados'
            and t.origin.template_name == 'requisicoes/historico_requisicoes.html'
            for t in response.templates
        )
        nomes = {t.name for t in response.templates}
        assert 'requisicoes/historico_requisicoes.html' not in nomes

    def test_caminho_nativo_redireciona_302_para_querystring_canonica(
        self, client, superuser
    ):
        """Submit do form emite as chaves vazias; a URL de auditoria não pode
        ter duas grafias para o mesmo recorte (issue #152)."""
        _login(client, superuser)
        response = client.get(
            URL_HISTORICO_REQUISICOES,
            {'texto': 'Obras', 'data_ini': '', 'data_fim': '', 'setor': ''},
        )
        assert response.status_code == 302
        assert response['Location'] == f'{URL_HISTORICO_REQUISICOES}?texto=Obras'

    def test_caminho_nativo_ja_canonico_nao_redireciona(self, client, superuser):
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES, {'texto': 'Obras'})
        assert response.status_code == 200

    def test_caminho_htmx_devolve_canonica_no_header_hx_push_url(
        self, client, superuser
    ):
        """Sem roundtrip extra: a canônica volta no header, o HTMX não serializa
        o que o form mandou."""
        _login(client, superuser)
        response = client.get(
            URL_HISTORICO_REQUISICOES,
            {'estados': ['atendida', 'rascunho'], 'data_ini': ''},
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200
        assert response['HX-Push-Url'] == (
            f'{URL_HISTORICO_REQUISICOES}?estados=atendida&estados=rascunho'
        )

    def test_requisicao_normal_devolve_template_completo(self, client, superuser):
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES)
        nomes = {t.name for t in response.templates}
        assert 'requisicoes/historico_requisicoes.html' in nomes

    def test_coluna_material_resume_item_unico(
        self, client, superuser, req_historico_obras, material_disponivel
    ):
        ItemRequisicao.objects.create(
            requisicao=req_historico_obras,
            material=material_disponivel,
            quantidade_solicitada=3,
        )
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES)
        assert material_disponivel.nome.encode() in response.content

    def test_coluna_material_resume_multiplos_itens(
        self,
        client,
        superuser,
        req_historico_obras,
        material_disponivel,
        material_disponivel_2,
    ):
        ItemRequisicao.objects.create(
            requisicao=req_historico_obras,
            material=material_disponivel,
            quantidade_solicitada=3,
        )
        ItemRequisicao.objects.create(
            requisicao=req_historico_obras,
            material=material_disponivel_2,
            quantidade_solicitada=1,
        )
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES)
        html = response.content.decode('utf-8')
        # Nome do primeiro material + "e mais N", a mesma grafia das duas filas
        # e de "Minhas requisições" (Etapa 8). A forma anterior ("2 itens", com
        # o nome só quando havia um item) escondia o conteúdo justamente nas
        # requisições maiores.
        assert material_disponivel.nome in html
        assert 'e mais 1' in html


class TestHistoricoRequisicoesChipsPorPapel:
    """Chips de recorte por papel (issue #153)."""

    def test_chefe_de_setor_ve_aguardando_minha_autorizacao(self, client, chefe_obras):
        _login(client, chefe_obras)
        chips = client.get(URL_HISTORICO_REQUISICOES).context['chips_filtro']
        rotulos = [c.rotulo for c in chips]
        assert 'Aguardando minha autorização' in rotulos
        assert 'Exceções' not in rotulos
        chip = next(c for c in chips if c.rotulo == 'Aguardando minha autorização')
        assert 'estados=aguardando_autorizacao' in chip.url

    def test_almoxarifado_ve_excecoes(self, client, chefe_almoxarifado):
        _login(client, chefe_almoxarifado)
        chips = client.get(URL_HISTORICO_REQUISICOES).context['chips_filtro']
        rotulos = [c.rotulo for c in chips]
        assert 'Exceções' in rotulos
        assert 'Aguardando minha autorização' not in rotulos
        chip = next(c for c in chips if c.rotulo == 'Exceções')
        assert 'estados=estornada' in chip.url
        assert 'estados=recusada' in chip.url

    def test_superuser_ve_excecoes(self, client, superuser):
        _login(client, superuser)
        chips = client.get(URL_HISTORICO_REQUISICOES).context['chips_filtro']
        assert [c.rotulo for c in chips] == ['Exceções']

    def test_chip_ativo_desliga_preservando_selecao_alheia(
        self, client, chefe_almoxarifado
    ):
        _login(client, chefe_almoxarifado)
        response = client.get(
            URL_HISTORICO_REQUISICOES,
            {'estados': ['estornada', 'recusada', 'atendida']},
            follow=True,
        )
        chip = next(
            c for c in response.context['chips_filtro'] if c.rotulo == 'Exceções'
        )
        assert chip.ativo is True
        assert 'estados=atendida' in chip.url
        assert 'estados=estornada' not in chip.url
        assert 'estados=recusada' not in chip.url

    def test_chip_reemitido_via_oob_no_swap_htmx(self, client, superuser):
        _login(client, superuser)
        parcial = client.get(URL_HISTORICO_REQUISICOES, HTTP_HX_REQUEST='true').content
        assert b'id="filter-chips"' in parcial
        assert b'hx-swap-oob="true"' in parcial


class TestHistoricoRequisicoesPresetsPeriodo:
    """Presets de período — datas absolutas, sem estado novo (issue #153)."""

    def test_preset_preenche_data_ini_e_data_fim_com_datas_absolutas(
        self, client, superuser
    ):
        _login(client, superuser)
        presets = client.get(URL_HISTORICO_REQUISICOES).context['presets_periodo']
        rotulos = [p.rotulo for p in presets]
        assert rotulos == ['Últimos 7 dias', 'Últimos 30 dias', 'Este mês']
        hoje = timezone.localdate().isoformat()
        for preset in presets:
            assert 'data_ini=' in preset.url and f'data_fim={hoje}' in preset.url
            assert 'periodo=' not in preset.url

    def test_preset_nao_introduz_estado_novo_na_querystring(self, client, superuser):
        _login(client, superuser)
        preset = client.get(URL_HISTORICO_REQUISICOES).context['presets_periodo'][1]
        query = preset.url.split('?', 1)[1]
        chaves = {p.split('=')[0] for p in query.split('&')}
        assert chaves <= {'data_ini', 'data_fim'}

    def test_preset_ativo_quando_url_ja_mostra_a_janela(self, client, superuser):
        _login(client, superuser)
        base = client.get(URL_HISTORICO_REQUISICOES).context['presets_periodo'][1]
        query = base.url.split('?', 1)[1]
        params = dict(p.split('=') for p in query.split('&'))
        presets = client.get(URL_HISTORICO_REQUISICOES, params).context[
            'presets_periodo'
        ]
        assert presets[1].ativo is True
        assert presets[0].ativo is False


class TestHistoricoRequisicoesFiltros:
    def test_filtro_texto_reduz_resultado(
        self, client, superuser, req_historico_obras, req_historico_ti
    ):
        _login(client, superuser)
        com = client.get(URL_HISTORICO_REQUISICOES, {'texto': 'Solicitante'})
        sem = client.get(URL_HISTORICO_REQUISICOES, {'texto': 'inexistente'})
        assert com.context['page_obj'].paginator.count == 1
        assert sem.context['page_obj'].paginator.count == 0

    def test_filtro_estado_reduz_resultado(
        self, client, superuser, req_historico_obras, req_historico_ti
    ):
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES, {'estados': ['autorizada']})
        pks = {r.pk for r in response.context['page_obj'].object_list}
        assert pks == {req_historico_ti.pk}

    def test_ordenacao_asc_inverte_cronologia(
        self, client, superuser, setor_obras, solicitante
    ):
        for i in range(2):
            Requisicao.objects.create(
                estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
                numero_publico=f'REQ-2026-2{i:03d}',
                criador=solicitante,
                beneficiario=solicitante,
                setor_beneficiario=setor_obras,
            )
        _login(client, superuser)
        desc = client.get(URL_HISTORICO_REQUISICOES).context['page_obj'].object_list
        asc = (
            client.get(URL_HISTORICO_REQUISICOES, {'ordem': 'asc'})
            .context['page_obj']
            .object_list
        )
        assert [r.pk for r in asc] == [r.pk for r in reversed(list(desc))]

    def test_filtro_setor_visivel_so_para_almox(
        self, client, chefe_almoxarifado, chefe_obras
    ):
        _login(client, chefe_almoxarifado)
        assert (
            client.get(URL_HISTORICO_REQUISICOES).context['mostrar_filtro_setor']
            is True
        )
        _login(client, chefe_obras)
        assert (
            client.get(URL_HISTORICO_REQUISICOES).context['mostrar_filtro_setor']
            is False
        )

    def test_cartao_omite_setor_quando_recorte_fixa_o_setor_do_chefe(
        self, client, chefe_obras, usuario_ti, setor_obras
    ):
        """Chefe de setor sem filtro: cartão do próprio setor não repete SETOR."""
        Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-3001',
            criador=chefe_obras,
            beneficiario=chefe_obras,
            setor_beneficiario=setor_obras,
        )
        _login(client, chefe_obras)
        resp = client.get(URL_HISTORICO_REQUISICOES)
        assert resp.context['setor_fixo_id'] == setor_obras.pk
        assert '>Setor:<' not in resp.content.decode()

    def test_cartao_mantem_setor_no_que_o_chefe_criou_fora_do_setor(
        self, client, chefe_obras, usuario_ti, setor_ti
    ):
        """Requisição criada pelo chefe fora do setor chefiado: SETOR não é
        redundante e continua no cartão (regressão do achado P2 do PR #44)."""
        Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-3002',
            criador=chefe_obras,
            beneficiario=usuario_ti,
            setor_beneficiario=setor_ti,
        )
        _login(client, chefe_obras)
        resp = client.get(URL_HISTORICO_REQUISICOES)
        assert '>Setor:<' in resp.content.decode()

    def test_chefe_setor_nao_filtra_por_setor_via_querystring(
        self, client, chefe_obras, req_historico_obras, req_historico_ti, setor_ti
    ):
        _login(client, chefe_obras)
        response = client.get(URL_HISTORICO_REQUISICOES, {'setor': setor_ti.pk})
        assert response.status_code == 200
        pks = {r.pk for r in response.context['page_obj'].object_list}
        assert req_historico_ti.pk not in pks

    def test_querystring_invalida_nao_quebra(self, client, superuser):
        _login(client, superuser)
        response = client.get(
            URL_HISTORICO_REQUISICOES,
            {
                'data_ini': 'abc',
                'data_fim': '2026-13-99',
                'setor': 'xyz',
                'ordem': 'lixo',
                'estados': 'nao_existe',
                'page': 'foo',
            },
            follow=True,
        )
        assert response.status_code == 200

    def test_flag_tem_filtro_ativo(self, client, superuser):
        _login(client, superuser)
        com = client.get(URL_HISTORICO_REQUISICOES, {'texto': 'x'})
        sem = client.get(URL_HISTORICO_REQUISICOES)
        assert com.context['tem_filtro_ativo'] is True
        assert sem.context['tem_filtro_ativo'] is False

    def test_empty_state_contextual_distingue_filtro_de_historico_vazio(
        self, client, superuser, req_historico_obras
    ):
        _login(client, superuser)
        # Termo com caractere HTML-especial: prova que `titulo_com_termo`
        # (apps/core/templatetags/core_tags.py) não marca o título como
        # seguro — o autoescape do Django roda sobre a string inteira, igual
        # rodava antes da extração pro empty_state.html. Sem isso, um termo
        # ASCII puro passaria mesmo se um `|safe` futuro desligasse o escape
        # por engano.
        filtrado = client.get(
            URL_HISTORICO_REQUISICOES, {'texto': '<b>inexistente</b>'}
        ).content.decode()
        assert (
            'Nenhum resultado para &quot;&lt;b&gt;inexistente&lt;/b&gt;&quot;'
            in filtrado
        )
        assert '<b>inexistente</b>' not in filtrado
        assert 'Nenhuma requisição encontrada' not in filtrado

    def test_vazio_de_filtro_e_vazio_inicial_usam_icones_diferentes(
        self, client, superuser, req_historico_obras
    ):
        """Os dois estados vazios não são o mesmo estado emocional.

        Até a #126 os dois usavam a seta de recarregar. "Atualizar" não é o que
        nenhum dos dois diz: um diz "seu recorte não achou nada" e o outro diz
        "a caixa está vazia". Ícone que não corresponde ao estado é ruído com
        aparência de informação.
        """
        raiz = Path(__file__).resolve().parents[3]
        icones = raiz / 'apps/core/templates/components/icons'
        funil = icones.joinpath('_funil.html').read_text().strip()
        caixa = icones.joinpath('_caixa_entrada.html').read_text().strip()

        _login(client, superuser)
        filtrado = client.get(
            URL_HISTORICO_REQUISICOES, {'texto': 'inexistente'}
        ).content.decode()

        assert funil in filtrado
        assert caixa not in filtrado

    def test_vazio_inicial_do_historico_usa_icone_de_caixa(
        self, client, chefe_almoxarifado
    ):
        """Sem filtro e sem dado: a caixa está vazia, não o recorte."""
        raiz = Path(__file__).resolve().parents[3]
        icones = raiz / 'apps/core/templates/components/icons'
        funil = icones.joinpath('_funil.html').read_text().strip()
        caixa = icones.joinpath('_caixa_entrada.html').read_text().strip()

        _login(client, chefe_almoxarifado)
        conteudo = client.get(URL_HISTORICO_REQUISICOES).content.decode()

        assert caixa in conteudo
        assert funil not in conteudo


class TestHistoricoRequisicoesFiltrosPartials:
    """Cobertura da extração dos campos de filtro em partials (issue #88)."""

    def test_form_expoe_method_get_e_action_nativos(self, client, superuser):
        _login(client, superuser)
        content = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        assert 'method="get"' in content
        assert f'action="{URL_HISTORICO_REQUISICOES}"' in content

    def test_submissao_nativa_sem_htmx_retorna_pagina_completa_filtrada(
        self, client, superuser, req_historico_obras, req_historico_ti
    ):
        # Sem HTTP_HX_REQUEST simula o fallback de navegação nativa do
        # <form method="get">: precisa renderizar a página completa (não só
        # o partial 'resultados') e ainda assim aplicar o filtro.
        _login(client, superuser)
        response = client.get(URL_HISTORICO_REQUISICOES, {'texto': 'Solicitante'})
        nomes = {t.name for t in response.templates}
        assert 'requisicoes/historico_requisicoes.html' in nomes
        assert response.context['page_obj'].paginator.count == 1

    def test_limpar_filtros_href_navegacao_nativa(
        self, client, superuser, req_historico_obras
    ):
        _login(client, superuser)
        content = client.get(
            URL_HISTORICO_REQUISICOES, {'texto': 'Solicitante'}
        ).content.decode()
        assert f'href="{URL_HISTORICO_REQUISICOES}"' in content
        assert 'Limpar filtros' in content

    def test_checkbox_estado_tem_alvo_de_toque(self, client, superuser):
        _login(client, superuser)
        content = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        idx = content.index('name="estados"')
        label_ini = content.rindex('<label', 0, idx)
        label_fim = content.index('</label>', idx) + len('</label>')
        assert 'min-h-11' in content[label_ini:label_fim]

    def test_filtro_setor_label_vinculado_ao_select(self, client, chefe_almoxarifado):
        _login(client, chefe_almoxarifado)
        content = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        assert 'for="filtro-setor"' in content
        assert 'id="filtro-setor"' in content

    def test_filtro_setor_ausente_para_chefe_de_setor(self, client, chefe_obras):
        _login(client, chefe_obras)
        content = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        assert 'id="filtro-setor"' not in content

    def test_limpar_filtros_reemitido_via_oob_no_swap_htmx(self, client, superuser):
        # Bug-regressão (achado do CodeRabbit): filter_acoes.html vive fora
        # de #resultados-historico-requisicoes (dentro do <form>), então numa
        # resposta HTMX precisa ser reemitido como out-of-band pra refletir
        # tem_filtro_ativo — senão "Limpar filtros" fica com o estado da
        # primeira renderização full-page.
        _login(client, superuser)
        parcial = client.get(
            URL_HISTORICO_REQUISICOES, {'texto': 'x'}, HTTP_HX_REQUEST='true'
        ).content
        assert b'id="filtro-acoes-historico-requisicoes"' in parcial
        assert b'hx-swap-oob="true"' in parcial
        assert b'Limpar filtros' in parcial

    def test_limpar_filtros_sem_oob_na_pagina_completa(self, client, superuser):
        _login(client, superuser)
        conteudo = client.get(URL_HISTORICO_REQUISICOES, {'texto': 'x'}).content
        assert conteudo.count(b'id="filtro-acoes-historico-requisicoes"') == 1
        assert b'hx-swap-oob' not in conteudo

    def test_limpar_filtros_e_link_navegavel_tambem_no_reemite_htmx(
        self, client, superuser
    ):
        """Bug-regressão: "Limpar filtros" saía inerte na resposta HTMX.

        O `{% url ... as url_historico %}` fica no topo da tela, fora do
        `{% partialdef resultados %}`, e não roda quando o fragmento é
        renderizado sozinho. Com `action_url` vazio o components/button.html cai
        no ramo `<button>`: um controle sem href e sem hx-get, que não fazia
        absolutamente nada — logo depois de aplicar um filtro, que é o momento
        em que limpar é necessário.
        """
        _login(client, superuser)
        parcial = client.get(
            URL_HISTORICO_REQUISICOES, {'texto': 'x'}, HTTP_HX_REQUEST='true'
        ).content.decode()
        marca = 'id="filtro-acoes-historico-requisicoes"'
        trecho = parcial[parcial.index(marca) :]
        trecho = trecho[: trecho.index('</span>')]
        assert f'href="{URL_HISTORICO_REQUISICOES}"' in trecho, (
            f'"Limpar filtros" precisa navegar de verdade; veio: {trecho}'
        )

    def test_limpar_filtros_navega_sem_htmx_para_ressincronizar_os_campos(
        self, client, superuser
    ):
        """Limpar por HTMX trocava só os resultados e deixava os campos sujos.

        Os campos do filtro vivem no `<form>`, fora do alvo do swap. Limpando
        por HTMX a URL ficava limpa e a listagem voltava sem filtro, mas o
        campo seguia exibindo o texto e o checkbox seguia marcado — e o
        "Aplicar filtros" seguinte reenviava, em silêncio, o filtro que a
        pessoa acabara de limpar. A navegação nativa rerenderiza o formulário
        inteiro pelo servidor, deixando campos, resultados e URL coerentes.
        """
        _login(client, superuser)
        pagina = client.get(URL_HISTORICO_REQUISICOES, {'texto': 'x'}).content.decode()
        marca = 'id="filtro-acoes-historico-requisicoes"'
        trecho = pagina[pagina.index(marca) :]
        trecho = trecho[: trecho.index('</span>')]
        assert 'Limpar filtros' in trecho
        assert 'hx-get' not in trecho, (
            f'Limpar precisa ser navegação nativa, não swap HTMX: {trecho}'
        )

    def test_submit_fica_fora_do_wrapper_reemitido_via_oob(self, client, superuser):
        """O swap OOB não pode destruir o botão que disparou a requisição.

        O wrapper reemitido já foi a linha inteira, "Aplicar filtros" incluído.
        Como `hx-swap-oob` substitui o elemento, o submit era removido do DOM
        pelo swap que ele mesmo disparou: o foco caía no `<body>` e o próximo
        Tab recomeçava a página inteira.
        """
        _login(client, superuser)
        parcial = client.get(
            URL_HISTORICO_REQUISICOES, {'texto': 'x'}, HTTP_HX_REQUEST='true'
        ).content.decode()
        marca = 'id="filtro-acoes-historico-requisicoes"'
        trecho = parcial[parcial.index(marca) :]
        trecho = trecho[: trecho.index('</span>')]
        assert 'hx-swap-oob="true"' in trecho
        assert 'Aplicar filtros' not in trecho, (
            f'O submit não pode ser reemitido no OOB: {trecho}'
        )

    def test_form_de_filtros_sinaliza_envio_em_andamento(self, client, superuser):
        """Aplicar filtro não devolvia sinal nenhum até o swap chegar."""
        _login(client, superuser)
        conteudo = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        # A partir do <details> — o primeiro <form> da página é o de logout.
        barra = conteudo[conteudo.index('<details') :]
        barra = barra[: barra.index('</details>')]
        assert (
            'data-prevent-double-submit'
            in barra[: barra.index('>', barra.index('<form'))]
        )

    def test_todos_os_campos_esperados_presentes(self, client, chefe_almoxarifado):
        _login(client, chefe_almoxarifado)
        content = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        for campo in (
            'name="texto"',
            'name="data_ini"',
            'name="data_fim"',
            'name="setor"',
            'name="estados"',
        ):
            assert campo in content


class TestHistoricoRequisicoesResponsivo:
    """Paridade estrutural da barra de filtros extraída (issue #88)."""

    def test_barra_filtros_html_balanceado(self, client, superuser):
        _login(client, superuser)
        content = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        inicio = content.index('<details')
        fim = content.index('</details>', inicio) + len('</details>')
        assert_html_balanceado(content[inicio:fim])

    def test_wrapper_form_tem_sm_block_important(self, client, superuser):
        _login(client, superuser)
        content = client.get(URL_HISTORICO_REQUISICOES).content.decode()
        assert 'sm:block!' in content

    def test_template_usa_partials_de_filtro_sem_duplicar_campos_inline(self):
        caminho = (
            Path(__file__).resolve().parent.parent
            / 'templates'
            / 'requisicoes'
            / 'historico_requisicoes.html'
        )
        fonte = caminho.read_text()
        assert 'components/filter_shell.html#abertura' in fonte
        assert 'components/filter_busca.html' in fonte
        assert 'components/filter_data.html' in fonte
        assert 'components/filter_checkbox_group.html' in fonte
        assert 'components/filter_acoes.html' in fonte
        assert 'type="search"' not in fonte
        assert 'type="date"' not in fonte
        assert 'type="checkbox"' not in fonte


class TestNavHistoricoRequisicoes:
    def test_menu_mostra_link_para_almox(self, client, chefe_almoxarifado):
        # Página 'minhas' (não a própria tela de histórico, que já contém sua
        # URL nos atributos hx-get do form de filtros) para isolar o link de nav.
        _login(client, chefe_almoxarifado)
        response = client.get(reverse('requisicoes:minhas'))
        assert 'Histórico de requisições'.encode() in response.content

    def test_menu_esconde_link_para_solicitante(self, client, solicitante):
        _login(client, solicitante)
        response = client.get(reverse('requisicoes:minhas'))
        assert 'Histórico de requisições'.encode() not in response.content


# ---------------------------------------------------------------------------
# Testes dos achados médios da auditoria UI/UX — issue #63
# M1: side nav lg+, M2: campo Atualizada em, M3: coluna Material histórico,
# M4: badge cancelada, M5: scroll shadow, M6: ordem cards pronta retirada
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_side_nav_renderiza_links_para_autenticado(client, solicitante):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    html = response.content.decode('utf-8')
    assert 'hidden lg:flex' in html
    assert 'Navegação principal' in html


@pytest.mark.django_db
def test_hamburger_oculto_em_lg(client, solicitante):
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    assert 'lg:hidden' in response.content.decode('utf-8')


@pytest.mark.django_db
def test_detalhe_nao_exibe_campo_atualizado_em(
    client, solicitante, req_enviada_solicitante
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    assert response.status_code == 200
    assert 'Atualizada em'.encode() not in response.content


@pytest.mark.django_db
def test_historico_material_mostra_contagem_para_multi_itens(
    client, superuser, setor_obras, material_disponivel, material_disponivel_2
):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-M301',
        criador=superuser,
        beneficiario=superuser,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req, material=material_disponivel, quantidade_solicitada=1
    )
    ItemRequisicao.objects.create(
        requisicao=req, material=material_disponivel_2, quantidade_solicitada=2
    )
    _login(client, superuser)
    response = client.get(reverse('requisicoes:historico'))
    html = response.content.decode('utf-8')
    assert material_disponivel.nome in html
    assert 'e mais 1' in html


@pytest.mark.django_db
def test_historico_material_mostra_nome_como_secundario_para_item_unico(
    client, superuser, setor_obras, material_disponivel
):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-M302',
        criador=superuser,
        beneficiario=superuser,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req, material=material_disponivel, quantidade_solicitada=1
    )
    _login(client, superuser)
    response = client.get(reverse('requisicoes:historico'))
    html = response.content.decode('utf-8')
    # Item único não ganha sufixo de contagem: o nome sozinho já é o conteúdo.
    # `e mais 0` é a forma que um `add:"-1"` sem guarda produziria — e "e mais"
    # solto colide com "atualmente mais recentes primeiro" do controle de ordem.
    assert material_disponivel.nome in html
    assert 'e mais 0' not in html
    assert 'e mais 1' not in html


@pytest.mark.django_db
def test_badge_cancelada_usa_cor_laranja(client, solicitante, setor_obras):
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.CANCELADA,
        numero_publico='REQ-2026-M401',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert 'bg-cancel-muted'.encode() in response.content


@pytest.mark.django_db
def test_badge_recusada_usa_cor_vermelha(
    client, solicitante, req_enviada_solicitante, chefe_obras
):
    from apps.requisicoes.services import recusar_requisicao

    req = recusar_requisicao(
        ator_id=chefe_obras.pk,
        requisicao_id=req_enviada_solicitante.pk,
        motivo='Sem orçamento.',
    )
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200
    assert 'bg-danger-muted-strong'.encode() in response.content


@pytest.mark.django_db
def test_atender_retirada_itens_sem_scroll_horizontal(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    )
    assert response.status_code == 200
    assert 'overflow-x-auto'.encode() not in response.content
    assert '<table'.encode() not in response.content
    # O nome do material saiu do rótulo de cada campo e virou o nome do grupo
    # da linha; o rótulo curto é o que aparece na tela abaixo de lg.
    assert 'role="group"'.encode() in response.content
    assert '>Entregue'.encode() in response.content


@pytest.mark.django_db
def test_detalhe_pronta_retirada_registrar_antes_cancelar(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk})
    )
    html = response.content.decode('utf-8')
    assert html.index('atender-retirada-titulo') < html.index('cancelamento-titulo')


# ---------------------------------------------------------------------------
# Issue #111 — timeline mostra o que a divergência de estoque significa
# ---------------------------------------------------------------------------


def _bloco_timeline(conteudo: str) -> str:
    """Recorta só a timeline da página, para não asserir contra o HTML inteiro."""
    inicio = conteudo.index('aria-label="Histórico da requisição"')
    fim = conteudo.index('</ol>', inicio)
    return conteudo[inicio:fim]


def _req_com_evento_divergencia(*, solicitante, setor_obras, material, metadata, ator):
    """Requisição autorizada com um evento de atualização de estoque relevante."""
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AUTORIZADA,
        numero_publico='REQ-2026-000111',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req,
        material=material,
        quantidade_solicitada=Decimal('3'),
        quantidade_autorizada=Decimal('3'),
    )
    TimelineRequisicao.objects.create(
        requisicao=req,
        evento=EventoTimeline.ATUALIZACAO_ESTOQUE_RELEVANTE,
        ator=ator,
        estado_resultante=None,
        metadata=metadata,
    )
    return req


@pytest.mark.django_db
def test_timeline_mostra_origem_saida_excepcional_e_orientacao(
    client, solicitante, setor_obras, material_disponivel
):
    """Origem saída excepcional: número público, materiais e orientação de resolução."""
    _login(client, solicitante)
    req = _req_com_evento_divergencia(
        solicitante=solicitante,
        setor_obras=setor_obras,
        material=material_disponivel,
        ator=solicitante,
        metadata={
            'saida_excepcional_id': 7,
            'numero_publico': 'SXP-2026-000042',
            'materiais': [
                {'codigo': material_disponivel.codigo, 'nome': material_disponivel.nome}
            ],
        },
    )

    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200

    timeline = _bloco_timeline(response.content.decode())
    assert 'Saída excepcional SXP-2026-000042' in ' '.join(timeline.split())
    assert 'deixou o saldo físico abaixo do reservado' in timeline
    assert f'{material_disponivel.codigo} — {material_disponivel.nome}' in timeline
    # Espaço em branco normalizado: a versão anterior procurava o trecho literal
    # e, com isso, obrigava o template a manter a frase numa linha física — um
    # teste ditando a formatação do HTML que ele mede.
    corrido = ' '.join(timeline.split())
    assert (
        'A separação para retirada fica bloqueada até a divergência ser '
        'resolvida ou esta requisição ser cancelada' in corrido
    )


@pytest.mark.django_db
def test_link_da_saida_excepcional_respeita_quem_pode_consultar(
    client, solicitante, aux_almoxarifado, setor_obras, material_disponivel
):
    """A rota de saída do alerta EST-07 existe só para quem pode abrir o destino.

    O alerta nomeava a saída e os materiais em texto puro e não oferecia rota
    para nada — quem lê no galpão tinha de decorar o número. Mas
    `detalhe_saida_excepcional_view` exige `pode_consultar_saidas_excepcionais`,
    então um link incondicional levaria o solicitante da própria requisição a um
    403: uma rota que promete e não entrega é pior que texto.
    """
    metadata = {
        # A saída em si não precisa existir: o template só monta a URL, e é a
        # emissão (ou não) do link que este teste mede.
        'saida_excepcional_id': 7,
        'numero_publico': 'SXP-2026-000042',
        'materiais': [
            {'codigo': material_disponivel.codigo, 'nome': material_disponivel.nome}
        ],
    }
    req = _req_com_evento_divergencia(
        solicitante=solicitante,
        setor_obras=setor_obras,
        material=material_disponivel,
        ator=solicitante,
        metadata=metadata,
    )
    url_destino = reverse('estoque:detalhe_saida_excepcional', kwargs={'pk': 7})
    url_detalhe = reverse('requisicoes:detalhe', kwargs={'pk': req.pk})

    # Solicitante: não pode consultar saídas excepcionais, então não recebe link.
    _login(client, solicitante)
    timeline = _bloco_timeline(client.get(url_detalhe).content.decode())
    assert 'Saída excepcional SXP-2026-000042' in timeline, (
        'sem permissão o número continua nomeado, só não vira rota'
    )
    assert url_destino not in timeline

    # Almoxarifado: é quem resolve a divergência, e recebe a rota.
    _login(client, aux_almoxarifado)
    timeline = _bloco_timeline(client.get(url_detalhe).content.decode())
    assert url_destino in timeline, (
        'quem pode resolver a divergência precisa chegar à saída que a causou'
    )


@pytest.mark.django_db
def test_timeline_mostra_origem_importacao_scpi_sem_numero_publico(
    client, solicitante, setor_obras, material_disponivel
):
    """Origem SCPI não tem numero_publico: template não quebra nem exibe rótulo vazio."""
    _login(client, solicitante)
    req = _req_com_evento_divergencia(
        solicitante=solicitante,
        setor_obras=setor_obras,
        material=material_disponivel,
        ator=solicitante,
        metadata={
            'importacao_id': 3,
            'materiais': [
                {'codigo': material_disponivel.codigo, 'nome': material_disponivel.nome}
            ],
        },
    )

    response = client.get(reverse('requisicoes:detalhe', kwargs={'pk': req.pk}))
    assert response.status_code == 200

    timeline = _bloco_timeline(response.content.decode())
    assert 'Importação SCPI' in timeline
    assert 'Saída excepcional' not in timeline
    assert f'{material_disponivel.codigo} — {material_disponivel.nome}' in timeline


# ---------------------------------------------------------------------------
# Auditoria das telas de listagem — regressões
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_estado_badge_nao_e_live_region(client, solicitante, req_enviada_solicitante):
    """Badge de estado é dado estático de listagem, não mensagem.

    `role="status"` implica `aria-live="polite"`: uma listagem de 25 linhas
    viraria 25 live regions, e no histórico elas ficariam aninhadas dentro da
    região do swap HTMX. O contexto "Estado:" passa por texto sr-only.
    """
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    html = response.content.decode()
    assert 'role="status"' not in html
    assert '<span class="sr-only">Estado: </span>' in html


@pytest.mark.django_db
def test_minhas_pagina_resultados(client, solicitante, setor_obras, monkeypatch):
    monkeypatch.setattr(views, 'PAGINA_MINHAS_REQUISICOES_TAMANHO', 2)
    for i in range(3):
        Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico=f'REQ-2026-P0{i}',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
    _login(client, solicitante)
    response = client.get(reverse('requisicoes:minhas'))
    assert response.context['page_obj'].paginator.num_pages == 2
    assert len(response.context['requisicoes']) == 2
    assert 'Próxima' in response.content.decode()

    # `next` do cartão codifica `request.get_full_path`: ao abrir um cartão da
    # página 2, o "Voltar" do detalhe tem que trazer de volta à página 2.
    from django.template.defaultfilters import urlencode as tpl_urlencode

    url = reverse('requisicoes:minhas')
    assert 'page%3D2' not in response.content.decode()
    pagina2 = client.get(url, {'page': 2}).content.decode()
    assert f'?next={tpl_urlencode(url + "?page=2")}' in pagina2


@pytest.mark.django_db
def test_fila_autorizacao_pagina_resultados(
    client, chefe_obras, solicitante, setor_obras, monkeypatch
):
    monkeypatch.setattr(views, 'PAGINA_FILA_TAMANHO', 2)
    for i in range(3):
        Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico=f'REQ-2026-F0{i}',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
    _login(client, chefe_obras)
    response = client.get(reverse('requisicoes:autorizacoes'))
    assert response.context['page_obj'].paginator.num_pages == 2
    assert len(response.context['requisicoes']) == 2

    from django.template.defaultfilters import urlencode as tpl_urlencode

    url = reverse('requisicoes:autorizacoes')
    pagina2 = client.get(url, {'page': 2}).content.decode()
    assert f'?next={tpl_urlencode(url + "?page=2")}' in pagina2


@pytest.mark.django_db
def test_fila_atendimento_pagina_resultados(
    client, aux_almoxarifado, solicitante, setor_obras, monkeypatch
):
    monkeypatch.setattr(views, 'PAGINA_FILA_TAMANHO', 2)
    for i in range(3):
        Requisicao.objects.create(
            estado=EstadoRequisicao.AUTORIZADA,
            numero_publico=f'REQ-2026-A0{i}',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
    _login(client, aux_almoxarifado)
    response = client.get(reverse('requisicoes:atendimentos'))
    assert response.context['page_obj'].paginator.num_pages == 2
    assert len(response.context['requisicoes']) == 2

    from django.template.defaultfilters import urlencode as tpl_urlencode

    url = reverse('requisicoes:atendimentos')
    pagina2 = client.get(url, {'page': 2}).content.decode()
    assert f'?next={tpl_urlencode(url + "?page=2")}' in pagina2


@pytest.mark.django_db
def test_fila_paginacao_preserva_ordem_do_selector(
    client, aux_almoxarifado, solicitante, setor_obras, monkeypatch
):
    """`?ordem=asc` é parâmetro do histórico, não das filas.

    A fila tem ordem de domínio (FIFO por `atualizado_em`) e a paginação não
    pode reordenar em cima dela.
    """
    monkeypatch.setattr(views, 'PAGINA_FILA_TAMANHO', 10)
    for i in range(3):
        Requisicao.objects.create(
            estado=EstadoRequisicao.AUTORIZADA,
            numero_publico=f'REQ-2026-O0{i}',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
    _login(client, aux_almoxarifado)
    sem_ordem = client.get(reverse('requisicoes:atendimentos'))
    com_ordem = client.get(reverse('requisicoes:atendimentos') + '?ordem=asc')
    numeros = [r.numero_publico for r in sem_ordem.context['requisicoes']]
    assert [r.numero_publico for r in com_ordem.context['requisicoes']] == numeros


@pytest.mark.django_db
def test_historico_live_region_vazia_no_carregamento_inicial(
    client, superuser, req_historico_obras
):
    """A região existe no DOM desde o load para poder anunciar depois, mas
    nasce vazia: nada mudou ainda e um anúncio aqui seria ruído.
    """
    _login(client, superuser)
    html = client.get(reverse('requisicoes:historico')).content.decode()
    assert (
        '<p id="resumo-historico-requisicoes" class="sr-only" role="status"></p>'
        in html
    )
    assert 'aria-live=' not in html


@pytest.mark.django_db
def test_historico_swap_htmx_anuncia_so_o_resumo(
    client, superuser, req_historico_obras
):
    """O swap troca só o conteúdo da live region (`innerHTML:`), preservando o
    elemento — e a listagem em si não é marcada como live region.
    """
    _login(client, superuser)
    response = client.get(
        reverse('requisicoes:historico'), headers={'hx-request': 'true'}
    )
    html = response.content.decode()
    assert 'hx-swap-oob="innerHTML:#resumo-historico-requisicoes"' in html
    assert '1 requisição encontrada.' in html
    assert 'aria-atomic=' not in html


@pytest.mark.django_db
def test_historico_swap_htmx_anuncia_plural_com_duas_requisicoes(
    client, superuser, req_historico_obras, req_historico_ti
):
    """O plural mais difícil do sistema, casado na frase inteira.

    Aqui dois `pluralize` flexionam juntos na mesma frase — o substantivo troca
    a sílaba tônica (`requisição`/`requisições`) e o particípio concorda com ele
    (`encontrada`/`encontradas`). Um teste que casasse só o número passaria por
    cima de "2 requisição encontrada" sem piscar.
    """
    _login(client, superuser)
    html = client.get(
        reverse('requisicoes:historico'), headers={'hx-request': 'true'}
    ).content.decode()

    assert '2 requisições encontradas.' in html


@pytest.mark.django_db
def test_historico_swap_htmx_anuncia_resultado_vazio(client, superuser):
    _login(client, superuser)
    response = client.get(
        reverse('requisicoes:historico') + '?texto=inexistente',
        headers={'hx-request': 'true'},
    )
    assert 'Nenhuma requisição encontrada.' in response.content.decode()


@pytest.mark.django_db
def test_historico_contagem_visivel_na_pagina_completa(
    client, superuser, req_historico_obras
):
    """Issue #144: com a contagem só em `hx-swap-oob`, carga de página
    completa não mostrava nada pra quem enxerga — `resumo-historico-
    requisicoes` nasce vazio. A contagem visível fica na mesma linha do
    controle de ordenação, e precisa aparecer mesmo com resultado único (sem
    paginação, que só renderiza com mais de uma página).
    """
    _login(client, superuser)
    response = client.get(reverse('requisicoes:historico'))
    assert response.context['page_obj'].paginator.num_pages == 1
    html = response.content.decode()

    idx_ordenacao = html.index('Mais antigas primeiro')
    linha = html.rindex('<div', 0, idx_ordenacao)
    trecho = html[linha:idx_ordenacao]
    assert 'tabular-nums">1</span>' in trecho
    assert 'requisição' in trecho


@pytest.mark.django_db
def test_historico_contagem_visivel_em_resposta_htmx(
    client, superuser, req_historico_obras
):
    """A mesma contagem visível também na resposta parcial HTMX — não só a
    sr-only via swap out-of-band."""
    _login(client, superuser)
    html = client.get(
        reverse('requisicoes:historico'), headers={'hx-request': 'true'}
    ).content.decode()

    idx_ordenacao = html.index('Mais antigas primeiro')
    linha = html.rindex('<div', 0, idx_ordenacao)
    trecho = html[linha:idx_ordenacao]
    assert 'tabular-nums">1</span>' in trecho
    assert 'requisição' in trecho


def _extrai_linha_da_contagem(html):
    idx_ordenacao = html.index('Mais antigas primeiro')
    linha = html.rindex('<div', 0, idx_ordenacao)
    return html[linha:idx_ordenacao]


@pytest.mark.django_db
def test_historico_contagem_com_paginacao_diz_pagina_e_recorte(
    client, superuser, solicitante, setor_obras
):
    """Issue #156: com paginação a linha de cima mostrava `<span>` vazio e a
    contagem do recorte só reaparecia no rodapé. Agora diz
    "25 de 26 requisições" — quantos nesta página `de` quantos no recorte —
    nos dois caminhos de render.
    """
    Requisicao.objects.bulk_create(
        Requisicao(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico=f'REQ-2026-90{n:02d}',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        for n in range(26)
    )
    _login(client, superuser)

    esperado = (
        'tabular-nums">25</span> de <span class="font-medium tabular-nums">26</span>'
    )

    completa = client.get(reverse('requisicoes:historico'))
    assert completa.context['page_obj'].paginator.num_pages == 2
    trecho_completa = _extrai_linha_da_contagem(completa.content.decode())
    assert esperado in trecho_completa
    assert 'requisições' in trecho_completa
    assert '<span></span>' not in trecho_completa

    parcial = client.get(
        reverse('requisicoes:historico'), headers={'hx-request': 'true'}
    ).content.decode()
    assert esperado in _extrai_linha_da_contagem(parcial)


@pytest.mark.django_db
def test_historico_ordenacao_disponivel_no_mobile(
    client, superuser, req_historico_obras
):
    """O <th> ordenável vive na tabela, que só existe a partir de 640px; o
    controle equivalente precisa existir no chrome de cards.

    O rótulo nomeia o **destino**, não o estado corrente: em `ordem=desc`
    (default) o controle leva para crescente, então diz "Mais antigas primeiro".
    Antes ele dizia "Mais recentes primeiro" — o que a tela já mostrava — e
    apontava para o inverso.
    """
    _login(client, superuser)
    html = client.get(reverse('requisicoes:historico')).content.decode()
    assert 'Mais antigas primeiro' in html
    assert 'Mais recentes primeiro' not in html
    assert (
        html.count(
            'aria-label="Ordenar por mais antigas primeiro; '
            'atualmente mais recentes primeiro"'
        )
        == 1
    )
    assert html.count('id="ordenacao-resultados-historico-requisicoes"') == 1


@pytest.mark.django_db
def test_historico_botoes_ver_tem_nome_acessivel_unico(
    client, superuser, req_historico_obras
):
    _login(client, superuser)
    html = client.get(reverse('requisicoes:historico')).content.decode()
    marcador = 'aria-label="Ver detalhes da requisição REQ-2026-0010"'
    assert html.count(marcador) == 1


@pytest.mark.django_db
def test_historico_material_nao_usa_prefetch_de_todos_os_itens(
    client,
    superuser,
    setor_obras,
    material_disponivel,
    material_disponivel_2,
):
    """O nome do material vem de Subquery: acrescentar itens à requisição não
    pode acrescentar query nenhuma à listagem.
    """
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
        numero_publico='REQ-2026-S001',
        criador=superuser,
        beneficiario=superuser,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req, material=material_disponivel, quantidade_solicitada=1
    )
    _login(client, superuser)
    url = reverse('requisicoes:historico')

    with CaptureQueriesContext(connection) as antes:
        client.get(url)

    ItemRequisicao.objects.create(
        requisicao=req, material=material_disponivel_2, quantidade_solicitada=2
    )
    with CaptureQueriesContext(connection) as depois:
        client.get(url)

    assert len(depois) == len(antes)


@pytest.mark.django_db
def test_listagens_tem_html_balanceado(
    client, superuser, setor_obras, material_disponivel
):
    """Guarda o padrão "abertura em partial, fechamento literal na tela".

    `components/table.html` e `components/filter_shell.html` só encapsulam as
    aberturas; `</div>`, `</table>` e `</article>` ficam soltos na tela
    chamadora. Uma reindentação distraída desbalanceia a página sem quebrar
    nenhum outro teste.
    """
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.AUTORIZADA,
        numero_publico='REQ-2026-B001',
        criador=superuser,
        beneficiario=superuser,
        setor_beneficiario=setor_obras,
    )
    ItemRequisicao.objects.create(
        requisicao=req, material=material_disponivel, quantidade_solicitada=1
    )
    _login(client, superuser)

    for nome_url in (
        'requisicoes:minhas',
        'requisicoes:autorizacoes',
        'requisicoes:atendimentos',
        'requisicoes:historico',
    ):
        response = client.get(reverse(nome_url))
        assert response.status_code == 200, nome_url
        assert_html_balanceado(response.content.decode())


# ---------------------------------------------------------------------------
# Título de tela — contrato de slots documentado em base_auth.html
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tela_principal_mantem_brand_e_poe_h1_no_conteudo(client, solicitante):
    """Leading default é a brand; só subtela troca por nav-icon + título.

    Uma tela principal que sobrescreve `topbar_leading` some com a brand e
    deixa o <main> sem cabeçalho para navegação por landmark.
    """
    _login(client, solicitante)
    html = client.get(reverse('requisicoes:minhas')).content.decode()
    assert 'app-bar__brand' in html
    assert 'app-bar__title' not in html
    assert (
        '<h1 class="text-2xl font-semibold text-text-primary sm:text-3xl mb-2">' in html
    )
    assert 'Minhas requisições' in html


@pytest.mark.django_db
def test_subtela_mantem_titulo_na_barra_com_back_arrow(
    client, solicitante, req_rascunho_solicitante
):
    """Pattern Material sancionado pelo brief: em subtela o <h1> vive na barra,
    ao lado do back-arrow, e o hambúrguer some.
    """
    _login(client, solicitante)
    html = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_rascunho_solicitante.pk})
    ).content.decode()
    assert 'app-bar__nav-icon' in html
    assert 'app-bar__title' in html


@pytest.mark.django_db
def test_telas_tem_exatamente_um_h1(
    client, solicitante, chefe_obras, req_rascunho_solicitante
):
    _login(client, solicitante)
    for url in (
        reverse('requisicoes:minhas'),
        reverse('requisicoes:detalhe', kwargs={'pk': req_rascunho_solicitante.pk}),
        reverse('requisicoes:nova_requisicao'),
    ):
        html = client.get(url).content.decode()
        assert html.count('<h1') == 1, url

    _login(client, chefe_obras)
    for url in (
        reverse('requisicoes:autorizacoes'),
        reverse('requisicoes:historico'),
    ):
        html = client.get(url).content.decode()
        assert html.count('<h1') == 1, url


# ---------------------------------------------------------------------------
# Acessibilidade dos formulários — auditoria rascunho_form / atender_retirada
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_radio_beneficiario_tem_fieldset_e_legend(client, aux_obras):
    """Sem <legend> os radios têm rótulo individual, mas a pergunta que eles
    respondem não existe no DOM — e é ela que separa Criador de Beneficiário.
    """
    _login(client, aux_obras)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert '<fieldset' in html
    assert '<legend class="sr-only">Criar para</legend>' in html


@pytest.mark.django_db
def test_campos_do_formset_de_atendimento_passam_pelo_componente(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """O componente injeta aria-invalid/aria-describedby; a versão à mão não.

    O `max` do item e o `step` da unidade continuam presentes — são o motivo
    pelo qual a linha escrevia o <input> na mão.
    """
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    ).content.decode()
    assert 'aria-describedby="hint-id_itens-0-quantidade_entregue"' in html
    assert 'max="2.000"' in html
    assert 'min-h-11' in html
    # BaseFormSet desliga use_required_attribute; sem `required` explícito o
    # checkValidity que guarda o modal não barraria campo vazio.
    assert 'required' in html
    # Binding Alpine precisa do atributo com hífen, não com underscore.
    assert 'x-bind:aria-required="parcial"' in html
    assert 'aria_required' not in html
    # Uma live region por linha viraria N regiões concorrentes na página.
    assert 'aria-live=' not in html


@pytest.mark.django_db
def test_atender_retirada_nao_expoe_pk_nem_ramo_morto(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    ).content.decode()
    assert f'#{req_pronta_view_com_itens.pk}' not in html
    assert 'Rascunho' not in html


@pytest.mark.django_db
def test_sumario_de_erros_lista_campos_invalidos(client, solicitante):
    """Formulário longo re-renderizado só com erro inline não identifica a
    falha: no celular o campo inválido pode estar três roladas abaixo.
    """
    _login(client, solicitante)
    response = client.post(
        reverse('requisicoes:nova_requisicao'),
        {
            'observacao_geral': '',
            'itens-TOTAL_FORMS': '1',
            'itens-INITIAL_FORMS': '0',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-material_id': '',
            'itens-0-material_label': '',
            'itens-0-quantidade_solicitada': '',
            'acao': 'rascunho',
        },
    )
    html = response.content.decode()
    assert 'role="alert"' in html
    assert 'tabindex="-1"' in html
    assert 'problema encontrado' in html or 'problemas encontrados' in html


def test_step_por_unidade_espelha_a_precisao_de_formatar_quantidade():
    """Se a tela formata 'un' como inteiro, o campo não pode aceitar 0,001 un."""
    from apps.core.templatetags.core_tags import formatar_quantidade, step_por_unidade

    assert step_por_unidade('un') == '1'
    assert formatar_quantidade(Decimal('3.000'), 'un') == '3'
    assert step_por_unidade('kg') == '0.1'
    assert step_por_unidade('cx') == '0.001'


# ---------------------------------------------------------------------------
# Auditoria do detalhe e da confirmação de cópia
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_copiar_confirmacao_recusa_estado_nao_copiavel(
    client, solicitante, req_rascunho_solicitante
):
    """A confirmação não pode prometer o que o POST recusaria: rascunho não é
    estado copiável, então o GET volta ao detalhe com o motivo.
    """
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:copiar', kwargs={'pk': req_rascunho_solicitante.pk})
    )
    assert response.status_code == 302
    assert response.url == reverse(
        'requisicoes:detalhe', kwargs={'pk': req_rascunho_solicitante.pk}
    )
    mensagens = [str(m) for m in get_messages(response.wsgi_request)]
    assert any('atendidas ou recusadas' in m for m in mensagens)


@pytest.mark.django_db
def test_copiar_confirmacao_nao_expoe_pk_e_lista_itens(
    client, solicitante, req_recusada_view
):
    """Na tela servida, o título usa o número público (nunca o __str__, que
    devolve a PK) e os itens a copiar ficam visíveis antes da confirmação.
    """
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:copiar', kwargs={'pk': req_recusada_view.pk})
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert req_recusada_view.numero_publico in html
    assert f'#{req_recusada_view.pk}' not in html
    assert 'Itens que serão copiados' in html


@pytest.mark.django_db
def test_detalhe_nao_usa_token_com_modificador_de_opacidade(
    client, solicitante, req_pronta_view_com_itens
):
    """`bg-token/60` produz cor que não existe na paleta e depende do que está
    atrás — o rebrand deixa de ser troca de valor em input.css.
    """
    _login(client, solicitante)
    html = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk})
    ).content.decode()
    import re

    achados = re.findall(r'class="[^"]*\b(?:bg|text)-[a-z-]+/\d\d\b[^"]*"', html)
    assert not achados, achados


@pytest.mark.django_db
def test_detalhe_respeita_a_escala_de_elevacao(
    client, solicitante, req_pronta_view_com_itens
):
    """0, 1dp, 8dp e 24dp — `shadow-md` é degrau inventado, e sombra como
    ênfase visual está fora do design system.
    """
    _login(client, solicitante)
    html = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk})
    ).content.decode()
    assert 'shadow-md' not in html


@pytest.mark.django_db
def test_detalhe_calcula_entregue_liquida_em_uma_query(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """Uma query por item era N+1 na tela mais consultada do almoxarifado."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.estoque.selectors import entregue_liquida_por_requisicao

    with CaptureQueriesContext(connection) as ctx:
        entregue_liquida_por_requisicao(requisicao_id=req_pronta_view_com_itens.pk)
    assert len(ctx) == 1


def test_button_tem_variante_return_outline():
    """Devolução é teal por regra do design system; sem a variante, a tela era
    empurrada a escrever o botão à mão.
    """
    from django.template.loader import render_to_string

    html = render_to_string(
        'components/button.html',
        {'variant': 'return-outline', 'label': 'Registrar devolução'},
    )
    assert 'text-return-text-strong' in html
    # `border-return` (teal-600, 3,66:1) e não `border-return-border` (teal-200,
    # 1,26:1): sobre `bg-surface` a borda é a única delimitação do controle, e a
    # WCAG 1.4.11 pede 3:1 — ver test_borda_de_controle_passa_em_1411.
    assert 'border-return ' in html
    assert 'min-h-11' in html


# ---------------------------------------------------------------------------
# Itens do detalhe: dupla renderização (sem tabela espremida no mobile)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_detalhe_itens_renderiza_como_pilha_em_toda_largura(
    client, solicitante, req_pronta_view_com_itens
):
    """Os itens deixaram de ter renderização em tabela: a pilha vale em
    qualquer viewport, sem contêiner de scroll horizontal.
    """
    _login(client, solicitante)
    html = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_pronta_view_com_itens.pk})
    ).content.decode()
    assert '<ul class="divide-y divide-border">' in html
    assert 'overflow-x-auto' not in html
    assert '<table' not in html


@pytest.mark.django_db
def test_detalhe_tabela_de_itens_nao_tem_coluna_de_acoes(
    client, aux_almoxarifado, req_atendida_view
):
    """A ação de devolução saiu da linha: com duas renderizações, um gatilho por
    linha duplicaria o <dialog> com o mesmo id.
    """
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_atendida_view.pk})
    ).content.decode()
    assert '>Ações</th>' not in html
    assert 'Devolução ao estoque' in html


@pytest.mark.django_db
def test_detalhe_renderiza_um_unico_modal_por_item_devolvivel(
    client, aux_almoxarifado, req_atendida_view
):
    """Id duplicado quebraria getElementById, o trap de foco e o retorno de foco."""
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_atendida_view.pk})
    ).content.decode()
    item = req_atendida_view.itens.first()
    assert html.count(f'id="devolver-{item.pk}"') == 1
    assert html.count(f'data-modal-trigger="devolver-{item.pk}"') == 1


@pytest.mark.django_db
def test_detalhe_omite_bloco_de_devolucao_sem_entregue_liquida(
    client, aux_almoxarifado, req_atendida_view
):
    """Devolvido tudo, o bloco não tem linha nenhuma — então não deve existir.

    A operação continua disponível no domínio; é a lista de itens devolvíveis
    que decide se a seção é renderizada.
    """
    from apps.requisicoes.services import registrar_devolucao

    _login(client, aux_almoxarifado)
    for item in req_atendida_view.itens.all():
        registrar_devolucao(
            ator_id=aux_almoxarifado.pk,
            requisicao_id=req_atendida_view.pk,
            item_id=item.pk,
            quantidade=item.quantidade_entregue,
        )

    html = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_atendida_view.pk})
    ).content.decode()
    assert 'Devolução ao estoque' not in html


@pytest.mark.django_db
def test_detalhe_nao_compara_estado_cru_no_template(
    client, aux_almoxarifado, req_atendida_view
):
    """Quais quantidades aparecem vem de flags da view, não de `estado == '...'`
    no template: o grafo de estados tem fonte única (PRODUCT.md).
    """
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_atendida_view.pk})
    )
    assert response.context['mostrar_quantidade_autorizada'] is True
    assert response.context['mostrar_quantidade_entregue'] is True
    assert response.context['cancelamento_inline'] is False
    html = response.content.decode()
    assert '>Autorizada</dt>' in html
    assert '>Entregue</dt>' in html


@pytest.mark.django_db
def test_detalhe_rascunho_nao_mostra_quantidades_de_decisao(
    client, solicitante, req_rascunho_solicitante
):
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_rascunho_solicitante.pk})
    )
    assert response.context['mostrar_quantidade_autorizada'] is False
    assert response.context['mostrar_quantidade_entregue'] is False
    assert response.context['cancelamento_inline'] is True
    html = response.content.decode()
    assert '>Autorizada</dt>' not in html
    assert '>Entregue</dt>' not in html


# ---------------------------------------------------------------------------
# Regressões da auditoria de UI — rascunho_form e atender_retirada
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rascunho_botao_adicionar_deriva_indice_do_total_forms(client, solicitante):
    """Índice da nova linha vem do TOTAL_FORMS, não de uma contagem no DOM.

    Contando `.item-form-row` no DOM, dois cliques rápidos liam o mesmo número
    antes de qualquer swap e o POST ficava com dois grupos `itens-N-*` — o
    QueryDict guardava só o último e um material sumia sem erro na tela.
    `hx-sync` fecha a janela; o TOTAL_FORMS é a fonte única do número.
    """
    _login(client, solicitante)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert 'hx-sync="this:queue all"' in html
    assert 'id_itens-TOTAL_FORMS' in html
    assert 'document.querySelectorAll(".item-form-row").length' not in html


@pytest.mark.django_db
def test_rascunho_nao_declara_script_inline_de_formset(client, solicitante):
    """Comportamento vive na factory Alpine, não num <script> inline global."""
    _login(client, solicitante)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert 'function incrementarTotalForms' not in html
    assert 'aoAdicionarLinha($event)' in html


@pytest.mark.django_db
def test_rascunho_radios_tem_id_que_casa_com_ancora_do_sumario(client, aux_obras):
    """Sem `id`, a âncora `#id_modo_criacao_0` do sumário não acha nada.

    É o campo que separa Criador de Beneficiário — o que o sumário mais precisa
    alcançar quando o formulário volta com erro no celular.
    """
    _login(client, aux_obras)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert 'id="id_modo_criacao_0"' in html
    assert 'id="id_modo_criacao_1"' in html


@pytest.mark.django_db
def test_rascunho_combobox_beneficiario_carrega_id_do_campo(client, aux_obras):
    """O id do campo fica no input visível; o hidden usa sufixo `-valor`.

    Âncora em `<input type="hidden">` não move foco nem rolagem: o hidden é
    `display:none`.
    """
    _login(client, aux_obras)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert 'id="id_beneficiario_id"' in html
    assert 'id="id_beneficiario_id-valor"' in html


@pytest.mark.django_db
def test_rascunho_secao_com_erro_marca_borda_e_nao_fundo(
    client, solicitante, material_disponivel
):
    """Fundo `danger-subtle` levava os rótulos slate-500 para ~4.35:1.

    O sumário de erros continua usando esse fundo — lá o texto é
    `danger-text-strong` e o contraste sobra. O que saiu foi a pintura da
    seção inteira, que envolvia campos e rótulos de metadado.
    """
    _login(client, solicitante)
    dados = _formset_post(material_disponivel.pk, quantidade='0')
    html = client.post(reverse('requisicoes:nova_requisicao'), dados).content.decode()
    assert 'rounded-xl border bg-surface border-danger-border-strong' in html
    assert 'border-danger-border-strong bg-danger-subtle' not in html.replace(
        'rounded-lg border border-danger-border-strong bg-danger-subtle', ''
    )


@pytest.mark.django_db
def test_rascunho_campo_quantidade_vem_do_componente_com_alvo_de_44px(
    client, solicitante
):
    """Linha de item usa form_field.html — e com ele o piso de toque e o ARIA."""
    _login(client, solicitante)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert 'id="id_itens-0-quantidade_solicitada"' in html
    assert 'min-h-11' in html
    assert 'inputmode="numeric"' in html


@pytest.mark.django_db
def test_rascunho_aviso_de_formset_e_regiao_viva_separada_da_dica(client, solicitante):
    """A dica estática perdia o texto original em dois cliques seguidos.

    Ela acumulava dica + live region + gancho de JS; agora o aviso tem região
    própria, vazia no carregamento — que é o único estado em que uma live
    region anuncia coisa alguma.
    """
    _login(client, solicitante)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert 'data-formset-aviso' in html
    assert 'aviso_quantidade' not in html


@pytest.mark.django_db
def test_atender_retirada_tem_barra_de_acao_fixa_no_mobile(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """A separação acontece em pé, no galpão: confirmar não pode exigir rolar
    a lista inteira de volta."""
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    ).content.decode()
    assert 'fixed inset-x-0 bottom-0 z-10' in html
    assert 'env(safe-area-inset-bottom)' in html


@pytest.mark.django_db
def test_linha_de_item_tira_min_e_step_do_widget_e_nao_do_template(client, solicitante):
    """`min`/`step` são restrição de domínio: moram no Form, não no template.

    Passá-los também como parâmetro do include criava duas fontes para a mesma
    regra, com o template ganhando de quem valida.
    """
    _login(client, solicitante)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    campo = re.search(
        r'<input[^>]*id="id_itens-0-quantidade_solicitada"[^>]*>', html
    ).group()
    assert 'min="1"' in campo
    assert 'step="1"' in campo
    assert campo.count('min=') == 1
    assert campo.count('step=') == 1


@pytest.mark.django_db
def test_botao_adicionar_nao_envia_total_forms_que_a_view_ignora(client, solicitante):
    """`hx-include` do TOTAL_FORMS era atributo morto: a view só lê `index`."""
    _login(client, solicitante)
    html = client.get(reverse('requisicoes:nova_requisicao')).content.decode()
    assert 'hx-include' not in html


@pytest.mark.django_db
def test_atender_sem_itens_desabilita_confirmar_com_motivo(
    client, aux_almoxarifado, solicitante, setor_obras
):
    """Ação de workflow bloqueada fica visível, desabilitada e com o motivo."""
    req = Requisicao.objects.create(
        estado=EstadoRequisicao.PRONTA_PARA_RETIRADA,
        numero_publico='REQ-2026-9200',
        criador=solicitante,
        beneficiario=solicitante,
        setor_beneficiario=setor_obras,
    )
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse('requisicoes:registrar_atendimento', kwargs={'pk': req.pk})
    ).content.decode()
    assert 'Confirmar retirada' in html
    assert 'disabled' in html
    assert 'id="motivo-sem-itens"' in html
    assert 'aria-describedby="motivo-sem-itens"' in html


@pytest.mark.django_db
def test_atender_preenche_quantidade_sem_zeros_a_direita(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """`1.000` num campo numérico é lido como mil em pt-BR — e ele baixa estoque."""
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    ).content.decode()
    campo = re.search(
        r'<input[^>]*id="id_itens-0-quantidade_entregue"[^>]*>', html
    ).group()
    assert 'value="2"' in campo
    assert 'value="2.000"' not in campo
    assert 'value="2,000"' not in campo


@pytest.mark.django_db
def test_atender_rotula_os_campos_da_linha(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """O campo que decide quanto sai do estoque não pode ficar sem rótulo.

    Visível abaixo de lg (onde não há cabeçalho de coluna) e `sr-only` a partir
    dele; o nome do material vem do `role="group"` da linha, não repetido dentro
    de cada rótulo.
    """
    item = req_pronta_view_com_itens.itens.first()
    _login(client, aux_almoxarifado)
    html = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    ).content.decode()
    assert f'aria-labelledby="item-{item.pk}-material"' in html
    assert f'id="item-{item.pk}-material"' in html
    assert 'role="group"' in html
    rotulo = re.search(
        r'<label[^>]*for="id_itens-0-quantidade_entregue"[^>]*>(.*?)</label>',
        html,
        re.S,
    )
    assert rotulo, 'campo de quantidade entregue sem <label> vinculada'
    assert 'Entregue' in rotulo.group(1)
    assert 'lg:sr-only' in rotulo.group()
    assert 'class="sr-only"' not in rotulo.group()


# ---------------------------------------------------------------------------
# Sumário de erros nas telas de formset longo (#125)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rascunho_post_invalido_traz_o_sumario(client, solicitante):
    """O guarda de arquivo vê o include; só o POST vê a view montar o contexto."""
    _login(client, solicitante)
    resp = client.post(
        reverse('requisicoes:nova_requisicao'),
        data={
            'observacao_geral': '',
            'itens-TOTAL_FORMS': '1',
            'itens-INITIAL_FORMS': '0',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-material_id': '',
            'itens-0-material_label': '',
            'itens-0-quantidade_solicitada': '',
        },
    )
    html = resp.content.decode()
    assert 'id="sumario-erros"' in html
    assert 'autofocus' in html
    assert 'Não foi possível salvar:' in html


@pytest.mark.django_db
def test_rascunho_erro_de_formset_aparece_uma_vez_so(client, solicitante):
    """A duplicata que a #125 removeu.

    O sumário no topo e o alerta de formset 150 linhas abaixo exibiam a mesma
    string, sem marcador de que era a mesma. Num viewport de 375px o usuário lê
    o total no topo, corrige, e reencontra um deles achando que é mais um.
    """
    _login(client, solicitante)
    resp = client.post(
        reverse('requisicoes:nova_requisicao'),
        data={
            'observacao_geral': '',
            'itens-TOTAL_FORMS': '1',
            'itens-INITIAL_FORMS': '0',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-material_id': '',
            'itens-0-material_label': '',
            'itens-0-quantidade_solicitada': '',
        },
    )
    html = resp.content.decode()
    assert html.count('A requisição precisa ter ao menos um item.') == 1


@pytest.mark.django_db
def test_atender_post_invalido_usa_a_frase_da_tela(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """A tela não salva nada: ela registra uma retirada.

    "Não foi possível salvar" descreve uma ação que esta tela não tem. A
    frase-líder é parametrizada pela tela; a pluralização segue no componente.
    """
    _login(client, aux_almoxarifado)
    item = req_pronta_view_com_itens.itens.first()
    resp = client.post(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        ),
        data={
            'itens-TOTAL_FORMS': '1',
            'itens-INITIAL_FORMS': '1',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-item_id': str(item.id),
            'itens-0-quantidade_entregue': '2',
            'itens-0-justificativa': '',
            'retirante_nome': '',
        },
    )
    html = resp.content.decode()
    assert 'id="sumario-erros"' in html
    assert 'Não foi possível registrar o atendimento:' in html
    assert 'Não foi possível salvar:' not in html


@pytest.mark.django_db
def test_atender_erro_de_formset_aparece_uma_vez_so(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """Fecha a terceira tela do guarda de duplicata.

    As outras duas já contavam `non_form_errors` no corpo da resposta; esta não
    tinha nenhuma contagem, e é a única cujo formset levanta o erro de conjunto
    (item duplicado) em vez do erro de "ao menos um item".
    """
    _login(client, aux_almoxarifado)
    item = req_pronta_view_com_itens.itens.first()
    resp = client.post(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        ),
        data={
            'itens-TOTAL_FORMS': '2',
            'itens-INITIAL_FORMS': '2',
            'itens-MIN_NUM_FORMS': '0',
            'itens-MAX_NUM_FORMS': '1000',
            'itens-0-item_id': str(item.id),
            'itens-0-quantidade_entregue': '1',
            'itens-0-justificativa': '',
            'itens-1-item_id': str(item.id),
            'itens-1-quantidade_entregue': '1',
            'itens-1-justificativa': '',
            'retirante_nome': 'Carlos',
        },
    )
    html = resp.content.decode()
    assert 'id="sumario-erros"' in html
    sumario = re.search(r'<div\s+id="sumario-erros".*?</div>', html, re.S).group(0)
    assert sumario.count('Item duplicado no atendimento.') == 1
    assert html.count('Item duplicado no atendimento.') == 1


# ---------------------------------------------------------------------------
# O modal nomeia o registro que está confirmando (#138)
# ---------------------------------------------------------------------------


class _TextoDosDialogos(HTMLParser):
    """Texto visível de dentro de cada `<dialog>`, indexado pelo id do diálogo.

    Estrutural e não por fatia de string: a asserção é "este número chegou
    **dentro** desta caixa", e uma busca no documento inteiro passaria só
    porque a tela atrás do modal também mostra o número — que é exatamente a
    situação que a #138 existe para consertar.
    """

    def __init__(self):
        super().__init__()
        self.texto = {}
        self._atual = None

    def handle_starttag(self, tag, attrs):
        if tag == 'dialog':
            self._atual = dict(attrs).get('id')
            self.texto[self._atual] = []

    def handle_endtag(self, tag):
        if tag == 'dialog':
            self._atual = None

    def handle_data(self, data):
        if self._atual is not None:
            self.texto[self._atual].append(data)


def _texto_dos_dialogos(html):
    parser = _TextoDosDialogos()
    parser.feed(html)
    return {
        modal_id: ' '.join(' '.join(partes).split())
        for modal_id, partes in parser.texto.items()
    }


@pytest.mark.django_db
def test_todo_modal_do_detalhe_carrega_o_numero_publico(
    client, chefe_obras, req_enviada_solicitante
):
    """Autorizar, recusar, retornar e cancelar confirmam sobre um documento nomeado.

    Em bloco de decisão no desktop a pessoa abre várias requisições em sequência
    e confirmava sem nenhuma âncora de qual estava na frente — o vetor clássico
    de executar a ação certa no documento errado, num sistema sem desfazer.
    """
    _login(client, chefe_obras)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
    )
    textos = _texto_dos_dialogos(response.content.decode('utf-8'))

    assert textos, 'tela de decisão renderizada sem nenhum <dialog>'
    for modal_id, texto in textos.items():
        assert req_enviada_solicitante.numero_publico in texto, modal_id
        assert req_enviada_solicitante.beneficiario.nome in texto, modal_id


@pytest.mark.django_db
def test_modal_de_rascunho_diz_rascunho_e_nao_vaza_o_pk(
    client, solicitante, req_rascunho_solicitante
):
    """O rascunho tem modal e não tem número — e o fallback não é o `__str__`.

    `str(requisicao)` devolve `Rascunho #<pk>`, e `docs/CONVENTIONS.md`
    §Identificadores na interface diz que PK interno não vaza
    para UI. Quem responde "qual documento?" aqui é o beneficiário e o setor.
    """
    _login(client, solicitante)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_rascunho_solicitante.pk})
    )
    textos = _texto_dos_dialogos(response.content.decode('utf-8'))

    assert textos
    for modal_id, texto in textos.items():
        assert 'Rascunho' in texto, modal_id
        assert f'Rascunho #{req_rascunho_solicitante.pk}' not in texto, modal_id
        assert req_rascunho_solicitante.beneficiario.nome in texto, modal_id


@pytest.mark.django_db
def test_modal_de_retirada_repete_as_quantidades_que_serao_baixadas(
    client, aux_almoxarifado, req_pronta_view_com_itens
):
    """A pessoa digitou quantidade item a item; o modal repetia nenhuma delas.

    O corpo lista material e quantidade autorizada pelo servidor, e declara de
    qual `<input>` cada célula lê a quantidade entregue — o valor vivo, que só
    existe no campo. Parear por `id` e não por posição é o que sobrevive a uma
    mudança de ordem entre as duas listas.
    """
    _login(client, aux_almoxarifado)
    response = client.get(
        reverse(
            'requisicoes:registrar_atendimento',
            kwargs={'pk': req_pronta_view_com_itens.pk},
        )
    )
    html = response.content.decode('utf-8')
    texto = _texto_dos_dialogos(html)['confirmar-atender-retirada']

    item = req_pronta_view_com_itens.itens.first()
    assert req_pronta_view_com_itens.numero_publico in texto
    assert item.material.nome in texto
    assert 'de 2 autorizada' in texto
    assert 'Esta ação não pode ser desfeita.' in texto
    # O gancho aponta para um `id` que existe de verdade no formulário.
    ganchos = re.findall(r'data-resumo-entregue-de="([^"]+)"', html)
    assert ganchos
    for gancho in ganchos:
        assert f'id="{gancho}"' in html


@pytest.mark.django_db
def test_modal_de_estorno_repete_a_entregue_liquida_que_volta_ao_saldo(
    client, chefe_almoxarifado, req_atendida_view
):
    """ "Estornar requisição" — qual, e quanto volta?

    A descrição diz "toda a entregue líquida"; a lista diz quanto é. Era a única
    superfície do sistema que confirmava uma reversão de estoque sem nomear um
    número sequer.
    """
    _login(client, chefe_almoxarifado)
    response = client.get(
        reverse('requisicoes:detalhe', kwargs={'pk': req_atendida_view.pk})
    )
    texto = _texto_dos_dialogos(response.content.decode('utf-8'))['estornar-modal']

    item = req_atendida_view.itens.first()
    assert req_atendida_view.numero_publico in texto
    assert item.material.nome in texto
    assert 'Esta operação é irreversível.' in texto


@pytest.mark.django_db
def test_estorno_422_devolve_o_modal_ainda_nomeado(
    client, chefe_almoxarifado, req_atendida_view
):
    """O 422 troca o corpo inteiro — inclusive o cabeçalho que carrega a identidade.

    É no re-render com erro, com a pessoa já tendo confirmado uma vez, que saber
    qual documento está na frente importa mais.
    """
    _login(client, chefe_almoxarifado)
    response = client.post(
        reverse('requisicoes:estornar', kwargs={'pk': req_atendida_view.pk}),
        data={'justificativa': ''},
        HTTP_HX_REQUEST='true',
    )
    assert response.status_code == 422
    html = response.content.decode('utf-8')
    assert req_atendida_view.numero_publico in html
    assert 'data-modal-registro' in html
    assert 'Esta operação é irreversível.' in html
    assert req_atendida_view.itens.first().material.nome in html


class TestEntregueLiquidaVisivelParaQuemLe:
    """A entregue líquida é leitura, não privilégio.

    Ela vivia só dentro do ramo das operações de escrita (`pode_devolver` /
    `pode_estornar`), então o beneficiário — dono do pedido — via `ENTREGUE 6` e
    nunca sabia que 2 tinham voltado ao estoque. O PRODUCT.md a declara derivada
    das movimentações; derivar e esconder é o pior dos dois mundos.
    """

    def _atendida_com_devolucao(
        self, solicitante, setor_obras, material_disponivel, almox
    ):
        from apps.requisicoes.services import (
            autorizar_requisicao,
            criar_requisicao,
            enviar_para_autorizacao,
            registrar_atendimento,
            registrar_devolucao,
            separar_para_retirada,
        )
        from apps.requisicoes.types import LinhaAtendimento

        req = criar_requisicao(
            ator_id=solicitante.id,
            beneficiario_id=solicitante.id,
            itens=[
                {
                    'material_id': material_disponivel.id,
                    'quantidade_solicitada': Decimal('6'),
                }
            ],
        )
        enviar_para_autorizacao(ator_id=solicitante.id, requisicao_id=req.id)
        autorizar_requisicao(ator_id=almox.id, requisicao_id=req.id)
        separar_para_retirada(ator_id=almox.id, requisicao_id=req.id)
        item = req.itens.get()
        registrar_atendimento(
            ator_id=almox.id,
            requisicao_id=req.id,
            itens=[
                LinhaAtendimento(
                    item_id=item.id,
                    quantidade_entregue=Decimal('6'),
                    justificativa='',
                )
            ],
            retirante_nome='Marcos Vinícius de Andrade',
        )
        registrar_devolucao(
            ator_id=almox.id,
            requisicao_id=req.id,
            item_id=item.id,
            quantidade=Decimal('2'),
        )
        return req

    @pytest.mark.django_db
    def test_beneficiario_ve_a_liquida_e_o_que_voltou(
        self,
        client,
        superuser,
        solicitante,
        chefe_obras,
        setor_obras,
        material_disponivel,
    ):
        """O ator do GET tem de ser quem a regressão escondia.

        Com `superuser` o teste passava dos dois lados: ele acumula criador,
        beneficiário e almoxarife, logo tem `REGISTRAR_DEVOLUCAO` e `ESTORNAR`
        em `acoes_disponiveis` e cairia dentro do ramo antigo. O solicitante é
        beneficiário e não tem nenhuma das duas.

        `chefe_obras` continua na assinatura como pré-condição, não como ator: o
        envio exige setor com chefe ativo.
        """
        req = self._atendida_com_devolucao(
            solicitante, setor_obras, material_disponivel, superuser
        )
        _login(client, solicitante)
        html = client.get(
            reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
        ).content.decode('utf-8')
        assert 'Líquida' in html
        assert 'de volta ao estoque' in html

    @pytest.mark.django_db
    def test_sem_devolucao_a_liquida_nao_aparece(
        self, client, superuser, chefe_obras, setor_obras, material_disponivel
    ):
        """Sem nada devolvido, uma segunda linha com o mesmo número é ruído."""
        from apps.requisicoes.services import (
            autorizar_requisicao,
            criar_requisicao,
            enviar_para_autorizacao,
            registrar_atendimento,
            separar_para_retirada,
        )
        from apps.requisicoes.types import LinhaAtendimento

        req = criar_requisicao(
            ator_id=superuser.id,
            beneficiario_id=superuser.id,
            itens=[
                {
                    'material_id': material_disponivel.id,
                    'quantidade_solicitada': Decimal('6'),
                }
            ],
        )
        enviar_para_autorizacao(ator_id=superuser.id, requisicao_id=req.id)
        autorizar_requisicao(ator_id=superuser.id, requisicao_id=req.id)
        separar_para_retirada(ator_id=superuser.id, requisicao_id=req.id)
        item = req.itens.get()
        registrar_atendimento(
            ator_id=superuser.id,
            requisicao_id=req.id,
            itens=[
                LinhaAtendimento(
                    item_id=item.id,
                    quantidade_entregue=Decimal('6'),
                    justificativa='',
                )
            ],
            retirante_nome='Ana Paula Ribeiro',
        )
        _login(client, superuser)
        html = client.get(
            reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
        ).content.decode('utf-8')
        assert 'de volta ao estoque' not in html


class TestSaldoVisivelNaDecisao:
    """Autorizar RESERVA estoque, e era a única escrita do produto confirmada
    com zero números na tela: o modal dizia "reserva o saldo necessário para
    todos os itens" sem dizer quanto, de quê, nem se existe."""

    def _com_item(self, requisicao, material):
        requisicao.itens.create(material=material, quantidade_solicitada=Decimal('3'))
        return requisicao

    @pytest.mark.django_db
    def test_chefe_ve_o_disponivel_por_item(
        self, client, chefe_obras, req_enviada_solicitante, material_disponivel
    ):
        self._com_item(req_enviada_solicitante, material_disponivel)
        _login(client, chefe_obras)
        response = client.get(
            reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
        )
        html = response.content.decode('utf-8')
        assert 'Disponível' in html

    @pytest.mark.django_db
    def test_solicitante_em_rascunho_nao_ve_a_coluna(
        self, client, solicitante, req_rascunho_solicitante
    ):
        """Uma consulta a mais só no estado em que ela decide algo."""
        _login(client, solicitante)
        response = client.get(
            reverse('requisicoes:detalhe', kwargs={'pk': req_rascunho_solicitante.pk})
        )
        itens = response.context['itens']
        assert all(getattr(i, 'saldo_disponivel_exibido', None) is None for i in itens)

    @pytest.mark.django_db
    def test_item_que_barrou_a_reserva_fica_marcado(
        self, client, chefe_obras, req_enviada_solicitante, material_disponivel
    ):
        """A faixa no topo nomeia o material; a marca diz onde ele está."""
        self._com_item(req_enviada_solicitante, material_disponivel)
        material_id = req_enviada_solicitante.itens.first().material_id
        _login(client, chefe_obras)
        url = reverse('requisicoes:detalhe', kwargs={'pk': req_enviada_solicitante.pk})
        html = client.get(f'{url}?item_erro={material_id}').content.decode('utf-8')
        assert 'aria-invalid="true"' in html
        assert 'border-danger-border-input' in html


class TestTimelineDevolveOQueOFormularioExige:
    """ "Auditabilidade acima de conveniência" é o princípio 2 do PRODUCT.md.

    A tela de atendimento força `RETIRANTE *` a quem está em pé no galpão; a
    devolução força a quantidade. Os dois eram gravados em
    `TimelineRequisicao.metadata` e nunca exibidos — `_timeline.html` só lia
    `metadata` no caso da EST-07. A pergunta que qualquer conferência faz — quem
    retirou e por que faltou — era a que o produto coletava e não devolvia.
    """

    @pytest.mark.django_db
    def test_retirante_e_quantidade_devolvida_aparecem(
        self, client, superuser, chefe_obras, setor_obras, material_disponivel
    ):
        from apps.requisicoes.services import (
            autorizar_requisicao,
            criar_requisicao,
            enviar_para_autorizacao,
            registrar_atendimento,
            registrar_devolucao,
            separar_para_retirada,
        )
        from apps.requisicoes.types import LinhaAtendimento

        req = criar_requisicao(
            ator_id=superuser.id,
            beneficiario_id=superuser.id,
            itens=[
                {
                    'material_id': material_disponivel.id,
                    'quantidade_solicitada': Decimal('6'),
                }
            ],
        )
        enviar_para_autorizacao(ator_id=superuser.id, requisicao_id=req.id)
        autorizar_requisicao(ator_id=superuser.id, requisicao_id=req.id)
        separar_para_retirada(ator_id=superuser.id, requisicao_id=req.id)
        item = req.itens.get()
        registrar_atendimento(
            ator_id=superuser.id,
            requisicao_id=req.id,
            itens=[
                LinhaAtendimento(
                    item_id=item.id,
                    quantidade_entregue=Decimal('6'),
                    justificativa='',
                )
            ],
            retirante_nome='Marcos Vinícius de Andrade',
        )
        registrar_devolucao(
            ator_id=superuser.id,
            requisicao_id=req.id,
            item_id=item.id,
            quantidade=Decimal('2'),
            observacao='Duas peças devolvidas sem uso.',
        )

        _login(client, superuser)
        html = client.get(
            reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
        ).content.decode('utf-8')

        assert 'Retirada por' in html
        assert 'Marcos Vinícius de Andrade' in html
        assert 'Duas peças devolvidas sem uso.' in html
        assert material_disponivel.nome in html


class TestBuscaNasListasDeTrabalho:
    """As três listagens onde se AGE sobre um registro não tinham como achar um.

    A divisão era o inverso da necessidade: recorte completo nas duas telas de
    histórico, que têm cartões inertes, e nada nas três em que se decide.
    """

    @pytest.mark.django_db
    def test_minhas_recorta_por_numero_publico(
        self, client, solicitante, setor_obras, material_disponivel
    ):
        alvo = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B001',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        outra = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B999',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        for req in (alvo, outra):
            req.itens.create(material=material_disponivel, quantidade_solicitada=1)

        _login(client, solicitante)
        html = client.get(
            reverse('requisicoes:minhas'), {'busca': 'B001'}
        ).content.decode('utf-8')
        assert 'REQ-2026-B001' in html
        assert 'REQ-2026-B999' not in html

    @pytest.mark.django_db
    def test_minhas_recorta_pelo_nome_do_material(
        self,
        client,
        solicitante,
        setor_obras,
        material_disponivel,
        material_disponivel_2,
    ):
        com_alvo = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B101',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        com_alvo.itens.create(material=material_disponivel, quantidade_solicitada=1)
        sem_alvo = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B102',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        sem_alvo.itens.create(material=material_disponivel_2, quantidade_solicitada=1)

        _login(client, solicitante)
        html = client.get(
            reverse('requisicoes:minhas'), {'busca': material_disponivel.nome}
        ).content.decode('utf-8')
        assert 'REQ-2026-B101' in html
        assert 'REQ-2026-B102' not in html

    @pytest.mark.django_db
    def test_busca_sem_resultado_nao_diz_que_a_lista_esta_vazia(
        self, client, solicitante, setor_obras
    ):
        """Quem busca "cimento" e não acha lia "Nenhuma requisição ainda" e um
        convite a criar a primeira — uma frase errada e a ação errada."""
        Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B201',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        _login(client, solicitante)
        html = client.get(
            reverse('requisicoes:minhas'), {'busca': 'inexistente'}
        ).content.decode('utf-8')
        assert 'Nenhuma requisição ainda' not in html
        assert 'Limpar busca' in html

    @pytest.mark.django_db
    def test_item_repetido_nao_duplica_a_requisicao(
        self,
        client,
        solicitante,
        setor_obras,
        material_disponivel,
        material_disponivel_2,
    ):
        """O join com `itens` multiplica a requisição por item que casa."""
        req = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B301',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        req.itens.create(material=material_disponivel, quantidade_solicitada=1)
        req.itens.create(material=material_disponivel_2, quantidade_solicitada=1)

        _login(client, solicitante)
        resposta = client.get(reverse('requisicoes:minhas'), {'busca': 'a'})
        numeros = [r.numero_publico for r in resposta.context['requisicoes']]
        assert numeros.count('REQ-2026-B301') == 1

    @pytest.mark.django_db
    def test_a_paginacao_das_tres_listas_preserva_a_busca(
        self,
        client,
        solicitante,
        chefe_obras,
        aux_almoxarifado,
        setor_obras,
        material_disponivel,
        monkeypatch,
    ):
        """Sem a querystring nos links, a página 2 de uma busca vira a lista inteira.

        As duas filas usam `paginar`, que não devolve querystring alguma — não
        têm ordenação a preservar. A busca elas têm, e desde a Etapa 8. `minhas`
        usa `paginar_com_filtros` e o valor existia, sem chegar ao template.
        """
        from apps.requisicoes import views as requisicoes_views

        # Dois pares: a fila de autorização só vê `aguardando_autorizacao`, e a
        # de atendimento só vê `autorizada`/`pronta_para_retirada`. Sem os dois
        # estados, uma das filas cai na primeira página e o teste não prova nada.
        cenarios = (
            ('REQ-2026-B501', EstadoRequisicao.AGUARDANDO_AUTORIZACAO),
            ('REQ-2026-B502', EstadoRequisicao.AGUARDANDO_AUTORIZACAO),
            ('REQ-2026-B503', EstadoRequisicao.AUTORIZADA),
            ('REQ-2026-B504', EstadoRequisicao.AUTORIZADA),
        )
        for numero, estado in cenarios:
            req = Requisicao.objects.create(
                estado=estado,
                numero_publico=numero,
                criador=solicitante,
                beneficiario=solicitante,
                setor_beneficiario=setor_obras,
            )
            req.itens.create(material=material_disponivel, quantidade_solicitada=1)

        monkeypatch.setattr(requisicoes_views, 'PAGINA_FILA_TAMANHO', 1)
        monkeypatch.setattr(requisicoes_views, 'PAGINA_MINHAS_REQUISICOES_TAMANHO', 1)

        busca = material_disponivel.nome
        for usuario, rota in (
            (solicitante, 'requisicoes:minhas'),
            (chefe_obras, 'requisicoes:autorizacoes'),
            (aux_almoxarifado, 'requisicoes:atendimentos'),
        ):
            _login(client, usuario)
            resposta = client.get(reverse(rota), {'busca': busca})
            html = resposta.content.decode('utf-8')
            assert 'busca=' in resposta.context['querystring_filtros'], rota
            assert 'page=2"' in html, rota
            assert 'href="?page=2"' not in html, rota

    @pytest.mark.django_db
    def test_as_tres_listas_de_trabalho_tem_o_mesmo_campo(
        self, client, solicitante, chefe_obras, aux_almoxarifado
    ):
        """Uma gramática de busca, não três."""
        for usuario, rota in (
            (solicitante, 'requisicoes:minhas'),
            (chefe_obras, 'requisicoes:autorizacoes'),
            (aux_almoxarifado, 'requisicoes:atendimentos'),
        ):
            _login(client, usuario)
            html = client.get(reverse(rota)).content.decode('utf-8')
            assert 'Requisição ou material' in html, rota
            assert 'role="search"' in html, rota

    @pytest.mark.django_db
    def test_busca_nao_encolhe_a_contagem_de_itens(
        self,
        client,
        solicitante,
        setor_obras,
        material_disponivel,
        material_disponivel_2,
    ):
        """O "e mais N" do cartão conta a requisição inteira, não o recorte.

        Em "Minhas requisições" a busca vem antes do `Count('itens')`: com um
        join no filtro, a anotação passaria a contar só os itens que casaram e
        o cartão diria "e mais 0" numa requisição de dois materiais.
        """
        req = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B401',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        req.itens.create(material=material_disponivel, quantidade_solicitada=1)
        req.itens.create(material=material_disponivel_2, quantidade_solicitada=1)

        _login(client, solicitante)
        resposta = client.get(
            reverse('requisicoes:minhas'), {'busca': material_disponivel.nome}
        )
        encontradas = list(resposta.context['requisicoes'])
        assert len(encontradas) == 1
        assert encontradas[0].quantidade_itens == 2

    @pytest.mark.django_db
    def test_busca_nao_multiplica_a_contagem_na_fila(
        self,
        client,
        chefe_obras,
        solicitante,
        setor_obras,
        material_disponivel,
        material_disponivel_2,
    ):
        """Nas filas a anotação vem antes da busca, e o erro é o oposto.

        `Count('itens')` já existe no seletor; um join no filtro abriria uma
        segunda cópia da mesma tabela e o produto cartesiano inflaria o total.
        A busca casa os DOIS itens de propósito: com um só, o produto de 2×1
        devolve o número certo por acidente e o defeito passa despercebido.
        """
        req = Requisicao.objects.create(
            estado=EstadoRequisicao.AGUARDANDO_AUTORIZACAO,
            numero_publico='REQ-2026-B402',
            criador=solicitante,
            beneficiario=solicitante,
            setor_beneficiario=setor_obras,
        )
        req.itens.create(material=material_disponivel, quantidade_solicitada=1)
        req.itens.create(material=material_disponivel_2, quantidade_solicitada=1)

        prefixo_comum = 'MAT00'
        assert prefixo_comum in material_disponivel.codigo
        assert prefixo_comum in material_disponivel_2.codigo

        _login(client, chefe_obras)
        resposta = client.get(
            reverse('requisicoes:autorizacoes'), {'busca': prefixo_comum}
        )
        encontradas = list(resposta.context['requisicoes'])
        assert len(encontradas) == 1
        assert encontradas[0].quantidade_itens == 2
