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

const MSG_FALHA_PDF = 'Não foi possível baixar o recibo.';

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
  baixandoPdf = new Set<number>();
  chatMessages: { role: string; content: string }[] = [];
  chatInput = '';
  chatEnviando = false;
  erroChat = '';

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
    this.api.getChatHistory().subscribe({
      next: (res: any) => this.chatMessages = res.messages || [],
      error: () => this.erroChat = 'Não foi possível carregar o histórico do chat.'
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

  temReciboPdf(p: any): boolean {
    return !!p?.receipt_pdf_url && (p.status === 'approved' || p.status === 'refunded');
  }

  baixarReciboPdf(p: any): void {
    if (this.baixandoPdf.has(p.id)) {
      return;
    }
    this.erroFinanceiro = '';
    this.baixandoPdf.add(p.id);
    this.api.downloadReceiptPdf(p.receipt_pdf_url).subscribe({
      next: (blob: Blob) => {
        this.baixandoPdf.delete(p.id);
        try {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `recibo-${p.id}.pdf`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch {
          this.erroFinanceiro = MSG_FALHA_PDF;
        }
      },
      error: () => {
        this.baixandoPdf.delete(p.id);
        this.erroFinanceiro = MSG_FALHA_PDF;
      }
    });
  }

  podeEnviarChat(): boolean {
    return !this.chatEnviando && this.chatInput.trim().length > 0;
  }

  enviarChat(): void {
    if (!this.podeEnviarChat()) {
      return;
    }
    const texto = this.chatInput;
    this.chatEnviando = true;
    this.erroChat = '';
    this.api.sendChatMessage(texto).subscribe({
      next: (res: any) => {
        this.chatMessages = [
          ...this.chatMessages,
          { role: 'user', content: texto },
          { role: 'assistant', content: res.message }
        ];
        this.chatInput = '';
        this.chatEnviando = false;
      },
      error: () => {
        this.erroChat = 'Não foi possível enviar a mensagem. Tente novamente.';
        this.chatEnviando = false;
      }
    });
  }
}
