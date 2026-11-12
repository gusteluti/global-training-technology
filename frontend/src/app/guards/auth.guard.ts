import { Injectable } from '@angular/core';
import { CanActivate, Router, ActivatedRouteSnapshot, RouterStateSnapshot } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Injectable({ providedIn: 'root' })
export class AuthGuard implements CanActivate {
  constructor(private auth: AuthService, private router: Router) {}

  canActivate(route: ActivatedRouteSnapshot, state: RouterStateSnapshot): boolean {
    if (this.auth.isAuthenticated()) {
      return true;
    }
    // Quem não está logado vai ao login e volta à rota pedida depois (D76). Se a sessão foi recusada pelo
    // servidor (D108), o aviso de expirada vai junto, mesmo que outra carga da página tenha recebido o 401.
    const queryParams: { [k: string]: string } = this.auth.consumirSessaoExpirada()
      ? { sessao: 'expirada', next: state.url } : { next: state.url };
    this.router.navigate(['/login'], { queryParams });
    return false;
  }
}
