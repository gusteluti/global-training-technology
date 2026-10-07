import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { PainelMatriculas } from '../../resolvers/enrollments.resolver';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';

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

// Status de pagamento em português (D67). Vocabulário do backend (E9); só um status fora dele apareceria em valor bruto.
const ROTULOS_PAGAMENTO: { [status: string]: string } = {
  approved: 'Aprovado',
  pending: 'Pendente',
  in_process: 'Em análise',
  rejected: 'Recusado',
  cancelled: 'Cancelado',
  refunded: 'Reembolsado',
  charged_back: 'Contestado'
};

const CLASSES_PAGAMENTO: { [status: string]: string } = {
  approved: 'bg-success',
  pending: 'bg-warning text-dark',
  in_process: 'bg-info text-dark',
  rejected: 'bg-danger',
  cancelled: 'bg-secondary',
  refunded: 'bg-secondary',
  charged_back: 'bg-danger'
};

// Pagamentos que o aluno ainda aguarda (contam no resumo "Pagamentos pendentes").
const PAGAMENTO_EM_ABERTO = ['pending', 'in_process'];

const FORMAS_PAGAMENTO: { [forma: string]: string } = {
  mercado_pago: 'Mercado Pago'
};

const MSG_FALHA_PDF = 'Não foi possível baixar o recibo.';

@Component({
  selector: 'app-student-dashboard',
  templateUrl: './student-dashboard.component.html',
  styleUrls: ['./student-dashboard.component.css']
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
  email = '';

  constructor(private route: ActivatedRoute, private api: ApiService, auth: AuthService) {
    // E-mail do próprio token (nunca de outro aluno): mostrado só no cabeçalho.
    this.email = auth.decodeToken()?.email || '';
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

  // ---- Resumo (D67) ----------------------------------------------------------------------------------
  get cursosAtivos(): number {
    return this.enrollments.filter(m => m.status === 'active').length;
  }

  get pagamentosPendentes(): number {
    return this.payments.filter(p => PAGAMENTO_EM_ABERTO.includes(p.status)).length;
  }

  // Só pagamento aprovado conta; reembolsado, pendente e recusado ficam de fora.
  get totalInvestido(): number {
    return this.payments
      .filter(p => p.status === 'approved')
      .reduce((soma, p) => soma + (Number(p.amount) || 0), 0);
  }

  // ---- Apresentação ---------------------------------------------------------------------------------
  iniciais(nome: string): string {
    const palavras = (nome || '').split(/\s+/).filter(p => /[A-Za-zÀ-ÿ0-9]/.test(p));
    return palavras.slice(0, 2).map(p => p[0].toUpperCase()).join('') || 'GT';
  }

  // "2026-10-07 20:10:00" ou ISO -> "07/10/2026", sem depender do parser de datas do navegador.
  dataBr(valor: string | null | undefined): string {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(valor || '');
    return m ? `${m[3]}/${m[2]}/${m[1]}` : '';
  }

  rotuloPagamento(status: string): string {
    return ROTULOS_PAGAMENTO[status] || status;
  }

  classePagamento(status: string): string {
    return CLASSES_PAGAMENTO[status] || 'bg-secondary';
  }

  rotuloForma(forma: string): string {
    return FORMAS_PAGAMENTO[forma] || (forma ? 'Outra' : '-');
  }

  irPara(id: string): void {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
