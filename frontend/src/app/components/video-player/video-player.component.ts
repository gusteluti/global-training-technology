import { AfterViewInit, Component, ElementRef, EventEmitter, Input, NgZone, OnChanges, OnDestroy, Output, SimpleChanges, ViewChild } from '@angular/core';

declare const YT: any;
declare const Vimeo: any;

export interface AvancoDoVideo {
  key: string;
  position: number;
  watched_delta: number;
  duration: number;
}

const SCRIPT_YOUTUBE = 'https://www.youtube.com/iframe_api';
const SCRIPT_VIMEO = 'https://player.vimeo.com/api/player.js';
const INTERVALO_MS = 1000;
const ENVIO_A_CADA_SEGUNDOS = 5;
const SALTO_MAXIMO_SEGUNDOS = 2.5; // acima disso foi um pulo na barra, não tempo assistido
const ESPERA_DO_PLAYER_MS = 15000;
const YOUTUBE_TOCANDO = 1;

const scripts: { [url: string]: Promise<void> } = {};

function carregarScript(url: string): Promise<void> {
  if (!scripts[url]) {
    scripts[url] = new Promise((resolve, reject) => {
      const elemento = document.createElement('script');
      elemento.src = url;
      elemento.onerror = () => {
        delete scripts[url];
        reject();
      };
      if (url === SCRIPT_YOUTUBE) {
        (window as any).onYouTubeIframeAPIReady = () => resolve();
      } else {
        elemento.onload = () => resolve();
      }
      document.head.appendChild(elemento);
    });
  }
  return scripts[url];
}

