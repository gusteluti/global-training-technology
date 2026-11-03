import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { ApiService } from '../../services/api.service';

const FORM_VAZIO = { module: '', title: '', kind: 'video', url: '', duration_minutes: null as number | null, is_extra: false, published: true };
const MSG_ERRO = 'Não foi possível salvar o conteúdo.';

@Component({
  selector: 'app-course-contents',
  templateUrl: './course-contents.component.html'
})
export class CourseContentsComponent implements OnInit {
  @Input() curso: any;
  @Output() fechar = new EventEmitter<void>();

  conteudos: any[] = [];
  form = { ...FORM_VAZIO };
  arquivo: File | null = null;
  editandoId: number | null = null;
  confirmandoId: number | null = null;
  erro = '';
  aviso = '';
  salvando = false;

  constructor(private api: ApiService) { }

  ngOnInit(): void {
    this.carregar();
  }

  private carregar(): void {
    this.api.getCourseContents(this.curso.id).subscribe({
      next: (r: any) => this.conteudos = r.contents || [],
      error: err => this.erro = this.mensagem(err)
    });
  }

  private mensagem(err: any): string {
    const detalhe = err && err.error && err.error.detail;
    return typeof detalhe === 'string' ? detalhe : MSG_ERRO;
  }

  escolherArquivo(evento: Event): void {
    this.arquivo = (evento.target as HTMLInputElement).files?.[0] || null;
  }

  salvar(): void {
    this.erro = '';
    this.aviso = '';
    if (!this.form.module.trim() || !this.form.title.trim()) {
      this.erro = 'Informe o módulo e o título.';
      return;
    }
    if (this.form.kind === 'file' && !this.editandoId && !this.arquivo) {
      this.erro = 'Escolha o arquivo.';
      return;
    }
    this.salvando = true;
    this.requisicao().subscribe({
      next: () => {
        this.salvando = false;
        this.aviso = 'Conteúdo salvo.';
        this.limpar();
        this.carregar();
      },
      error: err => {
        this.salvando = false;
        this.erro = this.mensagem(err);
      }
    });
  }

  private requisicao() {
    if (this.editandoId) {
      return this.api.updateCourseContent(this.editandoId, this.form);
    }
    if (this.form.kind === 'file') {
      return this.api.uploadCourseContent(this.curso.id, this.arquivo as File, this.form);
    }
    return this.api.createCourseContent(this.curso.id, this.form);
  }

  editar(item: any): void {
    this.editandoId = item.id;
    this.erro = '';
    this.aviso = '';
    this.form = {
      module: item.module, title: item.title, kind: item.kind, url: item.url || '',
      duration_minutes: item.duration_minutes, is_extra: item.is_extra, published: item.published
    };
  }

  limpar(): void {
    this.editandoId = null;
    this.arquivo = null;
    this.form = { ...FORM_VAZIO, module: this.form.module };
  }

  alternarPublicacao(item: any): void {
    this.api.updateCourseContent(item.id, { ...item, published: !item.published }).subscribe({
      next: () => this.carregar(),
      error: err => this.erro = this.mensagem(err)
    });
  }

  mover(item: any, direcao: 'up' | 'down'): void {
    this.api.moveCourseContent(item.id, direcao).subscribe({
      next: (r: any) => this.conteudos = r.contents || [],
      error: err => this.erro = this.mensagem(err)
    });
  }

  excluir(item: any): void {
    this.api.deleteCourseContent(item.id).subscribe({
      next: () => {
        this.confirmandoId = null;
        this.carregar();
      },
      error: err => this.erro = this.mensagem(err)
    });
  }

  rotuloTipo(item: any): string {
    return { video: 'Vídeo', file: 'Arquivo', link: 'Link' }[item.kind as string] || '';
  }
}
