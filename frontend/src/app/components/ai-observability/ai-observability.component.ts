import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Chart } from '../../charts';

const MOTIVOS_HANDOFF: { key: string; label: string }[] = [
  { key: 'user_request', label: 'Pedido do usuário' },
  { key: 'llm_failures', label: 'Falhas da IA' },
  { key: 'token_budget', label: 'Limite de tokens' },
  { key: 'unresolved', label: 'Dúvidas não resolvidas' }
];

// Guardrails (GR5, D95): vocabulário fechado de `guard`, na ordem do contrato, com rótulo em português.
const TIPOS_GUARD: { key: string; label: string }[] = [
  { key: 'no_source', label: 'Sem fonte na base ("não sei")' },
  { key: 'input_injection', label: 'Tentativa de injeção' },
  { key: 'input_off_topic', label: 'Fora do assunto' },
  { key: 'input_login', label: 'Dado do aluno sem login' },
  { key: 'input_pii', label: 'Dados pessoais mascarados' },
  { key: 'output_leak', label: 'Vazamento de instruções' },
  { key: 'output_offer', label: 'Desconto ou preço não oficial' },
  { key: 'output_link', label: 'Link removido' },
  { key: 'output_promise', label: 'Promessa bloqueada' },
  { key: 'output_unverified', label: 'Data ou turma não verificada' }
];

@Component({
  selector: 'app-ai-observability',
  templateUrl: './ai-observability.component.html'
})
export class AiObservabilityComponent implements OnInit, OnDestroy {
  @ViewChild('messagesChart', { static: true }) messagesChart!: ElementRef<HTMLCanvasElement>;
  @ViewChild('perDayChart', { static: true }) perDayChart!: ElementRef<HTMLCanvasElement>;

  metrics: any = null;
  handoffReasons: { label: string; count: number }[] = [];
  guardTypes: { key: string; label: string; count: number }[] = [];
  error = '';
  private chart?: Chart;
  private dayChart?: Chart;

  constructor(private api: ApiService, private auth: AuthService) { }

  saude: any = null;
  servicos: { rotulo: string; valor: string; texto: string }[] = [];

  private carregarSaude(): void {
    const rotulos: { [k: string]: string } = {
      database: 'Banco de dados', llm: 'IA (Groq)', payment_gateway: 'Pagamentos', email: 'E-mail', backup: 'Último backup'
    };
    const textos: { [k: string]: string } = {
      ok: 'ok', erro: 'erro', configurado: 'configurado', nao_configurado: 'não configurado',
      desligado: 'desligado', nenhum: 'nenhum'
    };
    this.api.getSaudeSistema().subscribe({
      next: (r: any) => {
        this.saude = r;
        this.servicos = Object.keys(rotulos).filter(k => r?.services && k in r.services).map(k => ({
          rotulo: rotulos[k], valor: r.services[k], texto: textos[r.services[k]] || r.services[k]
        }));
      },
      error: () => this.saude = { status: 'erro' }
    });
  }

  ngOnInit(): void {
    // SG1 (D109, P2): o detalhe de saúde é só da Gestão; Suporte e Financeiro nem chamam a rota.
    if (this.auth.getRole() === 'admin') {
      this.carregarSaude();
    }
    this.carregar();
  }

