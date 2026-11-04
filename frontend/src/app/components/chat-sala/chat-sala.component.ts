import { Component, Input } from '@angular/core';
import { ApiService } from '../../services/api.service';

const MSG_ERRO = 'Não foi possível enviar a mensagem. Tente novamente.';

interface MensagemDaSala {
  role: 'user' | 'assistant';
  content: string;
  fontes?: string[];
  piiMasked?: boolean;
}

// Assistente dentro da sala (D107): usa o mesmo chat do aluno, limitado pelo servidor ao curso aberto.
@Component({
  selector: 'app-chat-sala',
  templateUrl: './chat-sala.component.html'
})
export class ChatSalaComponent {
  @Input() cursoId = '';
  @Input() cursoNome = '';

  mensagens: MensagemDaSala[] = [];
  texto = '';
  enviando = false;
  erro = '';

  constructor(private api: ApiService) { }

  get podeEnviar(): boolean {
    return !this.enviando && !!this.texto.trim();
  }

  enviar(): void {
    if (!this.podeEnviar) {
      return;
    }
    const pergunta = this.texto.trim();
    this.enviando = true;
    this.erro = '';
    this.api.sendChatMessage(pergunta, this.cursoId).subscribe({
      next: (r: any) => {
        const fontes = (Array.isArray(r.sources) ? r.sources : []).map((f: any) => f.title).filter(Boolean);
        this.mensagens = [
          ...this.mensagens,
          { role: 'user', content: r.masked_message || pergunta },
          { role: 'assistant', content: r.message, fontes, piiMasked: r.pii_masked === true }
        ];
        this.texto = '';
        this.enviando = false;
      },
      error: () => {
        this.erro = MSG_ERRO;
        this.enviando = false;
      }
    });
  }
}
