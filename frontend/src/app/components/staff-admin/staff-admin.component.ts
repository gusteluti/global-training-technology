import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';

// Gestão da equipe (S3, D85): só a Gestão. A API aplica as mesmas regras (própria conta, última Gestão ativa).
@Component({
  selector: 'app-staff-admin',
  templateUrl: './staff-admin.component.html'
})
export class StaffAdminComponent implements OnInit {
  readonly perfis = [
    { value: 'admin', label: 'Gestão' },
    { value: 'financial', label: 'Financeiro' },
    { value: 'support', label: 'Suporte' }
  ];

  equipe: any[] = [];
  email = '';
  nome = '';
  perfil = 'support';
  ok = '';
  erro = '';
  meuId: number | null = null;

  constructor(private api: ApiService, private auth: AuthService) { }

  ngOnInit(): void {
    const dados = this.auth.decodeToken();
    this.meuId = dados && typeof dados.user_id === 'number' ? dados.user_id : null;
    this.carregar();
  }

  rotulo(perfil: string): string {
    return this.perfis.find(p => p.value === perfil)?.label || perfil;
  }

  carregar(): void {
    this.api.getStaff().subscribe({
      next: (r: any) => this.equipe = r.staff || [],
      error: err => this.erro = this.texto(err, 'Não foi possível carregar a equipe.')
    });
  }

  convidar(): void {
    this.ok = '';
    this.erro = '';
    const email = this.email.trim();
    this.api.inviteStaff({ email, name: this.nome.trim(), role: this.perfil }).subscribe({
      next: () => {
        this.ok = `Convite enviado para ${email}.`;
        this.email = '';
        this.nome = '';
        this.carregar();
      },
      error: err => this.erro = this.texto(err, 'Não foi possível enviar o convite.')
    });
  }

  trocarPerfil(pessoa: any, event: Event): void {
    const select = event.target as HTMLSelectElement;
    const anterior = pessoa.role;
    this.ok = '';
    this.erro = '';
    this.api.updateStaff(pessoa.id, { role: select.value }).subscribe({
      next: () => {
        this.ok = `Perfil de ${pessoa.name} alterado para ${this.rotulo(select.value)}.`;
        this.carregar();
      },
      error: err => {
        select.value = anterior;
        this.erro = this.texto(err, 'Não foi possível alterar o perfil.');
      }
    });
  }

  alterarAtivo(pessoa: any, ativo: boolean): void {
    const acao = ativo ? 'Reativar' : 'Desativar';
    if (!confirm(`${acao} a conta de "${pessoa.name}"?`)) {
      return;
    }
    this.ok = '';
    this.erro = '';
    this.api.setStaffActive(pessoa.id, ativo).subscribe({
      next: () => {
        this.ok = `Conta de ${pessoa.name} ${ativo ? 'reativada' : 'desativada'}.`;
        this.carregar();
      },
      error: err => this.erro = this.texto(err, 'Não foi possível alterar a conta.')
    });
  }

  private texto(err: any, padrao: string): string {
    const detail = err?.error?.detail;
    return typeof detail === 'string' && detail ? detail : padrao;
  }
}
