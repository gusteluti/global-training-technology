import { Injectable, Injector } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpHandler, HttpEvent, HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, catchError, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

// L2 (D56): o token só vai para as rotas protegidas. Login, cadastro, definição de senha, chat público,
// catálogo, checkout e webhook nunca levam Authorization, mesmo com token guardado no navegador.
const PREFIXOS_PROTEGIDOS = ['/api/admin/', '/api/dashboard/', '/api/student/', '/api/payments/refund/'];

// U9 (D80): 401 nestas rotas, com token enviado, encerra a sessão na SPA. O login nunca conta.
const PREFIXOS_SESSAO = ['/api/student/', '/api/dashboard/', '/api/admin/'];
const ROTAS_LOGIN = ['/api/token', '/api/admin/login'];

function caminhoDe(url: string): string {
  try {
    // Resolve o caminho também quando a URL é absoluta (BASE com host) ou relativa.
    return new URL(url, window.location.origin).pathname;
  } catch {
    return url;
  }
}

@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  // Router obtido sob demanda: evita dependência circular na criação do interceptor.
  constructor(private auth: AuthService, private injector: Injector) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const caminho = caminhoDe(req.url);
    const protegida = PREFIXOS_PROTEGIDOS.some(prefixo => caminho.startsWith(prefixo));
    if (!protegida) {
      return next.handle(req.headers.has('Authorization') ? req.clone({ headers: req.headers.delete('Authorization') }) : req);
    }
    const token = this.auth.getToken();
    if (!token) {
      return next.handle(req);
    }
    const autenticada = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
    return next.handle(autenticada).pipe(
      catchError((erro: any) => {
        if (erro instanceof HttpErrorResponse && erro.status === 401
            && PREFIXOS_SESSAO.some(prefixo => caminho.startsWith(prefixo)) && !ROTAS_LOGIN.includes(caminho)) {
          this.sessaoExpirada(token);
        }
        return throwError(() => erro);
      })
    );
  }

  private sessaoExpirada(tokenEnviado: string): void {
    // Só encerra se o token recusado ainda é o guardado (uma troca de senha pode ter gravado um novo).
    if (this.auth.getToken() !== tokenEnviado) {
      return;
    }
    this.auth.logout();
    const router = this.injector.get(Router);
    const navegacao = router.getCurrentNavigation();
    const atual = navegacao ? router.serializeUrl(navegacao.extractedUrl) : router.url;
    if (atual.startsWith('/login')) {
      return;
    }
    const queryParams: { [k: string]: string } = { sessao: 'expirada' };
    if (atual && atual !== '/') {
      queryParams['next'] = atual;
    }
    router.navigate(['/login'], { queryParams });
  }
}
