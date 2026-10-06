import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Chart } from '../../charts';

const STATUS_LABELS: { [status: string]: string } = {
  active: 'Ativa',
  pending: 'Pendente',
  cancelled: 'Cancelada',
  refunded: 'Reembolsada'
};

@Component({
  selector: 'app-courses-dashboard',
  templateUrl: './courses-dashboard.component.html'
})
export class CoursesDashboardComponent implements OnInit, OnDestroy {
  @ViewChild('enrollmentChart', { static: true }) enrollmentChart!: ElementRef<HTMLCanvasElement>;

  courses: any[] = [];
  error = '';
  private chart?: Chart;

  // Gerenciar turmas (L1): só a Gestão (perfil admin) vê e usa; Suporte e Financeiro só leem os números.
  canManage = false;
  manageCourseId = '';
  newName = '';
  newStart = '';
  newCapacity: number | null = null;
  enrollments: any[] = [];
  turmaError = '';

  constructor(private api: ApiService, private auth: AuthService) { }

  ngOnInit(): void {
    this.canManage = this.auth.getRole() === 'admin';
    this.loadCourses();
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private loadCourses(): void {
    this.api.getCoursesMetrics().subscribe({
      next: (r: any) => {
        this.courses = r.courses || [];
        this.renderEnrollmentChart();
      },
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar os cursos.'
    });
  }

  get manageClasses(): any[] {
    const course = this.courses.find(c => c.id === this.manageCourseId);
    return course?.classes || [];
  }

  statusLabel(status: string): string {
    return STATUS_LABELS[status] || status;
  }

  classOptionLabel(turma: any): string {
    const total = turma.total ?? ((turma.enrolled || 0) + (turma.pending || 0));
    return turma.capacity != null ? `${turma.name} (${total}/${turma.capacity})` : turma.name;
  }

  onManageCourseChange(): void {
    this.turmaError = '';
    this.enrollments = [];
    this.loadEnrollments();
  }

  private loadEnrollments(): void {
    const courseId = this.manageCourseId;
    if (!this.canManage || !courseId) {
      return;
    }
    this.api.getEnrollments(courseId).subscribe({
      next: (r: any) => {
        if (courseId === this.manageCourseId) {
          this.enrollments = r.enrollments || [];
        }
      },
      error: err => this.turmaError = this.errorText(err)
    });
  }

  createClass(): void {
    if (!this.canManage) {
      return;
    }
    this.turmaError = '';
    const body: { course_id: string; name: string; starts_on?: string; capacity?: number } = {
      course_id: this.manageCourseId,
      name: this.newName
    };
    if (this.newStart) {
      body.starts_on = this.newStart;
    }
    if (this.newCapacity !== null && this.newCapacity !== undefined && (this.newCapacity as any) !== '') {
      body.capacity = Number(this.newCapacity);
    }
    this.api.createClass(body).subscribe({
      next: () => {
        this.newName = '';
        this.newStart = '';
        this.newCapacity = null;
        this.refresh();
      },
      error: err => this.turmaError = this.errorText(err)
    });
  }

  assignClass(enrollment: any, event: Event): void {
    const select = event.target as HTMLSelectElement;
    const previous = enrollment.class_id === null || enrollment.class_id === undefined ? '' : String(enrollment.class_id);
    const classId = select.value === '' ? null : Number(select.value);
    this.turmaError = '';
    this.api.setEnrollmentClass(enrollment.id, classId).subscribe({
      next: () => {
        enrollment.class_id = classId;
        this.refresh();
      },
      error: err => {
        select.value = previous;
        this.turmaError = this.errorText(err);
      }
    });
  }

  // Atualiza números e matrículas sem recarregar a página.
  private refresh(): void {
    this.loadCourses();
    this.loadEnrollments();
  }

  // O erro da API (409/422/...) vem em `detail` e é mostrado como está.
  private errorText(err: any): string {
    const detail = err?.error?.detail;
    return typeof detail === 'string' && detail ? detail : 'Não foi possível concluir a operação.';
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
