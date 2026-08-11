"""Testes do admin de estoque.

- Guard de estoque único em `EstoqueAdmin` (issue #102, ADR-0017).
- Derivação de `PapelEfetivo` antes da policy em `MaterialAdmin` (issue #104).
- Nível das mensagens de erro de domínio (issue #107).
"""

import pytest
from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import User
from apps.estoque.admin import (
    EstoqueAdmin,
    MaterialAdmin,
    MovimentacaoEstoqueAdmin,
    SaldoEstoqueAdmin,
)
from apps.estoque.models import Estoque, Material, MovimentacaoEstoque, SaldoEstoque


@pytest.fixture
def estoque_admin():
    return EstoqueAdmin(Estoque, AdminSite())


@pytest.fixture
def request_de(rf: RequestFactory):
    """Devolve um request de admin já autenticado como o usuário dado."""

    def _request(usuario):
        req = rf.get('/admin/estoque/estoque/add/')
        req.user = usuario
        return req

    return _request


def test_nao_permite_adicionar_segundo_estoque(
    estoque_admin, request_de, superuser, estoque_principal
):
    assert estoque_admin.has_add_permission(request_de(superuser)) is False


def test_permite_adicionar_o_primeiro_estoque(estoque_admin, request_de, superuser):
    assert Estoque.objects.exists() is False

    assert estoque_admin.has_add_permission(request_de(superuser)) is True


def test_estoque_inativo_tambem_bloqueia_adicao(estoque_admin, request_de, superuser):
    """O guard não filtra por `ativo`.

    Os services localizam `SaldoEstoque` por `material_id` sem olhar
    `estoque.ativo`: um segundo estoque inativo com saldo quebraria a
    autorização do mesmo jeito.
    """
    Estoque.objects.create(codigo='EST99', nome='Estoque Desativado', ativo=False)

    assert estoque_admin.has_add_permission(request_de(superuser)) is False


def test_guard_nao_concede_permissao_a_quem_nao_tem(
    estoque_admin, request_de, chefe_almoxarifado
):
    """O guard compõe com a checagem padrão do Django, não a substitui."""
    assert Estoque.objects.exists() is False

    assert estoque_admin.has_add_permission(request_de(chefe_almoxarifado)) is False


# ---------------------------------------------------------------------------
# MaterialAdmin — derivação de papel antes da policy (issue #104)
# ---------------------------------------------------------------------------


def test_admin_index_responde_para_superusuario(client, superuser):
    """Regressão #104: o admin inteiro caía em 500, não só as telas de Material.

    `AdminSite.each_context` monta o menu lateral via `get_app_list`, que
    consulta as permissões de todo `ModelAdmin` registrado. Um erro em
    `MaterialAdmin` derruba `admin:index`, destino do redirect pós-login.
    """
    client.force_login(superuser)

    assert client.get(reverse('admin:index')).status_code == 200


@pytest.fixture
def material_admin():
    return MaterialAdmin(Material, AdminSite())


def test_material_changelist_responde_para_superusuario(client, superuser):
    client.force_login(superuser)

    resposta = client.get(reverse('admin:estoque_material_changelist'))

    assert resposta.status_code == 200


def test_material_add_responde_para_superusuario(client, superuser):
    client.force_login(superuser)

    resposta = client.get(reverse('admin:estoque_material_add'))

    assert resposta.status_code == 200


def test_pode_gerir_autoriza_superusuario(material_admin, request_de, superuser):
    assert material_admin._pode_gerir(request_de(superuser)) is True


def test_pode_gerir_nega_quem_nao_e_superusuario(
    material_admin, request_de, chefe_almoxarifado
):
    """Sem este caso, um `_pode_gerir` que sempre devolvesse `True` passaria
    nos smokes acima — trocando o 500 por uma brecha de permissão."""
    assert material_admin._pode_gerir(request_de(chefe_almoxarifado)) is False


