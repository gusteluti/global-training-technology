import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, forkJoin, map, of } from 'rxjs';
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

  constructor(private api: ApiService, private router: Router) { }

  ngOnInit(): void {
    // Se as matrículas não carregarem, o catálogo aparece como antes (o backend continua barrando duplicidade).
    const matriculas$ = this.api.getMyEnrollments().pipe(
      map((res: any) => (res && res.enrollments) || []),
      catchError(() => of([]))
    );
    forkJoin({ cursos: this.api.getPublicCourses(), matriculas: matriculas$ }).subscribe({
      next: ({ cursos, matriculas }: { cursos: any; matriculas: any[] }) => {
        this.cursos = (cursos && cursos.courses) || [];
        this.situacao = this.montarSituacao(matriculas);
        this.carregando = false;
      },
      error: () => {
        this.erro = 'Não foi possível carregar os cursos. Tente novamente.';
        this.carregando = false;
      }
    });
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
    if (this.comprandoId) {
      return;
    }
    this.erro = '';
    this.mensagem = '';
    this.comprandoId = curso.id;
    this.api.studentCheckout(curso.id).subscribe({
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
      }
    });
  }
}
