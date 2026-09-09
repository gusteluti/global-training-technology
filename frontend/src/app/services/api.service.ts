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

  public getFinancial() {
    return this.http.get(`${BASE}/api/v1/dashboard/financeiro`, this.authHeaders());
  }

  public getStudents() {
    return this.http.get(`${BASE}/api/v1/dashboard/alunos`, this.authHeaders());
  }

  public getCoursesMetrics() {
    return this.http.get(`${BASE}/api/v1/dashboard/cursos`, this.authHeaders());
  }

  public getAuditLogs() {
    return this.http.get(`${BASE}/api/v1/dashboard/audit`, this.authHeaders());
  }
}
