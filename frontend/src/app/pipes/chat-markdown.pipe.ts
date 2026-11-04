import { Pipe, PipeTransform } from '@angular/core';

function escapar(texto: string): string {
  return texto.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Markdown da resposta do assistente, nas mesmas regras do chat da landing. Escapa antes de formatar: texto do modelo
// nunca vira HTML próprio, e link vira só o texto, porque links do chat saem como botões montados pelo servidor.
@Pipe({ name: 'chatMarkdown' })
export class ChatMarkdownPipe implements PipeTransform {
  transform(texto: string | null | undefined): string {
    const formatado = escapar(texto || '')
      .replace(/\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g, '$1')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(\S(?:.*?\S)?)\*/g, '<em>$1</em>')
      .replace(/&lt;br\s*\/?&gt;/gi, '<br>');

    let html = '';
    let lista: string | null = null;
    let tabela = false;
    const fecharLista = () => {
      if (lista) {
        html += `</${lista}>`;
        lista = null;
      }
    };
    const fecharTabela = () => {
      if (tabela) {
        html += '</table>';
        tabela = false;
      }
    };
    for (const bruta of formatado.split('\n')) {
      const linha = bruta.trim();
      if (/^\|.*\|$/.test(linha)) {
        fecharLista();
        if (!/^\|[\s:|-]+\|$/.test(linha)) {
          const celulas = linha.slice(1, -1).split('|').map(celula => `<td>${celula.trim()}</td>`).join('');
          html += `${tabela ? '' : '<table class="table table-sm">'}<tr>${celulas}</tr>`;
          tabela = true;
        }
        continue;
      }
      fecharTabela();
      const marcador = /^[*+-]\s+(.*)$/.exec(linha);
      const numero = /^\d+\.\s+(.*)$/.exec(linha);
      const item = marcador || numero;
      if (item) {
        const tipo = marcador ? 'ul' : 'ol';
        if (lista !== tipo) {
          fecharLista();
          html += `<${tipo}>`;
          lista = tipo;
        }
        html += `<li>${item[1]}</li>`;
      } else {
        fecharLista();
        if (linha) {
          html += `<p>${linha}</p>`;
        }
      }
    }
    fecharLista();
    fecharTabela();
    return html;
  }
}
