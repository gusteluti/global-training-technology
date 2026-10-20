import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';

// Rótulos de status em português (E3/D67).
const ROTULOS_STATUS: { [status: string]: string } = {
  pending: 'Pendente',
  active: 'Ativa',
  cancelled: 'Cancelada',
  refunded: 'Reembolsada'
};

const ROTULOS_PAGAMENTO: { [status: string]: string } = {
  approved: 'Aprovado',
  pending: 'Pendente',
  in_process: 'Em análise',
  rejected: 'Recusado',
  cancelled: 'Cancelado',
  refunded: 'Reembolsado',
  charged_back: 'Contestado'
};

@Component({
  selector: 'app-students-dashboard',
  templateUrl: './students-dashboard.component.html'
})
export class StudentsDashboardComponent implements OnInit {
  metrics: any = null;
  students: any[] = [];
  error = '';

  // Detalhe do aluno (F3, D73). O valor só aparece quando a API manda `amount` (Suporte não recebe, D68).
  detalhe: any = null;
  detalheErro = '';
  private detalheId: number | null = null;

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getStudents().subscribe({
      next: (r: any) => {
        this.metrics = r.metrics;
        this.students = r.students || [];
      },
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar os alunos.'
    });
  }

  abrirDetalhe(aluno: any): void {
    const id = aluno?.id;
    this.detalheId = id;
    this.detalhe = null;
    this.detalheErro = '';
    this.api.getStudentDetail(id).subscribe({
      next: (r: any) => {
        if (this.detalheId === id) {
          this.detalhe = r;
        }
      },
      error: err => this.detalheErro = err?.error?.detail || 'Não foi possível carregar o aluno.'
    });
  }

  fecharDetalhe(): void {
    this.detalhe = null;
    this.detalheId = null;
    this.detalheErro = '';
  }

  get mostrarValores(): boolean {
    const pagamentos: any[] = this.detalhe?.payments || [];
    return pagamentos.some(p => p && Object.prototype.hasOwnProperty.call(p, 'amount'));
  }

  nomeCurso(courseId: string): string {
    const m = (this.detalhe?.enrollments || []).find((e: any) => e.course_id === courseId);
    return m?.course_name || courseId;
  }

  rotuloStatus(status: string): string {
    return ROTULOS_STATUS[status] || status;
  }

  rotuloPagamento(status: string): string {
    return ROTULOS_PAGAMENTO[status] || status;
  }
}
