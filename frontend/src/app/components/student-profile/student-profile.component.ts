import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { salvarArquivo } from '../../services/salvar-arquivo';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';

// Mensagem da API quando é texto; validação genérica do servidor (lista) cai no texto padrão.
function detalheDoErro(err: any, padrao: string): string {
  const detail = err?.error?.detail;
  return typeof detail === 'string' && detail ? detail : padrao;
}

// Perfil do próprio aluno (U3/S5, D80): nome, telefone e troca de senha. E-mail só leitura.
@Component({
  selector: 'app-student-profile',
  templateUrl: './student-profile.component.html'
})
export class StudentProfileComponent implements OnInit {
  nome = '';
  telefone = '';
  email = '';
  senhaAtual = '';
  senhaNova = '';
  ok = '';
  erro = '';
  enviando = false;
  senhaExclusao = '';

  constructor(private api: ApiService, private auth: AuthService, private router: Router) { }

  ngOnInit(): void {
    this.api.getMyProfile().subscribe({
      next: (res: any) => this.preencher(res),
      error: err => this.erro = detalheDoErro(err, 'Não foi possível carregar seu perfil.')
    });
  }

  private preencher(res: any): void {
    this.nome = res?.name || '';
    this.telefone = res?.phone || '';
    this.email = res?.email || '';
  }

  private limparMensagens(): void {
    this.ok = '';
    this.erro = '';
  }

  salvarDados(): void {
    if (this.enviando) {
      return;
    }
    this.limparMensagens();
    this.enviando = true;
    const telefone = this.telefone.trim();
    this.api.updateMyProfile(this.nome, telefone ? telefone : null).subscribe({
      next: (res: any) => {
        this.enviando = false;
        this.preencher(res);
        this.ok = 'Dados atualizados.';
      },
      error: err => {
        this.enviando = false;
        this.erro = detalheDoErro(err, 'Não foi possível salvar seus dados.');
      }
    });
  }

  trocarSenha(): void {
    if (this.enviando) {
      return;
    }
    this.limparMensagens();
    this.enviando = true;
    this.api.changeMyPassword(this.senhaAtual, this.senhaNova).subscribe({
      next: (res: any) => {
        this.enviando = false;
        if (res?.token) {
          // A sessão atual continua com o token novo; o antigo deixou de valer na API.
          this.auth.setToken(res.token);
        }
        this.senhaAtual = '';
        this.senhaNova = '';
        this.ok = 'Senha alterada.';
      },
      error: err => {
        this.enviando = false;
        this.erro = detalheDoErro(err, 'Não foi possível alterar a senha.');
      }
    });
  }

  exportarDados(): void {
    this.ok = '';
    this.erro = '';
    this.api.exportMyData().subscribe({
      next: resposta => salvarArquivo(resposta, 'meus-dados.json'),
      error: err => this.erro = detalheDoErro(err, 'Não foi possível baixar seus dados.')
    });
  }

  excluirConta(): void {
    if (!confirm('Excluir sua conta? Essa ação não pode ser desfeita.')) {
      return;
    }
    this.ok = '';
    this.erro = '';
    this.enviando = true;
    this.api.deleteMyAccount(this.senhaExclusao).subscribe({
      next: () => {
        this.enviando = false;
        this.auth.logout();
        this.router.navigate(['/login'], { queryParams: { conta: 'excluida' } });
      },
      error: err => {
        this.enviando = false;
        this.erro = detalheDoErro(err, 'Não foi possível excluir a conta.');
      }
    });
  }
}
