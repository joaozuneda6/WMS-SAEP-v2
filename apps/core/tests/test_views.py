"""Testes de integração para o dispatcher pós-login (apps/core/views.home)."""

import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import Setor, SetorClassificacao, VinculoAuxiliar


@pytest.mark.django_db
def test_home_nao_autenticado_redireciona_login(client):
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert '/login' in resposta['Location'] or 'accounts' in resposta['Location']


@pytest.mark.django_db
def test_home_superuser_e_roteado_pelo_produto_nao_pelo_admin(client):
    """`is_superuser` é flag técnica do Django, fora do domínio (PRODUCT.md): não
    sequestra a raiz. O superusuário é roteado pelo papel efetivo como qualquer
    outro — e o superusuário passa em `pode_ver_fila_atendimento`, logo cai na
    fila de atendimentos. O admin fica acessível por link explícito, não pela
    home."""
    User = get_user_model()
    usuario = User.objects.create_superuser(
        matricula='SUPER-001',
        password='senha-forte-123',
        nome='Super Admin',
    )
    client.force_login(usuario)
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert resposta['Location'] == reverse('requisicoes:atendimentos')
    assert resposta['Location'] != '/admin/'


@pytest.mark.django_db
def test_home_chefe_almoxarifado_redireciona_atendimentos(client):
    User = get_user_model()
    setor = Setor.objects.create(
        codigo='ALM', nome='Almoxarifado', classificacao=SetorClassificacao.ALMOXARIFADO
    )
    usuario = User.objects.create_user(
        matricula='ALMX-001',
        password='senha-forte-123',
        nome='Chefe Almox',
        setor=setor,
    )
    setor.chefe = usuario
    setor.save(update_fields=['chefe'])
    client.force_login(usuario)
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert resposta['Location'] == reverse('requisicoes:atendimentos')


@pytest.mark.django_db
def test_home_auxiliar_almoxarifado_redireciona_atendimentos(client):
    User = get_user_model()
    setor = Setor.objects.create(
        codigo='ALM2',
        nome='Almoxarifado',
        classificacao=SetorClassificacao.ALMOXARIFADO,
    )
    usuario = User.objects.create_user(
        matricula='ALMX-002',
        password='senha-forte-123',
        nome='Aux Almox',
        setor=setor,
    )
    VinculoAuxiliar.objects.create(usuario=usuario, setor=setor, ativo=True)
    client.force_login(usuario)
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert resposta['Location'] == reverse('requisicoes:atendimentos')


@pytest.mark.django_db
def test_home_chefe_setor_comum_redireciona_autorizacoes(client):
    User = get_user_model()
    setor = Setor.objects.create(
        codigo='OBR2', nome='Obras', classificacao=SetorClassificacao.COMUM
    )
    usuario = User.objects.create_user(
        matricula='CHEF-001',
        password='senha-forte-123',
        nome='Chefe Obras',
        setor=setor,
    )
    setor.chefe = usuario
    setor.save(update_fields=['chefe'])
    client.force_login(usuario)
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert resposta['Location'] == reverse('requisicoes:autorizacoes')


@pytest.mark.django_db
def test_home_solicitante_redireciona_minhas(client):
    User = get_user_model()
    setor = Setor.objects.create(
        codigo='OBR3', nome='Obras', classificacao=SetorClassificacao.COMUM
    )
    usuario = User.objects.create_user(
        matricula='SOL-001',
        password='senha-forte-123',
        nome='Solicitante',
        setor=setor,
    )
    client.force_login(usuario)
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert resposta['Location'] == reverse('requisicoes:minhas')


@pytest.mark.django_db
def test_home_staff_com_papel_almox_vai_para_atendimentos(client):
    """is_staff não bypassa o dispatcher — papel operacional tem prioridade."""
    User = get_user_model()
    setor = Setor.objects.create(
        codigo='ALM3',
        nome='Almoxarifado',
        classificacao=SetorClassificacao.ALMOXARIFADO,
    )
    usuario = User.objects.create_user(
        matricula='STAF-001',
        password='senha-forte-123',
        nome='Staff Almox',
        setor=setor,
        is_staff=True,
    )
    VinculoAuxiliar.objects.create(usuario=usuario, setor=setor, ativo=True)
    client.force_login(usuario)
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert resposta['Location'] == reverse('requisicoes:atendimentos')


@pytest.mark.django_db
def test_home_multi_papel_almox_chefe_vai_para_atendimentos(client):
    """Usuário com almoxarifado E chefe de setor comum → almox ganha (prioridade)."""
    User = get_user_model()
    setor_almox = Setor.objects.create(
        codigo='ALM4',
        nome='Almoxarifado',
        classificacao=SetorClassificacao.ALMOXARIFADO,
    )
    setor_comum = Setor.objects.create(
        codigo='OBR4', nome='Obras', classificacao=SetorClassificacao.COMUM
    )
    usuario = User.objects.create_user(
        matricula='MULT-001',
        password='senha-forte-123',
        nome='Multi Papel',
        setor=setor_almox,
    )
    VinculoAuxiliar.objects.create(usuario=usuario, setor=setor_almox, ativo=True)
    setor_comum.chefe = usuario
    setor_comum.save(update_fields=['chefe'])
    client.force_login(usuario)
    resposta = client.get(reverse('core:home'))
    assert resposta.status_code == 302
    assert resposta['Location'] == reverse('requisicoes:atendimentos')