// Player único da sala e da prévia da Gestão (D105). Mede o tempo realmente assistido: pulo na barra não conta.
@Component({
  selector: 'app-video-player',
  template: `<div class="ratio ratio-16x9 video-player" data-testid="sala-player"><div #alvo></div></div>`
})
export class VideoPlayerComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() embedUrl = '';
  @Input() inicio = 0;
  @Input() titulo = '';
  @Input() chave = '';
  @Output() avanco = new EventEmitter<AvancoDoVideo>();
  @Output() falha = new EventEmitter<void>();

  @ViewChild('alvo') private alvo!: ElementRef<HTMLElement>;
  private player: any = null;
  private vimeo = false;
  private relogio: any = null;
  private espera: any = null;
  private ultimaPosicao: number | null = null;
  private assistidoPendente = 0;
  private ultimoEnvio = 0;
  private ultimaEnviada: number | null = null;
  private jaTocou = false;
  private chaveAtiva = ''; // o último envio de um vídeo sai depois de `chave` já apontar para o próximo
  private duracao = 0;
  private montado = false;
  private geracao = 0;

  constructor(private zona: NgZone) { }

  ngAfterViewInit(): void {
    this.montado = true;
    this.criar();
  }

  // Só um vídeo novo recria o player: `inicio` muda a cada envio de progresso e não pode reiniciar a aula.
  ngOnChanges(mudancas: SimpleChanges): void {
    if (this.montado && mudancas['embedUrl']) {
      this.criar();
    }
  }

  ngOnDestroy(): void {
    this.encerrar();
  }

  private encerrar(): void {
    this.geracao++;
    clearInterval(this.relogio);
    clearTimeout(this.espera);
    this.relogio = null;
    if (this.player) {
      if (this.jaTocou) {
        this.enviar();
      }
      try {
        this.player.destroy();
      } catch {
        // o player pode já ter saído da página
      }
      this.player = null;
    }
  }

  private criar(): void {
    this.encerrar();
    this.ultimaPosicao = null;
    this.ultimaEnviada = null;
    this.jaTocou = false;
    this.chaveAtiva = this.chave;
    this.assistidoPendente = 0;
    this.duracao = 0;
    const geracao = this.geracao;
    const host = this.alvo.nativeElement;
    host.innerHTML = '';
    const lugar = document.createElement('div');
    host.appendChild(lugar);
    this.espera = setTimeout(() => this.avisarFalha(geracao), ESPERA_DO_PLAYER_MS);
    this.zona.runOutsideAngular(() => {
      const youtube = /youtube-nocookie\.com\/embed\/([\w-]{11})/.exec(this.embedUrl);
      if (youtube) {
        this.criarYoutube(lugar, youtube[1], geracao);
      } else {
        this.criarVimeo(lugar, geracao);
      }
    });
  }

  private avisarFalha(geracao: number): void {
    if (geracao === this.geracao) {
      clearTimeout(this.espera);
      clearInterval(this.relogio);
      this.zona.run(() => this.falha.emit());
    }
  }

  private criarYoutube(lugar: HTMLElement, videoId: string, geracao: number): void {
    this.vimeo = false;
    carregarScript(SCRIPT_YOUTUBE).then(() => {
      if (geracao !== this.geracao) {
        return;
      }
      this.player = new YT.Player(lugar, {
        host: 'https://www.youtube-nocookie.com',
        videoId,
        playerVars: { start: Math.floor(this.inicio), rel: 0, playsinline: 1, origin: location.origin },
        events: {
          onReady: () => this.pronto(geracao),
          onError: () => this.avisarFalha(geracao)
        }
      });
    }).catch(() => this.avisarFalha(geracao));
  }

  private criarVimeo(lugar: HTMLElement, geracao: number): void {
    this.vimeo = true;
    const achado = /player\.vimeo\.com\/video\/(\d+)(?:\?h=([0-9a-f]+))?/.exec(this.embedUrl);
    if (!achado) {
      this.avisarFalha(geracao);
      return;
    }
    carregarScript(SCRIPT_VIMEO).then(() => {
      if (geracao !== this.geracao) {
        return;
      }
      const url = `https://player.vimeo.com/video/${achado[1]}${achado[2] ? `?h=${achado[2]}` : ''}`;
      this.player = new Vimeo.Player(lugar, { url, responsive: false });
      this.player.on('error', () => this.avisarFalha(geracao));
      this.player.ready().then(() => {
        if (this.inicio > 0) {
          this.player.setCurrentTime(this.inicio);
        }
        this.pronto(geracao);
      }).catch(() => this.avisarFalha(geracao));
    }).catch(() => this.avisarFalha(geracao));
  }

  private pronto(geracao: number): void {
    if (geracao !== this.geracao) {
      return;
    }
    clearTimeout(this.espera);
    this.ultimoEnvio = Date.now();
    const quadro = this.alvo.nativeElement.querySelector('iframe');
    if (quadro) {
      quadro.title = this.titulo;
    }
    this.relogio = setInterval(() => this.medir(geracao), INTERVALO_MS);
  }

  private async lerEstado(): Promise<{ tocando: boolean; posicao: number; duracao: number }> {
    if (this.vimeo) {
      const [pausado, posicao, duracao] = await Promise.all(
        [this.player.getPaused(), this.player.getCurrentTime(), this.player.getDuration()]);
      return { tocando: !pausado, posicao, duracao };
    }
    return {
      tocando: this.player.getPlayerState() === YOUTUBE_TOCANDO,
      posicao: this.player.getCurrentTime(),
      duracao: this.player.getDuration()
    };
  }

  private async medir(geracao: number): Promise<void> {
    try {
      const { tocando, posicao, duracao } = await this.lerEstado();
      if (geracao !== this.geracao) {
        return;
      }
      this.duracao = duracao || this.duracao;
      const comecou = tocando && !this.jaTocou;
      this.jaTocou = this.jaTocou || tocando;
      const passo = this.ultimaPosicao === null ? 0 : posicao - this.ultimaPosicao;
      // Conta em qualquer estado: o início (carregando) e o fim (terminado) também são tempo assistido. O vídeo só avança
      // sozinho tocando; pulo na barra passa do limite e fica de fora.
      if (passo > 0 && passo <= SALTO_MAXIMO_SEGUNDOS) {
        this.assistidoPendente += passo;
      }
      const mudou = this.ultimaPosicao !== null && this.ultimaPosicao !== posicao;
      this.ultimaPosicao = posicao;
      const vencido = Date.now() - this.ultimoEnvio >= ENVIO_A_CADA_SEGUNDOS * 1000;
      if (comecou) {
        // O servidor só credita tempo depois de um primeiro envio: ele marca o início no relógio.
        this.enviar(0);
      }
      const parouEmOutroPonto = this.jaTocou && !tocando && posicao !== this.ultimaEnviada;
      if ((vencido && mudou && this.jaTocou) || parouEmOutroPonto) {
        this.enviar();
      }
    } catch {
      // leitura perdida: a próxima medição recupera a posição
    }
  }

  // `credito` 0 marca o início sem gastar o tempo pendente, que o servidor não creditaria no primeiro envio.
  private enviar(credito = this.assistidoPendente): void {
    if (!this.duracao || this.ultimaPosicao === null) {
      return;
    }
    const dados = {
      key: this.chaveAtiva, position: this.ultimaPosicao, watched_delta: credito, duration: this.duracao
    };
    this.assistidoPendente -= credito;
    this.ultimoEnvio = Date.now();
    this.ultimaEnviada = this.ultimaPosicao;
    this.zona.run(() => this.avanco.emit(dados));
  }
}
