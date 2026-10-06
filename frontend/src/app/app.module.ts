import { NgModule, LOCALE_ID } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule, HTTP_INTERCEPTORS } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { registerLocaleData } from '@angular/common';
import localePt from '@angular/common/locales/pt';

import { AppComponent } from './app.component';
import { AppRoutingModule } from './app-routing.module';
import { LoginComponent } from './components/login/login.component';
import { StudentDashboardComponent } from './components/student-dashboard/student-dashboard.component';
import { AdminDashboardComponent } from './components/admin-dashboard/admin-dashboard.component';
import { FinancialDashboardComponent } from './components/financial-dashboard/financial-dashboard.component';
import { StudentsDashboardComponent } from './components/students-dashboard/students-dashboard.component';
import { CoursesDashboardComponent } from './components/courses-dashboard/courses-dashboard.component';
import { CourseAdminComponent } from './components/course-admin/course-admin.component';
import { AiObservabilityComponent } from './components/ai-observability/ai-observability.component';
import { AuditLogsComponent } from './components/audit-logs/audit-logs.component';
import { CadastroComponent } from './components/cadastro/cadastro.component';
import { DefinirSenhaComponent } from './components/definir-senha/definir-senha.component';
import { AuthInterceptor } from './interceptors/auth.interceptor';

// Valores em reais e datas no formato brasileiro (R$ 1.234,56).
registerLocaleData(localePt);

@NgModule({
  declarations: [
    AppComponent,
    LoginComponent,
    StudentDashboardComponent,
    AdminDashboardComponent,
    FinancialDashboardComponent,
    StudentsDashboardComponent,
    CoursesDashboardComponent,
    CourseAdminComponent,
    AiObservabilityComponent,
    AuditLogsComponent,
    CadastroComponent,
    DefinirSenhaComponent
  ],
  imports: [
    BrowserModule,
    HttpClientModule,
    FormsModule,
    AppRoutingModule
  ],
  providers: [
    { provide: LOCALE_ID, useValue: 'pt' },
    { provide: HTTP_INTERCEPTORS, useClass: AuthInterceptor, multi: true }
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
