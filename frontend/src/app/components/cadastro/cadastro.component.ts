import { Component } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { caminhoInternoSeguro } from '../login/login.component';

@Component({
  selector: 'app-cadastro',
  templateUrl: './cadastro.component.html'
})
export class CadastroComponent {
  name = '';
  email = '';
  password = '';
  aceite = false;
  error = '';
  success = false;
  enviando = false;
  // D108: `next` interno vindo do login (ex.: catálogo com curso e turma do chat); volta ao login nos links.
  nextInterno: string | null = null;

  constructor(private api: ApiService, route: ActivatedRoute) {
    const next = route.snapshot.queryParamMap.get('next');
    this.nextInterno = caminhoInternoSeguro(next) ? next : null;
  }

  submit() {
    if (this.enviando) return;
    this.error = '';
    this.enviando = true;
    this.api.registerStudent({ name: this.name, email: this.email, password: this.password, accept_terms: this.aceite }).subscribe({
      next: () => {
        this.enviando = false;
        this.success = true;
      },
      error: err => {
        this.enviando = false;
        this.error = err?.error?.detail || 'Não foi possível concluir o cadastro.';
      }
    });
  }
}
