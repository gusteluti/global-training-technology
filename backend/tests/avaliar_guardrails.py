"""Avaliação adversarial dos guardrails (GR, D94/D95). Mede bloqueio e falso positivo do conjunto versionado.

Uso, a partir de backend/:
    python tests/avaliar_guardrails.py          # só as heurísticas, sem rede
    python tests/avaliar_guardrails.py --llm    # inclui o classificador real (usa a GROQ_API_KEY do backend/.env)
"""

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.guardrails import ContextoSaida, classificar_saida, conteudo_improprio  # noqa: E402
from agents.llm_guard import InputBlockedError, entrada_bloqueada  # noqa: E402

CONJUNTO = Path(__file__).with_name("guardrails_conjunto.json")


def carregar() -> Dict:
    return json.loads(CONJUNTO.read_text(encoding="utf-8"))


def contexto_de_avaliacao() -> ContextoSaida:
    return ContextoSaida(
        precos={Decimal("232.00")},
        catalogo="curso de Python e Excel",
        vocabulario={"python", "excel"},
        nomes_de_turma={"noite"},
        datas={(10, 8)},
        dominios={"wa.me"},
    )


def barrada_pela_heuristica(mensagem: str) -> bool:
    return entrada_bloqueada(mensagem) or conteudo_improprio(mensagem)


def _taxa(acertos: int, total: int) -> float:
    return round(acertos / total, 4) if total else 0


def medir(barrar: Callable[[str], bool] = barrada_pela_heuristica, camadas=("heuristica",)) -> Dict:
    conjunto = carregar()
    ataques = [a for a in conjunto["ataques"] if a["camada"] in camadas]
    passaram = [a["texto"] for a in ataques if not barrar(a["texto"])]
    falsos = [m for m in conjunto["legitimas"] if barrar(m)]
    contexto = contexto_de_avaliacao()
    saidas_ruins = conjunto["saidas_ruins"]
    saidas_errado = [s["texto"] for s in saidas_ruins if classificar_saida(s["texto"], contexto)[1] != s["tipo"]]
    saidas_falsas = [s for s in conjunto["saidas_boas"] if classificar_saida(s, contexto)[1] is not None]
    return {
        "bloqueio_entrada": _taxa(len(ataques) - len(passaram), len(ataques)),
        "falso_positivo_entrada": _taxa(len(falsos), len(conjunto["legitimas"])),
        "bloqueio_saida": _taxa(len(saidas_ruins) - len(saidas_errado), len(saidas_ruins)),
        "falso_positivo_saida": _taxa(len(saidas_falsas), len(conjunto["saidas_boas"])),
        "ataques_que_passaram": passaram,
        "falsos_positivos": falsos,
        "saidas_nao_barradas": saidas_errado,
        "saidas_falsas": saidas_falsas,
    }


def _barrar_com_llm():
    from agents.manager_agent import ManagerAgent

    agente = ManagerAgent()
    agente.load_courses()

    def barrar(mensagem: str) -> bool:
        if barrada_pela_heuristica(mensagem):
            return True
        try:
            agente.identify_course_intent(mensagem)
        except InputBlockedError:
            return True
        return False

    return barrar


def main(argv: Optional[List[str]] = None) -> None:
    usar_llm = "--llm" in (argv if argv is not None else sys.argv[1:])
    if usar_llm:
        resultado = medir(_barrar_com_llm(), ("heuristica", "classificador"))
    else:
        resultado = medir()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
