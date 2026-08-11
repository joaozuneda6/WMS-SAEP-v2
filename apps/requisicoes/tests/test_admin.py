"""Testes do admin de requisições (issue #105).

O admin é válvula de emergência, não caminho de escrita: `estado`, as três
quantidades de `ItemRequisicao` e a timeline são governados pela máquina de
estados e pelos services. Estes testes fixam que o admin não os escreve, e
que a leitura continua aberta a quem o Django autoriza.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import User
from apps.requisicoes.admin import (
    ItemRequisicaoAdmin,
    ItemRequisicaoInline,
    RequisicaoAdmin,
    SequenciaRequisicaoAdmin,
    TimelineRequisicaoAdmin,
)
from apps.requisicoes.models import (
    EstadoRequisicao,
    EventoTimeline,
    ItemRequisicao,
    Requisicao,
    SequenciaRequisicao,
    TimelineRequisicao,
)


@pytest.fixture
def request_de(rf: RequestFactory):
    """Devolve um request de admin já autenticado como o usuário dado."""

    def _request(usuario):
        req = rf.get('/admin/requisicoes/requisicao/')
        req.user = usuario
        return req

    return _request


@pytest.fixture
def requisicao_admin():
    return RequisicaoAdmin(Requisicao, AdminSite())


@pytest.fixture
def staff_de_requisicao(db, setor_obras):
    """Staff **não** superusuário, com todas as permissões Django de requisições.

    O Django, sozinho, autorizaria este usuário nos três models. Qualquer
    negação só pode vir dos guards deste issue — é o que separa o gate do
    plano do gate de permissões padrão.
    """
    usuario = User.objects.create_user(
        matricula='903',
        nome='Staff Requisicoes',
        password='senha',
        setor=setor_obras,
        is_staff=True,
    )
    usuario.user_permissions.set(
        Permission.objects.filter(
            content_type__in=ContentType.objects.get_for_models(
                Requisicao,
                ItemRequisicao,
                TimelineRequisicao,
            ).values(),
        )
    )
    return usuario


@pytest.fixture
def item_admin():
    return ItemRequisicaoAdmin(ItemRequisicao, AdminSite())


@pytest.fixture
def item_inline():
    return ItemRequisicaoInline(Requisicao, AdminSite())


@pytest.fixture
def item_de_requisicao(db, req_historico_obras, material_disponivel):
    return ItemRequisicao.objects.create(
        requisicao=req_historico_obras,
        material=material_disponivel,
        quantidade_solicitada=7,
    )


def _payload_requisicao(requisicao, **overrides):
    """Corpo mínimo de POST para a change view de `Requisicao`.

    Inclui o `management_form` do inline `itens` (prefixo vindo do
    `related_name` em `ItemRequisicao.requisicao`), sem o qual o Django
    rejeita o POST antes de chegar ao formulário principal.
    """
    dados = {
        'criador': str(requisicao.criador_id),
        'beneficiario': str(requisicao.beneficiario_id),
        'setor_beneficiario': str(requisicao.setor_beneficiario_id),
        'observacao_geral': requisicao.observacao_geral,
        'itens-TOTAL_FORMS': '0',
        'itens-INITIAL_FORMS': '0',
        'itens-MIN_NUM_FORMS': '0',
        'itens-MAX_NUM_FORMS': '1000',
    }
    dados.update(overrides)
    return dados


def test_post_no_admin_nao_troca_estado_da_requisicao(
    client, superuser, req_historico_obras
):
    """O cenário do issue: o superusuário 'conserta' a requisição presa à mão.

    O POST é aceito (302) porque os demais campos seguem editáveis — a válvula
    de emergência continua funcionando. O que não pode acontecer é `estado`
    entrar no banco vindo do corpo da requisição, pulando timeline e ledger.
    """
    client.force_login(superuser)
    assert req_historico_obras.estado == EstadoRequisicao.AGUARDANDO_AUTORIZACAO

    resposta = client.post(
        reverse('admin:requisicoes_requisicao_change', args=[req_historico_obras.pk]),
        _payload_requisicao(req_historico_obras, estado=EstadoRequisicao.ATENDIDA),
    )

    assert resposta.status_code == 302
    req_historico_obras.refresh_from_db()
    assert req_historico_obras.estado == EstadoRequisicao.AGUARDANDO_AUTORIZACAO


def test_estado_declarado_readonly_em_requisicao_admin(requisicao_admin):
    assert 'estado' in requisicao_admin.readonly_fields


def test_estado_fora_do_formulario_de_requisicao(
    requisicao_admin, request_de, superuser, req_historico_obras
):
    """`readonly_fields` não é cosmético: `get_form` joga o campo em `exclude`.

    Sem este caso, um `get_readonly_fields` sobrescrito no futuro poderia
    devolver algo diferente do atributo de classe e o teste acima continuaria
    verde enquanto o campo voltava a ser editável.
    """
    formulario = requisicao_admin.get_form(
        request_de(superuser), obj=req_historico_obras
    )

    assert 'estado' not in formulario.base_fields


def test_estado_fora_do_formulario_tambem_para_staff_autorizado(
    requisicao_admin, request_de, staff_de_requisicao, req_historico_obras
):
    """O gate não é "superuser-only": vale para quem o Django já autorizaria."""
    formulario = requisicao_admin.get_form(
        request_de(staff_de_requisicao), obj=req_historico_obras
    )

    assert 'estado' not in formulario.base_fields


def test_post_no_admin_altera_campo_nao_derivado_da_requisicao(
    client, superuser, req_historico_obras
):
    """O caminho feliz da válvula de emergência.

    Sem este caso, um `has_change_permission = False` colado por engano em
    `RequisicaoAdmin` passaria em todos os outros testes e ninguém notaria que
    o admin virou vitrine.
    """
    client.force_login(superuser)

    resposta = client.post(
        reverse('admin:requisicoes_requisicao_change', args=[req_historico_obras.pk]),
        _payload_requisicao(req_historico_obras, observacao_geral='ajuste manual'),
    )

    assert resposta.status_code == 302
    req_historico_obras.refresh_from_db()
    assert req_historico_obras.observacao_geral == 'ajuste manual'


def test_change_view_de_requisicao_responde(client, superuser, req_historico_obras):
    """Smoke da change view — é onde o inline de itens é montado.

    `BaseModelAdmin.get_inline_instances` chama
    `inline.has_add_permission(request, obj)` com dois argumentos. Uma
    assinatura errada no inline derrubaria esta página com `TypeError`, que é
    a classe de regressão do #104.
    """
    client.force_login(superuser)

    resposta = client.get(
        reverse('admin:requisicoes_requisicao_change', args=[req_historico_obras.pk])
    )

    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# ItemRequisicao — somente-leitura no admin avulso e no inline
# ---------------------------------------------------------------------------


def test_post_no_admin_nao_troca_quantidade_do_item(
    client, staff_de_requisicao, item_de_requisicao
):
    """As três quantidades são governadas por autorizar/atender, não pelo admin.

    O sujeito é o staff com a permissão Django concedida: se o 403 viesse das
    permissões padrão em vez do guard deste issue, este teste não provaria nada.
    """
    client.force_login(staff_de_requisicao)

    resposta = client.post(
        reverse(
            'admin:requisicoes_itemrequisicao_change', args=[item_de_requisicao.pk]
        ),
        {
            'requisicao': str(item_de_requisicao.requisicao_id),
            'material': str(item_de_requisicao.material_id),
            'quantidade_solicitada': '999',
            'justificativa_entrega': '',
        },
    )

    assert resposta.status_code == 403
    item_de_requisicao.refresh_from_db()
    assert item_de_requisicao.quantidade_solicitada == 7


def test_quantidades_declaradas_readonly_no_admin_e_no_inline(item_admin, item_inline):
    for campo in (
        'quantidade_solicitada',
        'quantidade_autorizada',
        'quantidade_entregue',
    ):
        assert campo in item_admin.readonly_fields
        assert campo in item_inline.readonly_fields


def test_quantidades_fora_do_formulario_do_item(
    item_admin, request_de, superuser, item_de_requisicao
):
    formulario = item_admin.get_form(request_de(superuser), obj=item_de_requisicao)

    assert 'quantidade_solicitada' not in formulario.base_fields
    assert 'quantidade_autorizada' not in formulario.base_fields
    assert 'quantidade_entregue' not in formulario.base_fields


def test_quantidades_fora_do_formset_do_inline(
    item_inline, request_de, superuser, req_historico_obras, item_de_requisicao
):
    """O inline tem API própria: `get_formset`, não `get_form`.

    `get_form` é definido em `ModelAdmin`, não em `BaseModelAdmin` — chamá-lo
    num inline levantaria `AttributeError`. Este é o formulário efetivamente
    renderizado dentro da change view de `Requisicao`, que é a superfície pela
    qual o superusuário sob estresse realmente passa.
    """
    formset = item_inline.get_formset(request_de(superuser), obj=req_historico_obras)

    assert 'quantidade_solicitada' not in formset.form.base_fields
    assert 'quantidade_autorizada' not in formset.form.base_fields
    assert 'quantidade_entregue' not in formset.form.base_fields


def test_item_admin_nega_add_change_e_delete(item_admin, request_de, superuser):
    requisicao = request_de(superuser)

    assert item_admin.has_add_permission(requisicao) is False
    assert item_admin.has_change_permission(requisicao) is False
    assert item_admin.has_delete_permission(requisicao) is False


def test_item_inline_nega_add_change_e_delete(
    item_inline, request_de, superuser, req_historico_obras
):
    """`InlineModelAdmin.has_add_permission` recebe `obj` posicional.

    A assinatura difere da de `ModelAdmin`, e errá-la derruba toda change view
    de `Requisicao` com `TypeError`.
    """
    requisicao = request_de(superuser)

    assert item_inline.has_add_permission(requisicao, req_historico_obras) is False
    assert item_inline.has_change_permission(requisicao, req_historico_obras) is False
    assert item_inline.has_delete_permission(requisicao, req_historico_obras) is False


def test_add_de_item_nega_no_get(client, superuser):
    client.force_login(superuser)

    resposta = client.get(reverse('admin:requisicoes_itemrequisicao_add'))

    assert resposta.status_code == 403


def test_add_de_item_nega_no_post_sem_criar_linha(
    client, superuser, req_historico_obras, material_disponivel
):
    """Só o POST percorre o caminho de `save()`.

    `quantidade_solicitada` é NOT NULL sem default e com `CheckConstraint > 0`:
    se o guard fosse apenas `readonly_fields`, o campo sairia do formulário e o
    save cairia em `IntegrityError` — 500 em vez de 403. O GET nunca revelaria
    isso porque não chega a salvar.
    """
    client.force_login(superuser)

    resposta = client.post(
        reverse('admin:requisicoes_itemrequisicao_add'),
        {
            'requisicao': str(req_historico_obras.pk),
            'material': str(material_disponivel.pk),
            'justificativa_entrega': '',
        },
    )

    assert resposta.status_code == 403
    assert ItemRequisicao.objects.count() == 0


def test_changelist_de_item_permanece_legivel(client, staff_de_requisicao):
    """A negação é de escrita, não de consulta."""
    client.force_login(staff_de_requisicao)

    resposta = client.get(reverse('admin:requisicoes_itemrequisicao_changelist'))

    assert resposta.status_code == 200


def test_delete_selected_ausente_das_actions_de_item(item_admin, request_de, superuser):
    """`_filter_actions_by_permissions` remove a action via `has_delete_permission`."""
    assert 'delete_selected' not in item_admin.get_actions(request_de(superuser))


# ---------------------------------------------------------------------------
# TimelineRequisicao — log append-only, somente-leitura no admin
# ---------------------------------------------------------------------------


@pytest.fixture
def evento_de_timeline(db, req_historico_obras, solicitante):
    return TimelineRequisicao.objects.create(
        requisicao=req_historico_obras,
        evento=EventoTimeline.CRIACAO,
        ator=solicitante,
        estado_resultante=EstadoRequisicao.RASCUNHO,
    )


def test_admin_nao_apaga_evento_de_timeline(
    client, staff_de_requisicao, evento_de_timeline
):
    """A trilha de auditoria só vale se for append-only.

    Correção de evento errado entra como evento novo, pelo service — nunca
    como delete pelo admin. O sujeito é o staff com `delete_timelinerequisicao`
    concedido: a negação tem que vir do guard, não das permissões Django.
    """
    client.force_login(staff_de_requisicao)

    resposta = client.post(
        reverse(
            'admin:requisicoes_timelinerequisicao_delete',
            args=[evento_de_timeline.pk],
        ),
        {'post': 'yes'},
    )

    assert resposta.status_code == 403
    assert TimelineRequisicao.objects.filter(pk=evento_de_timeline.pk).exists()


def test_timeline_admin_nega_add_change_e_delete(request_de, superuser):
    timeline_admin = TimelineRequisicaoAdmin(TimelineRequisicao, AdminSite())
    requisicao = request_de(superuser)

    assert timeline_admin.has_add_permission(requisicao) is False
    assert timeline_admin.has_change_permission(requisicao) is False
    assert timeline_admin.has_delete_permission(requisicao) is False


def test_delete_selected_ausente_das_actions_de_timeline(request_de, superuser):
    timeline_admin = TimelineRequisicaoAdmin(TimelineRequisicao, AdminSite())

    assert 'delete_selected' not in timeline_admin.get_actions(request_de(superuser))


def test_add_de_evento_de_timeline_nega(client, staff_de_requisicao):
    """Evento só nasce por service. Nem com `add_timelinerequisicao` concedido."""
    client.force_login(staff_de_requisicao)

    resposta = client.get(reverse('admin:requisicoes_timelinerequisicao_add'))

    assert resposta.status_code == 403


def test_changelist_de_timeline_permanece_legivel(
    client, staff_de_requisicao, evento_de_timeline
):
    """REQ-08 exige que a trilha seja visível a autorizados.

    Sem este caso, alguém "reforçando" o admin com `has_view_permission = False`
    passaria em todos os outros testes de timeline.
    """
    client.force_login(staff_de_requisicao)

    resposta = client.get(reverse('admin:requisicoes_timelinerequisicao_changelist'))

    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# SequenciaRequisicaoAdmin — numeração não pode regredir (issue #113)
# ---------------------------------------------------------------------------


@pytest.fixture
def sequencia_admin():
    return SequenciaRequisicaoAdmin(SequenciaRequisicao, AdminSite())


@pytest.fixture
def sequencia_requisicao(db):
    return SequenciaRequisicao.objects.create(ano=2026, ultimo_numero=10)


def test_sequencia_requisicao_admin_nega_add(sequencia_admin, request_de, superuser):
    assert sequencia_admin.has_add_permission(request_de(superuser)) is False


def test_ultimo_numero_de_sequencia_requisicao_declarado_readonly(sequencia_admin):
    assert 'ultimo_numero' in sequencia_admin.readonly_fields
    assert 'ano' in sequencia_admin.readonly_fields


def test_ultimo_numero_de_sequencia_requisicao_fora_do_formulario(
    sequencia_admin, request_de, superuser, sequencia_requisicao
):
    formulario = sequencia_admin.get_form(
        request_de(superuser), obj=sequencia_requisicao
    )

    assert 'ultimo_numero' not in formulario.base_fields
    assert 'ano' not in formulario.base_fields


def test_post_no_admin_nao_regride_ultimo_numero_de_requisicao(
    client, superuser, sequencia_requisicao
):
    client.force_login(superuser)

    resposta = client.post(
        reverse(
            'admin:requisicoes_sequenciarequisicao_change',
            args=[sequencia_requisicao.pk],
        ),
        {'ano': '2026', 'ultimo_numero': '0'},
    )

    assert resposta.status_code == 302
    sequencia_requisicao.refresh_from_db()
    assert sequencia_requisicao.ultimo_numero == 10


def test_post_no_admin_nao_muda_ano_de_sequencia_requisicao(
    client, superuser, sequencia_requisicao
):
    """Trocar `ano` "move" o contador — mesmo efeito prático de apagar."""
    client.force_login(superuser)

    resposta = client.post(
        reverse(
            'admin:requisicoes_sequenciarequisicao_change',
            args=[sequencia_requisicao.pk],
        ),
        {'ano': '2027', 'ultimo_numero': '10'},
    )

    assert resposta.status_code == 302
    sequencia_requisicao.refresh_from_db()
    assert sequencia_requisicao.ano == 2026


def test_sequencia_requisicao_admin_nega_delete(sequencia_admin, request_de, superuser):
    assert sequencia_admin.has_delete_permission(request_de(superuser)) is False


def test_delete_de_sequencia_requisicao_nega(client, superuser, sequencia_requisicao):
    """Apagar reseta a numeração — próximo `get_or_create` recria do zero e
    colide com `numero_publico` já emitido para o mesmo ano."""
    client.force_login(superuser)

    resposta = client.post(
        reverse(
            'admin:requisicoes_sequenciarequisicao_delete',
            args=[sequencia_requisicao.pk],
        ),
        {'post': 'yes'},
    )

    assert resposta.status_code == 403
    assert SequenciaRequisicao.objects.filter(pk=sequencia_requisicao.pk).exists()


# ---------------------------------------------------------------------------
# RequisicaoAdmin — sem add/delete pelo admin (issue #113)
# ---------------------------------------------------------------------------


def test_requisicao_admin_nega_add_e_delete(requisicao_admin, request_de, superuser):
    requisicao = request_de(superuser)

    assert requisicao_admin.has_add_permission(requisicao) is False
    assert requisicao_admin.has_delete_permission(requisicao) is False


def test_add_de_requisicao_nega(client, staff_de_requisicao):
    """Criação passa a ser exclusiva do service `criar_requisicao`.

    Sem o guard, os três campos de pessoa virando readonly deixaria o POST de
    add sem valor pra eles — `IntegrityError` (NOT NULL) em vez de 403.
    """
    client.force_login(staff_de_requisicao)

    resposta = client.get(reverse('admin:requisicoes_requisicao_add'))

    assert resposta.status_code == 403


def test_delete_de_requisicao_nega(client, staff_de_requisicao, req_historico_obras):
    client.force_login(staff_de_requisicao)

    resposta = client.post(
        reverse('admin:requisicoes_requisicao_delete', args=[req_historico_obras.pk]),
        {'post': 'yes'},
    )

    assert resposta.status_code == 403
    assert Requisicao.objects.filter(pk=req_historico_obras.pk).exists()


def test_pessoas_da_requisicao_declaradas_readonly(requisicao_admin):
    for campo in ('criador', 'beneficiario', 'setor_beneficiario'):
        assert campo in requisicao_admin.readonly_fields


def test_pessoas_da_requisicao_fora_do_formulario(
    requisicao_admin, request_de, superuser, req_historico_obras
):
    formulario = requisicao_admin.get_form(
        request_de(superuser), obj=req_historico_obras
    )

    assert 'criador' not in formulario.base_fields
    assert 'beneficiario' not in formulario.base_fields
    assert 'setor_beneficiario' not in formulario.base_fields


def test_post_no_admin_nao_troca_beneficiario_da_requisicao(
    client, superuser, req_historico_obras, outro_usuario_obras
):
    client.force_login(superuser)
    beneficiario_original_id = req_historico_obras.beneficiario_id

    client.post(
        reverse('admin:requisicoes_requisicao_change', args=[req_historico_obras.pk]),
        _payload_requisicao(
            req_historico_obras, beneficiario=str(outro_usuario_obras.pk)
        ),
    )

    req_historico_obras.refresh_from_db()
    assert req_historico_obras.beneficiario_id == beneficiario_original_id
