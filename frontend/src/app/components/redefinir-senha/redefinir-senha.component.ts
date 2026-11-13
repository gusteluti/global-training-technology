import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../services/api.service';

const ERRO_SEM_TOKEN = 'Link inválido ou incompleto. Use o link enviado para você.';
const ERRO_NAO_COINCIDEM = 'As senhas não coincidem.';
const ERRO_PADRAO = 'Não foi possível redefinir a senha. Tente novamente.';
// D108: aviso mostrado ao abrir um link inválido, expirado, já usado ou de outra finalidade.
export const AVISO_LINK_INVALIDO = 'Link inválido ou expirado. Peça um novo link para continuar.';

@Component({
  selector: 'app-redefinir-senha',
  templateUrl: './redefinir-senha.component.html'
})
export class RedefinirSenhaComponent implements OnInit {
  token = '';
  password = '';
  confirmar = '';
  error = '';
  mensagem = '';
  enviando = false;
  verificando = false;
  linkInvalido = false;
  readonly avisoLinkInvalido = AVISO_LINK_INVALIDO;

  constructor(private route: ActivatedRoute, private router: Router, private api: ApiService) { }

  ngOnInit() {
    this.token = this.route.snapshot.queryParamMap.get('token') || '';
    if (!this.token) {
      this.error = ERRO_SEM_TOKEN;
      return;
    }
    // D108: confere o link ao abrir, sem consumi-lo. Só 400 (ou link de outra finalidade) é inválido; erro de rede
    // ou limite mostra o formulário, e o envio continua validado pelo servidor.
    this.verificando = true;
    this.api.checkPasswordToken(this.token).subscribe({
      next: r => {
        this.verificando = false;
        this.linkInvalido = r?.valid === false || (!!r?.purpose && r.purpose !== 'reset');
      },
      error: err => {
        this.verificando = false;
        this.linkInvalido = err?.status === 400;
      }
    });
  }

  // O app não define <base href>; o routerLink geraria href absoluto. O href "/" fica explícito e a
  // navegação segue pelo roteador (sem recarregar a página).
  irParaLogin(evento: Event) {
    evento.preventDefault();
    this.router.navigate(['/']);
  }

  submit() {
    if (this.enviando || this.verificando || this.linkInvalido) return;
    if (!this.token) {
      this.error = ERRO_SEM_TOKEN;
      return;
    }
    if (this.password !== this.confirmar) {
      this.error = ERRO_NAO_COINCIDEM;
      return;
    }
    this.error = '';
    this.enviando = true;
    this.api.resetPassword({ token: this.token, password: this.password }).subscribe({
      next: (resposta: any) => {
        this.enviando = false;
        this.mensagem = 'Senha redefinida. Faça login para entrar.';
      },
      error: err => {
        this.enviando = false;
        this.error = err?.error?.detail || ERRO_PADRAO;
      }
    });
  }
}
