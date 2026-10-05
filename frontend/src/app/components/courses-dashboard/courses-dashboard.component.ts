import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { Chart } from '../../charts';

@Component({
  selector: 'app-courses-dashboard',
  templateUrl: './courses-dashboard.component.html'
})
export class CoursesDashboardComponent implements OnInit, OnDestroy {
  @ViewChild('enrollmentChart', { static: true }) enrollmentChart!: ElementRef<HTMLCanvasElement>;

  courses: any[] = [];
  error = '';
  private chart?: Chart;

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getCoursesMetrics().subscribe({
      next: (r: any) => {
        this.courses = r.courses || [];
        this.renderEnrollmentChart();
      },
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar os cursos.'
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private renderEnrollmentChart(): void {
    this.chart?.destroy();
    this.chart = new Chart(this.enrollmentChart.nativeElement, {
      type: 'bar',
      data: {
        labels: this.courses.map(c => c.name || c.id),
        datasets: [{
          label: 'Inscritos',
          data: this.courses.map(c => c.total_enrollments),
          backgroundColor: '#0d6efd'
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });
  }
}
