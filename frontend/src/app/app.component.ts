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
      <a class="gt-logo gt-logo-link" data-testid="app-logo" [routerLink]="inicio()" aria-label="Ir para a página inicial">
        <div class="gt-logo-circle" aria-hidden="true">GT</div>
        <div class="gt-logo-text">
          <span data-testid="app-logo-nome">Global Training</span>
          <span>Technology</span>
        </div>
      </a>
      <div class="gt-nav-actions">
        <a class="gt-nav-link" data-testid="app-voltar-site" [href]="landingUrl">Voltar ao site</a>
        <ng-container *ngIf="auth.isAuthenticated()">
          <span class="gt-nav-role">{{ auth.getRoleLabel() }}</span>
          <button class="gt-nav-cta" type="button" (click)="logout()">Sair</button>
        </ng-container>
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
  // Landing (vitrine) fica fora da SPA, servida pelo backend em /frontend/. Em desenvolvimento a SPA roda
  // no ng serve (porta 4200) e o backend na 8000; em qualquer outro host as duas dividem a mesma origem.
  // A meta "gtt-landing-url" do index.html, se preenchida, tem prioridade.
  readonly landingUrl = AppComponent.calcularLandingUrl();

  static calcularLandingUrl(): string {
    const meta = document.querySelector('meta[name="gtt-landing-url"]') as HTMLMetaElement | null;
    const configurada = meta && meta.content.trim();
    if (configurada) return configurada;
    const caminho = '/frontend/landing_global_training.html';
    const { protocol, hostname, port } = window.location;
    return port === '4200' ? `${protocol}//${hostname}:8000${caminho}` : caminho;
  }

  constructor(public auth: AuthService, private router: Router) { }

  // D93: o logo leva à área de quem está logado (funcionário -> /admin, aluno -> /student); sem sessão, ao login.
  inicio(): string {
    if (!this.auth.isAuthenticated()) {
      return '/';
    }
    return ['admin', 'financial', 'support'].includes(this.auth.getRole() || '') ? '/admin' : '/student';
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/']);
  }
}
