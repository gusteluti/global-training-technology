import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './components/login/login.component';
import { StudentDashboardComponent } from './components/student-dashboard/student-dashboard.component';
import { AdminDashboardComponent } from './components/admin-dashboard/admin-dashboard.component';

import { AuthGuard } from './guards/auth.guard';
import { RoleGuard } from './guards/role.guard';

// Perfis de funcionário (Gestão, Financeiro, Suporte) entram na área administrativa.
// Cada aba dela mostra o que o perfil pode ver; a API também reforça essas regras.
export const STAFF_ROLES = ['admin', 'financial', 'support'];

const routes: Routes = [
  { path: '', component: LoginComponent },
  { path: 'student', component: StudentDashboardComponent, canActivate: [AuthGuard, RoleGuard], data: { roles: ['student'] } },
  { path: 'admin', component: AdminDashboardComponent, canActivate: [AuthGuard, RoleGuard], data: { roles: STAFF_ROLES } },
  { path: '**', redirectTo: '' }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