@pytest.fixture
def staff_de_material(db, setor_obras):
    """Staff **não** superusuário, com as permissões Django de `Material`.

    O Django, sozinho, autorizaria este usuário. Qualquer 403 nas telas de
    `Material` só pode vir de `pode_gerir_catalogo` — é o que separa o gate da
    policy do gate de permissões padrão.
    """
    usuario = User.objects.create_user(
        matricula='902',
        nome='Staff Catalogo',
        password='senha',
        setor=setor_obras,
        is_staff=True,
    )
    usuario.user_permissions.set(
        Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(Material),
            codename__in=('add_material', 'change_material', 'view_material'),
        )
    )
    return usuario


def test_add_de_material_nega_staff_sem_autorizacao(client, staff_de_material):
    """`has_add_permission` consome `_pode_gerir`, e não só a permissão Django."""
    client.force_login(staff_de_material)

    resposta = client.get(reverse('admin:estoque_material_add'))

    assert resposta.status_code == 403


def test_change_de_material_nega_staff_sem_autorizacao(
    client, staff_de_material, material_disponivel
):
    """`has_change_permission` consome `_pode_gerir`.

    O POST é deliberado: `ModelAdmin._changeform_view` só consulta
    `has_change_permission` no POST; no GET consultaria
    `has_view_or_change_permission`, que `MaterialAdmin` não sobrescreve.
    """
    client.force_login(staff_de_material)

    resposta = client.post(
        reverse('admin:estoque_material_change', args=[material_disponivel.pk]), {}
    )

    assert resposta.status_code == 403


def test_changelist_de_material_permanece_legivel_para_staff(
    client, staff_de_material, material_disponivel
):
    """A policy gateia escrita, não leitura.

    `has_view_permission` não é sobrescrito, então a consulta ao catálogo segue
    governada pelas permissões Django. Fixar o 200 aqui impede que uma mudança
    futura amplie o gate para leitura sem que ninguém perceba.
    """
    client.force_login(staff_de_material)

    resposta = client.get(reverse('admin:estoque_material_changelist'))

    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# Nível das mensagens de erro de domínio (issue #107)
# ---------------------------------------------------------------------------


def test_changeform_traduz_conflito_em_warning(client, superuser, material_disponivel):
    """`ConflitoDominio` é `warning` pelo mapeamento de `docs/CONVENTIONS.md`.

    A ação não foi aplicada, mas o estado atual — material com saldo — é
    compreensível e não exige correção de dado pelo usuário.
    """
    client.force_login(superuser)

    resposta = client.post(
        reverse('admin:estoque_material_change', args=[material_disponivel.pk]),
        {
            'codigo': material_disponivel.codigo,
            'nome': material_disponivel.nome,
            'unidade': material_disponivel.unidade,
            'observacao_interna': '',
        },
        follow=True,
    )

    assert resposta.redirect_chain[-1][1] == 302
    avisos = [
        str(m) for m in resposta.context['messages'] if m.level == messages.WARNING
    ]
    assert avisos == [
        f"Material '{material_disponivel.nome}' possui saldo físico (100.000). "
        'Zere o saldo antes de desativar.'
    ]
    material_disponivel.refresh_from_db()
    assert material_disponivel.ativo is True


# ---------------------------------------------------------------------------
# SaldoEstoqueAdmin — saldo é derivado do ledger, somente-leitura (issue #105)
# ---------------------------------------------------------------------------


@pytest.fixture
def saldo_admin():
    return SaldoEstoqueAdmin(SaldoEstoque, AdminSite())


@pytest.fixture
def staff_de_saldo(db, setor_obras):
    """Staff **não** superusuário, com as permissões Django de `SaldoEstoque`.

    O Django, sozinho, autorizaria este usuário. Qualquer 403 nas telas de
    saldo só pode vir do guard do #105.
    """
    usuario = User.objects.create_user(
        matricula='904',
        nome='Staff Saldo',
        password='senha',
        setor=setor_obras,
        is_staff=True,
    )
    usuario.user_permissions.set(
        Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(SaldoEstoque),
        )
    )
    return usuario


