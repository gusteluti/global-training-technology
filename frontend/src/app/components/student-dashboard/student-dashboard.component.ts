import { DOCUMENT } from '@angular/common';
import { AfterViewInit, Component, ElementRef, HostListener, Inject, OnDestroy, OnInit, Renderer2, ViewChild } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { PainelMatriculas } from '../../resolvers/enrollments.resolver';
import { salvarArquivo } from '../../services/salvar-arquivo';
import { ApiService } from '../../services/api.service';
import { ConfirmacaoService } from '../../services/confirmacao.service';
import { AuthService } from '../../services/auth.service';
import { formatarDataSP } from '../../pipes/data-sp.pipe';
import { mensagemDeErroDoChat } from '../../services/erro-chat';

// Ação de matrícula devolvida pelo chat (D76).
interface AcaoChat {
  type: string;
  course_id: string;
  class_id: number | null;
  label: string;
}

// Ação de encaminhamento ao WhatsApp devolvida pelo chat (D77).
interface AcaoWhatsapp {
  type: string;
  url: string;
  label: string;
}

const PREFIXO_WHATSAPP = 'https://wa.me/';

// Até esta largura de janela (px) o painel do assistente é a tela inteira e o CSS usa as medidas de celular (16/84 px); é o mesmo
// limite do `@media (max-width: 600px)` do CSS do componente.
const LARGURA_MAXIMA_CELULAR = 600;
// Classe posta no <body> enquanto a área do aluno está aberta: o CSS do componente dá folga embaixo ao rodapé da casca
// (`.gt-footer`, de outro componente) para o botão flutuante não cobrir o texto dele. Sai no ngOnDestroy.
const CLASSE_BODY_ASSISTENTE = 'gt-assistente-flutuante';

type NotaFeedback = 'up' | 'down';

interface MensagemChat {
  role: string;
  content: string;
  fontes?: string[];
  piiMasked?: boolean;
  replyId?: string;
  feedback?: NotaFeedback | null;
  enviandoFeedback?: boolean;
}

// Ação de atalho devolvida pelo chat (GR4): abre uma seção da Área do aluno como os atalhos da D2.
type AlvoAbrir = 'financeiro' | 'cursos' | 'perfil';
interface AcaoAbrir {
  target: AlvoAbrir;
  label: string;
}

// Abas da área do aluno (R3-3, D125), no padrão do painel da gestão. "Meu perfil" não é aba (o assistente saiu da barra, D126).
type ChaveAba = 'cursos' | 'financeiro';
interface AbaAluno {
  chave: ChaveAba;
  rotulo: string;
}

// Só estes alvos e só os campos type/target/label; qualquer outro campo (ex.: `url`) descarta a ação inteira.
const SECOES_ABRIR: { [alvo: string]: string } = { financeiro: 'secao-financeiro', cursos: 'secao-cursos' };
const ALVOS_ABRIR = ['financeiro', 'cursos', 'perfil'];
const CAMPOS_ABRIR = ['type', 'target', 'label'];

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
  in_process: 'bg-primary',
  rejected: 'bg-danger',
  cancelled: 'bg-secondary',
  refunded: 'bg-secondary',
  charged_back: 'bg-danger'
};

// Pagamentos que o aluno ainda aguarda (contam no resumo "Pagamentos pendentes").
const PAGAMENTO_EM_ABERTO = ['pending', 'in_process'];

const FORMAS_PAGAMENTO: { [forma: string]: string } = {
  mercado_pago: 'Mercado Pago',
  manual: 'Matrícula manual'
};

const MSG_FALHA_PDF = 'Não foi possível baixar o recibo.';