  // Também chamado pela atualização automática (X5, D87).
  carregar(): void {
    this.api.getAiObservability().subscribe({
      next: (r: any) => {
        this.metrics = r.metrics || {};
        const porMotivo = (this.metrics.handoff && this.metrics.handoff.by_reason) || {};
        this.handoffReasons = MOTIVOS_HANDOFF.map(m => ({ label: m.label, count: Number(porMotivo[m.key] || 0) }));
        // Montada uma vez por carga (como handoffReasons): um getter com objetos novos recriaria as linhas a cada ciclo.
        const porTipo = (this.metrics.guards && this.metrics.guards.by_type) || {};
        this.guardTypes = TIPOS_GUARD.map(t => ({ key: t.key, label: t.label, count: Number(porTipo[t.key] || 0) }));
        this.renderMessagesChart();
        this.renderPerDayChart();
      },
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar a observabilidade de IA.'
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
    this.dayChart?.destroy();
  }

  get usage(): any {
    return (this.metrics && this.metrics.usage) || {};
  }

  get hasCost(): boolean {
    const cost = this.usage.cost_usd;
    return cost !== undefined && cost !== null;
  }

  get costText(): string {
    // D93: vírgula decimal (pt-BR), como o resto do sistema.
    return 'US$ ' + Number(this.usage.cost_usd || 0).toFixed(4).replace('.', ',');
  }

  get resolutionRateText(): string {
    return this.percent(this.metrics && this.metrics.resolution_rate);
  }

  get conversionRateText(): string {
    return this.percent(this.metrics && this.metrics.conversion && this.metrics.conversion.rate);
  }

  get topics(): { topic: string; count: number }[] {
    return (this.metrics && this.metrics.unresolved_topics) || [];
  }

  // Encaminhamentos ao WhatsApp (D77): total, taxa e motivos com rótulo em português.
  private diaBr(dia: string): string {
    const [, mes, numero] = String(dia).split('-');
    return numero ? `${numero}/${mes}` : dia;
  }

  get handoff(): any {
    return (this.metrics && this.metrics.handoff) || {};
  }

  get handoffRateText(): string {
    return this.percent(this.handoff.rate);
  }

  // Guardrails (GR5): total, um contador por tipo (zeros inclusive), "não sei" e feedback 👍/👎.
  get guards(): any {
    return (this.metrics && this.metrics.guards) || {};
  }

  get feedback(): any {
    return (this.metrics && this.metrics.feedback) || {};
  }

  // Sem feedback (rate null) mostra "—", nunca "0,0%".
  get feedbackRateText(): string {
    const taxa = this.feedback.rate;
    return taxa === null || taxa === undefined || !isFinite(Number(taxa)) ? '—' : this.percent(taxa);
  }

  private percent(fraction: number | undefined | null): string {
    return (Number(fraction || 0) * 100).toFixed(1).replace('.', ',') + '%';
  }

  get perCourse(): { label: string; value: number }[] {
    const map = (this.metrics && this.metrics.messages_per_course) || {};
    return Object.keys(map).map(key => ({ label: key, value: map[key] }));
  }

  private renderMessagesChart(): void {
    if (this.chart) {
      // Atualização automática (X5): troca os dados no lugar, sem redesenhar o gráfico do zero.
      this.chart.data.labels = this.perCourse.map(c => c.label);
      this.chart.data.datasets[0].data = this.perCourse.map(c => c.value);
      this.chart.update();
      return;
    }
    this.chart = new Chart(this.messagesChart.nativeElement, {
      type: 'bar',
      data: {
        labels: this.perCourse.map(c => c.label),
        datasets: [{
          label: 'Mensagens',
          data: this.perCourse.map(c => c.value),
          backgroundColor: '#00a6d6'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });
  }

  private renderPerDayChart(): void {
    const perDay: any[] = (this.metrics && this.metrics.per_day) || [];
    const datasets: any[] = [{
      label: 'Requisições',
      data: perDay.map(d => d.requests),
      backgroundColor: '#00a6d6',
      yAxisID: 'y'
    }];
    const scales: any = { y: { beginAtZero: true, ticks: { precision: 0 } } };
    if (perDay.some(d => d.cost_usd !== undefined && d.cost_usd !== null)) {
      datasets.push({
        label: 'Custo (USD)',
        data: perDay.map(d => d.cost_usd),
        backgroundColor: '#ff7a18',
        yAxisID: 'y1'
      });
      scales.y1 = { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false } };
    }
    if (this.dayChart) {
      // Atualização automática (X5): a série de custo pode aparecer ou sumir, então troca dados e escalas.
      this.dayChart.data = { labels: perDay.map(d => this.diaBr(d.date)), datasets };
      this.dayChart.options.scales = scales;
      this.dayChart.options.plugins = { legend: { display: datasets.length > 1 } };
      this.dayChart.update();
      return;
    }
    this.dayChart = new Chart(this.perDayChart.nativeElement, {
      type: 'bar',
      data: { labels: perDay.map(d => this.diaBr(d.date)), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: datasets.length > 1 } },
        scales
      }
    });
  }
}
