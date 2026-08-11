from django.contrib import admin

from apps.requisicoes.models import (
    Requisicao,
    ItemRequisicao,
    SequenciaRequisicao,
    TimelineRequisicao,
)


# Quantidades derivadas: `solicitada` nasce na criação da requisição,
# `autorizada` na autorização e `entregue` no atendimento — sempre por service,
# com timeline e movimentação de estoque na mesma transação.
QUANTIDADES_READONLY = (
    'quantidade_solicitada',
    'quantidade_autorizada',
    'quantidade_entregue',
)


class ItemRequisicaoInline(admin.TabularInline):
    """Itens da requisição em modo consulta.

    Some do formulário, mas não da tela: `has_view_permission` segue no
    default, então `get_inline_instances` mantém a inline e o superusuário
    continua vendo os itens da requisição que foi diagnosticar.
    """

    model = ItemRequisicao
    extra = 0
    can_delete = False
    readonly_fields = QUANTIDADES_READONLY

    def has_add_permission(self, request, obj):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Requisicao)
class RequisicaoAdmin(admin.ModelAdmin):
    list_display = (
        'numero_publico',
        'beneficiario',
        'criador',
        'setor_beneficiario',
        'estado',
        'criado_em',
    )
    list_filter = ('estado', 'setor_beneficiario', 'criado_em')
    search_fields = ('numero_publico', 'beneficiario__nome', 'criador__nome')
    ordering = ('-criado_em',)
    inlines = [ItemRequisicaoInline]
    fieldsets = (
        ('Informações Gerais', {'fields': ('numero_publico', 'estado')}),
        ('Pessoas', {'fields': ('criador', 'beneficiario', 'setor_beneficiario')}),
        ('Observações', {'fields': ('observacao_geral',)}),
        ('Datas', {'fields': ('criado_em', 'atualizado_em'), 'classes': ('collapse',)}),
    )
    # `estado` é derivado da máquina de estados: muda por service, com timeline
    # e ledger na mesma transação. `criador`/`beneficiario`/`setor_beneficiario`
    # roteiam a fila de autorização — trocá-los pelo admin pula a máquina de
    # estados. Todos seguem visíveis no fieldset (o superusuário precisa deles
    # para diagnosticar), mas fora do formulário.
    readonly_fields = (
        'numero_publico',
        'estado',
        'criador',
        'beneficiario',
        'setor_beneficiario',
        'criado_em',
        'atualizado_em',
    )

    # Os três campos de pessoa são FK sem `null=True`: readonly sem bloquear
    # add deixaria o POST de criação sem valor pra eles, e cai em
    # `IntegrityError` (NOT NULL) em vez de 403. Criação passa a ser exclusiva
    # do service `criar_requisicao`. Delete apaga timeline em cascata e o
    # número público, violando REQ-08.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ItemRequisicao)
class ItemRequisicaoAdmin(admin.ModelAdmin):
    list_display = (
        'requisicao',
        'material',
        'quantidade_solicitada',
        'quantidade_autorizada',
        'quantidade_entregue',
    )
    list_filter = ('requisicao__estado', 'material')
    search_fields = ('requisicao__numero_publico', 'material__nome', 'material__codigo')
    ordering = ('requisicao', 'id')
    readonly_fields = QUANTIDADES_READONLY

    # Item é criado por `criar_requisicao`/`copiar_requisicao` e mudado por
    # autorizar/atender. Não há caminho legítimo pelo admin: criar a linha
    # escreveria `quantidade_solicitada`, apagá-la zeraria as três de uma vez, e
    # trocar o `material` deixaria a reserva pendurada no material antigo.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SequenciaRequisicao)
class SequenciaRequisicaoAdmin(admin.ModelAdmin):
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


@admin.register(TimelineRequisicao)
class TimelineRequisicaoAdmin(admin.ModelAdmin):
    list_display = ('requisicao', 'evento', 'ator', 'estado_resultante', 'criado_em')
    list_filter = ('evento', 'estado_resultante', 'criado_em')
    search_fields = ('requisicao__numero_publico', 'ator__nome')
    ordering = ('-criado_em',)
    readonly_fields = ('criado_em',)

    # Log append-only (ADR-0002): eventos são escritos pelos services de
    # transição e correção entra como evento novo, nunca como edição ou delete.
    # Leitura fica aberta — a trilha só cumpre REQ-08 se for consultável.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
