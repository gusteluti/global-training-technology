import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { Chart } from '../../charts';
import { salvarArquivo } from '../../services/salvar-arquivo';

// Rótulos de status de pagamento em português (mesmos do detalhe do aluno, F3).
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
  selector: 'app-financial-dashboard',
  templateUrl: './financial-dashboard.component.html'
})
export class FinancialDashboardComponent implements OnInit, OnDestroy {
  @ViewChild('revenueChart', { static: true }) revenueChart!: ElementRef<HTMLCanvasElement>;

  totals: any = null;
  payments: any[] = [];
  error = '';
  refundingId: number | null = null;
  private chart?: Chart;

  // Busca e filtro de status da lista de transações (U1, D74); totais e gráfico continuam globais.
  busca = '';
  filtroStatus = '';
  readonly statusOpcoes = Object.keys(ROTULOS_PAGAMENTO);
  private buscaAplicada = '';
  private requisicao = 0;
  // A aba Financeiro só existe para Gestão e Financeiro, os mesmos perfis que podem exportar (D74).
  exportando = false;

  constructor(private api: ApiService) { }

  // Solicitações de cancelamento em aberto (U5, D82). A aba Financeiro só existe para Gestão e Financeiro.
  cancelamentos: any[] = [];
  erroCancelamentos = '';
  motivosRecusa: { [id: number]: string } = {};
  decidindoId: number | null = null;

  ngOnInit(): void {
    this.load();
    this.carregarCancelamentos();
  }

  carregarCancelamentos(): void {
    this.api.getCancellationRequests('open').subscribe({
      next: (r: any) => this.cancelamentos = r.requests || [],
      error: err => this.erroCancelamentos = err?.error?.detail || 'Não foi possível carregar as solicitações de cancelamento.'
    });
  }

  podeRecusar(pedido: any): boolean {
    const motivo = (this.motivosRecusa[pedido.id] || '').trim();
    return this.decidindoId === null && motivo.length >= 5 && motivo.length <= 300;
  }

  aprovarCancelamento(pedido: any): void {
    if (this.decidindoId !== null) {
      return;
    }
    if (!confirm(`Aprovar o cancelamento de ${pedido.course_name} e reembolsar ${pedido.student_name}? A ação fica registrada na auditoria.`)) {
      return;
    }
    this.decidir(pedido, this.api.approveCancellationRequest(pedido.id));
  }

  recusarCancelamento(pedido: any): void {
    if (!this.podeRecusar(pedido)) {
      return;
    }
    this.decidir(pedido, this.api.rejectCancellationRequest(pedido.id, this.motivosRecusa[pedido.id].trim()));
  }

  private decidir(pedido: any, chamada: any): void {
    this.decidindoId = pedido.id;
    this.erroCancelamentos = '';
    chamada.subscribe({
      next: () => {
        this.decidindoId = null;
        delete this.motivosRecusa[pedido.id];
        this.carregarCancelamentos();
        this.load();
      },
      error: (err: any) => {
        this.decidindoId = null;
        this.erroCancelamentos = err?.error?.detail || 'Não foi possível registrar a decisão.';
        this.carregarCancelamentos();
      }
    });
  }

  buscar(): void {
    this.buscaAplicada = this.busca.trim();
    this.load();
  }

  // Atualização automática (X5, D87): mesma busca e filtro aplicados; pausa durante reembolso ou decisão.
  get atualizacaoPausada(): boolean {
    return this.refundingId !== null || this.decidindoId !== null;
  }

  atualizar(): void {
    this.load();
    this.carregarCancelamentos();
  }

  rotuloPagamento(status: string): string {
    return ROTULOS_PAGAMENTO[status] || status;
  }

  exportarCsv(): void {
    if (this.exportando) {
      return;
    }
    this.exportando = true;
    this.api.exportFinancialCsv({ q: this.buscaAplicada, status: this.filtroStatus }).subscribe({
      next: resposta => {
        this.exportando = false;
        salvarArquivo(resposta, 'financeiro.csv');
      },
      error: () => {
        this.exportando = false;
        this.error = 'Não foi possível exportar o CSV.';
      }
    });
  }

  load(): void {
    const id = ++this.requisicao;
    this.error = '';
    this.api.getFinancial({ q: this.buscaAplicada, status: this.filtroStatus }).subscribe({
      next: (r: any) => {
        if (id !== this.requisicao) {
          return;
        }
        this.totals = r.totals;
        this.payments = r.payments || [];
        this.renderRevenueChart(r.monthly_revenue || []);
      },
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar o financeiro.'
    });
  }

  refund(payment: any): void {
    if (!confirm(`Confirmar o reembolso do pagamento #${payment.id}? A ação fica registrada na auditoria.`)) {
      return;
    }
    this.refundingId = payment.id;
    this.api.refundPayment(payment.id).subscribe({
      next: () => {
        this.refundingId = null;
        this.load();
        this.carregarCancelamentos();
      },
      error: err => {
        this.refundingId = null;
        this.error = err?.error?.detail || 'Não foi possível reembolsar o pagamento.';
      }
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private renderRevenueChart(monthly: any[]): void {
    if (this.chart) {
      // Atualização automática (X5): troca os dados no lugar, sem redesenhar o gráfico do zero.
      this.chart.data.labels = monthly.map(m => m.month);
      this.chart.data.datasets[0].data = monthly.map(m => m.revenue);
      this.chart.update();
      return;
    }
    this.chart = new Chart(this.revenueChart.nativeElement, {
      type: 'bar',
      data: {
        labels: monthly.map(m => m.month),
        datasets: [{
          label: 'Receita aprovada (R$)',
          data: monthly.map(m => m.revenue),
          backgroundColor: '#0096c7'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } }
      }
    });
  }
}
