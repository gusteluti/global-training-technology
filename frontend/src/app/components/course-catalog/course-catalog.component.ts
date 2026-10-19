import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
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

  constructor(private api: ApiService, private router: Router) { }

  ngOnInit(): void {
    this.api.getPublicCourses().subscribe({
      next: (res: any) => {
        this.cursos = (res && res.courses) || [];
        this.carregando = false;
      },
      error: () => {
        this.erro = 'Não foi possível carregar os cursos. Tente novamente.';
        this.carregando = false;
      }
    });
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
