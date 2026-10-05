import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './services/auth.service';

@Component({
  selector: 'app-root',
  template: `
    <nav class="navbar navbar-expand-lg navbar-light bg-light mb-3">
      <div class="container-fluid">
        <a class="navbar-brand" href="#">Global Training</a>
        <div class="d-flex align-items-center gap-2" *ngIf="auth.isAuthenticated()">
          <span class="badge bg-secondary">{{ auth.getRoleLabel() }}</span>
          <button class="btn btn-sm btn-outline-secondary" type="button" (click)="logout()">Sair</button>
        </div>
      </div>
    </nav>
    <div class="container">
      <router-outlet></router-outlet>
    </div>
  `
})
export class AppComponent {
  constructor(public auth: AuthService, private router: Router) { }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/']);
  }
}
