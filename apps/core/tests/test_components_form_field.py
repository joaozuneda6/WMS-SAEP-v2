"""Testes diretos de components/form_field.html (sem DB, sem view)."""

from django import forms
from django.template.loader import render_to_string


class _FormDeTeste(forms.Form):
    nome = forms.CharField(
        label='Nome completo',
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Digite seu nome'}),
    )
    apelido = forms.CharField(label='Apelido', required=False)
    bio = forms.CharField(
        label='Biografia',
        required=False,
        help_text='Até 200 caracteres.',
        widget=forms.Textarea,
    )


def _render(field_name='nome', form=None, **ctx):
    form = form or _FormDeTeste()
    ctx.setdefault('field', form[field_name])
    return render_to_string('components/form_field.html', ctx)


def test_label_vinculada_ao_input_via_for_e_id():
    html = _render()
    form = _FormDeTeste()
    id_campo = form['nome'].id_for_label
    assert f'for="{id_campo}"' in html
    assert f'id="{id_campo}"' in html


def test_usa_label_do_field_por_padrao():
    html = _render()
    assert 'Nome completo' in html


def test_label_override_sobrescreve_label_do_field():
    html = _render(label_override='Nome customizado')
    assert 'Nome customizado' in html
    assert 'Nome completo' not in html


def test_campo_obrigatorio_mostra_asterisco_automaticamente():
    html = _render(field_name='nome')
    assert 'aria-hidden="true">*</span>' in html


def test_campo_opcional_nao_mostra_asterisco_por_padrao():
    html = _render(field_name='apelido')
    assert '*</span>' not in html


def test_required_marker_true_forca_asterisco_em_campo_opcional():
    html = _render(field_name='apelido', required_marker=True)
    assert 'aria-hidden="true">*</span>' in html


def test_required_marker_false_esconde_asterisco_em_campo_obrigatorio():
    html = _render(field_name='nome', required_marker=False)
    assert '*</span>' not in html


def test_help_text_do_field_e_exibido():
    html = _render(field_name='bio')
    assert 'Até 200 caracteres.' in html


def test_help_text_ausente_nao_renderiza_paragrafo_de_ajuda():
    html = _render(field_name='nome')
    assert '-ajuda' not in html


def test_help_text_param_sobrescreve_help_text_do_field():
    html = _render(field_name='bio', help_text='Ajuda customizada')
    assert 'Ajuda customizada' in html
    assert 'Até 200 caracteres.' not in html


def test_erro_renderiza_com_role_alert():
    form = _FormDeTeste(data={})
    form.is_valid()
    html = _render(field_name='nome', form=form)
    assert 'role="alert"' in html
    assert 'obrigatório' in html or 'required' in html.lower()


def test_sem_erro_nao_renderiza_paragrafo_de_erro():
    html = _render(field_name='apelido')
    assert '-erro"' not in html


def test_label_class_default_usa_a_classe_unica_de_rotulo():
    html = _render()
    assert 'class="rotulo-campo"' in html


def test_rotulo_campo_carrega_a_regua_ate_o_campo():
    """A classe existe e traz o espaçamento junto — não só a tipografia.

    O componente entrega só o nome da classe; se `.rotulo-campo` perder a
    `margin-bottom`, o rótulo volta a encostar no campo em todos os
    formulários de uma vez, e nenhum teste de marcação perceberia.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    css = (raiz / 'assets/css/input.css').read_text()
    bloco = css[
        css.index('.rotulo-campo {') : css.index('}', css.index('.rotulo-campo {'))
    ]
    assert 'margin-bottom' in bloco
    assert 'text-transform: uppercase' in bloco
    assert 'letter-spacing' in bloco


def test_label_class_customizado_sobrescreve_default():
    html = _render(label_class='sr-only')
    assert 'sr-only' in html
    assert 'rotulo-campo' not in html


def test_class_passthrough_no_wrapper():
    html = _render(**{'class': 'meu-ajuste-customizado'})
    assert 'meu-ajuste-customizado' in html


def test_aria_describedby_compoe_ajuda_e_erro_juntos():
    form = _FormDeTeste(data={'nome': ''})
    form.is_valid()

    class _FormComAjudaEErro(forms.Form):
        campo = forms.CharField(required=True, help_text='Ajuda aqui')

    form2 = _FormComAjudaEErro(data={})
    form2.is_valid()
    html = _render(field_name='campo', form=form2)
    id_campo = form2['campo'].id_for_label
    assert f'aria-describedby="{id_campo}-ajuda {id_campo}-erro"' in html


def test_widget_required_nativo_preservado():
    html = _render(field_name='nome')
    assert 'required' in html
    assert 'placeholder="Digite seu nome"' in html
