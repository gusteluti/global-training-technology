import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-students-dashboard',
  templateUrl: './students-dashboard.component.html'
})
export class StudentsDashboardComponent implements OnInit {
  metrics: any = null;
  students: any[] = [];
  error = '';

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getStudents().subscribe({
      next: (r: any) => {
        this.metrics = r.metrics;
        this.students = r.students || [];
      },
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar os alunos.'
    });
  }
}
