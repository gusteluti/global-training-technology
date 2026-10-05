import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { Chart } from '../../charts';

@Component({
  selector: 'app-ai-observability',
  templateUrl: './ai-observability.component.html'
})
export class AiObservabilityComponent implements OnInit, OnDestroy {
  @ViewChild('messagesChart', { static: true }) messagesChart!: ElementRef<HTMLCanvasElement>;

  metrics: any = null;
  error = '';
  private chart?: Chart;

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getAiObservability().subscribe({
      next: (r: any) => {
        this.metrics = r.metrics || {};
        this.renderMessagesChart();
      },
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar a observabilidade de IA.'
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
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
          backgroundColor: '#0dcaf0'
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
}
