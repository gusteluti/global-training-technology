import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Chart } from '../../charts';
import { salvarArquivo } from '../../services/salvar-arquivo';

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

  // Alunos do curso (F4, D73): todos os perfis internos; a tela não mostra valores.
  alunosCurso: any = null;
  alunos: any[] = [];
  alunosErro = '';
  filtroStatus = '';
  filtroTurma = '';
  readonly statusOpcoes = ['active', 'pending', 'cancelled', 'refunded'];

  // Exportação CSV dos alunos do curso só para Gestão e Financeiro (U1, D74); Suporte não vê o botão.
  podeExportar = false;
  exportando = false;

  constructor(private api: ApiService, private auth: AuthService) { }

  ngOnInit(): void {
    this.canManage = this.auth.getRole() === 'admin';
    this.podeExportar = ['admin', 'financial'].includes(this.auth.getRole() || '');
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

  abrirAlunosCurso(curso: any): void {
    this.alunosCurso = curso;
    this.filtroStatus = '';
    this.filtroTurma = '';
    this.carregarAlunosCurso();
  }

  fecharAlunosCurso(): void {
    this.alunosCurso = null;
    this.alunos = [];
    this.alunosErro = '';
  }

  carregarAlunosCurso(): void {
    const curso = this.alunosCurso;
    if (!curso) {
      return;
    }
    const filtros = { status: this.filtroStatus, class_id: this.filtroTurma };
    this.alunosErro = '';
    this.api.getCourseStudents(curso.id, filtros).subscribe({
      next: (r: any) => {
        if (curso === this.alunosCurso && filtros.status === this.filtroStatus && filtros.class_id === this.filtroTurma) {
          this.alunos = r.students || [];
        }
      },
      error: err => this.alunosErro = this.errorText(err)
    });
  }

  exportarAlunosCurso(): void {
    const curso = this.alunosCurso;
    if (!curso || !this.podeExportar || this.exportando) {
      return;
    }
    this.exportando = true;
    this.api.exportCourseStudentsCsv(curso.id, { status: this.filtroStatus, class_id: this.filtroTurma }).subscribe({
      next: resposta => {
        this.exportando = false;
        salvarArquivo(resposta, 'alunos-curso.csv');
      },
      error: () => {
        this.exportando = false;
        this.alunosErro = 'Não foi possível exportar o CSV.';
      }
    });
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
          backgroundColor: '#0096c7'
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
