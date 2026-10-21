import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { salvarArquivo } from '../../services/salvar-arquivo';

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

  // Busca e paginação no servidor (U1, D74): 25 alunos por página; `metrics` continuam globais.
  readonly porPagina = 25;
  busca = '';
  pagina = 1;
  total = 0;
  private buscaAplicada = '';
  private requisicao = 0;

  // Exportação CSV só para Gestão e Financeiro (D74); a API devolve 403 aos demais.
  podeExportar = false;
  exportando = false;

  // Detalhe do aluno (F3, D73). O valor só aparece quando a API manda `amount` (Suporte não recebe, D68).
  detalhe: any = null;
  detalheErro = '';
  private detalheId: number | null = null;

  // Desativar/reativar conta (S4, D80): só Gestão; a API também reforça.
  podeGerenciarConta = false;
  alterandoConta = false;

  constructor(private api: ApiService, private auth: AuthService) { }

  ngOnInit(): void {
    this.podeExportar = ['admin', 'financial'].includes(this.auth.getRole() || '');
    this.podeGerenciarConta = this.auth.getRole() === 'admin';
    this.carregar();
  }

  get totalPaginas(): number {
    return Math.max(1, Math.ceil(this.total / this.porPagina));
  }

  buscar(): void {
    this.buscaAplicada = this.busca.trim();
    this.pagina = 1;
    this.carregar();
  }

  // Atualização automática (X5, D87): mesma busca e página; o detalhe aberto é recarregado sem fechar.
  atualizar(): void {
    this.carregar();
    const id = this.detalheId;
    if (id === null || !this.detalhe) {
      return;
    }
    this.api.getStudentDetail(id).subscribe({
      next: (r: any) => {
        if (this.detalheId === id && this.detalhe) {
          this.detalhe = r;
        }
      },
      error: () => { }
    });
  }

  irParaPagina(pagina: number): void {
    if (pagina < 1 || pagina > this.totalPaginas || pagina === this.pagina) {
      return;
    }
    this.pagina = pagina;
    this.carregar();
  }

  carregar(): void {
    const id = ++this.requisicao;
    this.error = '';
    this.api.getStudents({ q: this.buscaAplicada, page: this.pagina, page_size: this.porPagina }).subscribe({
      next: (r: any) => {
        if (id !== this.requisicao) {
          return;
        }
        this.metrics = r.metrics;
        this.students = r.students || [];
        this.total = r.pagination?.total ?? this.students.length;
      },
      error: err => {
        if (id === this.requisicao) {
          this.error = err?.error?.detail || 'Não foi possível carregar os alunos.';
        }
      }
    });
  }

  exportarCsv(): void {
    if (!this.podeExportar || this.exportando) {
      return;
    }
    this.exportando = true;
    this.api.exportStudentsCsv({ q: this.buscaAplicada }).subscribe({
      next: resposta => {
        this.exportando = false;
        salvarArquivo(resposta, 'alunos.csv');
      },
      error: () => {
        this.exportando = false;
        this.error = 'Não foi possível exportar o CSV.';
      }
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

  alternarConta(desativar: boolean): void {
    const aluno = this.detalhe?.student;
    if (!this.podeGerenciarConta || this.alterandoConta || !aluno) {
      return;
    }
    const pergunta = desativar
      ? `Desativar a conta de "${aluno.name}"?`
      : `Reativar a conta de "${aluno.name}"?`;
    if (!confirm(pergunta)) {
      return;
    }
    this.alterandoConta = true;
    this.detalheErro = '';
    const chamada = desativar ? this.api.deactivateStudent(aluno.id) : this.api.reactivateStudent(aluno.id);
    chamada.subscribe({
      next: () => {
        this.alterandoConta = false;
        this.abrirDetalhe(aluno);
        this.carregar();
      },
      error: err => {
        this.alterandoConta = false;
        this.detalheErro = err?.error?.detail || 'Não foi possível alterar a conta do aluno.';
      }
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
