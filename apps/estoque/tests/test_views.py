"""Testes de view para estoque.saidas_excepcionais."""

import re
from decimal import Decimal
from pathlib import Path

from django.urls import reverse

from apps.core.tests.documento import (
    assert_dialogo_nomeado_pelo_proprio_titulo,
    assert_html_balanceado,
    assert_sem_id_duplicado,
    ids_do_documento,
)
from apps.core.tests.marcacao import atributo, elementos, pares


URL = reverse('estoque:listar_saidas_excepcionais')

# Início dos dois glifos do catálogo que disputam o cabeçalho do modal de
# estorno: `devolver.svg` é o que a variante `return` escolhe em
# `_modal_icon.html`, e `alerta.svg` é o círculo de perigo que ela substituiu.
# Comparar o `<path>` renderizado, e não o nome do arquivo, é o que faz o teste
# medir o glifo que chega ao HTML.
PATH_DEVOLVER = 'M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62'
PATH_ALERTA = 'M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Z'


def assert_todo_dt_tem_dd(html: str) -> None:
    """Cada grupo de `<dl>` precisa de ao menos um `<dd>`.

    O modelo de conteúdo do elemento pareia nome e valor; `<dt>` sozinho não
    chega à árvore de acessibilidade como par, e o leitor de tela anuncia um
    termo sem definição. A varredura é por `<dl>`, contando `<dt>` e `<dd>`
    dentro dela, porque o pareamento é dentro da lista, não do documento.
    """
    for lista in re.findall(r'<dl\b.*?</dl>', html, re.S | re.I):
        termos = len(re.findall(r'<dt\b', lista, re.I))
        definicoes = len(re.findall(r'<dd\b', lista, re.I))
        assert termos <= definicoes, (
            f'<dl> com {termos} <dt> e {definicoes} <dd>: '
            f'há termo sem definição.\n{lista}'
        )


