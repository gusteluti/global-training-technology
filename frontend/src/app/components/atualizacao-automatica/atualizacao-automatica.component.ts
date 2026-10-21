import { Component, ElementRef, EventEmitter, Input, OnDestroy, OnInit, Output } from '@angular/core';

// X5 (D87): os painéis de /admin buscam de novo a cada 30 s, sempre ligado, e pelo botão "Atualizar".
// O ciclo é pulado com a aba do navegador escondida, com campo em foco dentro do painel ou com o painel pausado
// (formulário aberto ou ação em andamento).
const CICLO_MS = 30000;
const FORMATO_HORA = new Intl.DateTimeFormat('pt-BR', {
  timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', hour12: false
});

@Component({
  selector: 'app-atualizacao-automatica',
  template: `
    <div class="d-flex justify-content-end align-items-center gap-2 small text-muted mb-2">
      <span data-testid="atualizacao-hora">Atualizado às {{ hora }}</span>
      <button type="button" class="btn btn-sm btn-outline-secondary" data-testid="atualizacao-botao"
              (click)="atualizarAgora()">Atualizar</button>
    </div>
  `
})
export class AtualizacaoAutomaticaComponent implements OnInit, OnDestroy {
  @Input() pausado = false;
  @Output() atualizar = new EventEmitter<void>();

  hora = '';
  private timer?: ReturnType<typeof setInterval>;

  constructor(private el: ElementRef<HTMLElement>) { }

  ngOnInit(): void {
    this.marcarHora();
    this.timer = setInterval(() => this.ciclo(), CICLO_MS);
  }

  ngOnDestroy(): void {
    clearInterval(this.timer);
  }

  atualizarAgora(): void {
    this.atualizar.emit();
    this.marcarHora();
  }

  private ciclo(): void {
    if (this.pausado || document.hidden || this.campoEmFoco()) {
      return;
    }
    this.atualizarAgora();
  }

  // O componente fica no topo do painel; o elemento pai é o próprio painel (app-financial-dashboard etc.).
  private campoEmFoco(): boolean {
    const ativo = document.activeElement;
    const painel = this.el.nativeElement.parentElement;
    return !!ativo && !!painel && painel.contains(ativo) && ativo.matches('input, textarea, select');
  }

  private marcarHora(): void {
    const p: Record<string, string> = {};
    for (const parte of FORMATO_HORA.formatToParts(new Date())) {
      p[parte.type] = parte.value;
    }
    this.hora = `${p['hour'] === '24' ? '00' : p['hour']}:${p['minute']}`;
  }
}