def test_post_no_admin_nao_troca_saldo_fisico(
    client, staff_de_saldo, estoque_principal, material_disponivel
):
    """Escrita direta de saldo é mutação sem `MovimentacaoEstoque` (LED-01).

    O ledger passa a não reconciliar com o saldo (LED-02), e não há linha
    nenhuma que explique a diferença.
    """
    saldo = SaldoEstoque.objects.get(
        estoque=estoque_principal, material=material_disponivel
    )
    fisico_original = saldo.saldo_fisico
    client.force_login(staff_de_saldo)

    resposta = client.post(
        reverse('admin:estoque_saldoestoque_change', args=[saldo.pk]),
        {
            'estoque': str(saldo.estoque_id),
            'material': str(saldo.material_id),
            'saldo_fisico': '999',
            'saldo_reservado': '0',
        },
    )

    assert resposta.status_code == 403
    saldo.refresh_from_db()
    assert saldo.saldo_fisico == fisico_original


def test_saldos_declarados_readonly(saldo_admin):
    assert 'saldo_fisico' in saldo_admin.readonly_fields
    assert 'saldo_reservado' in saldo_admin.readonly_fields


def test_saldos_fora_do_formulario(
    saldo_admin, request_de, superuser, estoque_principal, material_disponivel
):
    saldo = SaldoEstoque.objects.get(
        estoque=estoque_principal, material=material_disponivel
    )

    formulario = saldo_admin.get_form(request_de(superuser), obj=saldo)

    assert 'saldo_fisico' not in formulario.base_fields
    assert 'saldo_reservado' not in formulario.base_fields


def test_saldo_admin_nega_add_change_e_delete(saldo_admin, request_de, superuser):
    requisicao = request_de(superuser)

    assert saldo_admin.has_add_permission(requisicao) is False
    assert saldo_admin.has_change_permission(requisicao) is False
    assert saldo_admin.has_delete_permission(requisicao) is False


def test_add_de_saldo_nega(client, staff_de_saldo):
    """Linha de saldo nasce na importação SCPI, não à mão.

    Criada pelo admin, ela nasceria zerada e sem nenhuma `MovimentacaoEstoque`
    correspondente — estado fora do ledger desde o primeiro instante.
    """
    client.force_login(staff_de_saldo)

    resposta = client.get(reverse('admin:estoque_saldoestoque_add'))

    assert resposta.status_code == 403


def test_changelist_de_saldo_permanece_legivel(
    client, staff_de_saldo, material_disponivel
):
    """A negação é de escrita, não de consulta."""
    client.force_login(staff_de_saldo)

    resposta = client.get(reverse('admin:estoque_saldoestoque_changelist'))

    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# MovimentacaoEstoqueAdmin — ledger imutável, somente-leitura (issue #113)
# ---------------------------------------------------------------------------


@pytest.fixture
def movimentacao_admin():
    return MovimentacaoEstoqueAdmin(MovimentacaoEstoque, AdminSite())


@pytest.fixture
def staff_de_movimentacao(db, setor_obras):
    """Staff **não** superusuário, com todas as permissões Django de `MovimentacaoEstoque`.

    O Django, sozinho, autorizaria este usuário. Qualquer 403 nas telas de
    movimentação só pode vir do guard deste issue.
    """
    usuario = User.objects.create_user(
        matricula='905',
        nome='Staff Movimentacao',
        password='senha',
        setor=setor_obras,
        is_staff=True,
    )
    usuario.user_permissions.set(
        Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(MovimentacaoEstoque),
        )
    )
    return usuario


def test_movimentacao_admin_nega_add_change_e_delete(
    movimentacao_admin, request_de, superuser
):
    requisicao = request_de(superuser)

    assert movimentacao_admin.has_add_permission(requisicao) is False
    assert movimentacao_admin.has_change_permission(requisicao) is False
    assert movimentacao_admin.has_delete_permission(requisicao) is False


