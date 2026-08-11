#!/usr/bin/env python3
"""Hook PreToolUse: bloqueia escrita manual em migrations locais.

Migrations deste projeto são artefatos efêmeros (AGENTS.md, .gitignore:17):
não são versionadas e devem ser recriadas do zero via `make setup`.
Escrever uma migration à mão gera trabalho descartável e diverge do
`makemigrations --check --dry-run` executado no CI.

Entrada: JSON do hook via stdin.
Saída: JSON com permissionDecision `deny` quando o path é uma migration.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PADRAO_MIGRATION = re.compile(r'(?:^|/)apps/[^/]+/migrations/[^/]+\.py$')

MENSAGEM = (
    'Bloqueado: `{caminho}` é uma migration local.\n\n'
    'Migrations neste projeto são efêmeras e não versionadas '
    '(AGENTS.md, .gitignore:17). Não crie nem edite arquivos de migration '
    'à mão.\n\n'
    'Para materializar uma mudança de schema, altere `models.py` e rode:\n'
    '  make setup\n\n'
    'A fonte de verdade são models, constraints, índices, regras de domínio '
    'e testes.'
)


def caminho_do_evento(evento: dict) -> str | None:
    entrada = evento.get('tool_input') or {}
    caminho = entrada.get('file_path')
    return caminho if isinstance(caminho, str) and caminho else None


def eh_migration(caminho: str, raiz: Path) -> bool:
    absoluto = Path(caminho)
    if not absoluto.is_absolute():
        absoluto = (raiz / absoluto).resolve()

    if absoluto.name == '__init__.py':
        return False

    return bool(PADRAO_MIGRATION.search(absoluto.as_posix()))


def main() -> int:
    try:
        evento = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    caminho = caminho_do_evento(evento)
    if caminho is None:
        return 0

    raiz = Path(evento.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or Path.cwd())

    if not eh_migration(caminho, raiz):
        return 0

    try:
        relativo = Path(caminho).resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        relativo = caminho

    resposta = {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': MENSAGEM.format(caminho=relativo),
        }
    }
    json.dump(resposta, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())
