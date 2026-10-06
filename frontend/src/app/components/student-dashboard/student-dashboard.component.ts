import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { PainelMatriculas } from '../../resolvers/enrollments.resolver';
import { ApiService } from '../../services/api.service';

// Rótulos e cores dos status de matrícula (conjunto fechado, D28).
const ROTULOS_STATUS: { [status: string]: string } = {
  pending: 'Pendente',
  active: 'Ativa',
  cancelled: 'Cancelada',
  refunded: 'Reembolsada'
};

const CLASSES_STATUS: { [status: string]: string } = {
  pending: 'bg-warning text-dark',
  active: 'bg-success',
  cancelled: 'bg-secondary',
  refunded: 'bg-danger'
};

const MENSAGENS_SEM_ACESSO: { [status: string]: string } = {
  pending: 'Pagamento em análise. Os materiais ficam disponíveis após a confirmação.',
  cancelled: 'Matrícula cancelada. Os materiais não estão disponíveis.',
  refunded: 'Pagamento reembolsado. Os materiais não estão mais disponíveis.'
};

@Component({
  selector: 'app-student-dashboard',
  templateUrl: './student-dashboard.component.html'
})
export class StudentDashboardComponent implements OnInit {
  enrollments: any[] = [];
  payments: any[] = [];
  erro = '';
  erroFinanceiro = '';
  receipt: any = null;

  constructor(private route: ActivatedRoute, private api: ApiService) {
    // Dados vindos do EnrollmentsResolver (rota /student).
    const painel: PainelMatriculas | undefined = this.route.snapshot.data['painel'];
    this.enrollments = painel?.enrollments || [];
    if (painel && !painel.ok) {
      this.erro = 'Não foi possível carregar suas matrículas.';
    }
  }

  ngOnInit(): void {
    this.api.getMyPayments().subscribe({
      next: (res: any) => this.payments = res.payments || [],
      error: () => this.erroFinanceiro = 'Não foi possível carregar seu histórico financeiro.'
    });
  }

  rotuloStatus(status: string): string {
    return ROTULOS_STATUS[status] || status;
  }

  classeStatus(status: string): string {
    return CLASSES_STATUS[status] || 'bg-secondary';
  }

  mensagemSemAcesso(status: string): string {
    return MENSAGENS_SEM_ACESSO[status] || 'Os materiais não estão disponíveis para esta matrícula.';
  }

  verRecibo(paymentId: number): void {
    this.erroFinanceiro = '';
    this.api.getMyPaymentReceipt(paymentId).subscribe({
      next: (res: any) => this.receipt = res.receipt || null,
      error: () => this.erroFinanceiro = 'Não foi possível carregar o recibo.'
    });
  }
}
