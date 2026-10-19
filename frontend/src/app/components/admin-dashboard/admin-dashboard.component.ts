import { Component, OnInit } from '@angular/core';
import { AuthService } from '../../services/auth.service';

interface DashboardTab {
  key: string;
  label: string;
  roles: string[];
}

@Component({
  selector: 'app-admin-dashboard',
  templateUrl: './admin-dashboard.component.html'
})
export class AdminDashboardComponent implements OnInit {
  // Visibilidade por perfil (item 2 do escopo da Fase 2). A API aplica as mesmas regras.
  readonly tabs: DashboardTab[] = [
    { key: 'financeiro', label: 'Financeiro', roles: ['admin', 'financial'] },
    { key: 'alunos', label: 'Alunos', roles: ['admin', 'financial', 'support'] },
    { key: 'cursos', label: 'Cursos', roles: ['admin', 'financial', 'support'] },
    { key: 'cadastro-cursos', label: 'Cadastro de cursos', roles: ['admin'] },
    { key: 'ia', label: 'Observabilidade de IA', roles: ['admin', 'financial', 'support'] },
    { key: 'auditoria', label: 'Auditoria', roles: ['admin'] }
  ];

  visibleTabs: DashboardTab[] = [];
  activeTab = '';

  constructor(private auth: AuthService) { }

  ngOnInit(): void {
    const role = this.auth.getRole() || '';
    this.visibleTabs = this.tabs.filter(tab => tab.roles.includes(role));
    this.activeTab = this.visibleTabs.length ? this.visibleTabs[0].key : '';
  }

  select(key: string): void {
    this.activeTab = key;
  }
}
