import { Component, OnInit } from '@angular/core';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';

const MSG_FAQ = 'Cada linha do FAQ deve ter o formato: Pergunta | Resposta.';
const MSG_URL = 'A URL do material deve começar com http:// ou https://.';
const MSG_MATERIAL = 'Cada linha de material deve ter o formato: Título | URL | tipo.';
const MSG_ERRO_PADRAO = 'Não foi possível concluir a operação.';

interface CourseForm {
  id: string;
  name: string;
  description: string;
  price: number | null;
  hours: number | null;
  level: string;
  audience: string;
  objectives: string;
  topics: string;
  benefits: string;
  faq: string;
  prompt: string;
  materials: string;
}

function emptyForm(): CourseForm {
  return {
    id: '', name: '', description: '', price: null, hours: null, level: '', audience: '',
    objectives: '', topics: '', benefits: '', faq: '', prompt: '', materials: ''
  };
}

// Uma linha por item; apara espaços e ignora linhas vazias (mesmo critério do admin.html legado).
function lines(value: string | null | undefined): string[] {
  return (value || '').split('\n').map(item => item.trim()).filter(Boolean);
}

@Component({
  selector: 'app-course-admin',
  templateUrl: './course-admin.component.html'
})
export class CourseAdminComponent implements OnInit {
  courses: any[] = [];
  form: CourseForm = emptyForm();
  editingId: string | null = null;
  deletingId: string | null = null;
  error = '';
  success = '';
  busy = false;

