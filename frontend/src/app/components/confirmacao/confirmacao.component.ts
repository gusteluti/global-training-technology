import { ChangeDetectorRef, Component, ElementRef, HostListener, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { Subscription } from 'rxjs';
import { ConfirmacaoService, OpcoesConfirmacao } from '../../services/confirmacao.service';

// DS1 (D115): janela de confirmação do app, um único componente na casca (app.component.ts).
// role="alertdialog" com título e texto ligados por aria-labelledby/aria-describedby; foco inicial em "Voltar";
// Tab e Shift+Tab presos na janela; Esc equivale a "Voltar"; ao fechar, o foco volta ao elemento que abriu.
@Component({
  selector: 'app-confirmacao',
  template: `
    <div class="gt-confirmacao-fundo" *ngIf="opcoes">
      <div class="gt-confirmacao" data-testid="confirmacao" role="alertdialog" aria-modal="true"
           aria-labelledby="confirmacao-titulo"
           [attr.aria-describedby]="opcoes.texto ? 'confirmacao-titulo confirmacao-texto' : 'confirmacao-titulo'"
           #janela>
        <h2 class="gt-confirmacao-titulo h4" id="confirmacao-titulo">{{ opcoes.titulo }}</h2>
        <p class="gt-confirmacao-texto" id="confirmacao-texto" *ngIf="opcoes.texto">{{ opcoes.texto }}</p>
        <div class="gt-confirmacao-acoes">
          <button type="button" class="btn btn-outline-secondary" data-testid="confirmacao-voltar" #voltar
                  (click)="responder(false)">Voltar</button>
          <button type="button" class="btn" data-testid="confirmacao-confirmar"
                  [class.btn-primary]="!opcoes.destrutiva" [class.gt-btn-destrutiva]="opcoes.destrutiva"
                  (click)="responder(true)">{{ opcoes.rotuloConfirmar }}</button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .gt-confirmacao-fundo {
      position: fixed; inset: 0; z-index: 1080;
      display: flex; align-items: center; justify-content: center;
      padding: 16px; background: rgba(23, 33, 43, 0.6);
    }
    .gt-confirmacao {
      background: #ffffff; color: var(--gt-text); border-radius: 8px;
      width: 100%; max-width: 460px; padding: 24px;
      box-shadow: 0 16px 40px rgba(16, 31, 45, 0.25);
    }
    .gt-confirmacao-titulo { margin-bottom: 8px; overflow-wrap: anywhere; }
    .gt-confirmacao-texto { margin-bottom: 0; overflow-wrap: anywhere; }
    .gt-confirmacao-acoes {
      display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 20px;
    }
    .gt-confirmacao-acoes .btn { min-height: 44px; }
    .gt-btn-destrutiva {
      --bs-btn-bg: #b42318; --bs-btn-border-color: #b42318; --bs-btn-color: #ffffff;
      --bs-btn-hover-bg: #912018; --bs-btn-hover-border-color: #912018; --bs-btn-hover-color: #ffffff;
      --bs-btn-active-bg: #912018; --bs-btn-active-border-color: #912018; --bs-btn-active-color: #ffffff;
      --bs-btn-focus-shadow-rgb: 180, 35, 24;
    }
    @media (prefers-reduced-motion: no-preference) {
      .gt-confirmacao-fundo { animation: gt-confirmacao-entrada .12s ease-out; }
    }
    @keyframes gt-confirmacao-entrada { from { opacity: 0; } to { opacity: 1; } }
  `]
})
export class ConfirmacaoComponent implements OnInit, OnDestroy {
  opcoes: OpcoesConfirmacao | null = null;

  @ViewChild('janela') private janela?: ElementRef<HTMLElement>;
  @ViewChild('voltar') private voltar?: ElementRef<HTMLButtonElement>;

  private origem: HTMLElement | null = null;
  private assinatura?: Subscription;

  constructor(private confirmacao: ConfirmacaoService, private cdr: ChangeDetectorRef) { }

  ngOnInit(): void {
    this.assinatura = this.confirmacao.pedido$.subscribe(pedido => {
      if (pedido) {
        this.abrir(pedido.opcoes);
      } else if (this.opcoes) {
        this.fechar();
      }
    });
  }

  ngOnDestroy(): void {
    this.assinatura?.unsubscribe();
  }

  responder(ok: boolean): void {
    this.confirmacao.responder(ok);
  }

  @HostListener('document:keydown', ['$event'])
  teclado(evento: KeyboardEvent): void {
    if (!this.opcoes) {
      return;
    }
    if (evento.key === 'Escape') {
      evento.preventDefault();
      this.responder(false);
      return;
    }
    if (evento.key !== 'Tab') {
      return;
    }
    const botoes = this.botoes();
    if (!botoes.length) {
      return;
    }
    evento.preventDefault();
    const atual = botoes.indexOf(document.activeElement as HTMLElement);
    const passo = evento.shiftKey ? -1 : 1;
    const proximo = atual < 0 ? 0 : (atual + passo + botoes.length) % botoes.length;
    botoes[proximo].focus();
  }

  private abrir(opcoes: OpcoesConfirmacao): void {
    const ativo = document.activeElement;
    this.origem = ativo instanceof HTMLElement && ativo !== document.body ? ativo : null;
    this.opcoes = opcoes;
    this.cdr.detectChanges();
    this.voltar?.nativeElement.focus();
  }

  private fechar(): void {
    this.opcoes = null;
    this.cdr.detectChanges();
    const origem = this.origem;
    this.origem = null;
    if (origem && origem.isConnected) {
      origem.focus();
    }
  }

  private botoes(): HTMLElement[] {
    const raiz = this.janela?.nativeElement;
    if (!raiz) {
      return [];
    }
    return Array.from(raiz.querySelectorAll<HTMLElement>('button:not([disabled])'));
  }
}
