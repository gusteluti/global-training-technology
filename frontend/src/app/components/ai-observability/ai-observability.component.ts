import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { Chart } from '../../charts';

@Component({
  selector: 'app-ai-observability',
  templateUrl: './ai-observability.component.html'
})
export class AiObservabilityComponent implements OnInit, OnDestroy {
  @ViewChild('messagesChart', { static: true }) messagesChart!: ElementRef<HTMLCanvasElement>;
  @ViewChild('perDayChart', { static: true }) perDayChart!: ElementRef<HTMLCanvasElement>;

  metrics: any = null;
  error = '';
  private chart?: Chart;
  private dayChart?: Chart;

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getAiObservability().subscribe({
      next: (r: any) => {
        this.metrics = r.metrics || {};
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
    return 'US$ ' + Number(this.usage.cost_usd).toFixed(4);
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

  private percent(fraction: number | undefined | null): string {
    return (Number(fraction || 0) * 100).toFixed(1) + '%';
  }

  get perCourse(): { label: string; value: number }[] {
    const map = (this.metrics && this.metrics.messages_per_course) || {};
    return Object.keys(map).map(key => ({ label: key, value: map[key] }));
  }

  private renderMessagesChart(): void {
    this.chart?.destroy();
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
    this.dayChart?.destroy();
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
    this.dayChart = new Chart(this.perDayChart.nativeElement, {
      type: 'bar',
      data: { labels: perDay.map(d => d.date), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: datasets.length > 1 } },
        scales
      }
    });
  }
}
