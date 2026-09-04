"""Configurações da implantação piloto.

Herda de ``base`` e endurece o que ``dev`` afrouxa: ``DEBUG`` desligado, hosts e
origens confiáveis obrigatórios, cookies restritos a HTTPS e os cabeçalhos de
segurança que ``manage.py check --deploy`` cobra.

Também recusa a inicialização quando ``DATABASE_URL`` não aponta para
PostgreSQL — ver ``config.settings.guardas``. Falhar no boot é deliberado: o
modo de falha oposto (subir com SQLite) é silencioso.
"""

import environ

from .base import *  # noqa: F401,F403
from .base import DATABASES
from .guardas import (
    exigir_bancos_postgresql,
    exigir_hosts_permitidos,
    exigir_origens_csrf_confiaveis,
)


# Instância própria, sem o schema de `base`. Lá, `ALLOWED_HOSTS` tem default
# `[]`, e reusar aquele `env` faria a variável ausente virar lista vazia sem
# ruído — exatamente o default permissivo que o piloto não pode ter. Sem schema,
# variável ausente levanta `ImproperlyConfigured` no import.
env_piloto = environ.Env()

# A atribuição vem DEPOIS do `import *` de propósito: `base` lê `DEBUG` do
# ambiente, e é esta linha que garante que `DEBUG=true` no ambiente do piloto
# não reabra o modo debug. Mover isto para antes do import quebraria a garantia
# silenciosamente.
DEBUG = False

# `env.list` faz o parsing; as guardas validam o valor bruto antes, porque o
# parsing descarta itens vazios e transformaria `ALLOWED_HOSTS=,,` em `[]`.
ALLOWED_HOSTS = exigir_hosts_permitidos(
    env_piloto.str('ALLOWED_HOSTS'),
    env_piloto.list('ALLOWED_HOSTS'),
)
CSRF_TRUSTED_ORIGINS = exigir_origens_csrf_confiaveis(
    env_piloto.str('CSRF_TRUSTED_ORIGINS'),
    env_piloto.list('CSRF_TRUSTED_ORIGINS'),
)

exigir_bancos_postgresql(DATABASES)


# Cookies e cabeçalhos de segurança

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = True

# HSTS fica gravado no navegador de quem visitou, e não há como revogar
# remotamente: se o domínio do piloto precisar servir HTTP depois — desativação,
# reaproveitamento —, os navegadores continuam forçando HTTPS até o `max-age`
# expirar, e `includeSubDomains` estende isso aos subdomínios. Num ambiente de
# validação isso é risco real, então o default é curto e a subida é deliberada:
# confirme que todo o tráfego funciona em HTTPS, depois aumente por etapas
# (1h → 1 dia → 1 semana → 1 ano).
SECURE_HSTS_SECONDS = env_piloto.int('PILOTO_HSTS_SECONDS', default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Os navegadores só consideram `preload` a partir de `max-age` de 1 ano, e a
# entrada na lista exige submissão manual do domínio — a diretiva aqui declara a
# intenção e satisfaz o `check --deploy`, não inscreve nada sozinha.
SECURE_HSTS_PRELOAD = True

X_FRAME_OPTIONS = 'DENY'

# ---------------------------------------------------------------------------
# Estáticos com hash no nome (cache busting)
# ---------------------------------------------------------------------------
#
# Sem isto o `app.css` — 57 KB, regenerado a cada `make css-build` — e os dez
# arquivos de JS são servidos sempre na mesma URL. O navegador que já os tem em
# cache continua com a versão antiga depois do deploy, e o defeito que aparece
# é o pior tipo: template novo com CSS velho, ou um `x-data` que referencia uma
# factory Alpine que o JS em cache não registra. O sintoma é
# `saldoLinha is not defined` no console e a tela renderizando quase certa —
# aconteceu duas vezes durante a Etapa 8, em desenvolvimento.
#
# `ManifestStaticFilesStorage` de fábrica: gerado no `collectstatic` e lido do
# disco, sem depender de cache em memória por processo. Consequência operacional: `collectstatic` passa a ser obrigatório
# no deploy, e ele **falha alto** se um template referenciar um estático que
# não existe — que é o comportamento desejado.
#
# `apps/core/static/core/css/input.css` (a fonte do Tailwind) não mora mais
# nesta árvore — ela vive em `assets/css/input.css`, fora de `STATIC_ROOT` —
# então não há mais um `@import "tailwindcss"` para o pós-processamento
# tropeçar, e o backend customizado que existia só para contornar isso saiu.
#
# Só no piloto. Em `dev` o servidor de desenvolvimento serve direto da árvore
# de origem e um manifesto obrigaria a rodar `collectstatic` a cada mudança de
# CSS.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

# Opt-in: confiar em `X-Forwarded-Proto` sem um proxy que sobrescreva o cabeçalho
# deixa qualquer cliente se declarar HTTPS. Sem isso, porém, `SECURE_SSL_REDIRECT`
# entra em laço de redirecionamento atrás de um proxy que termina TLS. Ligue
# apenas quando houver esse proxy na frente.
if env_piloto.bool('PILOTO_ATRAS_DE_PROXY_TLS', default=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # Mesma condição, mesma razão: confiar em `X-Forwarded-For` para identificar
    # o cliente exige um proxy na frente que sobrescreva o cabeçalho. Sem proxy,
    # o cliente escolheria o próprio IP e escaparia do lockout (ADR-0018)
    # trocando o cabeçalho a cada tentativa.
    #
    # `REMOTE_ADDR` fica como segundo item porque esta lista SUBSTITUI o default
    # `('REMOTE_ADDR',)` em vez de estendê-lo. Mas ele **não** é uma rede de
    # segurança geral: `AXES_IPWARE_PROXY_COUNT` faz o ipware validar a
    # contagem de proxies por origem, e `REMOTE_ADDR` sozinho tem zero proxies,
    # logo é descartado. Requisição que não passou pelo proxy resolve IP `None`
    # e a tentativa fica chaveada só pela matrícula — ainda bloqueia, sem
    # contaminar outros usuários, mas é sinal de que alguém alcançou o Django
    # por fora. O GL-02 cobra que isso seja impossível na implantação.
    AXES_IPWARE_META_PRECEDENCE_ORDER = ['HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']
    AXES_IPWARE_PROXY_COUNT = 1
