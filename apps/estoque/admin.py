from django.contrib import admin

from apps.estoque.models import (
    Material,
    Estoque,
    SaldoEstoque,
    SaidaExcepcional,
    ItemSaidaExcepcional,
    SequenciaSaidaExcepcional,
    ImportacaoSCPI,
    MovimentacaoEstoque,
)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'unidade', 'ativo')
    list_filter = ('unidade', 'ativo')
    search_fields = ('codigo', 'nome')
    ordering = ('nome',)

    def _pode_gerir(self, request):
        from apps.accounts.papeis import papel_efetivo
        from apps.estoque.policies import pode_gerir_catalogo

        return pode_gerir_catalogo(papel_efetivo(request.user))

    def has_add_permission(self, request):
        return self._pode_gerir(request)

    def has_change_permission(self, request, obj=None):
        return self._pode_gerir(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Captura erro de domínio de `save_model` e o exibe como mensagem.

        O nível segue o mapeamento de `docs/CONVENTIONS.md`: conflito de estado
        é `warning` (a ação não foi aplicada, mas o estado atual é
        compreensível); dado inválido é `error` (o usuário precisa corrigir).
        """
        from django.contrib import messages
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseRedirect

        from apps.core.exceptions import (
            ConflitoDominio,
            ErroDominio,
            EstadoInvalido,
            PermissaoNegada,
        )

        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except PermissaoNegada as exc:
            raise PermissionDenied(str(exc)) from exc
        except (EstadoInvalido, ConflitoDominio) as exc:
            self.message_user(request, str(exc), level=messages.WARNING)
            return HttpResponseRedirect(request.get_full_path())
        except ErroDominio as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

    def save_model(self, request, obj, form, change):
        if change and 'ativo' in form.changed_data and not obj.ativo:
            from apps.estoque.services import desativar_material

            desativar_material(ator_id=request.user.pk, material_id=obj.pk)
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied(
            "Materiais não podem ser excluídos. Use o campo 'ativo' para desativar."
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        return actions


@admin.register(Estoque)
class EstoqueAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('codigo', 'nome')
    ordering = ('nome',)

    def has_add_permission(self, request):
        """Barra a criação de um segundo Estoque (ADR-0017).

        Os services de estoque assumem um único `Estoque` nesta fase: localizam
        saldo só por `material_id` e tratam multiplicidade como erro. Um segundo
        estoque com saldo para material já usado quebraria autorização,
        separação, atendimento e cancelamento de qualquer setor.
        """
        return super().has_add_permission(request) and not Estoque.objects.exists()


@admin.register(SaldoEstoque)
class SaldoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        'estoque',
        'material',
        'saldo_fisico',
        'saldo_reservado',
        'saldo_disponivel',
        'divergente',
    )
    list_filter = ('estoque', 'material')
    search_fields = ('estoque__nome', 'material__nome', 'material__codigo')
    ordering = ('estoque', 'material')
    readonly_fields = (
        'saldo_fisico',
        'saldo_reservado',
        'saldo_disponivel',
        'divergente',
    )

    # Saldo é derivado do ledger (ADR-0015): toda mutação nasce de um service
    # que emite `MovimentacaoEstoque` na mesma transação (LED-01), e a soma dos
    # deltas tem de reconciliar com o saldo (LED-02). Criar, apagar ou reatribuir
    # o `material` de uma linha pelo admin quebra a reconciliação sem deixar
    # rastro. Leitura fica aberta.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemSaidaExcepcionalInline(admin.TabularInline):
    model = ItemSaidaExcepcional
    extra = 1

    # `InlineModelAdmin.has_add_permission` não herda de `SaidaExcepcionalAdmin`
    # — sem guard próprio, um staff com permissão Django de `ItemSaidaExcepcional`
    # continuaria adicionando/mudando itens pelo formset mesmo com o parent
    # bloqueado.
    def has_add_permission(self, request, obj):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SaidaExcepcional)
class SaidaExcepcionalAdmin(admin.ModelAdmin):
    list_display = (
        'numero_publico',
        'estoque',
        'registrado_por',
        'criado_em',
        'estado',
    )
    list_filter = ('estado', 'estoque', 'criado_em')
    search_fields = ('numero_publico', 'estoque__nome')
    ordering = ('-criado_em',)
    inlines = [ItemSaidaExcepcionalInline]

    # Criar/mudar/apagar pelo admin gera documento sem baixa de saldo e sem
    # ledger (EST-saida-01 só vale no service `registrar_saida_excepcional`).
    # Leitura via changelist fica aberta.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SequenciaSaidaExcepcional)
class SequenciaSaidaExcepcionalAdmin(admin.ModelAdmin):
    list_display = ('ano', 'ultimo_numero')
    ordering = ('-ano',)
    readonly_fields = ('ano', 'ultimo_numero')

    # Linha nasce por `get_or_create` no service na primeira emissão de
    # número do ano; sem caminho legítimo de add pelo admin. Regredir
    # `ultimo_numero` à mão colide com `numero_publico` unique no próximo
    # envio (`IntegrityError` → 500). Apagar ou trocar `ano` tem o mesmo
    # efeito prático: o ano original fica sem sequência e o próximo
    # `get_or_create` recria do zero, reemitindo números já usados.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImportacaoSCPI)
class ImportacaoSCPIAdmin(admin.ModelAdmin):
    list_display = (
        'arquivo_nome',
        'estoque',
        'importado_por',
        'importado_em',
        'status',
        'total_novos',
    )
    list_filter = ('status', 'estoque', 'importado_em')
    search_fields = ('arquivo_nome', 'estoque__nome')
    ordering = ('-importado_em',)
    readonly_fields = ('arquivo_hash', 'importado_em')

    # Importação nasce por `confirmar_importacao_scpi`; add manual não tem
    # caminho legítimo (sem CSV nem preview por trás). `status`/`total_*`/
    # `importado_por` são metadados de auditoria da confirmação — editá-los
    # falsifica a trilha de quem importou o quê. Apagar libera reimportação
    # do mesmo arquivo (dedup por `arquivo_hash`).
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        'tipo',
        'material',
        'estoque',
        'delta_fisico',
        'delta_reservado',
        'criado_em',
    )
    list_filter = ('tipo', 'estoque', 'criado_em')
    search_fields = ('material__nome', 'material__codigo')
    ordering = ('-criado_em',)
    readonly_fields = ('criado_em',)

    # Ledger imutável (LED-01/LED-02): toda linha nasce de um service que
    # também muta o saldo na mesma transação. Add pelo admin insere ledger
    # sem tocar o saldo; change/delete colidiriam com `save()`/`delete()` do
    # model, que já levantam `MovimentacaoEstoqueImutavel` — sem o guard aqui
    # isso vira 500 em vez de 403. Leitura fica aberta.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
