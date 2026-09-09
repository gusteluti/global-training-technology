import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-student-dashboard',
  templateUrl: './student-dashboard.component.html'
})
export class StudentDashboardComponent implements OnInit {
  courses: any[] = [];
  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getPublicCourses().subscribe((res: any) => {
      this.courses = res.courses || [];
    }, err => {
      console.error('Error loading courses', err);
    });
  }
}
