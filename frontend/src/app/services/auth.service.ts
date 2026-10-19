import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';

const BASE = '';

// Rótulos dos perfis, iguais aos do backend (models/user.py).
const ROLE_LABELS: { [role: string]: string } = {
  admin: 'Gestão',
  financial: 'Financeiro',
  support: 'Suporte',
  student: 'Aluno'
};

@Injectable({ providedIn: 'root' })
export class AuthService {
  tokenKey = 'gtt_token';

  constructor(private http: HttpClient) { }

  login(username: string, password: string): Observable<boolean> {
    const form = new HttpParams()
      .set('username', username)
      .set('password', password);

    return this.http.post<any>(`${BASE}/api/token`, form.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    }).pipe(
      map(res => {
        if (res && res.access_token) {
          localStorage.setItem(this.tokenKey, res.access_token);
          return true;
        }
        return false;
      })
    );
  }

  logout() {
    localStorage.removeItem(this.tokenKey);
  }

  getToken(): string | null {
    return localStorage.getItem(this.tokenKey);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  decodeToken(): any | null {
    const token = this.getToken();
    if (!token) return null;
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return null;
      const payload = parts[1];
      const padded = payload.replace(/-/g, '+').replace(/_/g, '/');
      const decoded = decodeURIComponent(atob(padded).split('').map(function(c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      return JSON.parse(decoded);
    } catch (e) {
      return null;
    }
  }

  getRole(): string | null {
    const data = this.decodeToken();
    if (!data) return null;
    return data.role || null;
  }

  getRoleLabel(): string {
    const role = this.getRole();
    return role ? (ROLE_LABELS[role] || role) : '';
  }
}
