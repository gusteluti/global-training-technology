import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { AuthService } from './auth.service';

const BASE = '';

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient, private auth: AuthService) { }

  private authHeaders() {
    const token = this.auth.getToken();
    let headers = new HttpHeaders({'Content-Type': 'application/json'});
    if (token) {
      headers = headers.set('Authorization', `Bearer ${token}`);
    }
    return { headers };
  }

  public getPublicCourses() {
    return this.http.get(`${BASE}/api/courses`);
  }

  // Dashboards de funcionário (Fase 2): mesmos endpoints usados pelo admin.html.
  public getFinancial() {
    return this.http.get(`${BASE}/api/dashboard/financeiro`, this.authHeaders());
  }

  public getStudents() {
    return this.http.get(`${BASE}/api/dashboard/alunos`, this.authHeaders());
  }

  public getCoursesMetrics() {
    return this.http.get(`${BASE}/api/dashboard/cursos`, this.authHeaders());
  }

  public getAiObservability() {
    return this.http.get(`${BASE}/api/dashboard/observabilidade-ia`, this.authHeaders());
  }

  public getAuditLogs() {
    return this.http.get(`${BASE}/api/admin/audit-logs`, this.authHeaders());
  }

  public refundPayment(paymentId: number) {
    return this.http.post(`${BASE}/api/payments/refund/${paymentId}`, {}, this.authHeaders());
  }
}
