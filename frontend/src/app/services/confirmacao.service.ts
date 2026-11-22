import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

// DS1 (D115): janela de confirmação do próprio app no lugar do confirm() do navegador.
// O comportamento é o mesmo do confirm(): a promessa resolve true em "Confirmar" e false em "Voltar"/Esc.
export interface OpcoesConfirmacao {
  titulo: string;
  texto?: string;
  rotuloConfirmar: string;
  destrutiva?: boolean;
}

export interface PedidoConfirmacao {
  opcoes: OpcoesConfirmacao;
  responder: (ok: boolean) => void;
}

@Injectable({ providedIn: 'root' })
export class ConfirmacaoService {
  private readonly pedidoAtual = new BehaviorSubject<PedidoConfirmacao | null>(null);
  readonly pedido$ = this.pedidoAtual.asObservable();

  confirmar(opcoes: OpcoesConfirmacao): Promise<boolean> {
    // Uma janela por vez: um pedido anterior ainda aberto conta como "Voltar".
    this.responder(false);
    return new Promise<boolean>(resolve => {
      this.pedidoAtual.next({ opcoes, responder: resolve });
    });
  }

  responder(ok: boolean): void {
    const pedido = this.pedidoAtual.value;
    if (!pedido) {
      return;
    }
    this.pedidoAtual.next(null);
    pedido.responder(ok);
  }
}
