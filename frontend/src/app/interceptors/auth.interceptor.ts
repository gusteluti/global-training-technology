import { Injectable } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpHandler, HttpEvent } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AuthService } from '../services/auth.service';

// L2 (D56): o token só vai para as rotas protegidas. Login, cadastro, definição de senha, chat público,
// catálogo, checkout e webhook nunca levam Authorization, mesmo com token guardado no navegador.
const PREFIXOS_PROTEGIDOS = ['/api/admin/', '/api/dashboard/', '/api/student/', '/api/payments/refund/'];

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
  constructor(private auth: AuthService) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const caminho = caminhoDe(req.url);
    const protegida = PREFIXOS_PROTEGIDOS.some(prefixo => caminho.startsWith(prefixo));
    if (!protegida) {
      return next.handle(req.headers.has('Authorization') ? req.clone({ headers: req.headers.delete('Authorization') }) : req);
    }
    const token = this.auth.getToken();
    if (token) {
      return next.handle(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
    }
    return next.handle(req);
  }
}