# ---------------------------------------------------------------------------
# Páginas de erro (Etapa 8)
# ---------------------------------------------------------------------------


class TestPaginasDeErro:
    """403/404/500 eram o HTML cru do Django — sem chrome e sem volta.

    O 403 do produto é rotina, não incidente: papel efetivo é derivado do ator
    diante de cada registro, então uma tela visível a um papel pode apontar para
    uma ação que só outro executa.
    """

    def test_403_e_404_trazem_codigo_titulo_e_saida(self, client, django_user_model):
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        usuario = django_user_model.objects.create_user(
            matricula='ERR001', nome='Usuário Erro', password='x'
        )
        request = RequestFactory().get('/rota-inexistente/')
        request.user = usuario

        for template, codigo in (('403.html', '403'), ('404.html', '404')):
            html = render_to_string(template, {}, request=request)
            assert f'Erro {codigo}' in html
            assert 'Ir para o início' in html
            assert '<h1' in html

    def test_500_nao_depende_de_context_processor(self):
        """`django.views.defaults.server_error` renderiza com contexto vazio e
        sem context processors: `user`, `{% url %}` e as tags da barra não
        existem ali. Renderizar sem request é o teste."""
        from django.template.loader import render_to_string

        html = render_to_string('500.html', {})
        assert 'Erro 500' in html
        assert 'Ir para o início' in html
        assert 'app-bar' not in html


class TestEstaticosDoPiloto:
    """`ManifestStaticFilesStorage` reescreve URLs dentro dos CSS coletados, e
    a fonte do Tailwind (`@import "tailwindcss"`) não é um caminho de arquivo:
    enquanto `input.css` morou dentro de `apps/core/static/`, o `collectstatic`
    do piloto morria com
    `The file 'core/css/tailwindcss' could not be found`.

    A correção (#168) foi tirar a fonte da árvore de estáticos — ela vive em
    `assets/css/input.css` — em vez de manter um storage customizado só para
    contornar o post-processamento. O piloto volta a usar o
    `ManifestStaticFilesStorage` de fábrica.
    """

    def test_o_piloto_usa_o_storage_de_fabrica(self, monkeypatch):
        """O módulo é importado à parte porque as guardas do piloto recusam o
        boot sem hosts, origens e Postgres; os valores abaixo só as satisfazem.
        """
        import importlib

        for chave, valor in {
            'ALLOWED_HOSTS': 'piloto.exemplo',
            'CSRF_TRUSTED_ORIGINS': 'https://piloto.exemplo',
            'DATABASE_URL': 'postgres://usuario:senha@localhost:5432/wms',
        }.items():
            monkeypatch.setenv(chave, valor)

        piloto = importlib.reload(importlib.import_module('config.settings.piloto'))

        assert (
            piloto.STORAGES['staticfiles']['BACKEND']
            == 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
        )

    def test_nenhum_css_coletavel_e_fonte_do_tailwind(self):
        """O defeito original não era "`input.css` naquele caminho" — era
        "qualquer CSS coletado cujo conteúdo começa com `@import "tailwindcss"`",
        que não é caminho de arquivo e derruba o pós-processamento do manifesto.
        Varre o conteúdo, não o nome: pega o caso antigo e qualquer app vizinho
        que reintroduza a mesma armadilha.
        """
        raiz = Path(settings.BASE_DIR)
        infratores = [
            str(css.relative_to(raiz))
            for css in raiz.glob('apps/*/static/**/*.css')
            if '@import "tailwindcss"' in css.read_text(encoding='utf-8')
        ]
        assert infratores == [], (
            f'Fonte do Tailwind dentro da árvore de estáticos: {infratores}'
        )

    def test_collectstatic_do_piloto_roda_e_da_hash_ao_app_css(self, tmp_path):
        """O defeito de #168 era um `ValueError` em tempo de `collectstatic`, não
        uma string de settings errada. Só rodar o comando de verdade prova que o
        pós-processamento do manifesto atravessa a árvore de estáticos inteira —
        e junto confirma que o artefato servido (`app.css`) continua ganhando
        hash, o que justificou o storage customizado que #168 removeu.
        """
        with override_settings(
            STATIC_ROOT=tmp_path,
            STORAGES={
                'default': settings.STORAGES['default'],
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
                },
            },
        ):
            call_command('collectstatic', interactive=False, verbosity=0)

        manifesto = json.loads((tmp_path / 'staticfiles.json').read_text())
        assert re.fullmatch(
            r'core/css/app\.[0-9a-f]{12}\.css', manifesto['paths']['core/css/app.css']
        )
