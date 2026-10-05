import { Component } from '@angular/core';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-cadastro',
  templateUrl: './cadastro.component.html'
})
export class CadastroComponent {
  name = '';
  email = '';
  password = '';
  error = '';
  success = false;
  enviando = false;

  constructor(private api: ApiService) { }

  submit() {
    if (this.enviando) return;
    this.error = '';
    this.enviando = true;
    this.api.registerStudent({ name: this.name, email: this.email, password: this.password }).subscribe({
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