def test_add_de_movimentacao_nega(client, staff_de_movimentacao):
    """Linha de ledger sem mutação de saldo correspondente quebra LED-01/LED-02."""
    client.force_login(staff_de_movimentacao)

    resposta = client.get(reverse('admin:estoque_movimentacaoestoque_add'))

    assert resposta.status_code == 403


def test_change_de_movimentacao_nega_sem_derrubar_em_500(
    client, staff_de_movimentacao, movimentacao_criada_pelo_chefe
):
    """`save()` do model levanta `MovimentacaoEstoqueImutavel` — sem o guard do
    admin isso cairia em 500 no POST em vez do 403 de `PermissionDenied`."""
    client.force_login(staff_de_movimentacao)

    resposta = client.post(
        reverse(
            'admin:estoque_movimentacaoestoque_change',
            args=[movimentacao_criada_pelo_chefe.pk],
        ),
        {},
    )

    assert resposta.status_code == 403


def test_delete_de_movimentacao_nega_sem_derrubar_em_500(
    client, staff_de_movimentacao, movimentacao_criada_pelo_chefe
):
    client.force_login(staff_de_movimentacao)

    resposta = client.post(
        reverse(
            'admin:estoque_movimentacaoestoque_delete',
            args=[movimentacao_criada_pelo_chefe.pk],
        ),
        {'post': 'yes'},
    )

    assert resposta.status_code == 403
    assert MovimentacaoEstoque.objects.filter(
        pk=movimentacao_criada_pelo_chefe.pk
    ).exists()


def test_changelist_de_movimentacao_permanece_legivel(
    client, staff_de_movimentacao, movimentacao_criada_pelo_chefe
):
    """A negação é de escrita, não de consulta."""
    client.force_login(staff_de_movimentacao)

    resposta = client.get(reverse('admin:estoque_movimentacaoestoque_changelist'))

    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# SaidaExcepcionalAdmin — sem baixa de saldo/ledger pelo admin (issue #113)
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_de_saida(db, setor_obras):
    """Staff **não** superusuário, com todas as permissões Django de `SaidaExcepcional`.

    O Django, sozinho, autorizaria este usuário. Qualquer 403 nas telas de
    saída excepcional só pode vir do guard deste issue.
    """
    from apps.estoque.models import SaidaExcepcional

    usuario = User.objects.create_user(
        matricula='906',
        nome='Staff Saida',
        password='senha',
        setor=setor_obras,
        is_staff=True,
    )
    usuario.user_permissions.set(
        Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(SaidaExcepcional),
        )
    )
    return usuario


def test_add_de_saida_nega(client, staff_de_saida):
    """Add pelo admin gera documento sem baixa de saldo e sem ledger."""
    client.force_login(staff_de_saida)

    resposta = client.get(reverse('admin:estoque_saidaexcepcional_add'))

    assert resposta.status_code == 403


def test_change_de_saida_responde_em_modo_consulta(
    client, staff_de_saida, saida_registrada
):
    """GET renderiza somente-leitura: `has_view_permission` segue default e não
    depende de `has_change_permission`. Só o POST fecha (teste abaixo)."""
    client.force_login(staff_de_saida)

    resposta = client.get(
        reverse('admin:estoque_saidaexcepcional_change', args=[saida_registrada.pk])
    )

    assert resposta.status_code == 200


def test_post_de_saida_nega(client, staff_de_saida, saida_registrada):
    client.force_login(staff_de_saida)

    resposta = client.post(
        reverse('admin:estoque_saidaexcepcional_change', args=[saida_registrada.pk]),
        {},
    )

    assert resposta.status_code == 403


def test_delete_de_saida_nega(client, staff_de_saida, saida_registrada):
    client.force_login(staff_de_saida)

    resposta = client.post(
        reverse('admin:estoque_saidaexcepcional_delete', args=[saida_registrada.pk]),
        {'post': 'yes'},
    )

    from apps.estoque.models import SaidaExcepcional

    assert resposta.status_code == 403
    assert SaidaExcepcional.objects.filter(pk=saida_registrada.pk).exists()