class TestListarSaidasExcepcionaisView:
    def test_chefe_almox_acessa_lista(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        assert response.status_code == 200

    def test_aux_almox_acessa_lista(self, client, aux_almoxarifado):
        client.force_login(aux_almoxarifado)
        response = client.get(URL)
        assert response.status_code == 200

    def test_superuser_acessa_lista(self, client, superuser):
        client.force_login(superuser)
        response = client.get(URL)
        assert response.status_code == 200

    def test_solicitante_recebe_403(self, client, solicitante):
        client.force_login(solicitante)
        response = client.get(URL)
        assert response.status_code == 403

    def test_lista_pagina_em_vez_de_carregar_tudo(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        """A lista só cresce: `listar_saidas_excepcionais` não tem recorte de
        período nem filtro, e a tela renderizava o queryset inteiro em cartões.
        """
        from apps.estoque.services import registrar_saida_excepcional
        from apps.estoque.views import PAGINA_SAIDAS_EXCEPCIONAIS_TAMANHO

        total = PAGINA_SAIDAS_EXCEPCIONAIS_TAMANHO + 2
        for i in range(total):
            registrar_saida_excepcional(
                ator_id=chefe_almoxarifado.pk,
                estoque_id=estoque_principal.pk,
                motivo=f'Descarte {i}',
                observacao='',
                itens=[{'material_id': material_disponivel.pk, 'quantidade': '1'}],
            )

        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        page_obj = response.context['page_obj']

        assert page_obj.paginator.count == total
        assert len(response.context['saidas']) == PAGINA_SAIDAS_EXCEPCIONAIS_TAMANHO
        assert 'Paginação das saídas excepcionais' in response.content.decode()

    def test_usuario_inativo_redirecionado_para_login(self, client, usuario_inativo):
        # Django ModelBackend trata is_active=False como não-autenticado;
        # @login_required redireciona para login (USR-01).
        client.force_login(usuario_inativo)
        response = client.get(URL)
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_anonimo_redirecionado_para_login(self, client):
        response = client.get(URL)
        assert response.status_code == 302
        assert (
            '/login' in response['Location'] or 'accounts/login' in response['Location']
        )

    def test_contexto_contem_saidas(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        assert 'saidas' in response.context

    def test_botao_ver_detalhes_preserva_aria_label(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        html = response.content.decode('utf-8')
        assert (
            f'aria-label="Ver detalhes da saída {saida_registrada.numero_publico}"'
            in html
        )

    def test_botao_ver_detalhes_fallback_pk_sem_numero_publico(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        saida_registrada.numero_publico = ''
        saida_registrada.save(update_fields=['numero_publico'])
        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        html = response.content.decode('utf-8')
        assert f'aria-label="Ver detalhes da saída {saida_registrada.pk}"' in html

    def test_lista_populada_oferece_a_acao_de_registrar(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """O único link para `saidas-excepcionais/nova/` vivia dentro do estado
        vazio — sumia no primeiro registro e não voltava, e a side nav não o
        tem. Depois da primeira saída não havia caminho pela interface para
        registrar a segunda."""
        client.force_login(chefe_almoxarifado)
        html = client.get(URL).content.decode('utf-8')
        assert html.count('/estoque/saidas-excepcionais/nova/') >= 1
        assert 'Nova saída excepcional' in html

    def test_acao_de_registrar_respeita_a_policy(
        self, client, aux_almoxarifado, saida_registrada
    ):
        """Só o chefe de almoxarifado registra saída excepcional; o auxiliar vê
        a lista e não pode a ação."""
        client.force_login(aux_almoxarifado)
        html = client.get(URL).content.decode('utf-8')
        assert '/estoque/saidas-excepcionais/nova/' not in html

    def test_empty_state_cta_delega_para_componente_button(
        self, client, chefe_almoxarifado
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        html = response.content.decode('utf-8')
        titulo_idx = html.index('Nenhuma saída excepcional registrada')
        match = re.search(r'<a\b[^>]*>', html[titulo_idx:])
        assert match is not None
        tag = match.group()
        assert 'min-h-11' in tag
        assert 'justify-center' in tag
        assert 'focus-visible:ring-offset-1' in tag
        assert 'ring-offset-2' not in tag

    def test_pode_registrar_verdadeiro_para_chefe(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        assert response.context['pode_registrar'] is True

    def test_pode_registrar_falso_para_aux(self, client, aux_almoxarifado):
        client.force_login(aux_almoxarifado)
        response = client.get(URL)
        assert response.context['pode_registrar'] is False

    def test_pode_registrar_verdadeiro_para_superuser(self, client, superuser):
        # Superuser tem override técnico para registrar (matriz-permissoes.md linha 78)
        client.force_login(superuser)
        response = client.get(URL)
        assert response.context['pode_registrar'] is True

    def test_vazia_com_permissao_exibe_cta(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL)
        html = response.content.decode()
        assert 'border-dashed border-border-strong' in html
        assert 'Nenhuma saída excepcional registrada' in html
        assert 'Registre a primeira baixa administrativa direta de material.' in html
        assert reverse('estoque:nova_saida_excepcional') in html

    def test_vazia_sem_permissao_oculta_cta(self, client, aux_almoxarifado):
        client.force_login(aux_almoxarifado)
        response = client.get(URL)
        html = response.content.decode()
        assert 'Nenhuma saída excepcional registrada' in html
        assert 'Não há saídas excepcionais no sistema.' in html
        assert reverse('estoque:nova_saida_excepcional') not in html

    def test_paginacao_preserva_a_ordem_ativa(
        self,
        client,
        chefe_almoxarifado,
        estoque_principal,
        material_disponivel,
        monkeypatch,
    ):
        """A página 2 de `?ordem=asc` voltava para a ordem descendente padrão.

        A view calculava `querystring_filtros` e não o expunha ao contexto, e o
        template não o repassava ao componente: os links nasciam `?page=2`, sem
        o recorte ativo. `per_page` de 1 evita criar 26 saídas para provar isso.
        """
        from decimal import Decimal

        from apps.estoque import views as estoque_views
        from apps.estoque.services import registrar_saida_excepcional

        for _ in range(2):
            registrar_saida_excepcional(
                ator_id=chefe_almoxarifado.pk,
                estoque_id=estoque_principal.pk,
                motivo='avaria',
                observacao='',
                itens=[
                    {
                        'material_id': material_disponivel.pk,
                        'quantidade': Decimal('1'),
                    }
                ],
            )
        monkeypatch.setattr(estoque_views, 'PAGINA_SAIDAS_EXCEPCIONAIS_TAMANHO', 1)

        client.force_login(chefe_almoxarifado)
        response = client.get(URL, {'ordem': 'asc'})
        assert response.context['querystring_filtros'] == 'ordem=asc'
        assert 'href="?ordem=asc&amp;page=2"' in response.content.decode()


URL_NOVA = reverse('estoque:nova_saida_excepcional')
URL_BUSCAR = reverse('estoque:buscar_materiais_saida_excepcional')


class TestNovaSaidaExcepcionalView:
    def test_chefe_acessa_formulario(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_NOVA)
        assert response.status_code == 200

    def test_get_formset_tem_uma_linha_inicial_vazia(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_NOVA)
        assert response.status_code == 200
        assert len(response.context['formset'].forms) == 1

    def test_container_itens_usa_factory_alpine_itensformset(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_NOVA)
        html = response.content.decode()
        assert 'id="itens-container"' in html
        # A factory passa a receber o prefixo do formset para ler o TOTAL_FORMS,
        # que é a fonte única do índice da próxima linha.
        assert 'x-data="itensFormset({ prefixo: \'itens\' })"' in html
        assert 'data-itens-container' in html

    def test_botao_remover_usa_click_alpine_sem_onclick_inline(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_NOVA)
        html = response.content.decode()
        assert '@click="removerLinha($event)"' in html
        assert 'onclick=' not in html

    def test_superuser_acessa_formulario(self, client, superuser, estoque_principal):
        client.force_login(superuser)
        response = client.get(URL_NOVA)
        assert response.status_code == 200

    def test_aux_recebe_403(self, client, aux_almoxarifado):
        client.force_login(aux_almoxarifado)
        response = client.get(URL_NOVA)
        assert response.status_code == 403

    def test_solicitante_recebe_403(self, client, solicitante):
        client.force_login(solicitante)
        response = client.get(URL_NOVA)
        assert response.status_code == 403

    def test_anonimo_redirecionado_para_login(self, client):
        response = client.get(URL_NOVA)
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_post_nao_htmx_valido_cria_saida_e_redireciona(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'Caixas molhadas',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 302
        from apps.estoque.models import SaidaExcepcional

        assert SaidaExcepcional.objects.count() == 1
        saida = SaidaExcepcional.objects.get()
        assert saida.numero_publico.startswith('SXP-')

    def test_post_htmx_valido_cria_saida_e_retorna_hx_redirect(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'Caixas molhadas',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 204
        assert response['HX-Redirect'] == reverse('estoque:listar_saidas_excepcionais')
        from apps.estoque.models import SaidaExcepcional

        assert SaidaExcepcional.objects.count() == 1

    def test_post_sem_motivo_retorna_form_com_erro(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': '',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 200
        assert 'motivo' in response.context['form'].errors

    def test_post_motivo_invalido_retorna_form_com_erro(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'nao_existe',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 200
        assert 'motivo' in response.context['form'].errors

    def test_post_sem_observacao_retorna_form_com_erro(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': '',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 200
        assert 'observacao' in response.context['form'].errors

    def test_post_sem_itens_retorna_formset_com_erro(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '0',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
            },
        )
        assert response.status_code == 200
        assert any(
            'ao menos um item' in e
            for e in response.context['formset'].non_form_errors()
        )

    def test_post_item_duplicado_retorna_erro_na_linha(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '2',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
                'itens-1-material_id': str(material_disponivel.pk),
                'itens-1-quantidade': '3',
            },
        )
        assert response.status_code == 200
        formset = response.context['formset']
        assert any('material_label' in f.errors for f in formset.forms)

    def test_post_quantidade_invalida_retorna_erro_na_linha(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '0',
            },
        )
        assert response.status_code == 200
        formset = response.context['formset']
        assert 'quantidade' in formset.forms[0].errors

    def test_post_material_inelegivel_retorna_erro_na_linha(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        from apps.estoque.models import Material, SaldoEstoque, UnidadeMedida

        material_inativo = Material.objects.create(
            codigo='MAT097', nome='Serrote', unidade=UnidadeMedida.UNIDADE, ativo=False
        )
        SaldoEstoque.objects.create(
            estoque=estoque_principal, material=material_inativo, saldo_fisico=10
        )
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_inativo.pk),
                'itens-0-quantidade': '1',
            },
        )
        assert response.status_code == 200
        formset = response.context['formset']
        assert 'material_label' in formset.forms[0].errors

    def test_post_aux_recebe_403_sem_persistencia(
        self, client, aux_almoxarifado, estoque_principal, material_disponivel
    ):
        from apps.estoque.models import SaidaExcepcional

        client.force_login(aux_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'Teste',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 403
        assert SaidaExcepcional.objects.count() == 0

    def test_post_solicitante_recebe_403_sem_persistencia(
        self, client, solicitante, estoque_principal, material_disponivel
    ):
        from apps.estoque.models import SaidaExcepcional

        client.force_login(solicitante)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'Teste',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 403
        assert SaidaExcepcional.objects.count() == 0

    def test_post_anonimo_redireciona_sem_persistencia(
        self, client, material_disponivel
    ):
        from apps.estoque.models import SaidaExcepcional

        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'Teste',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 302
        assert 'login' in response['Location']
        assert SaidaExcepcional.objects.count() == 0

    def test_dados_invalidos_do_service_gera_messages_error_e_rerender(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        """DadosInvalidos do service (ex: race pós-clean) vira messages.error e
        re-renderiza o form — sem redirect, mesma request (docs/CONVENTIONS.md)."""
        from unittest.mock import patch

        from apps.core.exceptions import DadosInvalidos

        client.force_login(chefe_almoxarifado)
        with patch(
            'apps.estoque.views.registrar_saida_excepcional',
            side_effect=DadosInvalidos('material inativo'),
        ):
            response = client.post(
                URL_NOVA,
                data={
                    'motivo': 'avaria',
                    'observacao': 'Teste',
                    'itens-TOTAL_FORMS': '1',
                    'itens-INITIAL_FORMS': '0',
                    'itens-MIN_NUM_FORMS': '0',
                    'itens-MAX_NUM_FORMS': '1000',
                    'itens-0-material_id': str(material_disponivel.pk),
                    'itens-0-quantidade': '5',
                },
            )

        assert response.status_code == 200
        mensagens = list(response.wsgi_request._messages)
        assert len(mensagens) == 1
        assert mensagens[0].level_tag == 'error'
        assert str(mensagens[0]) == 'material inativo'

    def test_conflito_dominio_do_service_gera_messages_warning_e_rerender(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        """ConflitoDominio do service (ex: saldo insuficiente na corrida entre
        clean() e select_for_update()) vira messages.warning e re-renderiza."""
        from unittest.mock import patch

        from apps.core.exceptions import ConflitoDominio

        client.force_login(chefe_almoxarifado)
        with patch(
            'apps.estoque.views.registrar_saida_excepcional',
            side_effect=ConflitoDominio('saldo físico insuficiente'),
        ):
            response = client.post(
                URL_NOVA,
                data={
                    'motivo': 'avaria',
                    'observacao': 'Teste',
                    'itens-TOTAL_FORMS': '1',
                    'itens-INITIAL_FORMS': '0',
                    'itens-MIN_NUM_FORMS': '0',
                    'itens-MAX_NUM_FORMS': '1000',
                    'itens-0-material_id': str(material_disponivel.pk),
                    'itens-0-quantidade': '5',
                },
            )

        assert response.status_code == 200
        mensagens = list(response.wsgi_request._messages)
        assert len(mensagens) == 1
        assert mensagens[0].level_tag == 'warning'
        assert str(mensagens[0]) == 'saldo físico insuficiente'


class TestBuscarMateriasSaidaExcepcionalView:
    def test_chefe_recebe_json(self, client, chefe_almoxarifado, material_disponivel):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_BUSCAR, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        data = response.json()
        assert 'resultados' in data

    def test_filtra_por_q(self, client, chefe_almoxarifado, material_disponivel):
        client.force_login(chefe_almoxarifado)
        response = client.get(
            URL_BUSCAR + '?q=Parafuso', HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        assert response.status_code == 200
        data = response.json()
        assert any('Parafuso' in r['nome'] for r in data['resultados'])

    def test_aux_recebe_403(self, client, aux_almoxarifado):
        client.force_login(aux_almoxarifado)
        response = client.get(URL_BUSCAR, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 403

    def test_anonimo_redirecionado(self, client):
        response = client.get(URL_BUSCAR)
        assert response.status_code == 302

    def test_aux_permissao_negada_retorna_json_403_nao_redirect(
        self, client, aux_almoxarifado
    ):
        """Opt-out: PermissaoNegada em buscar_materiais_saida_excepcional deve retornar
        JsonResponse 403 (não redirect com messages)."""
        client.force_login(aux_almoxarifado)
        response = client.get(URL_BUSCAR)
        assert response.status_code == 403
        assert response['Content-Type'].startswith('application/json')
        assert 'error' in response.json()


class TestDetalheSaidaExcepcionalView:
    def _url(self, pk):
        return reverse('estoque:detalhe_saida_excepcional', args=[pk])

    def test_chefe_almox_acessa_detalhe(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        assert response.status_code == 200

    def test_aux_almox_acessa_detalhe(self, client, aux_almoxarifado, saida_registrada):
        client.force_login(aux_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        assert response.status_code == 200

    def test_superuser_acessa_detalhe(self, client, superuser, saida_registrada):
        client.force_login(superuser)
        response = client.get(self._url(saida_registrada.pk))
        assert response.status_code == 200

    def test_solicitante_recebe_403(self, client, solicitante, saida_registrada):
        client.force_login(solicitante)
        response = client.get(self._url(saida_registrada.pk))
        assert response.status_code == 403

    def test_anonimo_redirecionado_para_login(self, client, saida_registrada):
        response = client.get(self._url(saida_registrada.pk))
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_usuario_inativo_redirecionado_para_login(
        self, client, usuario_inativo, saida_registrada
    ):
        client.force_login(usuario_inativo)
        response = client.get(self._url(saida_registrada.pk))
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_pk_inexistente_retorna_404(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(999999))
        assert response.status_code == 404

    def test_contexto_contem_saida_e_pode_estornar(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        assert 'saida' in response.context
        assert 'pode_estornar' in response.context
        assert response.context['pode_estornar'] is True

    def test_aux_nao_pode_estornar_no_contexto(
        self, client, aux_almoxarifado, saida_registrada
    ):
        client.force_login(aux_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        assert response.context['pode_estornar'] is False

    def test_voltar_url_preserva_pagina_da_listagem(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """O cartão da lista paginada manda `?next=` com a página de origem; os
        dois links "Voltar" do detalhe devem apontar de volta para ela (PR #40).
        """
        client.force_login(chefe_almoxarifado)
        proximo = f'{URL}?page=2'
        response = client.get(self._url(saida_registrada.pk), {'next': proximo})
        assert response.context['voltar_url'] == proximo
        assert response.content.decode().count(f'href="{proximo}"') == 2

    def test_voltar_url_rejeita_destino_externo(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """`next` para outro host cai no fallback — nunca vira open redirect."""
        client.force_login(chefe_almoxarifado)
        response = client.get(
            self._url(saida_registrada.pk), {'next': 'https://evil.example/x'}
        )
        assert response.context['voltar_url'] == URL

    def test_post_retorna_405(self, client, chefe_almoxarifado, saida_registrada):
        client.force_login(chefe_almoxarifado)
        response = client.post(self._url(saida_registrada.pk), data={})
        assert response.status_code == 405

    def test_modal_estorno_usa_componente_com_textarea_obrigatorio(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """Modal de estorno migrado para components/modal.html (issue #78)."""
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        html = response.content.decode('utf-8')
        assert 'data-modal-trigger="estornar-saida"' in html
        dialog_inicio = html.index('id="estornar-saida"')
        dialog_fim = html.index('</dialog>', dialog_inicio)
        dialog_html = html[dialog_inicio:dialog_fim]
        assert '<textarea' in dialog_html
        assert 'name="justificativa"' in dialog_html
        assert 'required' in dialog_html
        assert f'action="{self._estornar_url(saida_registrada.pk)}"' in dialog_html

    def test_modal_de_estorno_nomeia_a_saida_e_a_consequencia(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """ "Estornar saída excepcional" — qual? (#138)

        O modal devolve todos os itens ao saldo físico e não carregava número
        público nenhum. A frase de irreversibilidade saiu da descrição para o
        corpo, com ênfase maior que a dos dados que ela qualifica.
        """
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        html = response.content.decode('utf-8')
        inicio = html.index('id="estornar-saida"')
        dialog_html = html[inicio : html.index('</dialog>', inicio)]

        assert 'data-modal-registro' in dialog_html
        assert saida_registrada.numero_publico in dialog_html
        assert saida_registrada.estoque.nome in dialog_html
        assert 'Esta ação é irreversível.' in dialog_html

    def test_detalhe_com_modal_de_estorno_nao_repete_nenhum_id(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """A tela herda o contrato de id de `components/modal.html` (#139).

        A #131 pegou o id duplicado nas telas de `requisicoes`, onde o painel de
        decisão derivava o mesmo `{{ id }}-titulo` do `<h2>` do modal. Aqui não
        há painel, então o que falta é a guarda genérica: id repetido é HTML
        inválido e torna qualquer `getElementById` imprevisível.
        """
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        html = response.content.decode('utf-8')

        assert 'id="estornar-saida"' in html
        assert_sem_id_duplicado(html)

    def test_dialog_de_estorno_e_nomeado_pelo_titulo_do_proprio_modal(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """O nome acessível do `<dialog>` é o `<h2>` do corpo do modal (#139)."""
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        html = response.content.decode('utf-8')

        assert 'estornar-saida-titulo' in ids_do_documento(html)
        assert_dialogo_nomeado_pelo_proprio_titulo(html)

    def test_estorno_nao_usa_o_vocabulario_de_perigo(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """Reversão operacional nunca é vermelha (Regra da Reversão Não é Erro).

        Esta tela se contradizia sozinha: o bloco "Dados do estorno" já saía em
        `text-return-*` e o estado resultante em teal, enquanto o gatilho, o
        ícone do modal e o botão de confirmação saíam em vermelho — a ação e o
        seu efeito dizendo coisas opostas na mesma página. O estorno de
        requisição fez este caminho na #136; a saída excepcional ficou para
        trás, e `docs/design-system.md` passou a declarar as duas em `return`.

        Renderizado, e não lido do fonte do template: o que precisa estar certo
        são os tokens que chegam ao HTML e o glifo que `_modal_icon.html`
        escolhe. Um guarda de string passaria com a variante escrita e não
        resolvida.
        """
        client.force_login(chefe_almoxarifado)
        html = client.get(self._url(saida_registrada.pk)).content.decode('utf-8')

        (gatilho,) = [
            atributos
            for _, atributos, _ in elementos(html, 'button')
            if atributo(atributos, 'data-modal-trigger') == 'estornar-saida'
        ]
        classe = atributo(gatilho, 'class')
        assert 'text-return-text-strong' in classe
        assert 'border-return' in classe
        assert 'danger' not in classe, classe

        inicio = html.index('id="estornar-saida"')
        dialog = html[inicio : html.index('</dialog>', inicio)]

        assert 'bg-return-muted text-return-text' in dialog
        assert PATH_DEVOLVER in dialog
        assert 'bg-danger-muted' not in dialog
        assert PATH_ALERTA not in dialog

        (confirmar,) = [
            atributos
            for _, atributos, _ in elementos(dialog, 'button')
            # `data-modal-confirm` não tem valor, e `atributo` devolve `None`
            # tanto para ausente quanto para atributo sem valor.
            if 'data-modal-confirm' in {nome for nome, _ in pares(atributos)}
        ]
        classe_confirmar = atributo(confirmar, 'class')
        assert 'bg-return' in classe_confirmar
        assert 'danger' not in classe_confirmar, classe_confirmar

    def _estornar_url(self, pk):
        return reverse('estoque:estornar_saida_excepcional', args=[pk])


class TestEstornarSaidaExcepcionalView:
    def _url(self, pk):
        return reverse('estoque:estornar_saida_excepcional', args=[pk])

    def test_chefe_estorna_e_redireciona_para_detalhe(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Registro equivocado.'},
        )
        assert response.status_code == 302
        assert str(saida_registrada.pk) in response['Location']

    def test_superuser_estorna_e_redireciona(self, client, superuser, saida_registrada):
        client.force_login(superuser)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Override técnico.'},
        )
        assert response.status_code == 302
        assert str(saida_registrada.pk) in response['Location']

    def test_aux_recebe_403(self, client, aux_almoxarifado, saida_registrada):
        client.force_login(aux_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Tentativa.'},
        )
        assert response.status_code == 403

    def test_solicitante_recebe_403(self, client, solicitante, saida_registrada):
        client.force_login(solicitante)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Tentativa.'},
        )
        assert response.status_code == 403

    def test_anonimo_redirecionado_para_login(self, client, saida_registrada):
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Tentativa.'},
        )
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_pk_inexistente_retorna_404(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.post(self._url(999999), data={'justificativa': 'x'})
        assert response.status_code == 404

    def test_get_retorna_405(self, client, chefe_almoxarifado, saida_registrada):
        client.force_login(chefe_almoxarifado)
        response = client.get(self._url(saida_registrada.pk))
        assert response.status_code == 405

    def test_justificativa_vazia_redireciona_com_mensagem_erro(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': ''},
        )
        assert response.status_code == 302
        assert str(saida_registrada.pk) in response['Location']
        messages_list = list(response.wsgi_request._messages)
        assert any(m.tags == 'error' for m in messages_list)

    def test_saida_ja_estornada_redireciona_com_mensagem_warning(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        from apps.estoque.services import estornar_saida_excepcional

        estornar_saida_excepcional(
            ator_id=chefe_almoxarifado.pk,
            saida_id=saida_registrada.pk,
            justificativa='Primeiro.',
        )
        client.force_login(chefe_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Segundo.'},
        )
        assert response.status_code == 302
        assert str(saida_registrada.pk) in response['Location']
        messages_list = list(response.wsgi_request._messages)
        assert any(m.tags == 'warning' for m in messages_list)
        assert not any(m.tags == 'error' for m in messages_list)

    def test_estorno_nao_duplica_mensagem_no_detalhe(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        client.force_login(chefe_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Registro equivocado.'},
        )
        assert response.status_code == 302
        assert str(saida_registrada.pk) in response['Location']

        detalhe_response = client.get(response['Location'])
        assert detalhe_response.status_code == 200
        conteudo = detalhe_response.content.decode()
        mensagem = f'Saída {saida_registrada.numero_publico} estornada com sucesso.'
        assert conteudo.count(mensagem) == 1

    def test_conflito_dominio_mostra_warning_nao_error(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """Drift 6 (canônico): ConflitoDominio em estornar_saida_excepcional deve
        gerar messages.warning, nunca messages.error."""
        from unittest.mock import patch

        from apps.core.exceptions import ConflitoDominio

        client.force_login(chefe_almoxarifado)
        with patch(
            'apps.estoque.services.estornar_saida_excepcional',
            side_effect=ConflitoDominio('Já estornada'),
        ):
            response = client.post(
                self._url(saida_registrada.pk),
                data={'justificativa': 'Motivo'},
            )

        messages_list = list(response.wsgi_request._messages)
        assert any(m.tags == 'warning' for m in messages_list)
        assert not any(m.tags == 'error' for m in messages_list)

    def test_sem_htmx_post_valido_grava_o_estorno(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """Fallback sem JS: redirecionar para o lugar certo não basta.

        Sem esta metade, o teste passaria numa view que redireciona para o
        detalhe sem ter gravado nada — a mesma pergunta sem resposta que a
        issue trata, só que pela porta do fallback (ADR-0010).
        """
        from apps.estoque.models import EstadoSaidaExcepcional

        client.force_login(chefe_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Registro equivocado.'},
        )
        assert response.status_code == 302
        saida_registrada.refresh_from_db()
        assert saida_registrada.estado == EstadoSaidaExcepcional.ESTORNADA
        assert saida_registrada.estornado_em is not None

    def test_sem_htmx_post_invalido_nao_grava_nada(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        from apps.estoque.models import EstadoSaidaExcepcional

        client.force_login(chefe_almoxarifado)
        client.post(self._url(saida_registrada.pk), data={'justificativa': ''})
        saida_registrada.refresh_from_db()
        assert saida_registrada.estado == EstadoSaidaExcepcional.REGISTRADA
        assert saida_registrada.estornado_em is None

    def test_htmx_sucesso_devolve_204_com_hx_redirect(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """Sucesso via HTMX é PRG por cabeçalho, não 302 seguido pelo XHR.

        O modal faz `hx-post` com `hx-target="[data-modal-body]"` e
        `hx-swap="outerHTML"`: um 302 é seguido pelo próprio XHR, que recebe a
        página de detalhe inteira e a injeta dentro da caixa do modal.
        """
        client.force_login(chefe_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Registro equivocado.'},
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 204
        assert response['HX-Redirect'] == reverse(
            'estoque:detalhe_saida_excepcional', args=[saida_registrada.pk]
        )

    def test_htmx_erro_de_dominio_devolve_422_com_corpo_do_modal(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """Erro de domínio via HTMX mantém o modal de pé, sem página inteira."""
        client.force_login(chefe_almoxarifado)
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': ''},
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 422
        conteudo = response.content.decode()
        assert 'data-modal-body="estornar-saida"' in conteudo
        assert 'data-modal-erro' in conteudo
        # Não pode ter vindo página inteira dentro da caixa do modal.
        assert '<html' not in conteudo
        assert 'app-bar' not in conteudo

    def test_o_422_devolve_o_estorno_na_mesma_cor_em_que_ele_abriu(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """O 422 devolve o mesmo modal, e a cor da ação é parte dele.

        A view monta o corpo por conta própria — se ela ficar em `danger`, o
        modal que reabre com erro passa a ser um parente do que abriu: mesma
        ação, mesmo título, vermelho onde estava teal, e justamente no momento
        em que a pessoa está decidindo se repete a operação.
        """
        client.force_login(chefe_almoxarifado)
        conteudo = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': ''},
            HTTP_HX_REQUEST='true',
        ).content.decode('utf-8')

        assert 'bg-return-muted text-return-text' in conteudo
        assert PATH_DEVOLVER in conteudo
        assert 'bg-danger-muted' not in conteudo

        (confirmar,) = [
            atributos
            for _, atributos, _ in elementos(conteudo, 'button')
            if 'data-modal-confirm' in {nome for nome, _ in pares(atributos)}
        ]
        classe = atributo(confirmar, 'class')
        assert 'bg-return' in classe
        assert 'danger' not in classe, classe

    def test_o_422_conserva_o_progresso_e_o_foco_do_modal_que_abriu(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """`loading_label` e `corpo_com_campo_focavel` também são o mesmo modal.

        Os dois vêm do include em `detalhe_saida_excepcional.html` e a view monta
        o corpo do 422 por conta própria: omiti-los cai no default, e a segunda
        tentativa — a que a pessoa faz já tendo errado uma vez — perde o rótulo
        de progresso do botão e ganha uma parada de tabulação antes do
        `<textarea>` que o corpo já tem.
        """
        client.force_login(chefe_almoxarifado)
        conteudo = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': ''},
            HTTP_HX_REQUEST='true',
        ).content.decode('utf-8')

        (confirmar,) = [
            atributos
            for _, atributos, _ in elementos(conteudo, 'button')
            if 'data-modal-confirm' in {nome for nome, _ in pares(atributos)}
        ]
        assert atributo(confirmar, 'data-submit-loading-label') == 'Estornando…'

        rolaveis = [
            atributos
            for _, atributos, _ in elementos(conteudo, 'div')
            if 'overflow-y-auto' in (atributo(atributos, 'class') or '')
        ]
        assert rolaveis, 'corpo do 422 sem região rolável'
        for atributos in rolaveis:
            assert atributo(atributos, 'tabindex') is None
            assert atributo(atributos, 'aria-labelledby') is None

    def test_htmx_erro_preserva_justificativa_digitada(
        self, client, chefe_almoxarifado, saida_registrada
    ):
        """O 422 devolve a caixa aberta com o texto digitado, não em branco.

        É o que `recusar_requisicao_view` já faz com `motivo_recusa`. Sem isso a
        pessoa reescreve a justificativa a cada erro.
        """
        client.force_login(chefe_almoxarifado)
        from apps.estoque.services import estornar_saida_excepcional

        estornar_saida_excepcional(
            ator_id=chefe_almoxarifado.pk,
            saida_id=saida_registrada.pk,
            justificativa='Primeiro.',
        )
        response = client.post(
            self._url(saida_registrada.pk),
            data={'justificativa': 'Texto que não pode sumir.'},
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 422
        assert 'Texto que não pode sumir.' in response.content.decode()


class TestPreviewImportacaoScpiView:
    """Contrato HTTP de preview_importacao_scpi_view."""

    URL = '/estoque/importacao-scpi/pre-visualizacao/'

    def _csv_valido(
        self, codigo: str = '000.000.001', quantidade: str = '10.000'
    ) -> bytes:
        return f'CADPRO;DENOMINACAO;QUAN3\n{codigo};Teste;{quantidade}\n'.encode(
            'utf-8'
        )

    def test_nao_autenticado_redireciona_para_login(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_sem_permissao_retorna_403(self, client, aux_almoxarifado):
        """O limite é chefe de almoxarifado: o auxiliar não abre o preview."""
        client.force_login(aux_almoxarifado)
        resp = client.get(self.URL)
        assert resp.status_code == 403

    def test_superuser_get_retorna_200(self, client, superuser):
        client.force_login(superuser)
        resp = client.get(self.URL)
        assert resp.status_code == 200

    def test_chefe_almoxarifado_get_retorna_200(self, client, chefe_almoxarifado):
        """O chefe de almoxarifado é o dono do ritual de importação SCPI."""
        client.force_login(chefe_almoxarifado)
        resp = client.get(self.URL)
        assert resp.status_code == 200

    def test_post_csv_valido_retorna_200_com_preview(
        self, client, superuser, estoque_principal, material_scpi
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = self._csv_valido(material_scpi.codigo, '100.000')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        resp = client.post(self.URL, {'arquivo': arquivo})
        assert resp.status_code == 200
        assert (
            b'CADPRO' in resp.content or material_scpi.codigo.encode() in resp.content
        )

    def _preview_com_novos_e_divergencias(self, client, superuser, material_scpi):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n'
            f'{material_scpi.codigo};Teste;150.000\n'
            f'000.000.999;Material Novo;5.000\n'
        ).encode('utf-8')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        return client.post(self.URL, {'arquivo': arquivo}).content.decode()

    def _preview_de_arquivo_so_com_cabecalho(self, client, superuser):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        arquivo = SimpleUploadedFile(
            'vazio.csv', b'CADPRO;DENOMINACAO;QUAN3\n', content_type='text/csv'
        )
        return client.post(self.URL, {'arquivo': arquivo}).content.decode()

    def test_arquivo_so_com_cabecalho_nao_volta_em_silencio(
        self, client, superuser, estoque_principal
    ):
        """Enviar um CSV sem linhas de dados não pode parecer não ter feito nada.

        O template tinha um estado vazio para este caso, mas ele era inalcançável:
        o ramo de preview só é atingido com `linhas` truthy, então o `{% else %}`
        de dentro dele nunca renderizava. Na prática o POST caía de volta no
        formulário de upload, idêntico ao que a pessoa já estava vendo — sem
        alerta, sem foco, sem pista de que o arquivo foi lido e estava vazio.

        Num ritual recorrente feito por quem confia mais no papel que no
        software, uma tela que não reage é indistinguível de uma tela travada.
        """
        conteudo = self._preview_de_arquivo_so_com_cabecalho(client, superuser)

        assert 'linhas de dados' in conteudo
        assert 'Carregar arquivo CSV do SCPI' not in conteudo, (
            'voltou ao formulário de upload como se nada tivesse acontecido'
        )

    def test_arquivo_so_com_cabecalho_amarra_o_erro_ao_campo_de_retry(
        self, client, superuser, estoque_principal
    ):
        """Depois de um POST full-page o que anuncia é o foco, não live region.

        O caminho de erro do arquivo já tem o mecanismo montado — `autofocus`,
        `aria-invalid` e `aria-describedby` amarrando o texto ao campo. Reusá-lo
        é mais barato e mais acessível que inventar um quarto estado de tela.
        """
        conteudo = self._preview_de_arquivo_so_com_cabecalho(client, superuser)

        assert 'id="erro-arquivo-alerta"' in conteudo
        assert 'aria-describedby="erro-arquivo-alerta arquivo-retry-ajuda"' in conteudo
        assert 'autofocus' in conteudo

    def test_preview_nao_carrega_estado_vazio_inalcancavel(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """A caixa clonada à mão sai do arquivo, não vira include.

        Ela replicava as classes do `empty_state.html` sem usá-lo e carregava
        `text-text-disabled` (slate-400, 2.63:1 sobre branco, abaixo dos 4.5:1
        da WCAG 1.4.3). Trocá-la pelo componente manteria marcação que nunca
        renderiza; o certo é apagar e tratar o caso vazio onde ele de fato
        acontece.
        """
        conteudo = self._preview_com_novos_e_divergencias(
            client, superuser, material_scpi
        )

        assert 'border-dashed border-border-strong' not in conteudo

    def test_alerta_de_divergencia_mantem_variante_warning_e_role_status(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """O token âmbar e o anúncio não-assertivo são decisão de produto.

        Divergência é estado esperado da coexistência com o SCPI e a decisão é
        do chefe de almoxarifado — âmbar é exatamente "a decisão está com
        alguém". E no preview ela pede leitura, não interrupção: por isso o
        `role="status"` explícito, que sobrescreve o `alert` automático da
        variante. Sem este teste, nada impede uma passagem futura de "corrigir"
        qualquer um dos dois.
        """
        conteudo = self._preview_com_novos_e_divergencias(
            client, superuser, material_scpi
        )

        assert (
            'border-primary-border bg-primary-subtle text-primary-text-emphasis'
            in conteudo
        )
        assert 'border-warning-border bg-warning-subtle text-warning-text' in conteudo
        assert 'role="status"' in conteudo

    def test_preview_nao_declara_live_region_inerte(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """Live region só dispara com mudança.

        Os três `aria_live` passados a `alert.html` descreviam um anúncio que
        nunca aconteceu: o conteúdo já está presente no carregamento da
        resposta do POST. Sobra um só `aria-live`, o da barra de resumo, que
        não passa por `alert.html` e agora é o alvo do foco programático.
        """
        conteudo = self._preview_com_novos_e_divergencias(
            client, superuser, material_scpi
        )

        assert conteudo.count('aria-live=') == 1

    def test_resumo_do_preview_recebe_foco_no_retorno_do_upload(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """Depois de um POST full-page, o que anuncia é o foco, não a live region.

        Mesmo padrão GOV.UK de `components/error_summary.html`: `tabindex="-1"`
        mais foco no mount. O anel usa `focus:` e não `focus-visible:`, porque
        `focus-visible` não casa em foco programático que não veio do teclado.
        """
        conteudo = self._preview_com_novos_e_divergencias(
            client, superuser, material_scpi
        )

        assert 'tabindex="-1"' in conteudo
        assert 'x-init="$el.focus()"' in conteudo
        assert 'focus:ring-2' in conteudo

    def test_erro_de_arquivo_amarra_a_mensagem_ao_campo_de_retry(
        self, client, superuser
    ):
        """O `aria_live="assertive"` daqui também nunca anunciou nada.

        O mecanismo que funciona já estava meio pronto: o campo de retry tem
        `autofocus` e `aria-invalid`. Falta o texto do erro chegar junto — é o
        que o checklist do design system cobra, `aria-invalid` mais
        `aria-describedby`.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        arquivo = SimpleUploadedFile(
            'ruim.csv', b'COLUNA_ERRADA;OUTRA\nX;Y\n', content_type='text/csv'
        )
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert 'id="erro-arquivo-alerta"' in conteudo
        # O erro vem antes da ajuda de formato no `aria-describedby` (#164): o
        # que deu errado, e então o que se espera.
        assert 'aria-describedby="erro-arquivo-alerta arquivo-retry-ajuda"' in conteudo
        assert 'id="arquivo-retry-ajuda"' in conteudo
        assert 'CADPRO' in conteudo
        assert 'aria-live=' not in conteudo

    def test_botao_de_confirmar_e_descrito_pelos_alertas_da_importacao(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """Os alertas não estão na ordem de tabulação.

        Quem navega por teclado vai da barra de resumo direto ao botão de
        confirmar e nunca passa pelos dois alertas — ouviria as contagens e
        gravaria sem saber que a decisão é do chefe de almoxarifado. O
        `aria-describedby` põe a copy inteira no anúncio do próprio botão, no
        momento exato da decisão de gravar.

        O `id` fica no bloco que embrulha os alertas, não em cada um: o bloco
        existe sempre, os alertas são condicionais, e assim o
        `aria-describedby` nunca aponta para um `id` inexistente.
        """
        conteudo = self._preview_com_novos_e_divergencias(
            client, superuser, material_scpi
        )

        assert 'id="alertas-importacao"' in conteudo
        assert 'aria-describedby="alertas-importacao"' in conteudo

    def test_post_csv_com_dois_novos_flexiona_plural_corretamente(
        self, client, superuser, estoque_principal
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = (
            'CADPRO;DENOMINACAO;QUAN3\n'
            '000.000.997;Material Novo 1;5.000\n'
            '000.000.998;Material Novo 2;5.000\n'
        ).encode('utf-8')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        resp = client.post(self.URL, {'arquivo': arquivo})
        conteudo = resp.content.decode()

        assert 'serão criados' in conteudo
        assert 'seráão' not in conteudo

    def test_confirmar_importacao_passa_por_modal_e_nao_por_submit_nu(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """A gravação é irreversível e precisa de porta.

        Era a única escrita irreversível do sistema sem confirmação: um submit
        direto, com o botão depois de centenas de cartões. O PRODUCT.md declara
        que este fluxo exige "confirmação explícita antes de gravar", para gente
        que confia mais no papel do que no software.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = self._csv_valido(material_scpi.codigo, '150.000')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert 'data-modal-trigger="confirmar-importacao-scpi"' in conteudo
        assert '<dialog' in conteudo
        assert 'id="confirmar-importacao-scpi"' in conteudo
        assert 'Confirmar importação do SCPI?' in conteudo

    def test_preview_com_modal_de_confirmacao_nao_repete_nenhum_id(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """A tela herda o contrato de id de `components/modal.html` (#139).

        O estado sondado é o que emite o modal — preview com `pode_confirmar` —,
        e não o GET vazio, onde o `<dialog>` nem chega a ser renderizado.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = self._csv_valido(material_scpi.codigo, '150.000')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert 'id="confirmar-importacao-scpi"' in conteudo
        assert_sem_id_duplicado(conteudo)

    def test_dialog_do_scpi_e_nomeado_pelo_titulo_do_proprio_modal(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """O nome acessível do `<dialog>` é o `<h2>` do corpo do modal (#139)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = self._csv_valido(material_scpi.codigo, '150.000')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert 'confirmar-importacao-scpi-titulo' in ids_do_documento(conteudo)
        assert_dialogo_nomeado_pelo_proprio_titulo(conteudo)

    def test_modal_de_confirmacao_recapitula_os_numeros_a_gravar(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """No momento de confirmar, a lista já saiu da tela.

        A recapitulação repete os números em vez de mandar rolar de volta —
        inclusive os zeros, porque "nenhum material novo" é informação para quem
        confere contra o papel.

        Cada linha diz o que de fato grava (#164): material novo entra com o
        saldo do SCPI e esse saldo fica fora do histórico; divergência só
        registra alerta; "linhas lidas" é métrica de parsing e desce a metadado.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n'
            f'{material_scpi.codigo};Teste;150.000\n'
            f'000.000.999;Material Novo;5.000\n'
        ).encode('utf-8')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert 'material novo entra com o saldo do SCPI' in conteudo
        assert 'não gera movimentação no histórico' in conteudo
        assert 'divergência a registrar' in conteudo
        assert 'o saldo do WMS não muda' in conteudo
        assert '2 linhas lidas do arquivo' in conteudo

    def test_modal_quantifica_o_saldo_do_unico_material_novo(
        self, client, superuser, estoque_principal
    ):
        """ "1 material novo entra com o saldo do SCPI (5)" (#164).

        Com exatamente um material novo, a recapitulação diz qual saldo entra —
        o número já não está na tela no momento de confirmar.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = b'CADPRO;DENOMINACAO;QUAN3\n000.000.777;Bucha;5.000\n'
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert '1 material novo entra com o saldo do SCPI (5)' in conteudo
        assert 'não gera movimentação no histórico' in conteudo

    def test_recapitulacao_sem_material_novo_nao_deixa_dt_orfao(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """Zero não vira grupo de description list (#164).

        Só divergência: o "nenhum material novo" não tem consequência a
        descrever, logo não tem `<dd>` — e grupo sem `<dd>` viola o modelo de
        conteúdo da `<dl>` e some da árvore de acessibilidade como par. O texto
        continua na tela, como parágrafo.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        arquivo = SimpleUploadedFile(
            'teste.csv',
            self._csv_valido(material_scpi.codigo, '150.000'),
            content_type='text/csv',
        )
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert 'Nenhum material novo a criar' in conteudo
        assert 'divergência a registrar' in conteudo
        assert_todo_dt_tem_dd(conteudo)

    def test_recapitulacao_sem_divergencia_nao_deixa_dt_orfao(
        self, client, superuser, estoque_principal
    ):
        """O espelho do caso acima: só material novo, zero divergência (#164)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        arquivo = SimpleUploadedFile(
            'teste.csv',
            b'CADPRO;DENOMINACAO;QUAN3\n000.000.777;Bucha;5.000\n',
            content_type='text/csv',
        )
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()

        assert 'Nenhuma divergência a registrar' in conteudo
        assert 'material novo entra com o saldo do SCPI' in conteudo
        assert_todo_dt_tem_dd(conteudo)

    def test_arquivo_sem_efeito_nao_oferece_confirmacao(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """Arquivo que não muda nada não abre o modal de gravação definitiva (#164).

        Sem divergência e sem material novo não há escrita irreversível: gritar
        "A gravação não pode ser desfeita" para um no-op gasta o grito. O CTA
        some e um alerta informativo explica.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        # material_scpi tem saldo físico 100 — o arquivo bate com o WMS.
        csv_bytes = self._csv_valido(material_scpi.codigo, '100.000')
        arquivo = SimpleUploadedFile('igual.csv', csv_bytes, content_type='text/csv')
        resp = client.post(self.URL, {'arquivo': arquivo})
        conteudo = resp.content.decode()

        assert resp.context['pode_confirmar'] is False
        assert 'data-modal-trigger="confirmar-importacao-scpi"' not in conteudo
        assert 'id="confirmar-importacao-scpi"' not in conteudo
        assert 'Não há nada a importar' in conteudo

    def test_modal_do_scpi_nomeia_o_arquivo_na_linha_de_identidade(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """O registro aqui é o arquivo, e confirmar o errado grava saldo errado.

        O nome saiu do corpo e virou a linha de identidade do cabeçalho (#138) —
        é onde todo modal do sistema carrega o documento que está confirmando.
        Nos dois lugares seria a segunda grafia do mesmo dado.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = self._csv_valido(material_scpi.codigo, '150.000')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()
        dialogo = self._dialogo(conteudo, 'confirmar-importacao-scpi')

        assert 'data-modal-registro' in dialogo
        assert 'teste.csv' in dialogo
        assert dialogo.count('teste.csv') == 1

    def test_modal_do_scpi_nao_deixa_a_gravacao_definitiva_mais_apagada(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """A consequência irreversível não pode pesar menos que os números (#138).

        "A gravação não pode ser desfeita" era a `descricao` do cabeçalho, em
        `text-sm text-text-secondary`, enquanto as três contagens logo abaixo
        saíam em `text-base font-semibold`.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = self._csv_valido(material_scpi.codigo, '150.000')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        conteudo = client.post(self.URL, {'arquivo': arquivo}).content.decode()
        dialogo = self._dialogo(conteudo, 'confirmar-importacao-scpi')

        (classes,) = re.findall(
            r'<p(?=[^>]*data-modal-consequencia)(?=[^>]*class="([^"]*)")[^>]*>',
            dialogo,
        )
        assert 'font-semibold' in classes
        assert 'text-text-primary' in classes
        assert 'A gravação não pode ser desfeita.' in dialogo

    @staticmethod
    def _dialogo(html, modal_id):
        inicio = html.index(f'id="{modal_id}"')
        return html[inicio : html.index('</dialog>', inicio)]

    def test_preview_ordena_divergencia_e_novo_antes_de_ok(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """A tela existe para evidenciar delta.

        Na ordem do arquivo, conferir as divergências num CSV de centenas de
        linhas é caçar. O CSV entra na ordem inversa da desejada — "ok"
        primeiro, "divergente" por último — para que a asserção só passe se a
        ordenação de fato aconteceu.

        Os três status precisam existir de verdade: com só `novo` e `ok` o teste
        passa sem nunca exercitar a prioridade de `divergente`, que é a razão de
        a ordenação existir.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        # material_scpi tem saldo físico 100; material_scpi_critico tem 2.
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n'
            f'{material_scpi_critico.codigo};Saldo igual;2.000\n'
            f'000.000.999;Material Novo;5.000\n'
            f'{material_scpi.codigo};Saldo diferente;250.000\n'
        ).encode('utf-8')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        resp = client.post(self.URL, {'arquivo': arquivo})

        status_renderizados = [linha.status for linha in resp.context['linhas']]
        assert status_renderizados == ['divergente', 'novo', 'ok']

    def test_post_sem_arquivo_retorna_200_com_erro(self, client, superuser):
        client.force_login(superuser)
        resp = client.post(self.URL, {})
        assert resp.status_code == 200
        assert b'arquivo' in resp.content.lower() or b'obrigat' in resp.content.lower()

    def test_post_csv_invalido_retorna_200_com_mensagem_erro(
        self, client, superuser, estoque_principal
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_ruim = b'COLUNA_ERRADA;OUTRA\nX;Y\n'
        arquivo = SimpleUploadedFile('ruim.csv', csv_ruim, content_type='text/csv')
        resp = client.post(self.URL, {'arquivo': arquivo})
        assert resp.status_code == 200
        assert b'CADPRO' in resp.content or b'inv' in resp.content.lower()


class TestRecorteEAncoraDoPreviewScpi:
    """Recorte por status e âncoras da conferência SCPI (issue #162).

    Um CSV de 300 linhas rende ~61 telas e quase todas são linha "OK". Sem
    recorte, sem contagem que acompanhe a rolagem e sem barra de ação acima de
    `sm`, a conferência vira caçada. Os casos abaixo prendem as quatro decisões:
    o recorte vive na URL, as contagens descrevem o arquivo inteiro, os alertas
    chegam antes da lista e as duas barras ficam ancoradas.
    """

    URL = '/estoque/importacao-scpi/pre-visualizacao/'

    def _subir_csv(self, client, superuser, material_scpi, material_scpi_critico):
        """Sobe um CSV com um de cada status: divergente, novo e ok."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n'
            f'{material_scpi_critico.codigo};Saldo igual;2.000\n'
            f'000.000.999;Material Novo;5.000\n'
            f'{material_scpi.codigo};Saldo diferente;250.000\n'
        ).encode('utf-8')
        arquivo = SimpleUploadedFile('teste.csv', csv_bytes, content_type='text/csv')
        return client.post(self.URL, {'arquivo': arquivo})

    def test_preview_oferece_recorte_reusando_o_componente_de_chips(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """Os dois recortes que a conferência pede, no componente que já existe.

        Marcação nova para chip seria um segundo vocabulário de recorte na
        mesma aplicação; `components/filter_chips.html` já é o daqui.
        """
        conteudo = self._subir_csv(
            client, superuser, material_scpi, material_scpi_critico
        ).content.decode()

        assert 'id="filter-chips"' in conteudo
        assert 'Só divergências' in conteudo
        assert 'Só materiais novos' in conteudo
        assert 'status=divergente' in conteudo
        assert 'status=novo' in conteudo

    def test_recorte_e_estado_de_url_e_sobrevive_ao_link_compartilhado(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """Abrir a URL do recorte devolve o recorte, não a lista inteira.

        O clique no chip é um GET: a conferência é regerada do arquivo que a
        sessão guarda para a confirmação, e a URL — não um estado de
        JavaScript — decide o que a lista mostra (issue #152).
        """
        self._subir_csv(client, superuser, material_scpi, material_scpi_critico)

        resp = client.get(self.URL, {'status': 'divergente'})

        assert resp.status_code == 200
        assert [linha.status for linha in resp.context['linhas']] == ['divergente']
        assert material_scpi.codigo.encode() in resp.content
        assert material_scpi_critico.codigo.encode() not in resp.content

    def test_querystring_do_recorte_e_normalizada_por_302(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """Mesmo recorte lógico, mesma URL — senão o link deixa de ser recorte."""
        self._subir_csv(client, superuser, material_scpi, material_scpi_critico)

        resp = client.get(f'{self.URL}?status=novo&status=&status=divergente')

        assert resp.status_code == 302
        assert resp['Location'] == f'{self.URL}?status=divergente&status=novo'

    def test_status_ok_fica_fora_da_allowlist_e_nao_prende_o_recorte(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """`?status=ok` não é recorte: mostra o arquivo inteiro, sem trava.

        Não há chip "só OK" nem CTA de volta quando a lista não é vazia, então
        aceitar `ok` deixava o link compartilhado preso nesse recorte.
        """
        self._subir_csv(client, superuser, material_scpi, material_scpi_critico)

        resp = client.get(self.URL, {'status': 'ok'})

        assert resp.status_code == 200
        assert resp.context['tem_recorte'] is False
        assert resp.context['exibidas'] == resp.context['total'] == 3

    def test_contagens_descrevem_o_arquivo_inteiro_mesmo_sob_recorte(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """A barra de resumo é a âncora da conferência, não o rodapé da lista.

        Se as contagens encolhessem junto com o recorte, o número que a pessoa
        confere contra o papel mudaria de significado a cada clique de chip.
        """
        self._subir_csv(client, superuser, material_scpi, material_scpi_critico)

        resp = client.get(self.URL, {'status': 'divergente'})

        assert resp.context['total'] == 3
        assert resp.context['divergencias'] == 1
        assert resp.context['novos'] == 1
        assert resp.context['exibidas'] == 1

    def test_recorte_vazio_mostra_estado_vazio_com_saida(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """Recorte sem resultado precisa de porta de volta, não de lista muda."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n{material_scpi.codigo};Saldo igual;100.000\n'
        ).encode('utf-8')
        client.post(
            self.URL,
            {'arquivo': SimpleUploadedFile('teste.csv', csv_bytes, 'text/csv')},
        )

        conteudo = client.get(self.URL, {'status': 'novo'}).content.decode()

        assert 'Nenhuma linha neste recorte' in conteudo
        assert 'Ver todas as linhas' in conteudo

    def test_htmx_devolve_so_o_fragmento_com_push_url_e_chips_oob(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """Os chips vivem fora do alvo do swap — sem reemite OOB, congelam.

        Mesma regressão da #143: sem o `hx-swap-oob`, o estado ativo e a URL de
        alternância ficam presos na primeira renderização.
        """
        self._subir_csv(client, superuser, material_scpi, material_scpi_critico)

        resp = client.get(
            self.URL, {'status': 'divergente'}, headers={'hx-request': 'true'}
        )
        conteudo = resp.content.decode()

        assert resp['HX-Push-Url'] == f'{self.URL}?status=divergente'
        assert 'Importação SCPI — Pré-visualização' not in conteudo
        assert 'hx-swap-oob="true"' in conteudo
        assert 'hx-swap-oob="innerHTML:#resumo-recorte-preview"' in conteudo

    def test_get_sem_conferencia_pendente_volta_ao_formulario_de_upload(
        self, client, superuser
    ):
        """Sem arquivo na sessão o estado inicial da tela segue sendo o upload."""
        client.force_login(superuser)

        conteudo = client.get(self.URL).content.decode()

        assert 'Carregar arquivo CSV do SCPI' in conteudo
        assert 'id="filter-chips"' not in conteudo

    def test_barra_de_acao_fica_ancorada_em_todas_as_larguras(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """`sm:static` deixava o desktop — a cena real do ritual — sem barra.

        O botão de confirmar ficava depois de centenas de linhas exatamente na
        largura em que a conferência acontece.
        """
        conteudo = self._subir_csv(
            client, superuser, material_scpi, material_scpi_critico
        ).content.decode()

        assert 'sm:static' not in conteudo
        assert 'sm:sticky' in conteudo

    def test_barra_de_resumo_acompanha_a_rolagem_abaixo_da_barra_de_aplicacao(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """Sticky ancorado em `--app-bar-height` e no degrau `z-10` da escala.

        A barra de aplicação já ocupa o topo (`z-30`); a de resumo cola logo
        abaixo dela e fica acima do conteúdo, porém abaixo de popover ancorado
        (`z-20`) — a escala de empilhamento do DESIGN.md é fechada.
        """
        conteudo = self._subir_csv(
            client, superuser, material_scpi, material_scpi_critico
        ).content.decode()

        assert 'sticky top-[var(--app-bar-height)] z-10' in conteudo

    def test_alertas_qualificam_as_contagens_antes_da_lista(
        self, client, superuser, estoque_principal, material_scpi, material_scpi_critico
    ):
        """No rodapé, os dois alertas chegavam depois da decisão já tomada."""
        conteudo = self._subir_csv(
            client, superuser, material_scpi, material_scpi_critico
        ).content.decode()

        assert conteudo.index('id="alertas-importacao"') < conteudo.index(
            'id="resultados-preview-scpi"'
        )
        assert 'aria-describedby="alertas-importacao"' in conteudo


class TestConfirmarImportacaoScpiView:
    """Contrato HTTP de confirmar_importacao_scpi_view (POST) + sucesso_importacao_scpi_view (GET)."""

    URL_PREVIEW = '/estoque/importacao-scpi/pre-visualizacao/'
    URL = '/requisicoes/importacao-scpi/confirmar/'

    def _csv(self, cadpro: str = '000.888.001', quantidade: str = '10.000') -> bytes:
        return f'CADPRO;DENOMINACAO;QUAN3\n{cadpro};Teste;{quantidade}\n'.encode(
            'utf-8'
        )

    def _seed_session(self, client, superuser, csv_bytes: bytes):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(superuser)
        arquivo = SimpleUploadedFile('seed.csv', csv_bytes, content_type='text/csv')
        return client.post(self.URL_PREVIEW, {'arquivo': arquivo})

    def test_nao_autenticado_redireciona_para_login(self, client):
        resp = client.post(self.URL, {})
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_sem_permissao_retorna_403(self, client, aux_almoxarifado):
        """O limite é chefe de almoxarifado: o auxiliar não confirma."""
        client.force_login(aux_almoxarifado)
        resp = client.post(self.URL, {})
        assert resp.status_code == 403

    def test_chefe_almoxarifado_sem_session_retorna_200_com_erro(
        self, client, chefe_almoxarifado
    ):
        """A decisão sobre cada divergência é do chefe: ele confirma. Sem
        pré-visualização na sessão, cai no erro, não num 403."""
        client.force_login(chefe_almoxarifado)
        resp = client.post(self.URL, {})
        assert resp.status_code == 200

    def test_sem_session_retorna_200_com_erro(self, client, superuser):
        client.force_login(superuser)
        resp = client.post(self.URL, {})
        assert resp.status_code == 200
        assert (
            b'pr\xc3\xa9' in resp.content.lower()
            or b'upload' in resp.content.lower()
            or b'visualiza' in resp.content.lower()
            or b'novamente' in resp.content.lower()
        )

    def test_post_com_session_valida_redireciona_para_sucesso(
        self, client, superuser, estoque_principal
    ):
        csv_bytes = self._csv('000.888.010')
        self._seed_session(client, superuser, csv_bytes)
        resp = client.post(self.URL, {})
        assert resp.status_code == 302
        assert '/confirmada/' in resp['Location']

    def test_get_sucesso_retorna_200_com_metadados(
        self, client, superuser, estoque_principal
    ):
        csv_bytes = self._csv('000.888.011')
        self._seed_session(client, superuser, csv_bytes)
        redirect = client.post(self.URL, {})
        assert redirect.status_code == 302
        resp = client.get(redirect['Location'])
        assert resp.status_code == 200
        assert (
            b'sucesso' in resp.content.lower() or b'confirmad' in resp.content.lower()
        )

    def test_sucesso_lista_os_cadpros_divergentes_e_nao_so_a_contagem(
        self, client, superuser, estoque_principal, material_scpi
    ):
        """#161: a lista some com a sessão do preview se a tela não a mostrar."""
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n{material_scpi.codigo};Parafuso M6;130.000\n'
        ).encode('utf-8')
        self._seed_session(client, superuser, csv_bytes)
        redirect = client.post(self.URL, {})
        conteudo = client.get(redirect['Location']).content.decode()
        assert material_scpi.codigo in conteudo
        assert 'Divergências a acertar no SCPI' in conteudo
        assert 'Baixar CSV das divergências' in conteudo

    def test_sucesso_com_divergencia_tem_uma_unica_saida_primaria(
        self, client, superuser, estoque_principal, material_scpi
    ):
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n{material_scpi.codigo};Parafuso M6;130.000\n'
        ).encode('utf-8')
        self._seed_session(client, superuser, csv_bytes)
        redirect = client.post(self.URL, {})
        conteudo = client.get(redirect['Location']).content.decode()
        assert 'Ver a divergência' in conteudo
        # As outras três saídas continuam na tela, rebaixadas.
        assert 'Ver histórico de importações' in conteudo
        assert 'Ver catálogo de materiais' in conteudo
        assert 'Nova importação' in conteudo

    def test_sucesso_sem_divergencia_nao_renderiza_lista_nem_saida_primaria(
        self, client, superuser, estoque_principal, material_scpi
    ):
        csv_bytes = (
            f'CADPRO;DENOMINACAO;QUAN3\n{material_scpi.codigo};Parafuso M6;100.000\n'
        ).encode('utf-8')
        self._seed_session(client, superuser, csv_bytes)
        redirect = client.post(self.URL, {})
        conteudo = client.get(redirect['Location']).content.decode()
        assert 'Divergências a acertar no SCPI' not in conteudo
        assert 'Ver a divergência' not in conteudo
        assert 'Baixar CSV das divergências' not in conteudo

    def test_hash_duplicado_retorna_200_com_mensagem_erro(
        self, client, superuser, estoque_principal
    ):
        csv_bytes = self._csv('000.888.020')
        self._seed_session(client, superuser, csv_bytes)
        client.post(self.URL, {})

        self._seed_session(client, superuser, csv_bytes)
        resp = client.post(self.URL, {})
        assert resp.status_code == 200
        assert (
            b'duplicad' in resp.content.lower()
            or b'reimporta' in resp.content.lower()
            or b'j\xc3\xa1' in resp.content.lower()
        )

    def test_sem_htmx_post_valido_grava_a_importacao(
        self, client, superuser, estoque_principal
    ):
        from apps.estoque.models import ImportacaoSCPI

        self._seed_session(client, superuser, self._csv('000.888.070'))
        antes = ImportacaoSCPI.objects.count()
        resp = client.post(self.URL, {})
        assert resp.status_code == 302
        assert ImportacaoSCPI.objects.count() == antes + 1

    def test_sem_htmx_sem_preview_nao_grava_nada(self, client, superuser):
        from apps.estoque.models import ImportacaoSCPI

        client.force_login(superuser)
        antes = ImportacaoSCPI.objects.count()
        resp = client.post(self.URL, {})
        assert resp.status_code == 200
        assert ImportacaoSCPI.objects.count() == antes

    def _csv_divergente(self, material, quantidade_scpi: str) -> bytes:
        """CSV que discorda do saldo já gravado para `material` no WMS."""
        return (
            f'CADPRO;DENOMINACAO;QUAN3\n'
            f'{material.codigo};{material.nome};{quantidade_scpi}\n'
        ).encode('utf-8')

    def test_cta_das_divergencias_nomeia_verbo_e_contagem(
        self, client, superuser, estoque_principal
    ):
        """`"Ver as "|add:2` devolvia `""` e o rótulo saía como " divergências".

        O filtro `add` do Django tenta `int(value) + int(arg)` e, ao falhar,
        `value + arg`; com um `int` do outro lado a soma de string levanta
        TypeError e o filtro devolve `""` em silêncio. Justamente no botão que a
        #161 criou para entregar a lista ao chefe de almoxarifado.
        """
        from apps.estoque.models import Material, SaldoEstoque

        for i, cadpro in enumerate(('000.777.001', '000.777.002'), start=1):
            material = Material.objects.create(
                codigo=cadpro, nome=f'Material {i}', unidade='un'
            )
            SaldoEstoque.objects.create(
                material=material,
                estoque=estoque_principal,
                saldo_fisico=Decimal('100.000'),
                saldo_reservado=Decimal('0.000'),
            )

        csv_bytes = (
            'CADPRO;DENOMINACAO;QUAN3\n'
            '000.777.001;Material 1;90\n'
            '000.777.002;Material 2;80\n'
        ).encode('utf-8')
        self._seed_session(client, superuser, csv_bytes)
        resp = client.post(self.URL, {}, follow=True)
        html = resp.content.decode()
        assert 'Ver as 2 divergências' in html
        assert '> divergências<' not in html.replace('\n', '')

    def test_saldos_da_divergencia_nao_saem_com_virgula_de_milhar(
        self, client, superuser, estoque_principal
    ):
        """`820,000` em pt-BR se lê *oitocentos e vinte mil*."""
        from apps.estoque.models import Material, SaldoEstoque

        material = Material.objects.create(
            codigo='000.777.010', nome='Eletroduto', unidade='un'
        )
        SaldoEstoque.objects.create(
            material=material,
            estoque=estoque_principal,
            saldo_fisico=Decimal('820.000'),
            saldo_reservado=Decimal('0.000'),
        )
        self._seed_session(client, superuser, self._csv_divergente(material, '750'))
        resp = client.post(self.URL, {}, follow=True)
        html = resp.content.decode()
        assert '820,000' not in html
        assert '750,000' not in html

    def test_htmx_sucesso_devolve_204_com_hx_redirect(
        self, client, superuser, estoque_principal
    ):
        """A única escrita irreversível declarada do sistema não pode terminar
        com a página de sucesso injetada dentro da caixa do modal."""
        from django.urls import reverse

        from apps.estoque.models import ImportacaoSCPI

        self._seed_session(client, superuser, self._csv('000.888.040'))
        resp = client.post(self.URL, {}, HTTP_HX_REQUEST='true')
        assert resp.status_code == 204
        importacao = ImportacaoSCPI.objects.latest('pk')
        assert resp['HX-Redirect'] == reverse(
            'estoque:sucesso_importacao_scpi', kwargs={'pk': importacao.pk}
        )

    def test_htmx_sem_preview_na_sessao_devolve_422(self, client, superuser):
        """Segunda tentativa é o pior caso: a sessão do preview já foi limpa e a
        pessoa fica com duas evidências contraditórias, ambas dentro da caixa."""
        client.force_login(superuser)
        resp = client.post(self.URL, {}, HTTP_HX_REQUEST='true')
        assert resp.status_code == 422
        conteudo = resp.content.decode()
        assert 'data-modal-body="confirmar-importacao-scpi"' in conteudo
        assert 'data-modal-erro' in conteudo
        assert 'pré-visualização ativa' in conteudo
        assert '<html' not in conteudo

    def test_htmx_hash_duplicado_devolve_422(
        self, client, superuser, estoque_principal
    ):
        csv_bytes = self._csv('000.888.050')
        self._seed_session(client, superuser, csv_bytes)
        client.post(self.URL, {})

        self._seed_session(client, superuser, csv_bytes)
        resp = client.post(self.URL, {}, HTTP_HX_REQUEST='true')
        assert resp.status_code == 422
        conteudo = resp.content.decode()
        assert 'data-modal-body="confirmar-importacao-scpi"' in conteudo
        assert 'duplicad' in conteudo.lower() or 'já' in conteudo.lower()
        assert '<html' not in conteudo

    def test_copy_do_422_nao_diverge_do_render_inicial(
        self, client, superuser, estoque_principal
    ):
        """Título e descrição do modal não podem mudar no 422 (#135).

        O render inicial do modal é a própria resposta do POST de upload em
        `URL_PREVIEW` — é ali, com `linhas` no contexto, que
        `components/modal.html` é incluído pela primeira vez.
        """
        from apps.core.tests.contrato_modal import assert_copy_nao_diverge

        csv_bytes = self._csv('000.888.090')
        inicial = self._seed_session(client, superuser, csv_bytes)
        client.post(self.URL, {})

        self._seed_session(client, superuser, csv_bytes)
        resp = client.post(self.URL, {}, HTTP_HX_REQUEST='true')

        assert resp.status_code == 422
        assert_copy_nao_diverge(
            resp,
            html_inicial=inicial.content.decode(),
            modal_id='confirmar-importacao-scpi',
        )

    def test_htmx_sem_estoque_ativo_devolve_422(
        self, client, superuser, estoque_principal
    ):
        """A fixture `estoque_principal` é o que faz este teste testar algo.

        Sem ela não há `Estoque` no banco, o preview sai cedo sem semear a
        sessão, e o 422 vem do ramo "nenhuma pré-visualização ativa" — ou seja,
        uma cópia do teste de cima, com o ramo de estoque inativo sem cobertura
        nenhuma. É por isso que a asserção de texto abaixo importa: sem ela os
        três ramos de `_erro()` são indistinguíveis entre si.
        """
        from apps.estoque.models import Estoque

        self._seed_session(client, superuser, self._csv('000.888.060'))
        Estoque.objects.update(ativo=False)
        resp = client.post(self.URL, {}, HTTP_HX_REQUEST='true')
        assert resp.status_code == 422
        conteudo = resp.content.decode()
        assert 'data-modal-body="confirmar-importacao-scpi"' in conteudo
        assert 'estoque ativo' in conteudo

    def test_get_sucesso_usa_components_alert_com_aria(
        self, client, superuser, estoque_principal
    ):
        csv_bytes = self._csv('000.888.030')
        self._seed_session(client, superuser, csv_bytes)
        redirect = client.post(self.URL, {})
        resp = client.get(redirect['Location'])
        conteudo = resp.content.decode()

        assert 'border-success-border' in conteudo
        assert 'bg-success-subtle' in conteudo
        assert 'role="status"' in conteudo
        # `role="status"` já implica aria-live polido; declarar os dois fazia o
        # leitor de tela anunciar duas vezes. `aria_live` saiu do alert na #127.
        assert 'aria-live=' not in conteudo

    def test_hash_duplicado_usa_components_alert_com_aria(
        self, client, superuser, estoque_principal
    ):
        csv_bytes = self._csv('000.888.031')
        self._seed_session(client, superuser, csv_bytes)
        client.post(self.URL, {})

        self._seed_session(client, superuser, csv_bytes)
        resp = client.post(self.URL, {})
        conteudo = resp.content.decode()

        assert 'border-danger-border' in conteudo
        assert 'bg-danger-subtle' in conteudo
        assert 'role="alert"' in conteudo
        # `role="alert"` já é assertivo — a combinação era redundante (#127).
        assert 'aria-live=' not in conteudo

    def test_get_nao_permitido_retorna_405(self, client, superuser):
        client.force_login(superuser)
        resp = client.get(self.URL)
        assert resp.status_code == 405


class TestHistoricoImportacoesScpiView:
    """Contrato HTTP de historico_importacoes_scpi_view."""

    URL = '/estoque/importacao-scpi/historico/'

    def test_nao_autenticado_redireciona_para_login(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_sem_permissao_retorna_403(self, client, solicitante):
        client.force_login(solicitante)
        resp = client.get(self.URL)
        assert resp.status_code == 403

    def test_superuser_get_retorna_200(self, client, superuser):
        client.force_login(superuser)
        resp = client.get(self.URL)
        assert resp.status_code == 200

    def test_chefe_almoxarifado_get_retorna_200(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        resp = client.get(self.URL)
        assert resp.status_code == 200

    def test_post_retorna_405(self, client, superuser):
        client.force_login(superuser)
        resp = client.post(self.URL, {})
        assert resp.status_code == 405

    def test_lista_vazia_retorna_200(self, client, superuser):
        client.force_login(superuser)
        resp = client.get(self.URL)
        assert resp.status_code == 200

    def test_h1_e_title_repetem_o_rotulo_da_navegacao(self, client, superuser):
        """Rótulo do link tem de ser o rótulo do destino (issue #160).

        O H1 dizia "Importação SCPI — Histórico" enquanto o item de nav diz
        "Histórico de importações SCPI": quem clica perde a confirmação de que
        chegou no lugar certo. A fonte única do rótulo é `NAVEGACAO`, em
        `apps/core/templatetags/core_tags.py` — o teste lê de lá em vez de
        repetir a string, para que renomear na nav quebre aqui.
        """
        from apps.core.templatetags.core_tags import NAVEGACAO

        rotulo = next(
            item['rotulo']
            for secao in NAVEGACAO
            for item in secao['itens']
            if item['url_name'] == 'estoque:historico_importacoes_scpi'
        )
        client.force_login(superuser)
        html = client.get(self.URL).content.decode()
        assert f'>{rotulo}</h1>' in html
        assert f'<title>{rotulo} — WMS-SAEP</title>' in html
        assert 'Importação SCPI — Histórico' not in html

    def test_nova_importacao_aparece_para_quem_pode_importar(
        self, client, superuser, chefe_almoxarifado
    ):
        """O chefe de almoxarifado é o dono do ritual: vê o histórico e a ação
        "Nova importação". O botão continua derivando de
        `pode_visualizar_preview_scpi` para sumir se o histórico abrir para um
        papel que só consulta.
        """
        client.force_login(superuser)
        html_super = client.get(self.URL).content.decode()
        assert 'Nova importação' in html_super

        client.force_login(chefe_almoxarifado)
        html_chefe = client.get(self.URL).content.decode()
        assert 'Nova importação' in html_chefe
        assert '/estoque/importacao-scpi/pre-visualizacao/' in html_chefe

    def test_lista_vazia_usa_o_componente_de_estado_vazio(self, client, superuser):
        """Frase cinza solta era o estado vazio fora do componente — as outras
        seis listagens usam `empty_state.html`."""
        client.force_login(superuser)
        html = client.get(self.URL).content.decode()
        assert 'Nenhuma importação registrada' in html
        assert 'border-dashed' in html

    def test_exibe_metadados_da_importacao(self, client, superuser, estoque_principal):
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        ImportacaoSCPI.objects.create(
            arquivo_nome='relatorio.csv',
            arquivo_hash='e' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
            total_linhas=10,
            total_novos=2,
            total_divergentes=3,
        )
        client.force_login(superuser)
        resp = client.get(self.URL)
        assert resp.status_code == 200
        assert b'relatorio.csv' in resp.content

    def test_historico_pagina_em_vez_de_carregar_tudo(
        self, client, superuser, estoque_principal
    ):
        """A importação SCPI é ritual recorrente: o histórico só cresce. A
        contagem também vem do paginator agora — o `|length` anterior
        materializava o queryset inteiro só para exibir o número.
        """
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI
        from apps.estoque.views import PAGINA_IMPORTACOES_SCPI_TAMANHO

        total = PAGINA_IMPORTACOES_SCPI_TAMANHO + 2
        for i in range(total):
            ImportacaoSCPI.objects.create(
                arquivo_nome=f'scpi-{i}.csv',
                arquivo_hash=f'{i:064d}',
                importado_por=superuser,
                estoque=estoque_principal,
                status=StatusImportacaoSCPI.CONCLUIDA,
            )

        client.force_login(superuser)
        resp = client.get(self.URL)
        page_obj = resp.context['page_obj']
        conteudo = resp.content.decode()

        assert page_obj.paginator.count == total
        assert len(resp.context['importacoes']) == PAGINA_IMPORTACOES_SCPI_TAMANHO
        assert 'Paginação do histórico de importações SCPI' in conteudo
        assert f'{total} importações registradas' in conteudo

    def test_nao_expoe_csv_bruto(self, client, superuser, estoque_principal):
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        ImportacaoSCPI.objects.create(
            arquivo_nome='bruto.csv',
            arquivo_hash='f' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )
        client.force_login(superuser)
        resp = client.get(self.URL)
        assert b'conteudo_csv' not in resp.content

    def test_renderiza_cartoes_com_metadados(
        self, client, superuser, estoque_principal
    ):
        """Esta tela não tinha renderização em cartões e ganhou uma quando as
        tabelas saíram do sistema — sem ela, ficaria sem listagem nenhuma.
        """
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        ImportacaoSCPI.objects.create(
            arquivo_nome='relatorio.csv',
            arquivo_hash='a' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )
        client.force_login(superuser)
        conteudo = client.get(self.URL).content.decode()
        assert '<article class="relative rounded-xl border border-border' in conteudo
        # A ação do cartão passou a ser navegação para o detalhe (#161), e não
        # mais o download do CSV: por isso ele volta a marcar `data-cartao-link`
        # no título. O botão de download continua explícito ao lado — cartão que
        # baixa arquivo ao ser clicado seria surpresa, não conveniência, e é
        # justamente por isso que o alvo do cartão é o detalhe.
        # `(?![\]:])` separa o atributo das ocorrências dentro dos seletores
        # `has-[a[data-cartao-link]]` que o chrome imprime em todo <article>.
        assert re.search(r'data-cartao-link(?![\]:])', conteudo)
        assert 'relatorio.csv' in conteudo
        assert 'Concluída' in conteudo
        assert '<table' not in conteudo

    def test_listagem_nao_usa_contentor_de_scroll_horizontal(
        self, client, superuser, estoque_principal
    ):
        """Antes a tabela ficava num wrapper `overflow-x-auto` que rolava em
        qualquer janela de desktop não maximizada. O cartão dispensa o wrapper.
        """
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        ImportacaoSCPI.objects.create(
            arquivo_nome='relatorio.csv',
            arquivo_hash='b' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )
        client.force_login(superuser)
        conteudo = client.get(self.URL).content.decode()
        assert 'overflow-x-auto' not in conteudo

    def test_exibe_link_de_download_quando_ha_arquivo(
        self, client, settings, tmp_path, superuser, estoque_principal
    ):
        from django.core.files.base import ContentFile

        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        settings.MEDIA_ROOT = str(tmp_path)
        importacao = ImportacaoSCPI.objects.create(
            arquivo_nome='com_arquivo.csv',
            arquivo=ContentFile(b'CADPRO;DENOMINACAO;QUAN3\n', name='com_arquivo.csv'),
            arquivo_hash='b' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )
        client.force_login(superuser)
        resp = client.get(self.URL)
        url_download = f'/estoque/importacao-scpi/{importacao.pk}/arquivo/'
        assert url_download.encode() in resp.content
        # Nome acessível distingue as linhas: "Baixar" sozinho se repete na coluna.
        # "enviado" desde #161: o detalhe passou a oferecer um segundo CSV, o das
        # divergências que o WMS concluiu do arquivo.
        assert b'aria-label="Baixar CSV enviado de com_arquivo.csv"' in resp.content

    def test_nao_exibe_link_quando_importacao_legada(
        self, client, superuser, estoque_principal
    ):
        """Importação anterior ao arquivamento não ganha link morto."""
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        importacao = ImportacaoSCPI.objects.create(
            arquivo_nome='legada.csv',
            arquivo_hash='c' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )
        client.force_login(superuser)
        resp = client.get(self.URL)
        url_download = f'/estoque/importacao-scpi/{importacao.pk}/arquivo/'
        assert url_download.encode() not in resp.content

    def test_status_nao_mapeado_grita_em_vez_de_cinza_plausivel(
        self, client, superuser, estoque_principal
    ):
        """Decisão A-1 da issue #122: status fora do enum passava pelo
        `{% else %}` antigo e virava um badge cinza plausível. O
        `{% else %}` novo repassa o valor sob o prefixo `desconhecida:` e
        deixa o fallback vermelho do badge.html gritar.
        """
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        importacao = ImportacaoSCPI.objects.create(
            arquivo_nome='status-invalido.csv',
            arquivo_hash='d' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )
        ImportacaoSCPI.objects.filter(pk=importacao.pk).update(status='invalido')
        client.force_login(superuser)
        conteudo = client.get(self.URL).content.decode()
        assert 'Indisponível' in conteudo
        assert 'data-badge-variant="desconhecida:invalido"' in conteudo

    def test_status_cancel_colide_mas_gruda_no_fallback(
        self, client, superuser, estoque_principal
    ):
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        importacao = ImportacaoSCPI.objects.create(
            arquivo_nome='status-cancel.csv',
            arquivo_hash='9' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )
        ImportacaoSCPI.objects.filter(pk=importacao.pk).update(status='cancel')
        client.force_login(superuser)
        conteudo = client.get(self.URL).content.decode()
        assert 'Indisponível' in conteudo
        assert 'bg-cancel-muted' not in conteudo

    def test_status_conhecido_mantem_variante_de_hoje(
        self, client, superuser, estoque_principal
    ):
        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        ImportacaoSCPI.objects.create(
            arquivo_nome='com-alertas.csv',
            arquivo_hash='8' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.COM_ALERTAS,
        )
        client.force_login(superuser)
        conteudo = client.get(self.URL).content.decode()
        # Espaço final: `bg-warning-muted` é prefixo de `bg-warning-muted-strong`
        # (variante amber-strong do mesmo badge) — sem o espaço o teste passaria
        # mesmo que a variante trocasse silenciosamente para a mais forte.
        assert 'bg-warning-muted ' in conteudo
        assert 'Com alertas' in conteudo


class TestBaixarArquivoImportacaoScpiView:
    """Contrato HTTP de baixar_arquivo_importacao_scpi_view."""

    CSV = b'CADPRO;DENOMINACAO;QUAN3\n000.111.222;Parafuso M6;010.000\n'

    def _url(self, pk: int) -> str:
        return f'/estoque/importacao-scpi/{pk}/arquivo/'

    def _importacao(
        self,
        superuser,
        estoque_principal,
        *,
        arquivo_nome='relatorio.csv',
        com_arquivo=True,
    ):
        from django.core.files.base import ContentFile

        from apps.estoque.models import ImportacaoSCPI, StatusImportacaoSCPI

        return ImportacaoSCPI.objects.create(
            arquivo_nome=arquivo_nome,
            arquivo=ContentFile(self.CSV, name='arquivado.csv') if com_arquivo else '',
            arquivo_hash='1' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=StatusImportacaoSCPI.CONCLUIDA,
        )

    def _corpo(self, resp) -> bytes:
        return b''.join(resp.streaming_content)

    def test_nao_autenticado_get_redireciona_para_login(
        self, client, settings, tmp_path, superuser, estoque_principal
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(superuser, estoque_principal)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_nao_autenticado_post_redireciona_para_login(
        self, client, settings, tmp_path, superuser, estoque_principal
    ):
        """`login_required` por fora de `require_http_methods`: anônimo vê login, não 405."""
        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(superuser, estoque_principal)
        resp = client.post(self._url(importacao.pk), {})
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_post_autenticado_retorna_405(
        self, client, settings, tmp_path, superuser, estoque_principal
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(superuser)
        resp = client.post(self._url(importacao.pk), {})
        assert resp.status_code == 405

    def test_solicitante_retorna_403(
        self, client, settings, tmp_path, solicitante, superuser, estoque_principal
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(solicitante)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 403

    def test_chefe_almoxarifado_baixa_o_csv(
        self,
        client,
        settings,
        tmp_path,
        chefe_almoxarifado,
        superuser,
        estoque_principal,
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(chefe_almoxarifado)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 200
        assert resp['Content-Disposition'] == 'attachment; filename="relatorio.csv"'
        assert self._corpo(resp) == self.CSV

    def test_content_disposition_usa_basename_do_nome_original(
        self, client, settings, tmp_path, superuser, estoque_principal
    ):
        """Nome com componentes de caminho não vaza para o header."""
        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(
            superuser, estoque_principal, arquivo_nome='subdir/relatorio.csv'
        )
        client.force_login(superuser)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 200
        assert resp['Content-Disposition'] == 'attachment; filename="relatorio.csv"'

    def test_pk_inexistente_retorna_404(self, client, superuser):
        client.force_login(superuser)
        resp = client.get(self._url(999999))
        assert resp.status_code == 404

    def test_importacao_sem_arquivo_retorna_404(
        self, client, settings, tmp_path, superuser, estoque_principal
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(superuser, estoque_principal, com_arquivo=False)
        client.force_login(superuser)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 404

    def test_arquivo_removido_do_storage_retorna_404(
        self, client, settings, tmp_path, superuser, estoque_principal
    ):
        """Sem abrir o arquivo antes do FileResponse, isto estouraria 500 no meio do stream."""
        from pathlib import Path

        settings.MEDIA_ROOT = str(tmp_path)
        importacao = self._importacao(superuser, estoque_principal)
        Path(importacao.arquivo.path).unlink()
        client.force_login(superuser)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 404


class _BaseImportacaoComDivergencias:
    """Monta uma importação com divergências gravadas, sem passar pelo CSV."""

    def _importacao(self, superuser, estoque_principal, *, divergentes=2):
        from apps.estoque.models import (
            ImportacaoSCPI,
            LinhaDivergenteSCPI,
            StatusImportacaoSCPI,
        )

        importacao = ImportacaoSCPI.objects.create(
            arquivo_nome='saldo_scpi.csv',
            arquivo_hash='e' * 64,
            importado_por=superuser,
            estoque=estoque_principal,
            status=(
                StatusImportacaoSCPI.COM_ALERTAS
                if divergentes
                else StatusImportacaoSCPI.CONCLUIDA
            ),
            total_linhas=10,
            total_novos=0,
            total_divergentes=divergentes,
        )
        for i in range(divergentes):
            LinhaDivergenteSCPI.objects.create(
                importacao=importacao,
                cadpro=f'000.777.{i:03d}',
                denominacao=f'Parafuso sextavado {i}',
                saldo_wms=10,
                saldo_scpi=13,
                delta=3,
            )
        return importacao


class TestDetalheImportacaoScpiView(_BaseImportacaoComDivergencias):
    """Contrato HTTP de detalhe_importacao_scpi_view (#161)."""

    def _url(self, pk: int) -> str:
        return f'/estoque/importacao-scpi/{pk}/'

    def test_nao_autenticado_redireciona_para_login(
        self, client, superuser, estoque_principal
    ):
        importacao = self._importacao(superuser, estoque_principal)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_sem_permissao_retorna_403(
        self, client, superuser, solicitante, estoque_principal
    ):
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(solicitante)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 403

    def test_chefe_almoxarifado_acessa(
        self, client, superuser, chefe_almoxarifado, estoque_principal
    ):
        """A conferência no SCPI é dele; a policy do detalhe é a do histórico."""
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(chefe_almoxarifado)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 200

    def test_pk_inexistente_retorna_404(self, client, superuser):
        client.force_login(superuser)
        resp = client.get(self._url(999999))
        assert resp.status_code == 404

    def test_post_retorna_405(self, client, superuser, estoque_principal):
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(superuser)
        resp = client.post(self._url(importacao.pk), {})
        assert resp.status_code == 405

    def test_lista_os_cadpros_divergentes(self, client, superuser, estoque_principal):
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(superuser)
        conteudo = client.get(self._url(importacao.pk)).content.decode()
        assert '000.777.000' in conteudo
        assert '000.777.001' in conteudo
        assert 'Parafuso sextavado 0' in conteudo

    def test_sem_divergencia_nao_renderiza_lista_nem_botao_de_csv(
        self, client, superuser, estoque_principal
    ):
        importacao = self._importacao(superuser, estoque_principal, divergentes=0)
        client.force_login(superuser)
        conteudo = client.get(self._url(importacao.pk)).content.decode()
        assert 'Baixar CSV das divergências' not in conteudo
        assert 'Nenhuma divergência' in conteudo


class TestBaixarDivergenciasImportacaoScpiView(_BaseImportacaoComDivergencias):
    """Contrato HTTP da exportação da lista concluída pelo WMS (#161)."""

    def _url(self, pk: int) -> str:
        return f'/estoque/importacao-scpi/{pk}/divergencias/'

    def test_nao_autenticado_redireciona_para_login(
        self, client, superuser, estoque_principal
    ):
        importacao = self._importacao(superuser, estoque_principal)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 302
        assert '/login/' in resp['Location']

    def test_sem_permissao_retorna_403(
        self, client, superuser, solicitante, estoque_principal
    ):
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(solicitante)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 403

    def test_pk_inexistente_retorna_404(self, client, superuser):
        client.force_login(superuser)
        resp = client.get(self._url(999999))
        assert resp.status_code == 404

    def test_post_retorna_405(self, client, superuser, estoque_principal):
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(superuser)
        resp = client.post(self._url(importacao.pk), {})
        assert resp.status_code == 405

    def test_devolve_csv_com_cabecalho_e_linhas(
        self, client, chefe_almoxarifado, superuser, estoque_principal
    ):
        importacao = self._importacao(superuser, estoque_principal)
        client.force_login(chefe_almoxarifado)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 200
        assert resp['Content-Type'].startswith('text/csv')
        assert (
            resp['Content-Disposition']
            == f'attachment; filename="divergencias-importacao-{importacao.pk}.csv"'
        )
        texto = resp.content.decode('utf-8-sig')
        linhas = texto.splitlines()
        assert linhas[0] == 'CADPRO;DENOMINACAO;SALDO_WMS;SALDO_SCPI;DELTA'
        assert linhas[1] == '000.777.000;Parafuso sextavado 0;10.000;13.000;3.000'
        assert len(linhas) == 3

    def test_bom_utf8_preserva_acento_na_planilha(
        self, client, superuser, estoque_principal
    ):
        """Sem BOM, o Excel pt-BR lê UTF-8 como Latin-1 e estraga a denominação."""
        importacao = self._importacao(superuser, estoque_principal, divergentes=0)
        client.force_login(superuser)
        resp = client.get(self._url(importacao.pk))
        assert resp.content.startswith(b'\xef\xbb\xbf')

    def test_importacao_sem_divergencia_devolve_so_o_cabecalho(
        self, client, superuser, estoque_principal
    ):
        importacao = self._importacao(superuser, estoque_principal, divergentes=0)
        client.force_login(superuser)
        resp = client.get(self._url(importacao.pk))
        assert resp.status_code == 200
        assert resp.content.decode('utf-8-sig').splitlines() == [
            'CADPRO;DENOMINACAO;SALDO_WMS;SALDO_SCPI;DELTA'
        ]


URL_MATERIAIS = reverse('estoque:lista_materiais')


class TestListaMateriaisView:
    def test_ordena_pelo_codigo_que_o_cartao_destaca(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """O cartão imprime o código como `<h2>` semibold e o nome como linha
        secundária em cinza. Ordenar por nome deixava a única coluna em destaque
        aparentemente embaralhada — a chave de ordenação tem de ser a que a
        hierarquia visual promete."""
        from apps.estoque.models import Material, SaldoEstoque

        for codigo, nome in (
            ('MAT-900', 'Areia média lavada'),
            ('MAT-100', 'Zinco em pó'),
            ('MAT-500', 'Cimento Portland'),
        ):
            material = Material.objects.create(codigo=codigo, nome=nome, unidade='un')
            SaldoEstoque.objects.create(
                material=material,
                estoque=estoque_principal,
                saldo_fisico=Decimal('1.000'),
                saldo_reservado=Decimal('0.000'),
            )

        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MATERIAIS).content.decode('utf-8')
        posicoes = [html.index(c) for c in ('MAT-100', 'MAT-500', 'MAT-900')]
        assert posicoes == sorted(posicoes)

    def test_material_inativo_recebe_carimbo(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """`Material.ativo` é estado de domínio — material inativo não entra em
        requisição nova nem em saída excepcional. O catálogo é a única tela que
        lista material, e o cartão saía idêntico ao de um material em uso."""
        from apps.estoque.models import Material, SaldoEstoque

        material = Material.objects.create(
            codigo='MAT-800', nome='Lâmpada descontinuada', unidade='un', ativo=False
        )
        SaldoEstoque.objects.create(
            material=material,
            estoque=estoque_principal,
            saldo_fisico=Decimal('0.000'),
            saldo_reservado=Decimal('0.000'),
        )
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MATERIAIS).content.decode('utf-8')
        assert 'Inativo' in html
        assert 'aria-label="Material inativo"' in html

    def test_material_ativo_nao_recebe_carimbo_de_inativo(
        self, client, chefe_almoxarifado, material_disponivel
    ):
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MATERIAIS).content.decode('utf-8')
        assert 'aria-label="Material inativo"' not in html

    def test_chefe_almox_acessa_lista(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS)
        assert response.status_code == 200

    def test_aux_almox_acessa_lista(self, client, aux_almoxarifado):
        client.force_login(aux_almoxarifado)
        response = client.get(URL_MATERIAIS)
        assert response.status_code == 200

    def test_superuser_acessa_lista(self, client, superuser):
        client.force_login(superuser)
        response = client.get(URL_MATERIAIS)
        assert response.status_code == 200

    def test_solicitante_acessa_lista(self, client, solicitante):
        # Consultar materiais é permitido para todos os papéis ativos (matriz-permissoes.md).
        client.force_login(solicitante)
        response = client.get(URL_MATERIAIS)
        assert response.status_code == 200

    def test_usuario_inativo_redirecionado_para_login(self, client, usuario_inativo):
        # Django ModelBackend trata is_active=False como não-autenticado;
        # @login_required redireciona para login (USR-01).
        client.force_login(usuario_inativo)
        response = client.get(URL_MATERIAIS)
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_anonimo_redirecionado_para_login(self, client):
        response = client.get(URL_MATERIAIS)
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_contexto_contem_saldos(
        self, client, chefe_almoxarifado, material_disponivel, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS)
        assert 'saldos' in response.context

    def test_contexto_contem_busca_vazia_por_padrao(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS)
        assert response.context['busca'] == ''

    def test_nenhum_material_cadastrado_exibe_empty_state_dashed(
        self, client, chefe_almoxarifado
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS)
        html = response.content.decode()
        assert 'border-dashed border-border-strong' in html
        assert 'border-slate-200 bg-white p-8' not in html
        assert 'Nenhum material no cat' in html

    def test_catalogo_vazio_diz_por_onde_o_material_entra(
        self, client, chefe_almoxarifado
    ):
        """Estado vazio de primeiro uso sem próxima ação é beco sem saída.

        Não existe cadastro manual de material: o catálogo é alimentado pela
        importação do SCPI. Dizer só "nenhum material" deixa quem abriu a tela
        sem saber se falta dado, falta permissão ou falta um passo — e o passo
        existe. A frase nomeia a rota sem virar link, porque importar é
        privilégio do chefe de almoxarifado e o componente não decide permissão.
        """
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MATERIAIS).content.decode()
        # A navegação lateral também cita a importação SCPI: recortar a caixa do
        # estado vazio é o que separa "a tela diz" de "a tela tem um link no menu".
        inicio = html.index('border-dashed border-border-strong')
        caixa = html[inicio : html.index('</div>', inicio)]
        assert 'importa' in caixa and 'SCPI' in caixa

    def test_busca_sem_resultado_diz_o_que_tentar_alem_do_cta(
        self, client, chefe_almoxarifado
    ):
        """O CTA leva de volta; a descrição diz como acertar da próxima vez."""
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MATERIAIS, {'busca': 'inexistente-xyz'}).content.decode()
        assert 'Confira o c' in html

    def test_busca_sem_resultado_exibe_cta_secundario_link(
        self, client, chefe_almoxarifado
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS, {'busca': 'inexistente-xyz'})
        html = response.content.decode()
        assert 'border-dashed border-border-strong' in html
        titulo_idx = html.index('Nenhum material encontrado para')
        match = re.search(r'<a\b[^>]*>', html[titulo_idx:])
        assert match is not None
        tag = match.group()
        assert re.search(r'href="[^"]*"', tag)
        assert 'underline' in tag
        assert 'bg-blue-600' not in tag

    def test_busca_filtra_por_codigo(
        self,
        client,
        chefe_almoxarifado,
        material_disponivel,
        material_scpi_critico,
        estoque_principal,
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS, {'busca': 'MAT001'})
        assert response.status_code == 200
        saldos = list(response.context['saldos'])
        assert len(saldos) == 1
        assert saldos[0].material.codigo == 'MAT001'

    def test_flag_divergente_visivel_no_contexto(
        self, client, chefe_almoxarifado, material_scpi_critico, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS)
        saldos = list(response.context['saldos'])
        critico = next(s for s in saldos if s.material == material_scpi_critico)
        assert critico.divergente_calculado is True

    def test_renderiza_cartoes(
        self, client, chefe_almoxarifado, material_disponivel, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        conteudo = client.get(URL_MATERIAIS).content.decode()
        # <article> literal aqui: o estilo do cartão depende do estado de
        # divergência, então esta tela não usa o #card_abertura do chrome. O
        # container, esse sim, é o chrome — a variante densa (#cards_abertura_denso,
        # 3ª coluna em xl/1280px), porque o cartão do catálogo passou no critério
        # de densidade de DESIGN.md §A Regra do Cartão Único (issue #159).
        assert '<article' in conteudo
        assert 'grid gap-3 sm:grid-cols-2 xl:grid-cols-3' in conteudo
        assert '<table' not in conteudo
        # Quantidades empilhadas, não em `grid grid-cols-3` interno (issue #159):
        # a 322px de cartão (o que a variante densa dá a 1280px) três colunas
        # internas quebravam `Disponível: 50 un`, órfã da unidade.
        assert 'mt-4 space-y-1 text-sm' in conteudo
        assert 'grid grid-cols-3' not in conteudo
        assert conteudo.count('tabular-nums whitespace-nowrap') == 3

    def test_catalogo_pagina_em_vez_de_despejar_o_scpi_inteiro(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """O catálogo é populado pela importação SCPI, ou seja, cresce com o
        arquivo do sistema legado. Sem paginação, a tela renderizava o queryset
        inteiro — ~1,2 KB de HTML e 14 nós de DOM por cartão — numa página que o
        almoxarifado abre do celular, em pé no galpão.
        """
        from apps.estoque.models import Material, SaldoEstoque, UnidadeMedida
        from apps.estoque.views import PAGINA_MATERIAIS_TAMANHO

        total = PAGINA_MATERIAIS_TAMANHO + 3
        for i in range(total):
            material = Material.objects.create(
                codigo=f'900.000.{i:03d}',
                nome=f'Material {i}',
                unidade=UnidadeMedida.UNIDADE,
                ativo=True,
            )
            SaldoEstoque.objects.create(
                estoque=estoque_principal, material=material, saldo_fisico=1
            )

        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS)
        page_obj = response.context['page_obj']

        assert page_obj.paginator.count == total
        assert len(response.context['saldos']) == PAGINA_MATERIAIS_TAMANHO
        assert 'Paginação do catálogo de materiais' in response.content.decode()

    def test_paginacao_do_catalogo_preserva_a_busca(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """Sem `querystring_filtros`, ir para a página 2 caía no catálogo
        inteiro — perdendo exatamente o recorte que o usuário acabou de pedir."""
        from apps.estoque.models import Material, SaldoEstoque, UnidadeMedida
        from apps.estoque.views import PAGINA_MATERIAIS_TAMANHO

        for i in range(PAGINA_MATERIAIS_TAMANHO + 1):
            material = Material.objects.create(
                codigo=f'901.000.{i:03d}',
                nome=f'Tinta {i}',
                unidade=UnidadeMedida.UNIDADE,
                ativo=True,
            )
            SaldoEstoque.objects.create(
                estoque=estoque_principal, material=material, saldo_fisico=1
            )

        client.force_login(chefe_almoxarifado)
        conteudo = client.get(URL_MATERIAIS, {'busca': 'Tinta'}).content.decode()
        assert 'href="?busca=Tinta&amp;page=2"' in conteudo

    def test_material_divergente_realca_linha_e_card(
        self, client, chefe_almoxarifado, material_scpi_critico, estoque_principal
    ):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MATERIAIS)
        conteudo = response.content.decode()
        # Sem tabela, o realce de divergência vive só no cartão.
        assert 'border-danger-border-strong bg-danger-subtle' in conteudo
        # Sem `aria-label` no <article>: ele substituía o nome acessível do
        # cartão pelo rótulo genérico e apagava o código do material, que é a
        # identidade do registro. O badge diz o estado — e diz para todos.
        assert 'aria-label="Material com divergência crítica"' not in conteudo
        assert conteudo.count('Divergente') == 1


URL_MOVIMENTACOES = reverse('estoque:historico_movimentacoes')


class TestHistoricoMovimentacoesView:
    def test_chefe_almox_acessa(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MOVIMENTACOES)
        assert response.status_code == 200

    def test_superuser_acessa(self, client, superuser):
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES)
        assert response.status_code == 200

    def test_solicitante_recebe_403(self, client, solicitante):
        client.force_login(solicitante)
        response = client.get(URL_MOVIMENTACOES)
        assert response.status_code == 403

    def test_anonimo_redirecionado_para_login(self, client):
        response = client.get(URL_MOVIMENTACOES)
        assert response.status_code == 302
        assert 'login' in response['Location']

    def test_contexto_tem_page_obj(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MOVIMENTACOES)
        assert 'page_obj' in response.context

    def test_view_alimenta_page_obj_com_selector_escopado(
        self,
        client,
        chefe_obras,
        requisicao_autorizada,
        saida_registrada,
        movimentacao_outro_setor,
    ):
        # Contrato HTTP/render: a view delega o escopo ao selector e pagina o
        # resultado. A matriz de visibilidade em si é coberta em test_selectors.
        from apps.estoque.selectors import movimentacoes_visiveis_para

        client.force_login(chefe_obras)
        response = client.get(URL_MOVIMENTACOES)
        assert response.status_code == 200
        assert 'estoque/historico_movimentacoes.html' in {
            t.name for t in response.templates
        }
        esperado = movimentacoes_visiveis_para(chefe_obras.pk).count()
        assert response.context['page_obj'].paginator.count == esperado

    def test_aux_setor_acessa_e_recebe_o_recorte_do_selector(
        self,
        client,
        aux_obras,
        requisicao_autorizada,
        movimentacao_requisicao_do_aux,
        saida_registrada,
        movimentacao_outro_setor,
    ):
        # Contrato HTTP/render: a policy não mudou (#112), então o auxiliar entra
        # na página, e o que ela renderiza é o recorte do selector. A matriz de
        # visibilidade em si é coberta em test_selectors.
        from apps.estoque.selectors import movimentacoes_visiveis_para

        client.force_login(aux_obras)
        response = client.get(URL_MOVIMENTACOES)

        assert response.status_code == 200
        assert {m.pk for m in response.context['page_obj'].object_list} == set(
            movimentacoes_visiveis_para(aux_obras.pk).values_list('pk', flat=True)
        )

    def test_paginacao_server_side(
        self,
        client,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
    ):
        from decimal import Decimal

        from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque

        req, _ = requisicao_autorizada
        for _ in range(30):
            MovimentacaoEstoque.objects.create(
                tipo=TipoMovimentacaoEstoque.CONSUMO,
                material=material_disponivel,
                estoque=estoque_principal,
                delta_fisico=Decimal('-1'),
                delta_reservado=Decimal('-1'),
                requisicao=req,
                ator=superuser,
            )
        client.force_login(superuser)
        page1 = client.get(URL_MOVIMENTACOES)
        assert len(page1.context['page_obj'].object_list) == 25
        assert page1.context['page_obj'].has_next() is True
        page2 = client.get(URL_MOVIMENTACOES, {'page': 2})
        assert page2.status_code == 200
        assert len(page2.context['page_obj'].object_list) >= 1

    def test_empty_state_quando_ledger_vazio(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MOVIMENTACOES)
        assert response.context['page_obj'].paginator.count == 0
        assert b'Nenhuma movimenta' in response.content

    def test_heading_do_cartao_distingue_lancamentos_do_mesmo_minuto(
        self,
        client,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
        monkeypatch,
    ):
        """`date:"d/m/Y H:i"` tem precisão de minuto — um atendimento gera várias
        movimentações do mesmo material na mesma transação. O número do
        lançamento entra em `sr-only` para o nome acessível não colidir.
        """
        import re
        from decimal import Decimal

        from django.utils import timezone

        from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque

        req, _ = requisicao_autorizada
        # `criado_em` é `auto_now_add`; congela o relógio para as duas caírem no
        # mesmo instante — a colisão que o número do lançamento resolve —, sem
        # depender de o teste rodar rápido o bastante dentro do mesmo minuto.
        instante = timezone.now().replace(second=0, microsecond=0)
        monkeypatch.setattr('django.utils.timezone.now', lambda: instante)
        movs = [
            MovimentacaoEstoque.objects.create(
                tipo=TipoMovimentacaoEstoque.CONSUMO,
                material=material_disponivel,
                estoque=estoque_principal,
                delta_fisico=Decimal('-1'),
                delta_reservado=Decimal('-1'),
                requisicao=req,
                ator=superuser,
            )
            for _ in range(2)
        ]

        client.force_login(superuser)
        html = client.get(URL_MOVIMENTACOES).content.decode()

        headings = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S)
        nomes_acessiveis = [
            ' '.join(re.sub(r'<[^>]+>', '', h).split()) for h in headings
        ]
        # todo nome acessível é único, apesar de material e minuto repetidos
        assert len(set(nomes_acessiveis)) == len(nomes_acessiveis)
        nomes_das_criadas = [
            n for m in movs for n in nomes_acessiveis if f'lançamento {m.pk} em ' in n
        ]
        assert len(nomes_das_criadas) == 2
        # sem o número do lançamento os dois colidiriam: mesmo material, mesmo minuto
        sem_lancamento = [
            re.sub(r' — lançamento \d+ em ', ' em ', n) for n in nomes_das_criadas
        ]
        assert sem_lancamento[0] == sem_lancamento[1]

    def test_paginacao_usa_componente_com_rotulo_e_aria_label_proprios(
        self,
        client,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
    ):
        from decimal import Decimal

        from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque

        req, _ = requisicao_autorizada
        for _ in range(30):
            MovimentacaoEstoque.objects.create(
                tipo=TipoMovimentacaoEstoque.CONSUMO,
                material=material_disponivel,
                estoque=estoque_principal,
                delta_fisico=Decimal('-1'),
                delta_reservado=Decimal('-1'),
                requisicao=req,
                ator=superuser,
            )
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES)
        total = response.context['page_obj'].paginator.count
        assert 'aria-label="Paginação das movimentações"'.encode() in response.content
        esperado = f'<span class="tabular-nums">{total}</span> movimentações'
        assert esperado.encode() in response.content

    def test_menu_mostra_link_para_almox(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MOVIMENTACOES)
        assert URL_MOVIMENTACOES.encode() in response.content

    def test_texto_de_apoio_orienta_sem_narrar_implementacao(
        self, client, chefe_almoxarifado
    ):
        """Único texto de ajuda da tela (issue #160).

        Metade dele explicava que o recorte "fica na URL e pode ser
        compartilhado" — comportamento de querystring, que nenhum papel do
        PRODUCT.md pediu. Sobra o que orienta: o que a tela mostra e por onde
        filtrar.
        """
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MOVIMENTACOES).content.decode()
        assert 'fica na URL' not in html
        assert 'pode ser compartilhado' not in html
        assert (
            'Histórico imutável das movimentações de estoque visíveis ao seu papel.'
            in html
        )
        assert 'Filtre por' in html

    def test_link_da_origem_respeita_o_escopo_do_detalhe(
        self, client, chefe_almoxarifado, movimentacao_requisicao_rascunho
    ):
        """Ver a LINHA e poder abrir o DOCUMENTO não são a mesma permissão.

        O almoxarifado enxerga o ledger inteiro, inclusive movimentações de
        rascunho de terceiro; `requisicoes_visiveis_para` — o escopo que o
        detalhe usa — exclui esses rascunhos. O link incondicional levava a 404.
        """
        from django.urls import reverse as _reverse

        req = movimentacao_requisicao_rascunho.requisicao
        destino = _reverse('requisicoes:detalhe', kwargs={'pk': req.pk})

        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MOVIMENTACOES).content.decode()

        # A linha continua no ledger, com o número legível.
        assert req.numero_publico in html
        # Mas sem link, porque o destino não existe para quem está olhando.
        assert f'href="{destino}' not in html
        assert client.get(destino).status_code == 404
        # E sem a afordância que anuncia o link: prometer "Ver a origem" num
        # cartão que não leva a lugar nenhum é o mesmo defeito um degrau acima.
        assert 'Ver a origem' not in html

    def test_link_da_origem_existe_quando_a_requisicao_esta_no_escopo(
        self, client, chefe_almoxarifado, requisicao_autorizada
    ):
        """O caso normal não pode ter sido perdido junto com o rascunho."""
        from django.urls import reverse as _reverse

        req, _item = requisicao_autorizada
        destino = _reverse('requisicoes:detalhe', kwargs={'pk': req.pk})
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MOVIMENTACOES).content.decode()
        assert f'href="{destino}' in html

    def test_comentarios_dos_partials_nao_vazam_para_a_tela(
        self, client, superuser, requisicao_autorizada
    ):
        # Comentário multilinha precisa ser {% comment %}, não {# #} (que é
        # single-line) — senão o texto do comentário renderiza como conteúdo.
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES)
        assert 'Badge semântico'.encode() not in response.content
        assert 'Célula de delta'.encode() not in response.content
        assert 'Paginação server-side'.encode() not in response.content


class TestHistoricoMovimentacoesFiltros:
    """Camada de filtros HTMX sobre o ledger (issue #7)."""

    def test_filtro_material_reduz_resultado(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        com = client.get(URL_MOVIMENTACOES, {'material': 'MAT001'})
        sem = client.get(URL_MOVIMENTACOES, {'material': 'inexistente'})
        assert com.context['page_obj'].paginator.count >= 1
        assert sem.context['page_obj'].paginator.count == 0

    def test_requisicao_htmx_devolve_so_partial(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES, HTTP_HX_REQUEST='true')
        assert response.status_code == 200
        assert any(
            t.name == 'resultados'
            and t.origin.template_name == 'estoque/historico_movimentacoes.html'
            for t in response.templates
        )
        nomes = {t.name for t in response.templates}
        # Não renderiza o template completo (app-bar) num swap parcial.
        assert 'estoque/historico_movimentacoes.html' not in nomes

    def test_requisicao_normal_devolve_template_completo(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES)
        nomes = {t.name for t in response.templates}
        assert 'estoque/historico_movimentacoes.html' in nomes

    def test_caminho_nativo_redireciona_302_para_querystring_canonica(
        self, client, superuser
    ):
        """Chaves vazias e grafia ambígua não entram na URL de auditoria (#152)."""
        client.force_login(superuser)
        response = client.get(
            URL_MOVIMENTACOES,
            {'material': 'MAT001', 'data_ini': '', 'tipos': ''},
        )
        assert response.status_code == 302
        assert response['Location'] == f'{URL_MOVIMENTACOES}?material=MAT001'

    def test_caminho_nativo_ja_canonico_nao_redireciona(self, client, superuser):
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES, {'material': 'MAT001'})
        assert response.status_code == 200

    def test_caminho_htmx_devolve_canonica_no_header_hx_push_url(
        self, client, superuser
    ):
        client.force_login(superuser)
        response = client.get(
            URL_MOVIMENTACOES,
            {'tipos': ['saida_excepcional', 'consumo'], 'setor': ''},
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200
        assert response['HX-Push-Url'] == (
            f'{URL_MOVIMENTACOES}?tipos=consumo&tipos=saida_excepcional'
        )

    def test_ordenacao_asc_inverte_cronologia(
        self,
        client,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
    ):
        from decimal import Decimal

        from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque

        req, _ = requisicao_autorizada
        for _ in range(2):
            MovimentacaoEstoque.objects.create(
                tipo=TipoMovimentacaoEstoque.CONSUMO,
                material=material_disponivel,
                estoque=estoque_principal,
                delta_fisico=Decimal('-1'),
                delta_reservado=Decimal('-1'),
                requisicao=req,
                ator=superuser,
            )
        client.force_login(superuser)
        desc = client.get(URL_MOVIMENTACOES).context['page_obj'].object_list
        asc = (
            client.get(URL_MOVIMENTACOES, {'ordem': 'asc'})
            .context['page_obj']
            .object_list
        )
        assert [m.pk for m in asc] == [m.pk for m in reversed(list(desc))]
        assert client.get(URL_MOVIMENTACOES, {'ordem': 'asc'}).context['ordem'] == 'asc'

    def test_filtro_setor_visivel_so_para_almox(
        self, client, chefe_almoxarifado, chefe_obras
    ):
        client.force_login(chefe_almoxarifado)
        assert client.get(URL_MOVIMENTACOES).context['mostrar_filtro_setor'] is True
        client.force_login(chefe_obras)
        assert client.get(URL_MOVIMENTACOES).context['mostrar_filtro_setor'] is False

    def test_chefe_setor_nao_filtra_por_setor_via_querystring(
        self, client, chefe_obras, requisicao_autorizada, movimentacao_outro_setor
    ):
        # Mesmo forçando ?setor=<outro> na URL, chefe de setor não vaza dado.
        setor_ti = movimentacao_outro_setor.requisicao.setor_beneficiario_id
        client.force_login(chefe_obras)
        response = client.get(URL_MOVIMENTACOES, {'setor': setor_ti})
        assert response.status_code == 200
        pks = {m.pk for m in response.context['page_obj'].object_list}
        assert movimentacao_outro_setor.pk not in pks

    def test_querystring_invalida_nao_quebra(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        response = client.get(
            URL_MOVIMENTACOES,
            {
                'data_ini': 'abc',
                'data_fim': '2026-13-99',
                'setor': 'xyz',
                'ordem': 'lixo',
                'tipos': 'nao_existe',
                'page': 'foo',
            },
            follow=True,
        )
        assert response.status_code == 200

    def test_chip_de_filtro_marca_estado_ativo(
        self, client, superuser, requisicao_autorizada
    ):
        """O chip reflete o recorte em vigor, não a última vez que foi clicado.

        `ativo` sai da querystring, então a marca sobrevive a chegar na tela
        por link, por histórico do navegador ou por recarga.
        """
        client.force_login(superuser)
        ativo = client.get(
            URL_MOVIMENTACOES,
            {'tipos': ['consumo', 'saida_excepcional']},
        )
        inativo = client.get(URL_MOVIMENTACOES)
        assert ativo.context['chips_filtro'][0].ativo is True
        assert inativo.context['chips_filtro'][0].ativo is False

    def test_chip_de_filtro_reemitido_via_oob_no_swap_htmx(
        self, client, superuser, requisicao_autorizada
    ):
        """Bug-regressão: o chip vive fora de `#resultados-movimentacoes`.

        Numa resposta HTMX ele precisa ser reemitido como out-of-band, senão o
        estado ativo e a URL de alternância ficam com o recorte da primeira
        renderização full-page enquanto a lista já mostra outro.
        """
        client.force_login(superuser)
        parcial = client.get(
            URL_MOVIMENTACOES,
            {'tipos': ['consumo', 'saida_excepcional']},
            HTTP_HX_REQUEST='true',
        ).content
        assert b'id="filter-chips"' in parcial
        assert b'hx-swap-oob="true"' in parcial
        assert b'aria-current="true"' in parcial

    def test_chip_de_filtro_sem_oob_na_pagina_completa(
        self, client, superuser, requisicao_autorizada
    ):
        """O par do teste acima: no render completo o chip sai uma vez só.

        Com `hx-swap-oob` numa página inteira, o mesmo `id` apareceria duas
        vezes no documento e o HTMX passaria a trocar o nó errado.
        """
        client.force_login(superuser)
        conteudo = client.get(URL_MOVIMENTACOES).content
        assert conteudo.count(b'id="filter-chips"') == 1
        assert b'hx-swap-oob' not in conteudo

    def test_presets_periodo_datas_absolutas_sem_estado_novo(
        self, client, superuser, requisicao_autorizada
    ):
        # issue #153: preset resolve para datas absolutas em data_ini/data_fim,
        # sem token relativo nem chave nova na querystring.
        client.force_login(superuser)
        presets = client.get(URL_MOVIMENTACOES).context['presets_periodo']
        assert [p.rotulo for p in presets] == [
            'Últimos 7 dias',
            'Últimos 30 dias',
            'Este mês',
        ]
        for preset in presets:
            query = preset.url.split('?', 1)[1]
            chaves = {p.split('=')[0] for p in query.split('&')}
            assert chaves <= {'data_ini', 'data_fim'}
            assert 'periodo' not in chaves

    def test_flag_tem_filtro_ativo(self, client, superuser, requisicao_autorizada):
        client.force_login(superuser)
        com = client.get(URL_MOVIMENTACOES, {'material': 'x'})
        sem = client.get(URL_MOVIMENTACOES)
        assert com.context['tem_filtro_ativo'] is True
        assert sem.context['tem_filtro_ativo'] is False

    def test_empty_state_contextual_distingue_filtro_de_ledger_vazio(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        # Filtro sem resultado → mensagem específica de filtro, e NÃO a de
        # ledger vazio. Termo com caractere HTML-especial: prova que
        # `titulo_com_termo` (apps/core/templatetags/core_tags.py) não marca
        # o título como seguro — o autoescape do Django roda sobre a string
        # inteira, igual rodava antes da extração pro empty_state.html. Sem
        # isso, um termo ASCII puro passaria mesmo se um `|safe` futuro
        # desligasse o escape por engano.
        filtrado = client.get(
            URL_MOVIMENTACOES, {'material': '<b>inexistente</b>'}
        ).content.decode()
        assert (
            'Nenhum resultado para &quot;&lt;b&gt;inexistente&lt;/b&gt;&quot;'
            in filtrado
        )
        assert '<b>inexistente</b>' not in filtrado
        assert 'Nenhuma movimentação encontrada' not in filtrado

    def test_chip_de_filtro_preserva_filtros_atuais(
        self, client, chefe_almoxarifado, setor_obras
    ):
        """Bug-regressão: alternar o chip não pode descartar o recorte atual.

        A URL do chip carrega os filtros em vigor; sem isso, marcar "só saídas"
        jogava fora busca, ordem e setor que a pessoa acabara de montar.
        """
        client.force_login(chefe_almoxarifado)
        response = client.get(
            URL_MOVIMENTACOES,
            {'material': 'parafuso', 'ordem': 'asc', 'setor': setor_obras.pk},
            follow=True,
        )
        url_chip = response.context['chips_filtro'][0].url
        assert 'material=parafuso' in url_chip
        assert 'ordem=asc' in url_chip
        assert f'setor={setor_obras.pk}' in url_chip
        assert 'tipos=consumo' in url_chip
        assert 'tipos=saida_excepcional' in url_chip

    def test_chip_toggle_off_preserva_outros_tipos_selecionados(
        self, client, superuser, requisicao_autorizada
    ):
        # Bug-regressão #143: `setlist('tipos', [])` limpava TODOS os tipos
        # ao desligar o chip, não só os dois que ele próprio adicionou. Quem
        # tivesse "Reserva" marcada perdia a seleção em silêncio ao
        # alternar o chip.
        client.force_login(superuser)
        response = client.get(
            URL_MOVIMENTACOES,
            {'tipos': ['reserva', 'consumo', 'saida_excepcional']},
            follow=True,
        )
        # tipos=[reserva, consumo, saida_excepcional] → chip ativo (subconjunto);
        # a URL do chip desliga removendo SÓ consumo/saida_excepcional.
        chip = response.context['chips_filtro'][0]
        assert chip.ativo is True
        assert 'tipos=reserva' in chip.url
        assert 'tipos=consumo' not in chip.url
        assert 'tipos=saida_excepcional' not in chip.url

    def test_campos_do_form_reemitidos_via_oob_com_tipo_marcado_no_swap_htmx(
        self, client, superuser, requisicao_autorizada
    ):
        # Bug-regressão #143: os campos do filtro (inputs + fieldset de
        # checkbox) vivem fora de #resultados-movimentacoes; sem reemite
        # out-of-band, o checkbox de "tipos" ficava desmarcado após um swap
        # HTMX mesmo com o filtro aplicado na URL — o próximo "Aplicar
        # filtros" reenviava, em silêncio, um filtro vazio.
        client.force_login(superuser)
        parcial = client.get(
            URL_MOVIMENTACOES, {'tipos': 'consumo'}, HTTP_HX_REQUEST='true'
        ).content.decode()
        assert 'id="resultados-movimentacoes-campos"' in parcial
        assert 'hx-swap-oob="true"' in parcial
        idx = parcial.index('value="consumo"')
        trecho = parcial[idx : parcial.index('>', idx) + 1]
        assert 'checked' in trecho

    def test_campos_do_form_sem_oob_na_pagina_completa(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        conteudo = client.get(URL_MOVIMENTACOES, {'tipos': 'consumo'}).content
        assert conteudo.count(b'id="resultados-movimentacoes-campos"') == 1
        assert b'hx-swap-oob' not in conteudo


class TestHistoricoMovimentacoesFiltrosPartials:
    """Cobertura da extração dos campos de filtro em partials (issue #88)."""

    def test_form_expoe_method_get_e_action_nativos(self, client, superuser):
        client.force_login(superuser)
        content = client.get(URL_MOVIMENTACOES).content.decode()
        assert 'method="get"' in content
        assert f'action="{URL_MOVIMENTACOES}"' in content

    def test_submissao_nativa_sem_htmx_retorna_pagina_completa_filtrada(
        self, client, superuser, requisicao_autorizada
    ):
        # Sem HTTP_HX_REQUEST simula o fallback de navegação nativa do
        # <form method="get">: precisa renderizar a página completa (não só
        # o partial 'resultados') e ainda assim aplicar o filtro.
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES, {'material': 'MAT001'})
        nomes = {t.name for t in response.templates}
        assert 'estoque/historico_movimentacoes.html' in nomes
        assert response.context['page_obj'].paginator.count >= 1

    def test_limpar_filtros_href_navegacao_nativa(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        content = client.get(URL_MOVIMENTACOES, {'material': 'MAT001'}).content.decode()
        assert f'href="{URL_MOVIMENTACOES}"' in content
        assert 'Limpar filtros' in content

    def test_checkbox_tipo_tem_alvo_de_toque(self, client, superuser):
        client.force_login(superuser)
        content = client.get(URL_MOVIMENTACOES).content.decode()
        idx = content.index('name="tipos"')
        label_ini = content.rindex('<label', 0, idx)
        label_fim = content.index('</label>', idx) + len('</label>')
        assert 'min-h-11' in content[label_ini:label_fim]

    def test_filtro_setor_label_vinculado_ao_select(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        content = client.get(URL_MOVIMENTACOES).content.decode()
        assert 'for="filtro-setor"' in content
        assert 'id="filtro-setor"' in content

    def test_filtro_setor_ausente_para_chefe_de_setor(self, client, chefe_obras):
        client.force_login(chefe_obras)
        content = client.get(URL_MOVIMENTACOES).content.decode()
        assert 'id="filtro-setor"' not in content

    def test_limpar_filtros_reemitido_via_oob_no_swap_htmx(
        self, client, superuser, requisicao_autorizada
    ):
        # Bug-regressão (achado do CodeRabbit): filter_acoes.html vive fora
        # de #resultados-movimentacoes (dentro do <form>), então numa
        # resposta HTMX precisa ser reemitido como out-of-band pra refletir
        # tem_filtro_ativo — senão "Limpar filtros" fica com o estado da
        # primeira renderização full-page. Mesmo padrão do
        # components/filter_chips.html, reemitido via hx-swap-oob.
        client.force_login(superuser)
        parcial = client.get(
            URL_MOVIMENTACOES, {'material': 'MAT001'}, HTTP_HX_REQUEST='true'
        ).content
        assert b'id="filtro-acoes-movimentacoes"' in parcial
        assert b'hx-swap-oob="true"' in parcial
        assert b'Limpar filtros' in parcial

    def test_limpar_filtros_e_link_navegavel_tambem_no_reemite_htmx(
        self, client, superuser, requisicao_autorizada
    ):
        """Bug-regressão: "Limpar filtros" saía inerte na resposta HTMX.

        O `{% url ... as url_movimentacoes %}` fica no topo da tela, fora do
        `{% partialdef resultados %}`, e não roda quando o fragmento é
        renderizado sozinho. Com `action_url` vazio o components/button.html
        caía no ramo `<button>`: sem href e sem hx-get, um controle que não
        fazia nada — logo depois de aplicar um filtro.
        """
        client.force_login(superuser)
        parcial = client.get(
            URL_MOVIMENTACOES, {'material': 'MAT001'}, HTTP_HX_REQUEST='true'
        ).content.decode()
        marca = 'id="filtro-acoes-movimentacoes"'
        trecho = parcial[parcial.index(marca) :]
        trecho = trecho[: trecho.index('</span>')]
        assert f'href="{URL_MOVIMENTACOES}"' in trecho, (
            f'"Limpar filtros" precisa navegar de verdade; veio: {trecho}'
        )

    def test_submit_fica_fora_do_wrapper_reemitido_via_oob(
        self, client, superuser, requisicao_autorizada
    ):
        """O swap OOB não pode destruir o botão que disparou a requisição."""
        client.force_login(superuser)
        parcial = client.get(
            URL_MOVIMENTACOES, {'material': 'MAT001'}, HTTP_HX_REQUEST='true'
        ).content.decode()
        marca = 'id="filtro-acoes-movimentacoes"'
        trecho = parcial[parcial.index(marca) :]
        trecho = trecho[: trecho.index('</span>')]
        assert 'hx-swap-oob="true"' in trecho
        assert 'Aplicar filtros' not in trecho, (
            f'O submit não pode ser reemitido no OOB: {trecho}'
        )

    def test_limpar_filtros_sem_oob_na_pagina_completa(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        conteudo = client.get(URL_MOVIMENTACOES, {'material': 'MAT001'}).content
        assert conteudo.count(b'id="filtro-acoes-movimentacoes"') == 1
        assert b'hx-swap-oob' not in conteudo

    def test_todos_os_campos_esperados_presentes(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        content = client.get(URL_MOVIMENTACOES).content.decode()
        for campo in (
            'name="material"',
            'name="data_ini"',
            'name="data_fim"',
            'name="setor"',
            'name="tipos"',
        ):
            assert campo in content


class TestHistoricoMovimentacoesGruposDeTipo:
    """Partição do fieldset "Tipo" por origem da movimentação (issue #160).

    Os 7 tipos vinham numa fileira única enquanto o fieldset menor — os 8
    estados do histórico de requisições — já tinha ganhado a partição na issue
    #154. Aqui a partição espelha `_TIPOS_ORIGEM_REQUISICAO`/`_TIPOS_ORIGEM_SAIDA`
    de `apps/estoque/models.py`, a mesma que a constraint
    `movimentacao_tipo_origem_coerente` exige do ledger.
    """

    LEGENDA_REQUISICAO = '>De requisição</legend>'
    LEGENDA_SAIDA = '>De saída excepcional</legend>'

    def _fonte_do_template(self):
        return (
            Path(__file__).resolve().parent.parent
            / 'templates'
            / 'estoque'
            / 'historico_movimentacoes.html'
        ).read_text()

    def test_fieldset_de_tipo_ganha_os_dois_grupos(self, client, superuser):
        client.force_login(superuser)
        html = client.get(URL_MOVIMENTACOES).content.decode()
        assert '>Tipo</legend>' in html
        assert self.LEGENDA_REQUISICAO in html
        assert self.LEGENDA_SAIDA in html

    def test_grupos_preservam_as_7_caixas_e_os_7_valores(self, client, superuser):
        """Só a apresentação muda: mesmo `name`, mesmos 7 valores, mesma
        querystring que o uso plano produzia."""
        from apps.estoque.models import TipoMovimentacaoEstoque

        client.force_login(superuser)
        html = client.get(URL_MOVIMENTACOES).content.decode()
        assert html.count('name="tipos"') == 7
        assert html.count('type="checkbox"') == 7
        for tipo in TipoMovimentacaoEstoque:
            assert f'value="{tipo.value}"' in html

    def test_particao_do_template_espelha_as_constantes_de_origem(self):
        """Guarda de drift na fonte: a partição escrita no template tem de ser
        exatamente `_TIPOS_ORIGEM_REQUISICAO`/`_TIPOS_ORIGEM_SAIDA`, senão o
        espelho que o comentário promete deixou de valer em silêncio."""
        from apps.estoque.models import _TIPOS_ORIGEM_REQUISICAO, _TIPOS_ORIGEM_SAIDA

        chamada = re.search(
            r'{% agrupar_opcoes tipos_opcoes(.+?)as tipos_grupos %}',
            self._fonte_do_template(),
            re.S,
        )
        assert chamada is not None
        argumentos = re.findall(r'"([^"]*)"', chamada.group(1))
        assert argumentos[0] == 'De requisição'
        assert argumentos[2] == 'De saída excepcional'
        assert argumentos[1].split() == [t.value for t in _TIPOS_ORIGEM_REQUISICAO]
        assert argumentos[3].split() == [t.value for t in _TIPOS_ORIGEM_SAIDA]

    def test_particao_cobre_exatamente_os_tipos_canonicos(self):
        """Mudou `TipoMovimentacaoEstoque` sem mexer nas constantes de origem,
        `agrupar_opcoes` erra alto em vez de sumir com uma caixa."""
        from apps.core.templatetags.core_tags import agrupar_opcoes
        from apps.estoque.models import (
            _TIPOS_ORIGEM_REQUISICAO,
            _TIPOS_ORIGEM_SAIDA,
            TipoMovimentacaoEstoque,
        )

        grupos = agrupar_opcoes(
            TipoMovimentacaoEstoque.choices,
            'De requisição',
            ' '.join(t.value for t in _TIPOS_ORIGEM_REQUISICAO),
            'De saída excepcional',
            ' '.join(t.value for t in _TIPOS_ORIGEM_SAIDA),
        )
        assert [legenda for legenda, _ in grupos] == [
            'De requisição',
            'De saída excepcional',
        ]
        assert [len(pares) for _, pares in grupos] == [5, 2]

    def test_querystring_de_tipo_continua_filtrando_e_marcando(
        self, client, superuser, requisicao_autorizada
    ):
        client.force_login(superuser)
        com = client.get(URL_MOVIMENTACOES, {'tipos': 'reserva'}, follow=True)
        sem = client.get(URL_MOVIMENTACOES, {'tipos': 'consumo'}, follow=True)
        assert com.context['page_obj'].paginator.count >= 1
        assert sem.context['page_obj'].paginator.count == 0
        html = com.content.decode()
        idx = html.index('value="reserva"')
        assert 'checked' in html[idx : html.index('>', idx) + 1]

    def test_reemite_oob_do_caminho_htmx_traz_os_grupos(
        self, client, superuser, requisicao_autorizada
    ):
        """`agrupar_opcoes` vive DENTRO de `partialdef campos`.

        O fragmento é reemitido sozinho via `hx-swap-oob` nas respostas HTMX, e
        o que mora acima do partialdef não roda nesse caminho — a tag colocada
        lá em cima devolveria o reemite sem grupos, e a fileira única voltaria
        assim que o operador aplicasse o primeiro filtro.
        """
        client.force_login(superuser)
        parcial = client.get(
            URL_MOVIMENTACOES, {'tipos': 'reserva'}, HTTP_HX_REQUEST='true'
        ).content.decode()
        assert 'id="resultados-movimentacoes-campos"' in parcial
        assert 'hx-swap-oob="true"' in parcial
        assert self.LEGENDA_REQUISICAO in parcial
        assert self.LEGENDA_SAIDA in parcial
        assert parcial.count('name="tipos"') == 7

    def test_comentario_da_particao_nao_vaza_para_a_tela(self, client, superuser):
        # Comentário multilinha precisa ser {% comment %}, não {# #}.
        client.force_login(superuser)
        html = client.get(URL_MOVIMENTACOES).content.decode()
        assert '_TIPOS_ORIGEM_REQUISICAO' not in html
        assert 'agrupar_opcoes' not in html


class TestHistoricoMovimentacoesResponsivo:
    """Testes de estrutura HTML responsiva e atributos de acessibilidade."""

    def test_disclosure_nativo_presente_na_pagina(self, client, chefe_almoxarifado):
        # A barra de filtros usa <details>/<summary> nativo para disclosure mobile
        # — funciona sem JavaScript (progressive enhancement).
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MOVIMENTACOES)
        assert response.status_code == 200
        assert b'<details' in response.content
        assert b'<summary' in response.content

    def test_chip_de_filtro_visivel_fora_do_disclosure(
        self, client, chefe_almoxarifado
    ):
        """O chip sai antes do `<details>` no HTML.

        No mobile o disclosure de filtros começa fechado; dentro dele, o chip
        e o recorte que ele anuncia ficariam invisíveis até alguém abrir.
        """
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_MOVIMENTACOES)
        assert response.status_code == 200
        content = response.content.decode()
        pos_chip = content.find('id="filter-chips"')
        pos_details = content.find('<details')
        assert pos_chip != -1, 'id="filter-chips" não encontrado'
        assert pos_details != -1, '<details não encontrado'
        assert pos_chip < pos_details, 'chip deve aparecer antes do <details>'

    def _consumos_isolados(
        self,
        n,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
    ):
        """Cria `n` consumos e devolve o filtro que isola só eles.

        Duas coisas precisam ser verdade ao mesmo tempo: a contagem anunciada
        tem de ser exatamente `n`, e o ledger não pode ficar incoerente só para
        o teste caber.

        O isolamento é pelo **tipo**, não por um material inventado. As fixtures
        deixam uma `reserva` no ledger, então filtrar por `consumo` já separa o
        que este teste criou — sem material órfão, fora da requisição e sem
        `SaldoEstoque`. O material continua sendo o da própria requisição.

        A escrita direta no ledger é a mesma dos testes vizinhos desta classe:
        aqui o assunto é a frase anunciada, não a aritmética de saldo, que tem
        cobertura própria nos testes de service.
        """
        from decimal import Decimal

        from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque

        req, _ = requisicao_autorizada
        for _ in range(n):
            MovimentacaoEstoque.objects.create(
                tipo=TipoMovimentacaoEstoque.CONSUMO,
                material=material_disponivel,
                estoque=estoque_principal,
                delta_fisico=Decimal('-1'),
                delta_reservado=Decimal('-1'),
                requisicao=req,
                ator=superuser,
            )
        return {'tipos': TipoMovimentacaoEstoque.CONSUMO.value}

    def test_lista_de_resultados_nao_e_live_region(self, client, chefe_almoxarifado):
        """Marcar a listagem inteira como live region faz o leitor reler tudo.

        O wrapper carregava `aria-live="polite" aria-atomic="true"`: a cada
        ajuste de filtro, as 25 linhas eram relidas do começo. O anúncio útil é
        o tamanho do resultado, não o resultado — e ele vive fora da lista, no
        mesmo padrão que o histórico de requisições já usa.
        """
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MOVIMENTACOES).content.decode()

        inicio = html.index('id="resultados-movimentacoes"')
        wrapper = html[html.rindex('<div', 0, inicio) : html.index('>', inicio) + 1]

        assert 'aria-live' not in wrapper
        assert 'aria-atomic' not in wrapper

    def test_regiao_de_resumo_e_live_region_de_verdade(
        self, client, chefe_almoxarifado
    ):
        """Um `<p>` sem `role` troca de texto sem anunciar nada.

        Ele passaria em todos os testes de mensagem e não anunciaria uma única
        vez. O `role` é o contrato; o texto é só a carga.
        """
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MOVIMENTACOES).content.decode()

        inicio = html.index('id="resumo-movimentacoes"')
        tag = html[html.rindex('<', 0, inicio) : html.index('>', inicio) + 1]

        assert 'role="status"' in tag
        assert 'sr-only' in tag
        assert html[html.index('>', inicio) + 1 :].lstrip().startswith('<'), (
            'a região nasce vazia: no carregamento inicial nada mudou ainda'
        )

    def test_swap_oob_preserva_o_elemento_da_live_region(
        self, client, chefe_almoxarifado
    ):
        """`innerHTML:` troca o conteúdo; um oob sem prefixo levaria o `role` junto.

        A resposta HTMX não carrega o `<p>` — carrega só o conteúdo dele. Exigir
        `role="status"` aqui seria exigir o oposto do que o modo de swap faz. O
        que dá para provar numa resposta Django é o modo, e a ausência de um
        segundo `id` que reintroduziria a região por cima.
        """
        client.force_login(chefe_almoxarifado)
        html = client.get(URL_MOVIMENTACOES, HTTP_HX_REQUEST='true').content.decode()

        assert 'hx-swap-oob="innerHTML:#resumo-movimentacoes"' in html
        assert 'id="resumo-movimentacoes"' not in html

    def test_filtro_sem_resultado_anuncia_zero_movimentacoes(
        self, client, chefe_almoxarifado
    ):
        """O caso que a issue nomeia: a lista some e nada é dito.

        Sem anúncio, quem filtrou não sabe se filtrou demais ou se a requisição
        travou.
        """
        client.force_login(chefe_almoxarifado)
        html = client.get(
            URL_MOVIMENTACOES, {'material': 'inexistente-xyz'}, HTTP_HX_REQUEST='true'
        ).content.decode()

        assert 'Nenhuma movimentação encontrada.' in html

    def test_anuncio_no_singular_com_uma_movimentacao(
        self,
        client,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
    ):
        """ "1 movimentações" é o erro que um teste só do zero deixa passar."""
        filtro = self._consumos_isolados(
            1,
            superuser,
            requisicao_autorizada,
            material_disponivel,
            estoque_principal,
        )
        client.force_login(superuser)
        html = client.get(
            URL_MOVIMENTACOES, filtro, HTTP_HX_REQUEST='true'
        ).content.decode()

        assert '1 movimentação encontrada.' in html

    def test_anuncio_no_plural_com_duas_movimentacoes(
        self,
        client,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
    ):
        """Os dois `pluralize` flexionando juntos, casados na frase inteira."""
        filtro = self._consumos_isolados(
            2,
            superuser,
            requisicao_autorizada,
            material_disponivel,
            estoque_principal,
        )
        client.force_login(superuser)
        html = client.get(
            URL_MOVIMENTACOES, filtro, HTTP_HX_REQUEST='true'
        ).content.decode()

        assert '2 movimentações encontradas.' in html

    def test_contagem_visivel_na_pagina_completa(
        self, client, superuser, requisicao_autorizada
    ):
        """Issue #144: com a contagem só em `hx-swap-oob`, carga de página
        completa não mostrava nada pra quem enxerga — `resumo-movimentacoes`
        nasce vazio. A contagem visível fica na mesma linha do controle de
        ordenação, e precisa aparecer mesmo com resultado único (sem
        paginação, que só renderiza com mais de uma página).
        """
        client.force_login(superuser)
        response = client.get(URL_MOVIMENTACOES)
        assert response.context['page_obj'].paginator.num_pages == 1
        html = response.content.decode()

        idx_ordenacao = html.index('Mais antigas primeiro')
        linha = html.rindex('<div', 0, idx_ordenacao)
        trecho = html[linha:idx_ordenacao]
        assert 'tabular-nums">1</span>' in trecho
        assert 'movimentação' in trecho

    def test_contagem_visivel_em_resposta_htmx(
        self, client, superuser, requisicao_autorizada
    ):
        """A mesma contagem visível também na resposta parcial HTMX — não só
        a sr-only via swap out-of-band."""
        client.force_login(superuser)
        html = client.get(URL_MOVIMENTACOES, HTTP_HX_REQUEST='true').content.decode()

        idx_ordenacao = html.index('Mais antigas primeiro')
        linha = html.rindex('<div', 0, idx_ordenacao)
        trecho = html[linha:idx_ordenacao]
        assert 'tabular-nums">1</span>' in trecho
        assert 'movimentação' in trecho

    def test_contagem_com_paginacao_diz_pagina_e_recorte(
        self,
        client,
        superuser,
        requisicao_autorizada,
        material_disponivel,
        estoque_principal,
    ):
        """Issue #156: com paginação a linha de cima mostrava `<span>` vazio e
        a contagem do recorte só reaparecia no rodapé. Agora diz
        "25 de 26 movimentações" — quantas nesta página `de` quantas no
        recorte — nos dois caminhos de render.
        """
        filtro = self._consumos_isolados(
            26,
            superuser,
            requisicao_autorizada,
            material_disponivel,
            estoque_principal,
        )
        client.force_login(superuser)

        esperado = (
            'tabular-nums">25</span> de '
            '<span class="font-medium tabular-nums">26</span>'
        )

        completa = client.get(URL_MOVIMENTACOES, filtro)
        assert completa.context['page_obj'].paginator.num_pages == 2
        html = completa.content.decode()
        idx = html.index('Mais antigas primeiro')
        trecho = html[html.rindex('<div', 0, idx) : idx]
        assert esperado in trecho
        assert 'movimentações' in trecho
        assert '<span></span>' not in trecho

        parcial = client.get(
            URL_MOVIMENTACOES, filtro, HTTP_HX_REQUEST='true'
        ).content.decode()
        idx_p = parcial.index('Mais antigas primeiro')
        assert esperado in parcial[parcial.rindex('<div', 0, idx_p) : idx_p]


class TestHistoricoMovimentacoesFiltrosResponsivo:
    """Paridade estrutural da barra de filtros extraída (issue #88)."""

    def test_barra_filtros_html_balanceado(self, client, superuser):
        client.force_login(superuser)
        content = client.get(URL_MOVIMENTACOES).content.decode()
        inicio = content.index('<details')
        fim = content.index('</details>', inicio) + len('</details>')
        assert_html_balanceado(content[inicio:fim])

    def test_wrapper_form_tem_sm_block_important(self, client, superuser):
        # Regressão de drift: historico_movimentacoes.html não tinha
        # `sm:block!` no wrapper do form (só historico_requisicoes.html
        # tinha) — filter_shell.html#abertura unifica as 2 telas.
        client.force_login(superuser)
        content = client.get(URL_MOVIMENTACOES).content.decode()
        assert 'sm:block!' in content

    def test_template_usa_partials_de_filtro_sem_duplicar_campos_inline(self):
        caminho = (
            Path(__file__).resolve().parent.parent
            / 'templates'
            / 'estoque'
            / 'historico_movimentacoes.html'
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

    def test_chip_de_filtro_composto_fora_do_filter_shell(self):
        """Guarda de posição na fonte, par do teste de render acima.

        `components/filter_chips.html` tem de vir antes da abertura do
        `filter_shell` no template — é o que mantém o chip fora do disclosure.
        """
        caminho = (
            Path(__file__).resolve().parent.parent
            / 'templates'
            / 'estoque'
            / 'historico_movimentacoes.html'
        )
        fonte = caminho.read_text()
        idx_chip = fonte.index('components/filter_chips.html')
        idx_shell = fonte.index('filter_shell.html#abertura')
        assert idx_chip < idx_shell


URL_NOVA_LINHA_ITEM = reverse('estoque:nova_linha_item_saida_excepcional')


class TestNovaLinhaItemSaidaExcepcionalView:
    def test_chefe_recebe_partial_com_linha_vazia(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_NOVA_LINHA_ITEM, {'index': '2'})
        assert response.status_code == 200
        html = response.content.decode()
        assert 'itens-2-material_id' in html
        assert 'itens-2-quantidade' in html

    def test_index_ausente_usa_zero(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        response = client.get(URL_NOVA_LINHA_ITEM)
        assert response.status_code == 200
        assert 'itens-0-material_id' in response.content.decode()

    def test_solicitante_recebe_403(self, client, solicitante):
        client.force_login(solicitante)
        response = client.get(URL_NOVA_LINHA_ITEM)
        assert response.status_code == 403

    def test_anonimo_redirecionado_para_login(self, client):
        response = client.get(URL_NOVA_LINHA_ITEM)
        assert response.status_code == 302
        assert 'login' in response['Location']


class TestNovaSaidaExcepcionalAvisoDivergencia:
    """Issue #111: a view liga o hook de aviso e avisa o operador."""

    def _post(self, client, material, quantidade):
        return client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'Material avariado em vistoria',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material.pk),
                'itens-0-quantidade': quantidade,
            },
            follow=False,
        )

    def test_view_injeta_o_hook_de_divergencia(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        """O service é chamado com _pos_saida_hook não nulo."""
        from unittest.mock import patch

        from apps.estoque.models import SaidaExcepcional

        client.force_login(chefe_almoxarifado)
        with patch(
            'apps.estoque.views.registrar_saida_excepcional',
            return_value=SaidaExcepcional(numero_publico='SXP-2026-000001'),
        ) as service:
            self._post(client, material_disponivel, '5')

        # A view envolve o hook num closure para capturar os ids avisados, então
        # não dá para comparar identidade com
        # registrar_timeline_divergencia_saida_excepcional. O efeito real é
        # travado pelos dois testes de integração abaixo.
        assert service.call_count == 1
        hook = service.call_args.kwargs['_pos_saida_hook']
        assert hook is not None
        assert callable(hook)

    def test_baixa_que_cria_divergencia_avisa_o_operador(
        self,
        client,
        chefe_almoxarifado,
        estoque_principal,
        material_disponivel,
        requisicao_autorizada,
    ):
        """messages.warning além do success, citando as requisições afetadas."""
        client.force_login(chefe_almoxarifado)
        response = self._post(client, material_disponivel, '98')

        mensagens = list(response.wsgi_request._messages)
        niveis = [m.level_tag for m in mensagens]
        assert 'success' in niveis
        assert 'warning' in niveis

        # Texto completo: a contagem faz parte do contrato, e uma asserção de
        # substring aceitaria qualquer dígito solto vindo do número da saída.
        aviso = next(m for m in mensagens if m.level_tag == 'warning')
        assert str(aviso) == (
            'Esta baixa criou divergência crítica de estoque: '
            '1 requisição autorizada foi avisada. A separação delas fica bloqueada '
            'até a divergência ser resolvida ou a requisição ser cancelada.'
        )

    def test_baixa_sem_divergencia_nao_avisa_o_operador(
        self,
        client,
        chefe_almoxarifado,
        estoque_principal,
        material_disponivel,
        requisicao_autorizada,
    ):
        """Sem divergência criada, só o success de sempre."""
        client.force_login(chefe_almoxarifado)
        response = self._post(client, material_disponivel, '5')

        mensagens = list(response.wsgi_request._messages)
        assert [m.level_tag for m in mensagens] == ['success']


class TestSumarioDeErrosNaSaidaExcepcional:
    """A tela onde falhar em silêncio custa mais — a issue #125.

    Baixa administrativa direta, restrita ao chefe de almoxarifado, com formset
    de itens e autocomplete, sem reversão fácil. Era a única tela longa de
    formset **sem** o sumário que o projeto construiu para exatamente isso.
    """

    DADOS_INVALIDOS = {
        'motivo': 'avaria',
        'observacao': '',
        'itens-TOTAL_FORMS': '1',
        'itens-INITIAL_FORMS': '0',
        'itens-MIN_NUM_FORMS': '0',
        'itens-MAX_NUM_FORMS': '1000',
        'itens-0-material_id': '',
        'itens-0-quantidade': '',
    }

    def _post_invalido(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        return client.post(URL_NOVA, data=self.DADOS_INVALIDOS)

    def test_post_invalido_traz_o_sumario(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """O guarda de arquivo vê o include; só o POST vê a view montar o contexto.

        `{% erros_do_formulario form formset %}` depende de a view devolver os
        dois nomes no contexto de erro. Uma tag correta sobre um contexto vazio
        renderiza silêncio — que é exatamente a falha que a tela tinha.
        """
        html = self._post_invalido(client, chefe_almoxarifado).content.decode()
        assert 'id="sumario-erros"' in html
        assert 'autofocus' in html
        assert 'problema' in html

    def test_post_invalido_nomeia_o_campo_com_erro(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        html = self._post_invalido(client, chefe_almoxarifado).content.decode()
        assert 'href="#id_observacao"' in html

    def test_erro_de_formset_aparece_uma_vez_so(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """A duplicata que a #125 removeu: sumário no topo e alerta lá embaixo.

        Num viewport de 375px os dois pontos ficam a várias roladas de
        distância, sem marcador de que são o mesmo erro. O usuário lê o total
        no topo, corrige, e reencontra um deles achando que é mais um.
        """
        html = self._post_invalido(client, chefe_almoxarifado).content.decode()
        assert html.count('A saída precisa ter ao menos um item.') == 1

    def test_item_duplicado_conta_um_problema_e_nao_dois(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        """A duplicata que sobrou depois da #125: duas redações, uma falha.

        `BaseItemSaidaExcepcionalFormSet.clean()` anexava o erro à linha ("Este
        material já foi adicionado em outra linha.") e levantava outra frase no
        formset ("Não é permitido adicionar o mesmo material mais de uma vez.").
        A proteção de `coletar_erros` casa mensagens **idênticas**, então as
        duas passavam: o sumário abria com "2 problemas encontrados" para um
        material repetido, e o segundo item não tinha âncora para lugar nenhum.
        """
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '2',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-material_label': material_disponivel.nome,
                'itens-0-quantidade': '1',
                'itens-1-material_id': str(material_disponivel.pk),
                'itens-1-material_label': material_disponivel.nome,
                'itens-1-quantidade': '2',
            },
        )

        html = response.content.decode()
        assert response.status_code == 200
        assert '1 problema encontrado' in html
        assert 'problemas encontrados' not in html
        assert 'mais de uma vez' not in html

    def test_erro_de_formset_leva_a_secao_de_materiais(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """O item sem campo do sumário precisa ser link, e o alvo precisa existir.

        "A saída precisa ter ao menos um item." não pertence a campo nenhum, e
        por isso saía do sumário como texto solto no meio de uma lista de links.
        O sumário anunciava e contava, mas não levava — a terceira coisa que ele
        promete valia só para erro de campo.
        """
        client.force_login(chefe_almoxarifado)
        response = client.post(
            URL_NOVA,
            data={
                'motivo': 'avaria',
                'observacao': 'obs válida',
                'itens-TOTAL_FORMS': '0',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
            },
        )

        html = response.content.decode()
        assert 'href="#sec-materiais"' in html
        assert 'id="sec-materiais"' in html
        assert 'tabindex="-1"' in html


class TestCerimoniaDaSaidaExcepcional:
    """A cerimônia da ação seguia o template, não a consequência.

    Baixa administrativa DIRETA no saldo físico gravava sem confirmação
    nenhuma, enquanto `Autorizar` — que só move reserva — tinha `alertdialog`.
    """

    URL = '/estoque/saidas-excepcionais/nova/'

    def test_tem_modal_de_confirmacao(self, client, chefe_almoxarifado):
        client.force_login(chefe_almoxarifado)
        html = client.get(self.URL).content.decode('utf-8')
        assert 'id="confirmar-saida-excepcional"' in html
        assert 'A gravação não pode ser desfeita.' in html
        # A recapitulação é reconstruída na abertura a partir das linhas
        # visíveis do formset — aqui elas são criadas e removidas no cliente.
        assert 'data-resumo-linhas-de="#itens-container"' in html

    def test_modal_nomeia_o_estoque_onde_a_baixa_cai(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """Não há documento a nomear: é ele que se vai criar. O que responde
        "sobre o quê?" é o estoque — mesma situação do arquivo do SCPI."""
        client.force_login(chefe_almoxarifado)
        html = client.get(self.URL).content.decode('utf-8')
        assert estoque_principal.nome in html

    def test_motivo_nao_vem_pre_selecionado_com_valor_real(
        self, client, chefe_almoxarifado
    ):
        """`Avaria / Deterioração` era o default: quem não olhasse registrava
        "avaria" por omissão. Um select obrigatório cujo default já é uma
        resposta válida não pergunta nada."""
        from apps.estoque.forms import SaidaExcepcionalForm

        assert SaidaExcepcionalForm().fields['motivo'].choices[0][0] == ''
        client.force_login(chefe_almoxarifado)
        html = client.get(self.URL).content.decode('utf-8')
        assert 'Selecione o motivo' in html

    def test_post_invalido_preserva_material_e_unidade_para_a_recapitulacao(
        self, client, chefe_almoxarifado, estoque_principal, material_disponivel
    ):
        """A recapitulação lê `data-material`/`data-unidade` da linha, e num
        re-render por erro nenhum evento de seleção dispara para escrevê-los.

        Sem os atributos vindos do servidor, a tela em que a pessoa está
        corrigindo o formulário mostraria o material como `—` e a quantidade
        sem unidade — justamente na confirmação de uma baixa irreversível.
        """
        client.force_login(chefe_almoxarifado)
        html = client.post(
            self.URL,
            data={
                # Sem `motivo`: o formulário volta inválido e re-renderizado.
                'motivo': '',
                'observacao': '',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': str(material_disponivel.pk),
                'itens-0-material_label': material_disponivel.nome,
                'itens-0-quantidade': '5',
            },
        ).content.decode('utf-8')

        assert f'data-material="{material_disponivel.nome}"' in html
        assert f'data-unidade="{material_disponivel.unidade}"' in html

    def test_material_id_forjado_nao_derruba_o_re_render(
        self, client, chefe_almoxarifado, estoque_principal
    ):
        """Os ids chegam crus do POST, e é o formulário inválido que os traz.

        `pk__in` prepara cada item para o PK inteiro: um `material_id` não
        numérico levantava `ValueError` no meio do render e trocava a página de
        erros do formset por um 500.
        """
        client.force_login(chefe_almoxarifado)
        response = client.post(
            self.URL,
            data={
                'motivo': '',
                'observacao': '',
                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '0',
                'itens-MAX_NUM_FORMS': '1000',
                'itens-0-material_id': 'abc',
                'itens-0-material_label': 'qualquer',
                'itens-0-quantidade': '5',
            },
        )
        assert response.status_code == 200
        assert 'data-unidade=""' in response.content.decode('utf-8')
