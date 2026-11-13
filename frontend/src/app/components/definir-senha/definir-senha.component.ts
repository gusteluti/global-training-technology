import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api.service';

import { AVISO_LINK_INVALIDO } from '../redefinir-senha/redefinir-senha.component';

const ERRO_SEM_TOKEN = 'Link inválido ou incompleto. Use o link enviado para você.';

@Component({
  selector: 'app-definir-senha',
  templateUrl: './definir-senha.component.html'
})
export class DefinirSenhaComponent implements OnInit {
  token = '';
  password = '';
  error = '';
  success = false;
  enviando = false;
  verificando = false;
  linkInvalido = false;
  readonly avisoLinkInvalido = AVISO_LINK_INVALIDO;

  constructor(private route: ActivatedRoute, private api: ApiService) { }

  ngOnInit() {
    this.token = this.route.snapshot.queryParamMap.get('token') || '';
    if (!this.token) {
      this.error = ERRO_SEM_TOKEN;
      return;
    }
    // D108: confere o link ao abrir, sem consumi-lo. Só 400 (ou link de redefinição, que esta tela não aceita) é
    // inválido; erro de rede ou limite mostra o formulário, e o envio continua validado pelo servidor.
    this.verificando = true;
    this.api.checkPasswordToken(this.token).subscribe({
      next: r => {
        this.verificando = false;
        this.linkInvalido = r?.valid === false || (!!r?.purpose && r.purpose !== 'setup');
      },
      error: err => {
        this.verificando = false;
        this.linkInvalido = err?.status === 400;
      }
    });
  }

  submit() {
    if (this.enviando || this.verificando || this.linkInvalido) return;
    if (!this.token) {
      this.error = ERRO_SEM_TOKEN;
      return;
    }
    this.error = '';
    this.enviando = true;
    this.api.setPassword({ token: this.token, password: this.password }).subscribe({
      next: () => {
        this.enviando = false;
        this.success = true;
      },
      error: err => {
        this.enviando = false;
        this.error = err?.error?.detail || 'Não foi possível definir a senha.';
      }
    });
  }
}
