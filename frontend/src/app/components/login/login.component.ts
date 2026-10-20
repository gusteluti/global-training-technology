import { Component } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';

// Caminho interno da aplicação (D76): começa com '/', não com '//', sem '\' nem caractere de controle.
// Começar com uma única '/' já exclui esquema ('https:', 'javascript:') e host externo.
export function caminhoInternoSeguro(caminho: string | null): caminho is string {
  if (!caminho || !caminho.startsWith('/') || caminho.startsWith('//')) {
    return false;
  }
  return !caminho.includes('\\') && !/[\u0000-\u001f\u007f]/.test(caminho);
}

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html'
})
export class LoginComponent {
  email = '';
  password = '';
  error = '';

  constructor(private auth: AuthService, private router: Router, private route: ActivatedRoute) { }

  submit() {
    this.error = '';
    this.auth.login(this.email, this.password).subscribe({
      next: ok => {
        if (ok) {
          // Gestão, Financeiro e Suporte vão para a área administrativa; o restante, para a área do aluno.
          const role = this.auth.getRole();
          const isStaff = ['admin', 'financial', 'support'].includes(role || '');
          if (isStaff) {
            this.router.navigate(['/admin']);
          } else {
            // Aluno volta à rota pedida (D76) só se for caminho interno; senão, /student (sem redirecionamento aberto).
            const next = this.route.snapshot.queryParamMap.get('next');
            this.router.navigateByUrl(caminhoInternoSeguro(next) ? next : '/student');
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
