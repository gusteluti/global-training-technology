import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './components/login/login.component';
import { StudentDashboardComponent } from './components/student-dashboard/student-dashboard.component';
import { AdminDashboardComponent } from './components/admin-dashboard/admin-dashboard.component';
import { CadastroComponent } from './components/cadastro/cadastro.component';
import { DefinirSenhaComponent } from './components/definir-senha/definir-senha.component';
import { EsqueciSenhaComponent } from './components/esqueci-senha/esqueci-senha.component';
import { RedefinirSenhaComponent } from './components/redefinir-senha/redefinir-senha.component';

import { AuthGuard } from './guards/auth.guard';
import { RoleGuard } from './guards/role.guard';
import { EnrollmentsResolver } from './resolvers/enrollments.resolver';

// Perfis de funcionário (Gestão, Financeiro, Suporte) entram na área administrativa.
// Cada aba dela mostra o que o perfil pode ver; a API também reforça essas regras.
export const STAFF_ROLES = ['admin', 'financial', 'support'];

const routes: Routes = [
  { path: '', component: LoginComponent },
  // Link do e-mail de conta existente (D26). Rota explícita: sem ela cai no curinga.
  { path: 'login', component: LoginComponent },
  { path: 'student', component: StudentDashboardComponent, canActivate: [AuthGuard, RoleGuard], data: { roles: ['student'] }, resolve: { painel: EnrollmentsResolver } },
  { path: 'admin', component: AdminDashboardComponent, canActivate: [AuthGuard, RoleGuard], data: { roles: STAFF_ROLES } },
  // Rotas públicas da conta do aluno (sem AuthGuard). Devem vir antes do curinga.
  { path: 'cadastro', component: CadastroComponent },
  { path: 'definir-senha', component: DefinirSenhaComponent },
  { path: 'esqueci-senha', component: EsqueciSenhaComponent },
  { path: 'redefinir-senha', component: RedefinirSenhaComponent },
  { path: '**', redirectTo: '' }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
