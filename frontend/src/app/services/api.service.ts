import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
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

  // Turmas (L1, D53). Escrita e leitura de matrículas são da Gestão; o responsável sempre vem do token.
  public createClass(dados: { course_id: string; name: string; starts_on?: string; capacity?: number }) {
    return this.http.post(`${BASE}/api/admin/classes`, dados, this.authHeaders());
  }

  public getEnrollments(courseId: string) {
    const params = new HttpParams().set('course_id', courseId);
    return this.http.get(`${BASE}/api/admin/enrollments`, { ...this.authHeaders(), params });
  }

  // classId: número JSON estrito, ou null para "Sem turma".
  public setEnrollmentClass(enrollmentId: number, classId: number | null) {
    return this.http.put(`${BASE}/api/admin/enrollments/${enrollmentId}/class`, { class_id: classId }, this.authHeaders());
  }

  // Cadastro de cursos (L2, D56). Leitura é da equipe; escrita só da Gestão (a API devolve 403 aos demais).
  public getAdminCourses() {
    return this.http.get(`${BASE}/api/admin/courses`, this.authHeaders());
  }

  public getAdminCourse(courseId: string) {
    return this.http.get(`${BASE}/api/admin/course/${encodeURIComponent(courseId)}`, this.authHeaders());
  }

  public createCourse(curso: any) {
    return this.http.post(`${BASE}/api/admin/create-course`, curso, this.authHeaders());
  }

  public updateCourse(courseId: string, curso: any) {
    return this.http.put(`${BASE}/api/admin/course/${encodeURIComponent(courseId)}`, curso, this.authHeaders());
  }

  public deleteCourse(courseId: string) {
    return this.http.delete(`${BASE}/api/admin/course/${encodeURIComponent(courseId)}`, this.authHeaders());
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

  public requestPasswordReset(dados: { email: string }) {
    return this.http.post(`${BASE}/api/auth/password-reset/request`, dados, this.publicHeaders());
  }

  public resetPassword(dados: { token: string; password: string }) {
    return this.http.post(`${BASE}/api/auth/password-reset`, dados, this.publicHeaders());
  }

  private publicHeaders() {
    return { headers: new HttpHeaders({'Content-Type': 'application/json'}) };
  }
}
