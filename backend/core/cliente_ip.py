"""IP real do cliente atrás de proxy confiável (SG3, D109 P4; revisa a D79).

Função única usada pelo limite de taxa (`rate_limit`) e pelo limite de login (`login_limit`).

Variável `TRUSTED_PROXIES`: IPs e CIDRs (IPv4 e IPv6) separados por vírgula, lida a CADA requisição. Vazia ou
ausente = só o par TCP (`request.client.host`); o cabeçalho é ignorado. Entradas inválidas são ignoradas.

Regra, só quando o par TCP está em `TRUSTED_PROXIES` (senão o cabeçalho é ignorado: anti-spoof):
  - lê `X-Forwarded-For` da direita para a esquerda e pula os itens que são proxies confiáveis;
  - o primeiro item que não é proxy é o cliente; se ele for malformado, vale o par TCP;
  - tudo à esquerda desse item é ignorado (quem controla é o cliente);
  - se todos os itens são proxies, vale o mais à esquerda.
Só `X-Forwarded-For` conta (`X-Real-IP` e `Forwarded` são ignorados). IPv6 sai comprimido e em minúsculas.
"""

import ipaddress
import os
from typing import List, Optional, Union

from fastapi import Request

_IP = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
_REDE = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def _como_ip(texto: str) -> Optional[_IP]:
    """IP puro ou None. Recusa porta, colchetes, escopo (`%`) e qualquer coisa que `ipaddress` não aceite."""
    texto = (texto or "").strip()
    if not texto or "%" in texto:
        return None
    try:
        return ipaddress.ip_address(texto)
    except ValueError:
        return None


def _proxies_confiaveis() -> List[_REDE]:
    redes: List[_REDE] = []
    for entrada in os.environ.get("TRUSTED_PROXIES", "").split(","):
        entrada = entrada.strip()
        if not entrada or "%" in entrada:
            continue
        try:
            redes.append(ipaddress.ip_network(entrada, strict=False))
        except ValueError:
            continue
    return redes


def _e_proxy(ip: _IP, redes: List[_REDE]) -> bool:
    return any(ip.version == rede.version and ip in rede for rede in redes)


def ip_do_cliente(request: Request) -> Optional[str]:
    """IP efetivo do cliente (texto) ou None se não há par TCP."""
    host = request.client.host if request.client and request.client.host else None
    if host is None:
        return None
    par = _como_ip(host)
    if par is None:
        return host  # não é IP (ex.: "testclient"): nunca é proxy; sai como está
    efetivo_do_par = str(par)
    redes = _proxies_confiaveis()
    if not redes or not _e_proxy(par, redes):
        return efetivo_do_par
    cabecalho = ",".join(request.headers.getlist("x-forwarded-for"))
    itens = cabecalho.split(",")
    ultimo: Optional[_IP] = None
    for texto in reversed(itens):
        ip = _como_ip(texto)
        if ip is None:
            return efetivo_do_par
        if not _e_proxy(ip, redes):
            return str(ip)
        ultimo = ip
    # todos os itens são proxies: o mais à esquerda
    return str(ultimo) if ultimo is not None else efetivo_do_par
