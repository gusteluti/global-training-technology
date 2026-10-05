import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html'
})
export class LoginComponent {
  email = '';
  password = '';
  error = '';

  constructor(private auth: AuthService, private router: Router) { }

  submit() {
    this.error = '';
    this.auth.login(this.email, this.password).subscribe({
      next: ok => {
        if (ok) {
          // Gestão, Financeiro e Suporte vão para a área administrativa; o restante, para a área do aluno.
          const role = this.auth.getRole();
          const isStaff = ['admin', 'financial', 'support'].includes(role || '');
          this.router.navigate([isStaff ? '/admin' : '/student']);
        } else {
          this.error = 'Credenciais inválidas';
        }
      },
      error: err => {
        this.error = err?.error?.detail || 'Erro ao autenticar';
      }
    });
  }
}
