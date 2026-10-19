"""
Script simples para gerar um MP3 a partir de um arquivo de texto usando gTTS.
Instale: pip install gTTS
Uso: python tools/tts_generate.py ../DOCUMENTACAO_TECNICA_TCC_TTS_FULL.txt output.mp3
"""
import sys
from gtts import gTTS

def generate_mp3(input_path, output_path, lang='pt'):
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()
    # gTTS tem limites práticos de tamanho; dividir em blocos é recomendável
    # Aqui dividimos por 4500 caracteres para evitar erros de requisição
    max_chunk = 4500
    chunks = [text[i:i+max_chunk] for i in range(0, len(text), max_chunk)]

    if len(chunks) == 1:
        tts = gTTS(text=chunks[0], lang=lang)
        tts.save(output_path)
        print(f'Áudio salvo em {output_path}')
        return

    # Quando houver múltiplos chunks, gerar audios temporários e concatenar
    temp_files = []
    for idx, chunk in enumerate(chunks):
        temp_file = f'{output_path}.part{idx}.mp3'
        gTTS(text=chunk, lang=lang).save(temp_file)
        temp_files.append(temp_file)
        print(f'Gerado {temp_file}')

    # Concatenar arquivos mp3 simples: isto funciona na maioria dos players para mp3 simples
    # Para concatenação robusta, recomendamos usar ffmpeg. Aqui tentamos concatenar bytes.
    with open(output_path, 'wb') as outfile:
        for tf in temp_files:
            with open(tf, 'rb') as infile:
                outfile.write(infile.read())
    print(f'Áudio concatenado em {output_path}')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Uso: python tools/tts_generate.py <input.txt> <output.mp3>')
        sys.exit(1)
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    generate_mp3(input_path, output_path)
