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

  // X4 (D90): estado das dependências (público, sem dado sensível).
  public getHealth() {
    return this.http.get(`${BASE}/api/health`);
  }

  public getPublicCourses() {
    return this.http.get(`${BASE}/api/courses`);
  }

  // Turmas abertas de um curso (F5a, D75): rota pública, sem dado de aluno.
  public getCourseTurmas(courseId: string) {
    return this.http.get(`${BASE}/api/courses/${encodeURIComponent(courseId)}/turmas`);
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

  // Recibo em PDF (B2, D63): download autenticado (token no cabeçalho, nunca na URL). `url` é o
  // receipt_pdf_url do item de /api/student/payments.
  public downloadReceiptPdf(url: string) {
    return this.http.get(`${BASE}${url}`, { ...this.authHeaders(), responseType: 'blob' as const });
  }

  // Chat do aluno logado (E5). O corpo leva só a mensagem: a identidade vem do JWT.
  public sendChatMessage(message: string) {
    return this.http.post(`${BASE}/api/student/chat`, { message }, this.authHeaders());
  }

  public getChatHistory() {
    return this.http.get(`${BASE}/api/student/chat/history`, this.authHeaders());
  }

  // Perfil do próprio aluno (U3/S5, D80). Nenhuma chamada leva id de usuário: a identidade vem do JWT.
  public getMyProfile() {
    return this.http.get(`${BASE}/api/student/me`, this.authHeaders());
  }

  public updateMyProfile(name: string, phone: string | null) {
    return this.http.put(`${BASE}/api/student/me`, { name, phone }, this.authHeaders());
  }

  public changeMyPassword(currentPassword: string, newPassword: string) {
    return this.http.post(`${BASE}/api/student/me/password`,
      { current_password: currentPassword, new_password: newPassword }, this.authHeaders());
  }

  // Checkout do aluno logado (Parte 1): o corpo leva só o curso; o aluno vem do JWT no backend.
  // F5a (D75): `class_id` opcional; sem ele, o corpo é o de antes.
  public studentCheckout(courseId: string, classId?: number | null) {
    const corpo: any = { course_id: courseId };
    if (classId !== undefined && classId !== null) {
      corpo.class_id = classId;
    }
    return this.http.post(`${BASE}/api/student/checkout`, corpo, this.authHeaders());
  }

  // Dashboards de funcionário (Fase 2): mesmos endpoints usados pelo admin.html.
  // U1 (D74): filtros opcionais; parâmetro vazio não é enviado (sem filtro, a resposta é a de antes).
  public getFinancial(filtros: { q?: string; status?: string } = {}) {
    const params = this.parametros(filtros);
    return this.http.get(`${BASE}/api/dashboard/financeiro`, { ...this.authHeaders(), params });
  }

  public getStudents(filtros: { q?: string; page?: number; page_size?: number } = {}) {
    const params = this.parametros(filtros);
    return this.http.get(`${BASE}/api/dashboard/alunos`, { ...this.authHeaders(), params });
  }

  // Exportação CSV (U1, D74): só Gestão e Financeiro. Download autenticado como Blob (o token vai no cabeçalho,
  // nunca na URL); `observe: 'response'` para ler o nome do arquivo no Content-Disposition.
  public exportStudentsCsv(filtros: { q?: string } = {}) {
    return this.baixarCsv(`${BASE}/api/dashboard/alunos.csv`, filtros);
  }

  public exportFinancialCsv(filtros: { q?: string; status?: string } = {}) {
    return this.baixarCsv(`${BASE}/api/dashboard/financeiro.csv`, filtros);
  }

  public exportCourseStudentsCsv(courseId: string, filtros: { status?: string; class_id?: string } = {}) {
    return this.baixarCsv(`${BASE}/api/dashboard/cursos/${encodeURIComponent(courseId)}/alunos.csv`, filtros);
  }

  private baixarCsv(url: string, filtros: { [nome: string]: any }) {
    return this.http.get(url, {
      headers: this.authHeaders().headers,
      params: this.parametros(filtros),
      observe: 'response' as const,
      responseType: 'blob' as const
    });
  }

  private parametros(filtros: { [nome: string]: any }): HttpParams {
    let params = new HttpParams();
    for (const nome of Object.keys(filtros)) {
      const valor = filtros[nome];
      if (valor !== undefined && valor !== null && String(valor).trim() !== '') {
        params = params.set(nome, String(valor).trim());
      }
    }
    return params;
  }

  // F3/F4 (D73): detalhe do aluno e alunos de um curso. `amount` não vem para o Suporte (D68).
  public getStudentDetail(userId: number) {
    return this.http.get(`${BASE}/api/dashboard/alunos/${encodeURIComponent(String(userId))}`, this.authHeaders());
  }

  // Filtros opcionais: status (pending/active/cancelled/refunded) e class_id (id da turma ou 'none').
  public getCourseStudents(courseId: string, filtros: { status?: string; class_id?: string } = {}) {
    let params = new HttpParams();
    if (filtros.status) {
      params = params.set('status', filtros.status);
    }
    if (filtros.class_id) {
      params = params.set('class_id', filtros.class_id);
    }
    return this.http.get(`${BASE}/api/dashboard/cursos/${encodeURIComponent(courseId)}/alunos`,
      { ...this.authHeaders(), params });
  }

  public getCoursesMetrics() {
    return this.http.get(`${BASE}/api/dashboard/cursos`, this.authHeaders());
  }

  public getAiObservability() {
    return this.http.get(`${BASE}/api/dashboard/observabilidade-ia`, this.authHeaders());
  }

  // U1 (D74): `q` (descrição ou e-mail do responsável), `date_from`/`date_to` (AAAA-MM-DD, dias de São Paulo).
  public getAuditLogs(filtros: { q?: string; date_from?: string; date_to?: string } = {}) {
    const params = this.parametros(filtros);
    return this.http.get(`${BASE}/api/admin/audit-logs`, { ...this.authHeaders(), params });
  }

  // Turmas (L1, D53). Escrita e leitura de matrículas são da Gestão; o responsável sempre vem do token.
  public createClass(dados: { course_id: string; name: string; starts_on?: string; ends_on?: string;
                               schedule?: string; capacity?: number }) {
    return this.http.post(`${BASE}/api/admin/classes`, dados, this.authHeaders());
  }

  // U8 (D83): só os campos enviados mudam; null limpa.
  public updateClass(classId: number, dados: { [campo: string]: any }) {
    return this.http.put(`${BASE}/api/admin/classes/${classId}`, dados, this.authHeaders());
  }

  // Avaliação do curso (X2, D92).
  public reviewCourse(enrollmentId: number, rating: number, comment: string) {
    return this.http.post(`${BASE}/api/student/enrollments/${enrollmentId}/review`, { rating, comment }, this.authHeaders());
  }

  // Progresso e certificado (X1, D91).
  public markMaterial(enrollmentId: number, url: string, done: boolean) {
    return this.http.post(`${BASE}/api/student/enrollments/${enrollmentId}/progress`, { url, done }, this.authHeaders());
  }

  public downloadCertificate(enrollmentId: number) {
    return this.http.get(`${BASE}/api/student/enrollments/${enrollmentId}/certificate.pdf`,
      { ...this.authHeaders(), observe: 'response', responseType: 'blob' });
  }

  // LGPD (U7, D89): exportar e excluir os próprios dados.
  public exportMyData() {
    return this.http.get(`${BASE}/api/student/me/export`, { ...this.authHeaders(), observe: 'response', responseType: 'blob' });
  }

  public deleteMyAccount(password: string) {
    return this.http.post(`${BASE}/api/student/me/delete`, { password }, this.authHeaders());
  }

  // Equipe (S3, D85): só a Gestão.
  public getStaff() {
    return this.http.get(`${BASE}/api/admin/staff`, this.authHeaders());
  }

  public inviteStaff(dados: { email: string; name: string; role: string }) {
    return this.http.post(`${BASE}/api/admin/staff`, dados, this.authHeaders());
  }

  public updateStaff(userId: number, dados: { role?: string; name?: string }) {
    return this.http.put(`${BASE}/api/admin/staff/${userId}`, dados, this.authHeaders());
  }

  public setStaffActive(userId: number, ativo: boolean) {
    const acao = ativo ? 'reactivate' : 'deactivate';
    return this.http.post(`${BASE}/api/admin/staff/${userId}/${acao}`, {}, this.authHeaders());
  }

  public deleteClass(classId: number) {
    return this.http.delete(`${BASE}/api/admin/classes/${classId}`, this.authHeaders());
  }

  public getEnrollments(courseId: string) {
    const params = new HttpParams().set('course_id', courseId);
    return this.http.get(`${BASE}/api/admin/enrollments`, { ...this.authHeaders(), params });
  }

  // Matrícula manual (U4, D81): só a Gestão; cria a conta se preciso e grava pagamento `manual` aprovado.
  public createManualEnrollment(dados: { email: string; name?: string; course_id: string; class_id?: number;
                                          reason: string; amount?: number }) {
    return this.http.post(`${BASE}/api/admin/enrollments`, dados, this.authHeaders());
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

  // F7 (D78): rascunho de curso a partir de anexo (JSON ou PDF). Multipart com o campo `file`; sem Content-Type
  // fixo para o navegador definir o boundary. O token vai pelo interceptor (rota /api/admin/).
  public createCourseDraft(arquivo: File) {
    const dados = new FormData();
    dados.append('file', arquivo, arquivo.name);
    return this.http.post(`${BASE}/api/admin/course-draft`, dados);
  }

  public updateCourse(courseId: string, curso: any) {
    return this.http.put(`${BASE}/api/admin/course/${encodeURIComponent(courseId)}`, curso, this.authHeaders());
  }

  public deleteCourse(courseId: string) {
    return this.http.delete(`${BASE}/api/admin/course/${encodeURIComponent(courseId)}`, this.authHeaders());
  }

  // Arquivar tira o curso do catálogo e do chat; o aluno ativo mantém o acesso (F1, D68). Só a Gestão.
  public archiveCourse(courseId: string) {
    return this.http.post(`${BASE}/api/admin/course/${encodeURIComponent(courseId)}/archive`, {}, this.authHeaders());
  }

  public unarchiveCourse(courseId: string) {
    return this.http.post(`${BASE}/api/admin/course/${encodeURIComponent(courseId)}/unarchive`, {}, this.authHeaders());
  }

  // Desativar/reativar conta de aluno (S4, D80): só Gestão; a API devolve 403 aos demais.
  public deactivateStudent(userId: number) {
    return this.http.post(`${BASE}/api/admin/students/${encodeURIComponent(String(userId))}/deactivate`, {}, this.authHeaders());
  }

  public reactivateStudent(userId: number) {
    return this.http.post(`${BASE}/api/admin/students/${encodeURIComponent(String(userId))}/reactivate`, {}, this.authHeaders());
  }

  // Pedido de cancelamento em 7 dias (U5, D82). O aluno só pede da própria matrícula (dono pelo JWT).
  public requestCancellation(enrollmentId: number, reason: string) {
    return this.http.post(`${BASE}/api/student/enrollments/${encodeURIComponent(String(enrollmentId))}/cancel-request`,
      { reason }, this.authHeaders());
  }

  // Solicitações de cancelamento (U5, D82): Financeiro e Gestão; a API devolve 403 aos demais.
  public getCancellationRequests(status = 'open') {
    const params = new HttpParams().set('status', status);
    return this.http.get(`${BASE}/api/admin/cancellation-requests`, { ...this.authHeaders(), params });
  }

  public approveCancellationRequest(requestId: number) {
    return this.http.post(`${BASE}/api/admin/cancellation-requests/${encodeURIComponent(String(requestId))}/approve`,
      {}, this.authHeaders());
  }

  public rejectCancellationRequest(requestId: number, reason: string) {
    return this.http.post(`${BASE}/api/admin/cancellation-requests/${encodeURIComponent(String(requestId))}/reject`,
      { reason }, this.authHeaders());
  }

  public refundPayment(paymentId: number) {
    return this.http.post(`${BASE}/api/payments/refund/${paymentId}`, {}, this.authHeaders());
  }

  // Endpoints públicos da conta do aluno: sem cabeçalho de autenticação.
  public registerStudent(dados: { name: string; email: string; password: string; accept_terms?: boolean }) {
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
