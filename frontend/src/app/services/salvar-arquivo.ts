import { HttpResponse } from '@angular/common/http';

// Nome do arquivo no Content-Disposition (`attachment; filename="x.csv"`); sem cabeçalho, vale o padrão.
export function nomeDoArquivo(resposta: HttpResponse<Blob>, padrao: string): string {
  const cabecalho = resposta.headers.get('Content-Disposition') || '';
  const achado = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cabecalho);
  const nome = achado ? decodeURIComponent(achado[1].trim()) : '';
  return nome || padrao;
}

// Salva o Blob baixado (U1, D74). O download é feito pelo HttpClient para o token ir no cabeçalho.
export function salvarArquivo(resposta: HttpResponse<Blob>, padrao: string): void {
  const blob = resposta.body;
  if (!blob) {
    return;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = nomeDoArquivo(resposta, padrao);
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
