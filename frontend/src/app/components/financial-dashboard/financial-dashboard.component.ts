import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { Chart } from '../../charts';

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

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.error = '';
    this.api.getFinancial().subscribe({
      next: (r: any) => {
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
    this.chart?.destroy();
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