def test_changelist_de_saida_permanece_legivel(
    client, staff_de_saida, saida_registrada
):
    """A negação é de escrita, não de consulta."""
    client.force_login(staff_de_saida)

    resposta = client.get(reverse('admin:estoque_saidaexcepcional_changelist'))

    assert resposta.status_code == 200


def test_item_inline_nega_add_change_e_delete(request_de, superuser, saida_registrada):
    """`InlineModelAdmin.has_add_permission` não herda de `SaidaExcepcionalAdmin`
    por padrão — precisa de guard próprio pra cumprir a AC "e itens" do #113."""
    from apps.estoque.admin import ItemSaidaExcepcionalInline
    from apps.estoque.models import SaidaExcepcional

    inline = ItemSaidaExcepcionalInline(SaidaExcepcional, AdminSite())
    requisicao = request_de(superuser)

    assert inline.has_add_permission(requisicao, saida_registrada) is False
    assert inline.has_change_permission(requisicao, saida_registrada) is False
    assert inline.has_delete_permission(requisicao, saida_registrada) is False


# ---------------------------------------------------------------------------
# SequenciaSaidaExcepcionalAdmin — numeração não pode regredir (issue #113)
# ---------------------------------------------------------------------------


@pytest.fixture
def sequencia_saida_admin():
    from apps.estoque.admin import SequenciaSaidaExcepcionalAdmin
    from apps.estoque.models import SequenciaSaidaExcepcional

    return SequenciaSaidaExcepcionalAdmin(SequenciaSaidaExcepcional, AdminSite())


@pytest.fixture
def sequencia_de_saida(db, saida_registrada):
    from apps.estoque.models import SequenciaSaidaExcepcional

    return SequenciaSaidaExcepcional.objects.get(ano=saida_registrada.criado_em.year)


def test_sequencia_saida_admin_nega_add(sequencia_saida_admin, request_de, superuser):
    assert sequencia_saida_admin.has_add_permission(request_de(superuser)) is False


def test_ultimo_numero_de_sequencia_saida_declarado_readonly(sequencia_saida_admin):
    assert 'ultimo_numero' in sequencia_saida_admin.readonly_fields
    assert 'ano' in sequencia_saida_admin.readonly_fields


def test_ultimo_numero_de_sequencia_saida_fora_do_formulario(
    sequencia_saida_admin, request_de, superuser, sequencia_de_saida
):
    formulario = sequencia_saida_admin.get_form(
        request_de(superuser), obj=sequencia_de_saida
    )

    assert 'ultimo_numero' not in formulario.base_fields
    assert 'ano' not in formulario.base_fields


def test_post_no_admin_nao_regride_ultimo_numero_de_saida(
    client, superuser, sequencia_de_saida
):
    """Regredir `ultimo_numero` colide com `numero_publico` unique no próximo
    envio — `IntegrityError` (500) em vez de erro tratado."""
    client.force_login(superuser)
    numero_original = sequencia_de_saida.ultimo_numero

    resposta = client.post(
        reverse(
            'admin:estoque_sequenciasaidaexcepcional_change',
            args=[sequencia_de_saida.pk],
        ),
        {'ano': str(sequencia_de_saida.ano), 'ultimo_numero': '0'},
    )

    assert resposta.status_code == 302
    sequencia_de_saida.refresh_from_db()
    assert sequencia_de_saida.ultimo_numero == numero_original


def test_post_no_admin_nao_muda_ano_de_sequencia_saida(
    client, superuser, sequencia_de_saida
):
    """Trocar `ano` "move" o contador pra outro ano com o mesmo efeito de
    apagar: o ano original fica sem sequência e o próximo `get_or_create`
    reemite números já usados."""
    client.force_login(superuser)
    ano_original = sequencia_de_saida.ano

    resposta = client.post(
        reverse(
            'admin:estoque_sequenciasaidaexcepcional_change',
            args=[sequencia_de_saida.pk],
        ),
        {
            'ano': str(ano_original + 1),
            'ultimo_numero': str(sequencia_de_saida.ultimo_numero),
        },
    )

    assert resposta.status_code == 302
    sequencia_de_saida.refresh_from_db()
    assert sequencia_de_saida.ano == ano_original


