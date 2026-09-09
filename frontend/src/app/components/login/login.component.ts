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
          const role = this.auth.getRole();
          if (role === 'admin') {
            this.router.navigate(['/admin']);
          } else {
            this.router.navigate(['/student']);
          }
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
