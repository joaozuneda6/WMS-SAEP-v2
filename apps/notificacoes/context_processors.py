"""Context processors de notificações."""

from django.db import InterfaceError, OperationalError

from apps.notificacoes.selectors import contagem_de_notificacoes_pendentes


def notificacoes_ctx(request):
    """Injeta a contagem de pendências em todo request de usuário autenticado.

    Pendência, e não "não lidas": o sino contava avisos, e aviso é registro de
    evento passado — o número crescia com o histórico e discordava da fila que
    ele deveria antecipar (issue #175). Passa a contar as requisições em que o
    destinatário ainda pode agir, resposta que vem do domínio (tabela de
    transições + policies). Assim a conta do sino pode ser conferida contra a da
    Fila de autorização sem discordar dela.

    Roda em toda página autenticada, então o seletor filtra no banco pelo estado
    atual e nunca carrega o histórico do usuário para dentro do Python — o custo
    acompanha o tamanho da fila, não o do diário.
    """
    usuario = getattr(request, 'user', None)
    if usuario is None or not usuario.is_authenticated:
        return {'notificacoes_pendentes': 0}
    try:
        count = contagem_de_notificacoes_pendentes(usuario.pk)
    except (OperationalError, InterfaceError):
        # Zero mentiria: é indistinguível de "nada pendente", e um sino que
        # afirma fila vazia sem ter apurado desfaz por outro caminho a garantia
        # da #175 — pior de diagnosticar, porque não há sintoma. `None` diz
        # "não sei", e os dois `{% if %}` de `base_auth.html` (sufixo do
        # aria-label e badge) já o tratam como ausência de contagem.
        #
        # Só INDISPONIBILIDADE é tolerada: banco fora do ar (`OperationalError`)
        # e conexão inutilizável (`InterfaceError`). Não vale `django.db.Error`,
        # que é a base comum e arrastaria junto `ProgrammingError`, `DataError`
        # e `IntegrityError` — defeitos de schema e de query, exatamente o
        # "campo renomeado" e a "regressão de query" que a #183 existe para
        # tornar visíveis. Tolerá-los devolveria o silêncio por uma fresta menor.
        #
        # Defeito de código propaga, como já propaga em
        # `requisicoes.context_processors.flags_de_papel`, que roda
        # `papel_efetivo` sem defesa e está registrado ANTES deste em TEMPLATES:
        # engolir a mesma classe de erro aqui não salvaria requisição nenhuma,
        # só trocaria o sintoma por silêncio.
        count = None
    return {'notificacoes_pendentes': count}