@Component({
  selector: 'app-student-dashboard',
  templateUrl: './student-dashboard.component.html',
  styleUrls: ['./student-dashboard.component.css']
})
export class StudentDashboardComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('abas') listaAbas?: ElementRef<HTMLElement>;
  @ViewChild('indicador') indicador?: ElementRef<HTMLElement>;
  // O botão flutuante fica sempre no DOM; o campo do chat só existe com o painel aberto (*ngIf), por isso a busca é dinâmica.
  @ViewChild('botaoAssistente') botaoAssistente?: ElementRef<HTMLButtonElement>;
  @ViewChild('campoChat') campoChat?: ElementRef<HTMLInputElement>;

  readonly tabs: AbaAluno[] = [
    { chave: 'cursos', rotulo: 'Meus cursos' },
    { chave: 'financeiro', rotulo: 'Financeiro' }
  ];
  abaAtiva: ChaveAba = 'cursos';

  enrollments: any[] = [];
  payments: any[] = [];
  erro = '';
  erroFinanceiro = '';
  receipt: any = null;
  baixandoPdf = new Set<number>();
  // `fontes`: títulos de `sources` da resposta (GR1). Só nesta sessão de tela; o histórico do servidor não traz fonte.
  // `piiMasked`: a resposta veio com `pii_masked: true` (GR3); mostra AVISO_PII abaixo da resposta. Também só na sessão.
  // `replyId`/`feedback`/`enviandoFeedback` (GR5): só respostas desta sessão com reply_id ganham 👍/👎; o histórico
  // do servidor não traz reply_id, então não mostra botões.
  chatMessages: MensagemChat[] = [];
  // Painel do assistente aberto (R3-4, D126). Só controla a exibição: chatMessages e o resto do estado do chat nunca são zerados.
  painelAberto = false;
  chatInput = '';
  chatEnviando = false;
  // Ações de matrícula da última resposta (F5b, D76). Montadas pelo servidor e não persistidas no histórico.
  chatAcoes: AcaoChat[] = [];
  chatWhatsapp: AcaoWhatsapp | null = null;
  // Atalhos da última resposta (GR4); o `label` aparece só como texto.
  chatAbrir: AcaoAbrir[] = [];
  erroChat = '';
  email = '';
  // Primeiro nome do próprio aluno (GET /api/student/me, D80); vazio mantém a saudação genérica.
  primeiroNome = '';

  // Pedido de cancelamento em 7 dias (U5, D82): cartão com o formulário aberto, motivo, envio e erro.
  cancelarAbertoId: number | null = null;
  motivoCancelamento = '';
  enviandoCancelamento = false;
  erroCancelamento: { [enrollmentId: number]: string } = {};

  constructor(private route: ActivatedRoute, private router: Router, private api: ApiService, auth: AuthService,
              private confirmacao: ConfirmacaoService, private renderer: Renderer2,
              @Inject(DOCUMENT) private documento: Document) {
    // E-mail do próprio token (nunca de outro aluno): mostrado só no cabeçalho.
    this.email = auth.decodeToken()?.email || '';
    // Dados vindos do EnrollmentsResolver (rota /student).
    const painel: PainelMatriculas | undefined = this.route.snapshot.data['painel'];
    this.enrollments = this.ativasPrimeiro(painel?.enrollments || []);
    if (painel && !painel.ok) {
      this.erro = 'Não foi possível carregar suas matrículas.';
    }
  }

  ngOnInit(): void {
    this.renderer.addClass(this.documento.body, CLASSE_BODY_ASSISTENTE);
    this.api.getMyProfile().subscribe({
      next: (res: any) => this.primeiroNome = String(res?.name || '').trim().split(/\s+/)[0] || '',
      error: () => this.primeiroNome = ''
    });
    this.api.getMyPayments().subscribe({
      next: (res: any) => this.payments = res.payments || [],
      error: () => this.erroFinanceiro = 'Não foi possível carregar seu histórico financeiro.'
    });
    this.api.getChatHistory().subscribe({
      next: (res: any) => this.chatMessages = res.messages || [],
      error: () => this.erroChat = 'Não foi possível carregar o histórico do chat.'
    });
  }

  ngAfterViewInit(): void {
    this.moverIndicador();
    // A fonte da interface pode terminar de carregar depois da primeira medida e mudar a largura das abas.
    document.fonts?.ready.then(() => this.moverIndicador());
  }

  ngOnDestroy(): void {
    this.renderer.removeClass(this.documento.body, CLASSE_BODY_ASSISTENTE);
  }

  // ---- Assistente flutuante (R3-4, D126) -------------------------------------------------------------
  // O painel não é modal (sem aria-modal nem trava de foco). Abrir leva o foco ao campo; fechar (botão, X ou Esc) devolve o foco ao
  // botão. Nenhuma chamada à API: o histórico já foi carregado no ngOnInit e fica guardado no componente.
  alternarPainel(): void {
    if (this.painelAberto) {
      this.fecharPainel();
    } else {
      this.abrirPainel();
    }
  }

  abrirPainel(): void {
    this.painelAberto = true;
    // O campo só existe no ciclo de detecção seguinte (*ngIf).
    setTimeout(() => this.campoChat?.nativeElement.focus({ preventScroll: true }));
  }

  fecharPainel(): void {
    if (!this.painelAberto) {
      return;
    }
    this.painelAberto = false;
    this.botaoAssistente?.nativeElement.focus({ preventScroll: true });
  }

  // Esc fecha o painel aberto. Se a janela de confirmação da casca tratou o Esc (ela chama preventDefault), o painel fica como está.
  @HostListener('document:keydown.escape', ['$event'])
  aoApertarEsc(evento: Event): void {
    if (this.painelAberto && !evento.defaultPrevented) {
      this.fecharPainel();
    }
  }

  // ---- Abas (R3-3, D125) -----------------------------------------------------------------------------
  // Só troca o painel exibido: os dados são carregados uma vez (ngOnInit/resolver) e o estado da tela
  // (recibo aberto, avaliação em edição, cancelamento aberto) fica como está.
  selecionarAba(chave: ChaveAba): void {
    this.abaAtiva = chave;
    this.moverIndicador();
  }

  // O indicador desliza até a aba ativa (posição e largura medidas no DOM, inclusive com rolagem lateral), como na gestão.
  @HostListener('window:resize')
  moverIndicador(): void {
    setTimeout(() => {
      const lista = this.listaAbas?.nativeElement;
      const indicador = this.indicador?.nativeElement;
      const ativa = lista?.querySelector<HTMLElement>(`[data-aba="${this.abaAtiva}"]`);
      if (!lista || !indicador || !ativa) {
        return;
      }
      indicador.style.width = `${ativa.offsetWidth}px`;
      indicador.style.transform = `translateX(${ativa.offsetLeft}px)`;
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

  // Texto UTC da API ("2026-10-08 01:30:00" ou ISO) -> dia de São Paulo "07/10/2026" (D71).
  dataBr(valor: string | null | undefined): string {
    return formatarDataSP(valor, true);
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

  // ---- Cancelamento em 7 dias (U5, D82) ------------------------------------------------------------
  textoCancelamento(c: any): string {
    if (!c) {
      return '';
    }
    if (c.status === 'open') {
      return 'Cancelamento em análise';
    }
    if (c.status === 'approved') {
      return 'Cancelamento aprovado';
    }
    if (c.status === 'rejected') {
      return `Cancelamento recusado: ${c.decision_reason || ''}`.trim();
    }
    return '';
  }

  abrirCancelamento(m: any): void {
    this.cancelarAbertoId = m.id;
    this.motivoCancelamento = '';
    delete this.erroCancelamento[m.id];
  }

  enviarCancelamento(m: any): void {
    if (this.enviandoCancelamento) {
      return;
    }
    this.confirmacao.confirmar({
      titulo: `Pedir o cancelamento de ${m.course_name}?`,
      texto: 'O reembolso é analisado pelo financeiro.',
      rotuloConfirmar: 'Pedir cancelamento'
    }).then(ok => {
      if (!ok) {
        return;
      }
      this.enviandoCancelamento = true;
      delete this.erroCancelamento[m.id];
      this.api.requestCancellation(m.id, this.motivoCancelamento.trim()).subscribe({
        next: () => {
          this.enviandoCancelamento = false;
          this.cancelarAbertoId = null;
          this.motivoCancelamento = '';
          this.recarregarMatriculas();
        },
        error: (err: any) => {
          this.enviandoCancelamento = false;
          const detalhe = err?.error?.detail;
          this.erroCancelamento[m.id] = typeof detalhe === 'string' ? detalhe : 'Não foi possível pedir o cancelamento.';
          this.recarregarMatriculas();
        }
      });
    });
  }

  notaAvaliacao: { [id: number]: number } = {};
  comentarioAvaliacao: { [id: number]: string } = {};

  avaliacaoOk: { [id: number]: string } = {};
  avaliacaoErro: { [id: number]: string } = {};
  avaliandoId: number | null = null;

  // D93: o seletor mostra a nota que será enviada (a já dada ou 5), nunca fica em branco.
  notaDe(matricula: any): number {
    return this.notaAvaliacao[matricula.id] ?? matricula.review?.rating ?? 5;
  }

  comentarioDe(matricula: any): string {
    return this.comentarioAvaliacao[matricula.id] ?? matricula.review?.comment ?? '';
  }

  avaliar(matricula: any): void {
    const id = matricula.id;
    this.avaliacaoOk[id] = '';
    this.avaliacaoErro[id] = '';
    this.avaliandoId = id;
    this.api.reviewCourse(id, this.notaDe(matricula), this.comentarioDe(matricula)).subscribe({
      next: (r: any) => {
        matricula.review = r.review;
        this.avaliandoId = null;
        this.avaliacaoOk[id] = 'Avaliação enviada. Obrigado!';
      },
      error: () => {
        this.avaliandoId = null;
        this.avaliacaoErro[id] = 'Não foi possível enviar a avaliação. Tente novamente.';
      }
    });
  }

  marcarMaterial(matricula: any, url: string, feito: boolean): void {
    this.api.markMaterial(matricula.id, url, feito).subscribe({
      next: (r: any) => matricula.progress = r.progress,
      error: () => this.recarregarMatriculas()
    });
  }

  baixarCertificado(matricula: any): void {
    this.api.downloadCertificate(matricula.id).subscribe({
      next: resposta => salvarArquivo(resposta, 'certificado.pdf'),
      error: () => this.recarregarMatriculas()
    });
  }

  private recarregarMatriculas(): void {
    this.api.getMyEnrollments().subscribe({
      next: (res: any) => {
        this.enrollments = this.ativasPrimeiro(res.enrollments || []);
        this.erro = '';
      },
      error: () => this.erro = 'Não foi possível carregar suas matrículas.'
    });
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

  // O curso em andamento vem antes dos pendentes, e os encerrados ficam por último.
  private ativasPrimeiro(matriculas: any[]): any[] {
    const ordem: { [status: string]: number } = { active: 0, pending: 1 };
    const posicao = (m: any) => ordem[m.status] ?? 2;
    return [...matriculas].sort((a, b) => posicao(a) - posicao(b));
  }

  enviarChat(): void {
    if (!this.podeEnviarChat()) {
      return;
    }
    const texto = this.chatInput;
    this.chatEnviando = true;
    this.erroChat = '';
    this.chatAcoes = [];
    this.chatWhatsapp = null;
    this.chatAbrir = [];
    this.api.sendChatMessage(texto).subscribe({
      next: (res: any) => {
        this.chatMessages = [
          ...this.chatMessages,
          { role: 'user', content: res.masked_message || texto },
          { role: 'assistant', content: res.message, fontes: this.titulosDasFontes(res.sources),
            piiMasked: res.pii_masked === true,
            replyId: typeof res.reply_id === 'string' && res.reply_id ? res.reply_id : undefined,
            feedback: null, enviandoFeedback: false }
        ];
        this.chatAcoes = (Array.isArray(res.actions) ? res.actions : [])
          .filter((a: any) => a && a.type === 'enroll' && a.course_id && a.label);
        this.chatWhatsapp = this.acaoWhatsapp(res.actions);
        this.chatAbrir = this.acoesAbrir(res.actions);
        this.chatInput = '';
        this.chatEnviando = false;
      },
      error: (err: any) => {
        this.erroChat = mensagemDeErroDoChat(err);
        this.chatWhatsapp = this.acaoWhatsapp(err?.error?.actions);
        this.chatEnviando = false;
      }
    });
  }

  // Feedback 👍/👎 (GR5): aceito (200) trava o par e marca o escolhido; falha libera para tentar de novo.
  enviarFeedback(msg: MensagemChat, nota: NotaFeedback): void {
    if (!msg.replyId || msg.feedback || msg.enviandoFeedback) {
      return;
    }
    msg.enviandoFeedback = true;
    this.api.sendChatFeedback(msg.replyId, nota).subscribe({
      next: () => {
        msg.feedback = nota;
        msg.enviandoFeedback = false;
      },
      error: () => {
        msg.feedback = null;
        msg.enviandoFeedback = false;
      }
    });
  }

  // Títulos de `sources` (GR1): só strings não vazias; sem fonte, lista vazia e nada aparece na tela.
  private titulosDasFontes(sources: any): string[] {
    if (!Array.isArray(sources)) {
      return [];
    }
    return sources
      .map((f: any) => (f && typeof f.title === 'string' ? f.title.trim() : ''))
      .filter((t: string) => t.length > 0);
  }

  // Só aceita link que aponte para https://wa.me/ (defesa, D77).
  private acaoWhatsapp(actions: any): AcaoWhatsapp | null {
    if (!Array.isArray(actions)) {
      return null;
    }
    const acao = actions.find((a: any) => a && a.type === 'handoff' && typeof a.url === 'string'
      && a.url.startsWith(PREFIXO_WHATSAPP) && typeof a.label === 'string' && a.label);
    return acao ? { type: acao.type, url: acao.url, label: acao.label } : null;
  }

  // Ações `open` do servidor (GR4): alvo da lista fechada, label texto não vazio e nenhum campo a mais.
  private acoesAbrir(actions: any): AcaoAbrir[] {
    if (!Array.isArray(actions)) {
      return [];
    }
    return actions
      .filter((a: any) => a && typeof a === 'object' && a.type === 'open'
        && Object.keys(a).every(k => CAMPOS_ABRIR.includes(k))
        && typeof a.target === 'string' && ALVOS_ABRIR.includes(a.target)
        && typeof a.label === 'string' && a.label.trim().length > 0)
      .map((a: any) => ({ target: a.target as AlvoAbrir, label: a.label }));
  }

  // Financeiro e cursos selecionam a aba e rolam até o painel (R3-3, D125); perfil navega pela rota /student/perfil.
  // O painel da aba só nasce no ciclo seguinte (*ngIf), por isso a rolagem espera a renderização. Com a janela de celular
  // (<= 600 px) o painel do assistente cobriria a tela e fecha depois da ação; acima disso continua aberto (R3-4, D126).
  abrirAtalho(acao: AcaoAbrir): void {
    if (acao.target === 'perfil') {
      this.router.navigate(['/student/perfil']);
      return;
    }
    const secao = SECOES_ABRIR[acao.target];
    if (secao) {
      this.selecionarAba(acao.target as ChaveAba);
      if (window.innerWidth <= LARGURA_MAXIMA_CELULAR) {
        this.fecharPainel();
      }
      setTimeout(() => this.irPara(secao));
    }
  }

  // Leva ao catálogo com o curso e, se houver, a turma pré-selecionada (D75/D76).
  abrirMatricula(acao: AcaoChat): void {
    const queryParams: { [k: string]: string } = { curso: String(acao.course_id) };
    if (acao.class_id !== null && acao.class_id !== undefined) {
      queryParams['turma'] = String(acao.class_id);
    }
    this.router.navigate(['/catalogo'], { queryParams });
  }
}
