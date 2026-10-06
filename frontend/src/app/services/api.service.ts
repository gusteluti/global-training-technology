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

  // Área do aluno (E3, D28): só as matrículas do próprio usuário do token.
  public getMyEnrollments() {
    return this.http.get(`${BASE}/api/student/enrollments`, this.authHeaders());
  }

  // Histórico financeiro do próprio aluno (E4). O backend deriva o usuário do JWT.
  public getMyPayments() {
    return this.http.get(`${BASE}/api/student/payments`, this.authHeaders());
  }

  public getMyPaymentReceipt(paymentId: number) {
    return this.http.get(`${BASE}/api/student/payments/${paymentId}/receipt`, this.authHeaders());
  }

  // Chat do aluno logado (E5). O corpo leva só a mensagem: a identidade vem do JWT.
  public sendChatMessage(message: string) {
    return this.http.post(`${BASE}/api/student/chat`, { message }, this.authHeaders());
  }

  public getChatHistory() {
    return this.http.get(`${BASE}/api/student/chat/history`, this.authHeaders());
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

  // Endpoints públicos da conta do aluno: sem cabeçalho de autenticação.
  public registerStudent(dados: { name: string; email: string; password: string }) {
    return this.http.post(`${BASE}/api/auth/register`, dados, this.publicHeaders());
  }

  public setPassword(dados: { token: string; password: string }) {
    return this.http.post(`${BASE}/api/auth/password-setup`, dados, this.publicHeaders());
  }

  private publicHeaders() {
    return { headers: new HttpHeaders({'Content-Type': 'application/json'}) };
  }
}
