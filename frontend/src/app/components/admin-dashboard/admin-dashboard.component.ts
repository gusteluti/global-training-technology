import { AfterViewInit, Component, ElementRef, HostListener, OnInit, ViewChild } from '@angular/core';
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
export class AdminDashboardComponent implements OnInit, AfterViewInit {
  @ViewChild('abas') abas?: ElementRef<HTMLElement>;
  @ViewChild('indicador') indicador?: ElementRef<HTMLElement>;

  // Visibilidade por perfil (item 2 do escopo da Fase 2). A API aplica as mesmas regras.
  readonly tabs: DashboardTab[] = [
    { key: 'financeiro', label: 'Financeiro', roles: ['admin', 'financial'] },
    { key: 'alunos', label: 'Alunos', roles: ['admin', 'financial', 'support'] },
    { key: 'cursos', label: 'Cursos', roles: ['admin', 'financial', 'support'] },
    { key: 'cadastro-cursos', label: 'Cadastro de cursos', roles: ['admin'] },
    { key: 'ia', label: 'Observabilidade de IA', roles: ['admin', 'financial', 'support'] },
    { key: 'auditoria', label: 'Auditoria', roles: ['admin'] },
    { key: 'equipe', label: 'Equipe', roles: ['admin'] }
  ];

  visibleTabs: DashboardTab[] = [];
  activeTab = '';

  constructor(private auth: AuthService) { }

  ngOnInit(): void {
    const role = this.auth.getRole() || '';
    this.visibleTabs = this.tabs.filter(tab => tab.roles.includes(role));
    this.activeTab = this.visibleTabs.length ? this.visibleTabs[0].key : '';
  }

  ngAfterViewInit(): void {
    this.moverIndicador();
  }

  select(key: string): void {
    this.activeTab = key;
    this.moverIndicador();
  }

  // D95: o indicador desliza até a aba ativa (posição e largura medidas no DOM, inclusive com rolagem lateral).
  @HostListener('window:resize')
  moverIndicador(): void {
    setTimeout(() => {
      const lista = this.abas?.nativeElement;
      const indicador = this.indicador?.nativeElement;
      const ativa = lista?.querySelector<HTMLElement>(`[data-aba="${this.activeTab}"]`);
      if (!lista || !indicador || !ativa) {
        return;
      }
      indicador.style.width = `${ativa.offsetWidth}px`;
      indicador.style.transform = `translateX(${ativa.offsetLeft}px)`;
    });
  }
}
