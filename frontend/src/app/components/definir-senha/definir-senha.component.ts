import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api.service';

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

  constructor(private route: ActivatedRoute, private api: ApiService) { }

  ngOnInit() {
    this.token = this.route.snapshot.queryParamMap.get('token') || '';
    if (!this.token) {
      this.error = ERRO_SEM_TOKEN;
    }
  }

  submit() {
    if (this.enviando) return;
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
