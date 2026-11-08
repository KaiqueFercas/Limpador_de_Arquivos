"""
Limpador automático de Downloads e arquivos temporários.

- Organiza os arquivos soltos da pasta Downloads em subpastas por tipo
  (PDFs, Imagens, Vídeos, Instaladores...).
- Só mexe em arquivos com mais de N dias (padrão: 1), para não atrapalhar
  downloads recentes ou em andamento.
- Opcional: apaga arquivos antigos da pasta TEMP do Windows.
- Nada é apagado dos Downloads: os arquivos só são movidos.

Uso:
    py limpador.py --simular          # mostra o que faria, sem mexer em nada
    py limpador.py                    # organiza uma vez
    py limpador.py --limpar-temp      # organiza e limpa a pasta TEMP
    py limpador.py --loop 30          # fica rodando e repete a cada 30 minutos
"""

import argparse
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# CONFIGURAÇÃO — ajuste à vontade
# ----------------------------------------------------------------------------

IDADE_MINIMA_DIAS = 1        # só organiza arquivos com mais de N dias
IDADE_TEMP_DIAS = 7          # só apaga arquivos do TEMP com mais de N dias

CATEGORIAS = {
    "PDFs":          {".pdf"},
    "Imagens":       {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
                      ".ico", ".heic", ".tif", ".tiff", ".avif"},
    "Videos":        {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"},
    "Audios":        {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"},
    "Documentos":    {".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".epub"},
    "Planilhas":     {".xls", ".xlsx", ".ods", ".csv"},
    "Apresentacoes": {".ppt", ".pptx", ".odp"},
    "Compactados":   {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Instaladores":  {".exe", ".msi", ".msix", ".appx", ".iso", ".apk"},
    "Codigo":        {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                      ".java", ".c", ".cpp", ".cs", ".sql", ".ipynb", ".sh", ".bat", ".ps1"},
    "Torrents":      {".torrent"},
    "Fontes":        {".ttf", ".otf", ".woff", ".woff2"},
}
PASTA_OUTROS = "Outros"

# Extensões de downloads incompletos — nunca mexer
IGNORAR = {".crdownload", ".part", ".partial", ".download", ".tmp", ".opdownload"}

# ----------------------------------------------------------------------------

PASTA_SCRIPT = Path(__file__).resolve().parent
ARQUIVO_LOG = PASTA_SCRIPT / "limpador.log"
log = logging.getLogger("limpador")


def pasta_downloads() -> Path:
    """Descobre a pasta Downloads real (mesmo se ela tiver sido movida)."""
    try:
        import winreg
        chave = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave) as k:
            valor, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
            return Path(os.path.expandvars(valor))
    except (ImportError, OSError):
        return Path.home() / "Downloads"


def categoria_de(arquivo: Path) -> str:
    ext = arquivo.suffix.lower()
    for nome, extensoes in CATEGORIAS.items():
        if ext in extensoes:
            return nome
    return PASTA_OUTROS


def destino_livre(destino: Path) -> Path:
    """Se já existir um arquivo com o mesmo nome, gera 'nome (1).ext', 'nome (2).ext'..."""
    if not destino.exists():
        return destino
    n = 1
    while True:
        candidato = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        if not candidato.exists():
            return candidato
        n += 1


def idade_em_dias(caminho: Path) -> float:
    return (time.time() - caminho.stat().st_mtime) / 86400


def organizar_downloads(simular: bool) -> None:
    downloads = pasta_downloads()
    if not downloads.is_dir():
        log.error("Pasta Downloads não encontrada: %s", downloads)
        return

    movidos = 0
    for item in downloads.iterdir():
        # Só arquivos soltos na raiz — subpastas ficam como estão
        if not item.is_file():
            continue
        if item.name.startswith(".") or item.name.lower() == "desktop.ini":
            continue
        if item.suffix.lower() in IGNORAR:
            continue
        try:
            if idade_em_dias(item) < IDADE_MINIMA_DIAS:
                continue
        except OSError:
            continue

        pasta_destino = downloads / categoria_de(item)
        destino = destino_livre(pasta_destino / item.name)

        if simular:
            log.info("[SIMULAÇÃO] %s  ->  %s", item.name, destino.relative_to(downloads))
            movidos += 1
            continue

        try:
            pasta_destino.mkdir(exist_ok=True)
            shutil.move(str(item), str(destino))
            log.info("Movido: %s  ->  %s", item.name, destino.relative_to(downloads))
            movidos += 1
        except (PermissionError, OSError) as e:
            # Arquivo aberto em outro programa, por exemplo
            log.warning("Não foi possível mover %s: %s", item.name, e)

    verbo = "seriam movidos" if simular else "movidos"
    log.info("Downloads: %d arquivo(s) %s.", movidos, verbo)


def limpar_temp(simular: bool) -> None:
    temp = Path(os.environ.get("TEMP", ""))
    if not temp.is_dir():
        log.error("Pasta TEMP não encontrada.")
        return

    apagados, bytes_liberados = 0, 0
    # Percorre de baixo para cima para conseguir remover pastas que ficarem vazias
    for raiz, pastas, arquivos in os.walk(temp, topdown=False):
        for nome in arquivos:
            caminho = Path(raiz) / nome
            try:
                if idade_em_dias(caminho) < IDADE_TEMP_DIAS:
                    continue
                tamanho = caminho.stat().st_size
                if not simular:
                    caminho.unlink()
                apagados += 1
                bytes_liberados += tamanho
            except OSError:
                pass  # em uso por algum programa — normal no TEMP, só pula
        if not simular:
            for nome in pastas:
                try:
                    (Path(raiz) / nome).rmdir()  # só remove se estiver vazia
                except OSError:
                    pass

    mb = bytes_liberados / (1024 * 1024)
    verbo = "seriam apagados" if simular else "apagados"
    log.info("TEMP: %d arquivo(s) %s (%.1f MB).", apagados, verbo, mb)


def configurar_log() -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%d/%m/%Y %H:%M:%S")
    arquivo = logging.FileHandler(ARQUIVO_LOG, encoding="utf-8")
    arquivo.setFormatter(fmt)
    log.addHandler(arquivo)
    if sys.stdout is not None:  # no modo segundo plano (pythonw) não há console
        tela = logging.StreamHandler(sys.stdout)
        tela.setFormatter(fmt)
        log.addHandler(tela)


def main() -> None:
    p = argparse.ArgumentParser(description="Organiza a pasta Downloads e limpa arquivos temporários.")
    p.add_argument("--simular", action="store_true", help="só mostra o que faria, sem mexer em nada")
    p.add_argument("--limpar-temp", action="store_true", help="também apaga arquivos antigos do TEMP")
    p.add_argument("--loop", type=int, metavar="MIN", help="repete a cada MIN minutos (modo segundo plano)")
    args = p.parse_args()

    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    configurar_log()

    while True:
        log.info("=== Limpeza iniciada (%s) ===", datetime.now().strftime("%d/%m %H:%M"))
        organizar_downloads(args.simular)
        if args.limpar_temp:
            limpar_temp(args.simular)
        if not args.loop:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
