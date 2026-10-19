import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../services/api.service';

const ERRO_SEM_TOKEN = 'Link inválido ou incompleto. Use o link enviado para você.';
const ERRO_NAO_COINCIDEM = 'As senhas não coincidem.';
const ERRO_PADRAO = 'Não foi possível redefinir a senha. Tente novamente.';

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

  constructor(private route: ActivatedRoute, private router: Router, private api: ApiService) { }

  ngOnInit() {
    this.token = this.route.snapshot.queryParamMap.get('token') || '';
    if (!this.token) {
      this.error = ERRO_SEM_TOKEN;
    }
  }

  // O app não define <base href>; o routerLink geraria href absoluto. O href "/" fica explícito e a
  // navegação segue pelo roteador (sem recarregar a página).
  irParaLogin(evento: Event) {
    evento.preventDefault();
    this.router.navigate(['/']);
  }

  submit() {
    if (this.enviando) return;
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
