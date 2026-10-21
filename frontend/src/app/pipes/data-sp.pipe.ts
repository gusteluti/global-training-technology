import { Pipe, PipeTransform } from '@angular/core';

// D71: o banco e a API gravam UTC ("AAAA-MM-DD HH:MM:SS", sem fuso); a tela mostra o horário de São Paulo,
// sem depender do fuso nem do idioma da máquina. Datas só de dia ("AAAA-MM-DD") não são deslocadas.
const FUSO = 'America/Sao_Paulo';
const SO_DIA = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATA_HORA = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/;

const FORMATO_DATA_HORA = new Intl.DateTimeFormat('pt-BR', {
  timeZone: FUSO, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false
});
const FORMATO_DIA = new Intl.DateTimeFormat('pt-BR', {
  timeZone: FUSO, day: '2-digit', month: '2-digit', year: 'numeric'
});

function partes(formato: Intl.DateTimeFormat, data: Date): Record<string, string> {
  const saida: Record<string, string> = {};
  for (const p of formato.formatToParts(data)) {
    saida[p.type] = p.value;
  }
  return saida;
}

function instante(texto: string): Date | null {
  const m = DATA_HORA.exec(texto.trim());
  if (!m) {
    return null;
  }
  const iso = `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] || '00'}${m[7] ? (m[7] === 'Z' ? 'Z' : m[7]) : 'Z'}`;
  const data = new Date(iso);
  return isNaN(data.getTime()) ? null : data;
}

/** Texto UTC da API -> "dd/MM/aaaa HH:mm" (ou só "dd/MM/aaaa" com soDia) no horário de São Paulo. */
export function formatarDataSP(valor: string | null | undefined, soDia = false): string {
  const texto = (valor || '').trim();
  if (!texto) {
    return '';
  }
  const dia = SO_DIA.exec(texto);
  if (dia) {
    return `${dia[3]}/${dia[2]}/${dia[1]}`;
  }
  const data = instante(texto);
  if (!data) {
    return texto;
  }
  const p = partes(soDia ? FORMATO_DIA : FORMATO_DATA_HORA, data);
  const dataBr = `${p['day']}/${p['month']}/${p['year']}`;
  if (soDia) {
    return dataBr;
  }
  const hora = p['hour'] === '24' ? '00' : p['hour'];
  return `${dataBr} ${hora}:${p['minute']}`;
}

@Pipe({ name: 'dataSP' })
export class DataSpPipe implements PipeTransform {
  transform(valor: string | null | undefined, modo: 'dataHora' | 'dia' = 'dataHora'): string {
    return formatarDataSP(valor, modo === 'dia');
  }
}
