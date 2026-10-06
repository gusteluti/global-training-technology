import { Component } from '@angular/core';
import { ApiService } from '../../services/api.service';

const ERRO_REDE = 'Não foi possível enviar o pedido. Tente novamente.';

@Component({
  selector: 'app-esqueci-senha',
  templateUrl: './esqueci-senha.component.html'
})
export class EsqueciSenhaComponent {
  email = '';
  mensagem = '';
  erro = '';
  enviando = false;

  constructor(private api: ApiService) { }

  submit() {
    if (this.enviando) return;
    this.mensagem = '';
    this.erro = '';
    this.enviando = true;
    this.api.requestPasswordReset({ email: this.email }).subscribe({
      next: (resposta: any) => {
        this.enviando = false;
        // A API responde sempre com a mesma mensagem, exista a conta ou não.
        this.mensagem = resposta?.message || '';
        if (!this.mensagem) {
          this.erro = ERRO_REDE;
        }
      },
      error: () => {
        this.enviando = false;
        this.erro = ERRO_REDE;
      }
    });
  }
}
