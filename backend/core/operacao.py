"""Operação mínima de SaaS (X3/X4, D90): backup do SQLite e estado dos serviços para o /health.

Backup: cópia consistente pela API de backup do SQLite (funciona com o servidor no ar) para BACKUP_DIR, um arquivo
por dia (`db-AAAAMMDD.sqlite`), mantendo os BACKUP_KEEP mais recentes (padrão 7). Roda no startup quando BACKUP_DIR
está definida; também pode ser chamado à mão: `py -3 -c "from core.operacao import fazer_backup; fazer_backup()"`.
Restaurar: parar o backend e copiar o arquivo escolhido por cima do `db.sqlite`.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from db import Database

PADRAO_MANTER = 7


def _manter() -> int:
    try:
        return max(1, int(os.getenv("BACKUP_KEEP") or PADRAO_MANTER))
    except ValueError:
        return PADRAO_MANTER


def fazer_backup(diretorio: Optional[str] = None, agora: Optional[datetime] = None) -> Optional[Path]:
    """Cria (ou atualiza) o backup do dia e apaga os mais antigos além de BACKUP_KEEP. None sem diretório."""
    destino_dir = diretorio or (os.getenv("BACKUP_DIR") or "").strip()
    if not destino_dir:
        return None
    pasta = Path(destino_dir)
    pasta.mkdir(parents=True, exist_ok=True)
    dia = (agora or datetime.now(timezone.utc)).strftime("%Y%m%d")
    destino = pasta / f"db-{dia}.sqlite"
    temporario = destino.with_suffix(".tmp")
    origem = sqlite3.connect(Database.DB_PATH)
    copia = sqlite3.connect(temporario)
    try:
        origem.backup(copia)
    finally:
        copia.close()
        origem.close()
    os.replace(temporario, destino)
    backups = sorted(pasta.glob("db-*.sqlite"))
    for antigo in backups[:-_manter()]:
        antigo.unlink(missing_ok=True)
    return destino


def ultimo_backup() -> Optional[str]:
    pasta = (os.getenv("BACKUP_DIR") or "").strip()
    if not pasta or not Path(pasta).exists():
        return None
    backups = sorted(Path(pasta).glob("db-*.sqlite"))
    return backups[-1].name if backups else None


def verificar_servicos() -> Dict[str, str]:
    """Estado de cada dependência, sem chamar serviço externo pago (o LLM não é chamado)."""
    estado = {}
    try:
        conn = sqlite3.connect(Database.DB_PATH, timeout=5)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        estado["database"] = "ok"
    except Exception:
        estado["database"] = "erro"
    estado["llm"] = "configurado" if (os.getenv("GROQ_API_KEY") or "").strip() else "nao_configurado"
    estado["payment_gateway"] = ("configurado" if (os.getenv("MERCADO_PAGO_ACCESS_TOKEN") or "").strip()
                                 else "nao_configurado")
    estado["email"] = "configurado" if (os.getenv("SMTP_HOST") or "").strip() else "nao_configurado"
    estado["backup"] = ultimo_backup() or ("nenhum" if (os.getenv("BACKUP_DIR") or "").strip() else "desligado")
    return estado
