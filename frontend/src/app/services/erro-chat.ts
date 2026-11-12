// Erro ao enviar mensagem no chat do aluno (Área do aluno e sala do curso).
export const MSG_ERRO_CHAT = 'Não foi possível enviar a mensagem. Tente novamente.';

// D108: no limite de mensagens (429) o aluno vê o aviso que o servidor mandou (`message` ou `detail`);
// qualquer outro erro continua com a mensagem genérica.
export function mensagemDeErroDoChat(err: any): string {
  if (err?.status === 429) {
    const corpo = err?.error;
    const texto = typeof corpo?.message === 'string' ? corpo.message : corpo?.detail;
    if (typeof texto === 'string' && texto.trim()) {
      return texto.trim();
    }
  }
  return MSG_ERRO_CHAT;
}
