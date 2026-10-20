import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { catchError, forkJoin, map, of, switchMap } from 'rxjs';
import { ApiService } from '../../services/api.service';

// Catálogo de cursos do aluno logado (Parte 1): mostra os mesmos cursos da landing e permite
// comprar/matricular. A compra abre o checkout do Mercado Pago; o acesso ao curso (materiais) só
// é liberado quando o pagamento for aprovado (matrícula nasce 'pending').
interface CursoCatalogo {
  id: string;
  name: string;
  price: number | null;
  level: string;
}

// Turma aberta de um curso (F5a, D75): `seats_left` nulo quando a turma não tem capacidade.
interface TurmaCatalogo {
  id: number;
  name: string;
  starts_on: string | null;
  capacity: number | null;
  seats_left: number | null;
}

@Component({
  selector: 'app-course-catalog',
  templateUrl: './course-catalog.component.html'
})
export class CourseCatalogComponent implements OnInit {
  cursos: CursoCatalogo[] = [];
  carregando = true;
  erro = '';
  mensagem = '';
  comprandoId: string | null = null;
  // Situação do aluno por curso (D72): 'active' esconde a compra; 'pending' vira "Retomar pagamento".
  situacao: Record<string, 'active' | 'pending'> = {};
  // Turmas abertas por curso e turma escolhida (F5a, D75). Curso com turmas exige a escolha antes da compra.
  turmas: Record<string, TurmaCatalogo[]> = {};
  turmaEscolhida: Record<string, number | null> = {};

  constructor(private api: ApiService, private router: Router, private route: ActivatedRoute) { }

  ngOnInit(): void {
    // Se as matrículas não carregarem, o catálogo aparece como antes (o backend continua barrando duplicidade).
    const matriculas$ = this.api.getMyEnrollments().pipe(
      map((res: any) => (res && res.enrollments) || []),
      catchError(() => of([]))
    );
    forkJoin({ cursos: this.api.getPublicCourses(), matriculas: matriculas$ }).pipe(
      switchMap(({ cursos, matriculas }: { cursos: any; matriculas: any[] }) => {
        const lista: CursoCatalogo[] = (cursos && cursos.courses) || [];
        const turmas$ = lista.length
          ? forkJoin(lista.map(c => this.turmasDe(c.id)))
          : of([] as TurmaCatalogo[][]);
        return turmas$.pipe(map(turmas => ({ lista, matriculas, turmas })));
      })
    ).subscribe({
      next: ({ lista, matriculas, turmas }) => {
        this.cursos = lista;
        this.situacao = this.montarSituacao(matriculas);
        lista.forEach((c, i) => {
          this.turmas[c.id] = turmas[i] || [];
          this.turmaEscolhida[c.id] = null;
        });
        this.preSelecionar();
        this.carregando = false;
      },
      error: () => {
        this.erro = 'Não foi possível carregar os cursos. Tente novamente.';
        this.carregando = false;
      }
    });
  }

  // Se as turmas de um curso não carregarem, o cartão fica como o de um curso sem turmas.
  private turmasDe(courseId: string) {
    return this.api.getCourseTurmas(courseId).pipe(
      map((res: any) => (Array.isArray(res) ? res : []) as TurmaCatalogo[]),
      catchError(() => of([] as TurmaCatalogo[]))
    );
  }

  // `?curso=<id>&turma=<id>` pré-seleciona a turma (D75), só se ela estiver aberta e com vaga.
  private preSelecionar(): void {
    const params = this.route.snapshot.queryParamMap;
    const curso = params.get('curso');
    const turma = Number(params.get('turma'));
    if (!curso || !turma || !this.turmas[curso]) {
      return;
    }
    const alvo = this.turmas[curso].find(t => t.id === turma);
    if (alvo && !this.lotada(alvo)) {
      this.turmaEscolhida[curso] = alvo.id;
    }
  }

  lotada(turma: TurmaCatalogo): boolean {
    return turma.seats_left !== null && turma.seats_left !== undefined && turma.seats_left <= 0;
  }

  rotuloTurma(turma: TurmaCatalogo): string {
    const partes = [turma.name, turma.starts_on ? `início ${this.dataBr(turma.starts_on)}` : 'sem data definida'];
    if (this.lotada(turma)) {
      partes.push('(lotada)');
    } else if (turma.seats_left !== null && turma.seats_left !== undefined) {
      partes.push(turma.seats_left === 1 ? '1 vaga' : `${turma.seats_left} vagas`);
    }
    return partes.join(' — ');
  }

  private dataBr(iso: string): string {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
  }

  escolherTurma(courseId: string, valor: string): void {
    const id = Number(valor);
    this.turmaEscolhida[courseId] = valor && id ? id : null;
  }

  // Curso com turmas: a compra fica bloqueada até escolher uma turma.
  faltaTurma(curso: CursoCatalogo): boolean {
    return (this.turmas[curso.id] || []).length > 0 && !this.turmaEscolhida[curso.id];
  }

  private montarSituacao(matriculas: any[]): Record<string, 'active' | 'pending'> {
    const situacao: Record<string, 'active' | 'pending'> = {};
    for (const m of matriculas) {
      if (!m || !m.course_id) {
        continue;
      }
      if (m.status === 'active') {
        situacao[m.course_id] = 'active';
      } else if (m.status === 'pending' && situacao[m.course_id] !== 'active') {
        situacao[m.course_id] = 'pending';
      }
    }
    return situacao;
  }

  precoBr(valor: number | null): string {
    if (valor === null || valor === undefined || isNaN(Number(valor))) {
      return 'Sob consulta';
    }
    return Number(valor).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  comprar(curso: CursoCatalogo): void {
    if (this.comprandoId || this.faltaTurma(curso)) {
      return;
    }
    this.erro = '';
    this.mensagem = '';
    this.comprandoId = curso.id;
    this.api.studentCheckout(curso.id, this.turmaEscolhida[curso.id] || null).subscribe({
      next: (res: any) => {
        this.comprandoId = null;
        if (res && res.mocked) {
          // Demonstração: pagamento mockado já ativou a matrícula no backend.
          this.mensagem = `Matrícula em "${curso.name}" concluída (pagamento simulado). Redirecionando para a área do aluno...`;
          setTimeout(() => this.router.navigate(['/student']), 1200);
          return;
        }
        const url = res && res.checkout_url;
        if (url) {
          this.mensagem = 'Checkout criado. Abrimos o pagamento em uma nova aba — o curso é liberado após a confirmação.';
          window.open(url, '_blank', 'noopener,noreferrer');
        } else {
          this.erro = 'Não foi possível obter o link de pagamento. Tente novamente.';
        }
      },
      error: (err: any) => {
        this.comprandoId = null;
        this.erro = err?.error?.detail || 'Não foi possível iniciar a compra. Tente novamente.';
        // Turma lotada ou encerrada (409/404): recarrega as vagas para o aluno escolher outra.
        if ((err?.status === 409 || err?.status === 404) && (this.turmas[curso.id] || []).length > 0) {
          this.turmasDe(curso.id).subscribe(lista => {
            this.turmas[curso.id] = lista;
            const atual = lista.find(t => t.id === this.turmaEscolhida[curso.id]);
            if (!atual || this.lotada(atual)) {
              this.turmaEscolhida[curso.id] = null;
            }
          });
        }
      }
    });
  }
}
