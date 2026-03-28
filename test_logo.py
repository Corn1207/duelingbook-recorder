"""
test_logo.py

Toma los primeros 30 segundos de un video grabado y aplica el overlay del logo
para verificar posición y tamaño sin procesar el video completo.

Uso:
    python test_logo.py
    python test_logo.py "output/raw/mi_video.mkv"
"""

import subprocess
import sys
from pathlib import Path

from postprocess.outro import LOGO_H, LOGO_IMAGE, LOGO_W, LOGO_X, LOGO_Y

# Video de entrada: el más reciente en output/raw/, o el que se pase como argumento
if len(sys.argv) > 1:
    input_video = Path(sys.argv[1])
else:
    raw_dir = Path("output/raw")
    videos = sorted(raw_dir.glob("*.mkv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        print("No se encontraron videos en output/raw/")
        sys.exit(1)
    input_video = videos[0]

output_path = Path("output/test_logo_preview.mp4")
output_path.parent.mkdir(parents=True, exist_ok=True)

logo = Path(LOGO_IMAGE)
if not logo.exists():
    print(f"Logo no encontrado: {logo}")
    sys.exit(1)

print(f"Video de entrada : {input_video}")
print(f"Logo             : {logo}")
print(f"Posición         : x={LOGO_X}, y={LOGO_Y}")
print(f"Tamaño           : {LOGO_W}x{LOGO_H}px")
print(f"Salida           : {output_path}")
print()

filter_complex = (
    f"[1:v]scale={LOGO_W}:{LOGO_H}[logo];"
    f"[0:v][logo]overlay={LOGO_X}:{LOGO_Y}[vout]"
)

cmd = [
    "ffmpeg", "-y",
    "-ss", "0", "-t", "50",          # primeros 50 segundos
    "-i", str(input_video),
    "-i", str(logo),
    "-filter_complex", filter_complex,
    "-map", "[vout]",
    "-map", "0:a",
    "-c:v", "libx264", "-preset", "fast",
    "-c:a", "copy",
    str(output_path),
]

print("Procesando...")
result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode != 0:
    print("ERROR en ffmpeg:")
    print(result.stderr[-2000:])
    sys.exit(1)

print(f"\nListo: {output_path.resolve()}")
print("Abre el video y ajusta LOGO_X, LOGO_Y, LOGO_W, LOGO_H en postprocess/outro.py")
