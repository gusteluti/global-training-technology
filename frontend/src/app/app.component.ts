import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './services/auth.service';

// Casca da SPA no design da landing page (D66): barra escura com o logo "GT", conteúdo e rodapé escuro.
// O logo não é link: o link "voltar ao login" das telas de senha é verificado pelo e2e da B1 e não pode
// ficar trivialmente satisfeito pela barra.
@Component({
  selector: 'app-root',
  template: `
    <nav class="gt-nav" data-testid="app-nav">
      <div class="gt-logo" data-testid="app-logo">
        <div class="gt-logo-circle" aria-hidden="true">GT</div>
        <div class="gt-logo-text">
          <span data-testid="app-logo-nome">Global Training</span>
          <span>Technology</span>
        </div>
      </div>
      <div class="gt-nav-actions" *ngIf="auth.isAuthenticated()">
        <span class="gt-nav-role">{{ auth.getRoleLabel() }}</span>
        <button class="gt-nav-cta" type="button" (click)="logout()">Sair</button>
      </div>
    </nav>
    <main class="gt-main">
      <div class="container gt-container">
        <router-outlet></router-outlet>
      </div>
    </main>
    <footer class="gt-footer" data-testid="app-footer">
      <strong>Global Training Technology</strong> · Plataforma educacional
    </footer>
  `
})
export class AppComponent {
  constructor(public auth: AuthService, private router: Router) { }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/']);
  }
}
