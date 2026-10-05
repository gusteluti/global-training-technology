import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-audit-logs',
  templateUrl: './audit-logs.component.html'
})
export class AuditLogsComponent implements OnInit {
  logs: any[] = [];
  error = '';

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.api.getAuditLogs().subscribe({
      next: (r: any) => this.logs = r.logs || [],
      error: err => this.error = err?.error?.detail || 'Não foi possível carregar a auditoria.'
    });
  }

  actor(log: any): string {
    if (log.role) return log.role;
    return log.user_id ? `conta #${log.user_id}` : 'sistema';
  }
}
