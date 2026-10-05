import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-admin-dashboard',
  templateUrl: './admin-dashboard.component.html'
})
export class AdminDashboardComponent implements OnInit {
  financial: any = null;
  students: any = null;
  courses: any = null;
  logs: any[] = [];

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getFinancial().subscribe((r: any) => this.financial = r.revenue_data, () => {});
    this.api.getStudents().subscribe((r: any) => this.students = r.student_metrics, () => {});
    this.api.getCoursesMetrics().subscribe((r: any) => this.courses = r.course_metrics, () => {});
    this.api.getAuditLogs().subscribe((r: any) => this.logs = r.logs || [], () => {});
  }
}
