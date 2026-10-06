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

  // Responsável: e-mail e perfil; só o nome (token legado); "sistema" quando não há pessoa.
  actor(log: any): string {
    if (log.actor_email) return log.role ? `${log.actor_email} (${log.role})` : log.actor_email;
    if (log.actor_name) return log.actor_name;
    if (log.role && log.role !== 'system') return log.role;
    return log.user_id ? `conta #${log.user_id}` : 'sistema';
  }

  // Valor de uma alteração: texto cru para string e número, JSON para lista/objeto, "null" para nulo.
  value(v: any): string {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'string') return v;
    return typeof v === 'object' ? JSON.stringify(v) : String(v);
  }
}