def test_sequencia_saida_admin_nega_delete(
    sequencia_saida_admin, request_de, superuser
):
    assert sequencia_saida_admin.has_delete_permission(request_de(superuser)) is False


def test_delete_de_sequencia_saida_nega(client, superuser, sequencia_de_saida):
    """Apagar reseta a numeração — próximo `get_or_create` recria do zero e
    colide com `numero_publico` já emitido para o mesmo ano."""
    client.force_login(superuser)

    resposta = client.post(
        reverse(
            'admin:estoque_sequenciasaidaexcepcional_delete',
            args=[sequencia_de_saida.pk],
        ),
        {'post': 'yes'},
    )

    from apps.estoque.models import SequenciaSaidaExcepcional

    assert resposta.status_code == 403
    assert SequenciaSaidaExcepcional.objects.filter(pk=sequencia_de_saida.pk).exists()


# ---------------------------------------------------------------------------
# ImportacaoSCPIAdmin — apagar libera reimportação do mesmo arquivo (#113)
# ---------------------------------------------------------------------------


@pytest.fixture
def importacao_scpi(db, chefe_almoxarifado, estoque_principal):
    from apps.estoque.models import ImportacaoSCPI

    return ImportacaoSCPI.objects.create(
        arquivo_nome='scpi_2025.csv',
        arquivo_hash='a' * 64,
        importado_por=chefe_almoxarifado,
        estoque=estoque_principal,
    )


@pytest.fixture
def staff_de_importacao(db, setor_obras):
    from apps.estoque.models import ImportacaoSCPI

    usuario = User.objects.create_user(
        matricula='907',
        nome='Staff Importacao',
        password='senha',
        setor=setor_obras,
        is_staff=True,
    )
    usuario.user_permissions.set(
        Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(ImportacaoSCPI),
        )
    )
    return usuario


def test_add_de_importacao_nega(client, staff_de_importacao):
    """Importação nasce por `confirmar_importacao_scpi`, não à mão pelo admin."""
    client.force_login(staff_de_importacao)

    resposta = client.get(reverse('admin:estoque_importacaoscpi_add'))

    assert resposta.status_code == 403


def test_change_de_importacao_nega(client, staff_de_importacao, importacao_scpi):
    """`status`/`total_*`/`importado_por` são metadados de auditoria — editá-los
    pelo admin falsifica a trilha de quem importou o quê."""
    client.force_login(staff_de_importacao)
    status_original = importacao_scpi.status

    resposta = client.post(
        reverse('admin:estoque_importacaoscpi_change', args=[importacao_scpi.pk]),
        {
            'arquivo_nome': importacao_scpi.arquivo_nome,
            'importado_por': str(importacao_scpi.importado_por_id),
            'estoque': str(importacao_scpi.estoque_id),
            'status': 'com_alertas',
            'total_linhas': '999',
            'total_novos': '999',
            'total_divergentes': '999',
        },
    )

    assert resposta.status_code == 403
    importacao_scpi.refresh_from_db()
    assert importacao_scpi.status == status_original


def test_delete_de_importacao_nega(client, staff_de_importacao, importacao_scpi):
    """Apagar libera reimportação do mesmo arquivo (dedup por `arquivo_hash`)."""
    client.force_login(staff_de_importacao)

    resposta = client.post(
        reverse('admin:estoque_importacaoscpi_delete', args=[importacao_scpi.pk]),
        {'post': 'yes'},
    )

    from apps.estoque.models import ImportacaoSCPI

    assert resposta.status_code == 403
    assert ImportacaoSCPI.objects.filter(pk=importacao_scpi.pk).exists()


def test_changelist_de_importacao_permanece_legivel(
    client, staff_de_importacao, importacao_scpi
):
    client.force_login(staff_de_importacao)

    resposta = client.get(reverse('admin:estoque_importacaoscpi_changelist'))

    assert resposta.status_code == 200
