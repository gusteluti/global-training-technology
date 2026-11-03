import { Component, OnInit } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { salvarArquivo } from '../../services/salvar-arquivo';

// Só estes players entram no iframe; o endereço é montado pelo servidor (D96).
const PLAYERS = ['https://www.youtube-nocookie.com/embed/', 'https://player.vimeo.com/video/'];
const MSG_ERRO = 'Não foi possível abrir este curso. Ele só fica disponível com a matrícula ativa.';
const MSG_ARQUIVO = 'Não foi possível baixar o arquivo. Tente novamente.';

@Component({
  selector: 'app-course-room',
  templateUrl: './course-room.component.html'
})
export class CourseRoomComponent implements OnInit {
  sala: any = null;
  atual: any = null;
  player: SafeResourceUrl | null = null;
  erro = '';
  erroArquivo = '';
  carregando = true;
  private matriculaId = 0;

  constructor(private api: ApiService, private route: ActivatedRoute, private sanitizer: DomSanitizer) { }

  ngOnInit(): void {
    this.matriculaId = Number(this.route.snapshot.paramMap.get('id'));
    this.api.getCourseRoom(this.matriculaId).subscribe({
      next: (sala: any) => {
        this.sala = sala;
        this.carregando = false;
        this.abrir(this.itemDaChave(sala.next_key) || this.aulas()[0] || sala.extras[0] || null);
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

  abrir(item: any): void {
    this.atual = item;
    this.erroArquivo = '';
    const embed = item && item.embed_url;
    const permitido = embed && PLAYERS.some(prefixo => embed.startsWith(prefixo));
    this.player = permitido ? this.sanitizer.bypassSecurityTrustResourceUrl(embed) : null;
  }

  alternarConcluido(item: any, feito: boolean): void {
    item.done = feito;
    this.api.markMaterial(this.matriculaId, item.key, feito).subscribe({
      next: (r: any) => this.sala.progress = r.progress,
      error: () => item.done = !feito
    });
  }

  baixar(item: any): void {
    this.erroArquivo = '';
    this.api.downloadContent(this.matriculaId, item.content_id).subscribe({
      next: resposta => salvarArquivo(resposta, item.file_name || 'arquivo'),
      error: () => this.erroArquivo = MSG_ARQUIVO
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
      error: () => {
        aba?.close();
        this.erroArquivo = MSG_ARQUIVO;
      }
    });
  }

  baixarCertificado(): void {
    this.api.downloadCertificate(this.matriculaId).subscribe({
      next: resposta => salvarArquivo(resposta, 'certificado.pdf'),
      error: () => this.erroArquivo = MSG_ARQUIVO
    });
  }

  ePdf(item: any): boolean {
    return (item.file_name || '').toLowerCase().endsWith('.pdf');
  }

  rotuloTipo(item: any): string {
    return { video: 'Vídeo', file: 'Arquivo', link: 'Link' }[item.kind as string] || '';
  }
}
