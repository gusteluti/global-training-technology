import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { salvarArquivo } from '../../services/salvar-arquivo';
import { AvancoDoVideo } from '../video-player/video-player.component';

const MSG_ERRO = 'Não foi possível abrir este curso. Ele só fica disponível com a matrícula ativa.';
const MSG_ARQUIVO = 'Não foi possível baixar o arquivo. Tente novamente.';
const MSG_ACESSO_ENCERRADO = 'Seu acesso a este curso foi encerrado.';
const TIPOS_DE_MATERIAL: { [tipo: string]: string } = {
  pdf: 'PDF', xls: 'Planilha', xlsx: 'Planilha', doc: 'Documento', docx: 'Documento', ppt: 'Slides', pptx: 'Slides'
};

@Component({
  selector: 'app-course-room',
  templateUrl: './course-room.component.html'
})
export class CourseRoomComponent implements OnInit {
  sala: any = null;
  atual: any = null;
  videoComFalha = false;
  erro = '';
  erroArquivo = '';
  carregando = true;
  private matriculaId = 0;

  constructor(private api: ApiService, private route: ActivatedRoute) { }

  ngOnInit(): void {
    this.matriculaId = Number(this.route.snapshot.paramMap.get('id'));
    this.api.getCourseRoom(this.matriculaId).subscribe({
      next: (sala: any) => {
        this.sala = sala;
        this.carregando = false;
        this.abrir(this.itemDaChave(sala.resume_key) || this.aulas()[0] || sala.extras[0] || null);
      },
      error: () => {
        this.erro = MSG_ERRO;
        this.carregando = false;
      }
    });
  }

  private aulas(): any[] {
    return this.sala.modules.reduce((todas: any[], modulo: any) => todas.concat(modulo.items), []);
  }

  private itemDaChave(chave: string | null): any {
    return [...this.aulas(), ...this.sala.extras].find(item => item.key === chave);
  }

  // Só uma escolha do aluno grava a posição e leva ao conteúdo; a abertura da página não muda nada.
  escolher(item: any): void {
    this.abrir(item);
    this.api.markContentSeen(this.matriculaId, item.key).subscribe({ error: err => this.verificarAcesso(err) });
    setTimeout(() => document.querySelector('.sala-atual')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }

  get proxima(): any {
    const aulas = this.aulas();
    const posicao = aulas.indexOf(this.atual);
    return posicao >= 0 ? aulas[posicao + 1] : undefined;
  }

  // 409: a matrícula deixou de estar ativa com a página aberta. A sala sai da tela.
  private verificarAcesso(err: any): boolean {
    if (err && err.status === 409) {
      this.sala = null;
      this.atual = null;
      this.erro = MSG_ACESSO_ENCERRADO;
      return true;
    }
    return false;
  }

  abrir(item: any): void {
    this.atual = item;
    this.erroArquivo = '';
    this.videoComFalha = false;
  }

  // Aula concluída recomeça do início; as demais continuam de onde o aluno parou.
  get inicioDoVideo(): number {
    return !this.atual || this.atual.done ? 0 : this.atual.position || 0;
  }

  registrarAvanco(avanco: AvancoDoVideo): void {
    const item = this.itemDaChave(avanco.key);
    if (!item) {
      return;
    }
    this.api.saveVideoProgress(this.matriculaId, avanco).subscribe({
      next: (r: any) => {
        item.position = r.video.position;
        item.watched_percent = r.video.percent;
        item.done = item.done || r.video.complete;
        this.sala.progress = r.progress;
      },
      error: err => this.verificarAcesso(err)
    });
  }

  alternarConcluido(item: any, feito: boolean): void {
    item.done = feito;
    this.api.markMaterial(this.matriculaId, item.key, feito).subscribe({
      next: (r: any) => this.sala.progress = r.progress,
      error: err => {
        item.done = !feito;
        this.verificarAcesso(err);
      }
    });
  }

  baixar(item: any): void {
    this.erroArquivo = '';
    this.api.downloadContent(this.matriculaId, item.content_id).subscribe({
      next: resposta => salvarArquivo(resposta, item.file_name || 'arquivo'),
      error: err => this.falhaNoArquivo(err)
    });
  }

  abrirPdf(item: any): void {
    this.erroArquivo = '';
    const aba = window.open('', '_blank');
    this.api.downloadContent(this.matriculaId, item.content_id).subscribe({
      next: resposta => {
        if (aba && resposta.body) {
          aba.location.href = URL.createObjectURL(new Blob([resposta.body], { type: 'application/pdf' }));
        }
      },
      error: err => {
        aba?.close();
        this.falhaNoArquivo(err);
      }
    });
  }

  private falhaNoArquivo(err: any): void {
    if (!this.verificarAcesso(err)) {
      this.erroArquivo = MSG_ARQUIVO;
    }
  }

  baixarCertificado(): void {
    this.api.downloadCertificate(this.matriculaId).subscribe({
      next: resposta => salvarArquivo(resposta, 'certificado.pdf'),
      error: err => this.falhaNoArquivo(err)
    });
  }

  ePdf(item: any): boolean {
    return (item.file_name || '').toLowerCase().endsWith('.pdf');
  }

  rotuloTipo(item: any): string {
    if (item.kind === 'file' && this.ePdf(item)) {
      return 'PDF';
    }
    const material = TIPOS_DE_MATERIAL[String(item.material_type || '').toLowerCase()];
    return material || { video: 'Vídeo', file: 'Arquivo', link: 'Link' }[item.kind as string] || '';
  }
}
