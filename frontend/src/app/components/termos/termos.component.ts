import { Component } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

// Termos de uso e política de privacidade (U7, D89). Texto de projeto acadêmico; revisão jurídica fica para a
// operação real. A rota define qual documento aparece (data.doc).
@Component({
  selector: 'app-termos',
  template: `
<div class="row justify-content-center mt-4">
  <div class="col-lg-8">
    <div class="card"><div class="card-body" data-testid="termos-texto">
      <ng-container *ngIf="doc === 'privacidade'; else termos">
        <h3>Política de Privacidade</h3>
        <p class="text-muted small">Versão 2026-10 · Projeto acadêmico (TCC)</p>
        <h5>Quais dados coletamos</h5>
        <p>Nome, e-mail, telefone (opcional), senha (guardada só como código irreversível), matrículas, pagamentos
          e as mensagens enviadas ao assistente virtual.</p>
        <h5>Para que usamos</h5>
        <p>Para criar sua conta, liberar os cursos comprados, emitir recibos, atender pelo chat e cumprir obrigações
          legais e fiscais. Não vendemos nem compartilhamos seus dados para publicidade.</p>
        <h5>Conversas com o assistente</h5>
        <p>As mensagens do chat são gravadas para dar contexto ao atendimento e melhorar o serviço. Não envie dados
          sensíveis (documentos, cartões, senhas).</p>
        <h5>Seus direitos (LGPD, art. 18)</h5>
        <p>Na área do aluno, em <strong>Meu perfil</strong>, você pode baixar todos os seus dados e excluir sua conta.
          Na exclusão, nome, e-mail, telefone, senha e conversas são apagados; matrículas e pagamentos ficam sem
          identificação pessoal, porque o registro financeiro é obrigação legal (art. 16).</p>
      </ng-container>
      <ng-template #termos>
        <h3>Termos de Uso</h3>
        <p class="text-muted small">Versão 2026-10 · Projeto acadêmico (TCC)</p>
        <p>Ao criar uma conta você concorda em usar a plataforma de forma lícita, manter sua senha em sigilo e
          fornecer dados verdadeiros.</p>
        <p>O acesso aos materiais de um curso é liberado depois da confirmação do pagamento. Você pode pedir o
          cancelamento em até 7 dias da aprovação do pagamento (Código de Defesa do Consumidor, art. 49).</p>
        <p>O assistente virtual é automatizado e pode errar; em caso de dúvida, fale com um atendente.</p>
        <p>O tratamento dos seus dados segue a <a routerLink="/privacidade">Política de Privacidade</a>.</p>
      </ng-template>
      <a routerLink="/cadastro" class="btn btn-link px-0">Voltar ao cadastro</a>
    </div></div>
  </div>
</div>`
})
export class TermosComponent {
  doc: string;

  constructor(route: ActivatedRoute) {
    this.doc = route.snapshot.data['doc'] || 'termos';
  }
}
