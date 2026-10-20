"""Backend de teste dos e2e da F6 (handoff para o WhatsApp, D77). Não é código de produção.

É exatamente o backend da F5b (`servidor_e2e_f5b.py`: harness D58, catálogo do bot no diretório temporário de cursos,
Groq falso que ecoa a última mensagem), com o handoff LIGADO por um número FABRICADO em `WHATSAPP_HANDOFF_NUMBER`
(nunca o número real do PM) e o orçamento padrão (`CHAT_TOKEN_BUDGET` removido). As variáveis são definidas à força
no processo do backend, antes do import do app; um `backend/.env` não as sobrescreve (o python-dotenv não troca
variável já definida). Importar este módulo (para ler a constante) não mexe no ambiente de quem importa.

Uso (feito pelo teste, não à mão): mesmos argumentos do `servidor_e2e_f5b.py`.
"""

import os
import sys
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

NUMERO_FABRICADO = "5511900000000"


def main() -> None:
    os.environ["WHATSAPP_HANDOFF_NUMBER"] = NUMERO_FABRICADO
    os.environ.pop("CHAT_TOKEN_BUDGET", None)
    import servidor_e2e_f5b as f5b  # noqa: PLC0415

    f5b.main()


if __name__ == "__main__":
    main()