  // Materiais carregados na edição: se o campo não foi tocado, é exatamente isso que volta no PUT.
  private loadedMaterials: any[] = [];
  private loadedMaterialsText = '';

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.loadCourses();
  }

  get editing(): boolean {
    return this.editingId !== null;
  }

  // Obrigatórios: todos, exceto materiais. Preço > 0; duração inteira > 0.
  get valid(): boolean {
    const f = this.form;
    const texts = [f.id, f.name, f.description, f.level, f.audience, f.prompt];
    if (texts.some(t => !(t || '').trim())) {
      return false;
    }
    if ([f.objectives, f.topics, f.benefits, f.faq].some(t => lines(t).length === 0)) {
      return false;
    }
    const price = f.price;
    const hours = f.hours;
    if (typeof price !== 'number' || !isFinite(price) || price <= 0) {
      return false;
    }
    return typeof hours === 'number' && Number.isInteger(hours) && hours > 0;
  }

  // A lista da API traz id, nome, preço e nível; a duração vem do detalhe de cada curso.
  private loadCourses(): void {
    this.api.getAdminCourses().subscribe({
      next: (r: any) => {
        const resumos: any[] = r.courses || [];
        if (!resumos.length) {
          this.courses = [];
          return;
        }
        forkJoin(resumos.map(c =>
          this.api.getAdminCourse(c.id).pipe(
            catchError(() => of(null))
          )
        )).subscribe(detalhes => {
          this.courses = resumos.map((c, i) => {
            const detalhe: any = (detalhes[i] as any)?.course;
            return { ...c, duration_hours: detalhe?.duration_hours ?? null };
          });
        });
      },
      error: err => this.error = this.errorText(err)
    });
  }

  edit(course: any): void {
    this.clearMessages();
    this.deletingId = null;
    this.api.getAdminCourse(course.id).subscribe({
      next: (r: any) => this.fillForm(r.course),
      error: err => this.error = this.errorText(err)
    });
  }

  private fillForm(c: any): void {
    const materials: any[] = c.materials || [];
    const materialsText = materials.map(m => `${m.title} | ${m.url} | ${m.type}`).join('\n');
    this.loadedMaterials = materials;
    this.loadedMaterialsText = materialsText;
    this.editingId = c.id;
    this.form = {
      id: c.id,
      name: c.name || '',
      description: c.description || '',
      price: c.price ?? null,
      hours: c.duration_hours ?? null,
      level: c.level || '',
      audience: c.target_audience || '',
      objectives: (c.objectives || []).join('\n'),
      topics: (c.topics || []).join('\n'),
      benefits: (c.benefits || []).join('\n'),
      faq: (c.faq || []).map((i: any) => `${i.question} | ${i.answer}`).join('\n'),
      prompt: c.system_prompt || '',
      materials: materialsText
    };
  }

  cancelEdit(): void {
    this.resetForm();
    this.clearMessages();
  }

  private resetForm(): void {
    this.form = emptyForm();
    this.editingId = null;
    this.loadedMaterials = [];
    this.loadedMaterialsText = '';
  }

  private clearMessages(): void {
    this.error = '';
    this.success = '';
  }

  save(): void {
    if (this.busy || !this.valid) {
      return;
    }
    this.clearMessages();
    const faq = this.parseFaq();
    if (faq === null) {
      this.error = MSG_FAQ;
      return;
    }
    const materials = this.parseMaterials();
    if (typeof materials === 'string') {
      this.error = materials;
      return;
    }
    const f = this.form;
    const body = {
      id: f.id.trim(),
      name: f.name.trim(),
      description: f.description.trim(),
      price: Number(f.price),
      duration_hours: Number(f.hours),
      level: f.level.trim(),
      target_audience: f.audience.trim(),
      objectives: lines(f.objectives),
      topics: lines(f.topics),
      benefits: lines(f.benefits),
      faq,
      system_prompt: f.prompt.trim(),
      materials
    };
    this.busy = true;
    const chamada = this.editingId !== null
      ? this.api.updateCourse(this.editingId, body)
      : this.api.createCourse(body);
    chamada.subscribe({
      next: () => {
        this.busy = false;
        this.resetForm();
        this.success = 'Curso salvo.';
        this.loadCourses();
      },
      error: err => {
        this.busy = false;
        this.error = this.errorText(err);
      }
    });
  }

  // `Pergunta | Resposta`: separa no primeiro "|" (a resposta pode ter outros). null se alguma linha for inválida.
  private parseFaq(): { question: string; answer: string }[] | null {
    const result: { question: string; answer: string }[] = [];
    for (const row of lines(this.form.faq)) {
      const cut = row.indexOf('|');
      if (cut < 0) {
        return null;
      }
      const question = row.slice(0, cut).trim();
      const answer = row.slice(cut + 1).trim();
      if (!question || !answer) {
        return null;
      }
      result.push({ question, answer });
    }
    return result;
  }

  // `Título | URL | tipo` (tipo opcional, padrão "link"). Devolve a mensagem de erro (texto) se inválido.
  private parseMaterials(): { title: string; url: string; type: string }[] | string {
    if (this.editing && this.form.materials === this.loadedMaterialsText) {
      return this.loadedMaterials;
    }
    const result: { title: string; url: string; type: string }[] = [];
    for (const row of lines(this.form.materials)) {
      const parts = row.split('|').map(p => p.trim());
      const title = parts[0];
      const url = parts[1] || '';
      const type = parts[2] || 'link';
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        return MSG_URL;
      }
      if (!title) {
        return MSG_MATERIAL;
      }
      result.push({ title, url, type });
    }
    return result;
  }

  askDelete(course: any): void {
    this.clearMessages();
    this.deletingId = course.id;
  }

  cancelDelete(): void {
    this.deletingId = null;
  }

  confirmDelete(course: any): void {
    if (this.busy) {
      return;
    }
    this.clearMessages();
    this.busy = true;
    this.api.deleteCourse(course.id).subscribe({
      next: () => {
        this.busy = false;
        this.deletingId = null;
        if (this.editingId === course.id) {
          this.resetForm();
        }
        this.success = 'Curso removido.';
        this.loadCourses();
      },
      error: err => {
        this.busy = false;
        this.deletingId = null;
        this.error = this.errorText(err);
      }
    });
  }

  // O erro da API vem em `detail` e é mostrado como está; sem texto, mensagem padrão.
  private errorText(err: any): string {
    const detail = err?.error?.detail;
    return typeof detail === 'string' && detail ? detail : MSG_ERRO_PADRAO;
  }
}
