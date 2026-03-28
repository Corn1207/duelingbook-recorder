# PLAN.md — Duelingbook Replay Recorder

## Project Overview

A Python automation tool for macOS that:
1. Opens a duelingbook.com replay URL in a browser
2. Records the playback using OBS Studio via WebSocket
3. Mixes background music into the recorded video using ffmpeg
4. Optionally uploads the result to YouTube

---

## Project Structure

```
duelingbook-recorder/
├── README.md
├── PLAN.md
├── requirements.txt
├── config.yaml                  # User configuration (OBS host, music folder, etc.)
├── .env                         # Secrets (OBS password, YouTube OAuth, etc.)
├── main.py                      # CLI entry point
│
├── recorder/
│   ├── __init__.py
│   ├── browser.py               # Playwright browser automation
│   ├── obs_controller.py        # OBS WebSocket client (obsws-python)
│   ├── replay_monitor.py        # Detects replay end via DOM polling
│   └── pipeline.py              # Orchestrates the full recording flow
│
├── postprocess/
│   ├── __init__.py
│   ├── music_mixer.py           # ffmpeg: mix background music into video
│   └── youtube_uploader.py      # YouTube Data API v3 upload
│
├── utils/
│   ├── __init__.py
│   ├── config_loader.py         # Loads config.yaml and .env
│   ├── file_manager.py          # Output path management, naming
│   └── logger.py                # Structured logging setup
│
├── music/                       # Local folder of background music files
│   └── (user places .mp3/.wav files here)
│
├── output/                      # Recorded and processed videos land here
│   ├── raw/                     # OBS raw recordings
│   └── final/                   # After music mixing
│
└── tests/
    ├── test_browser.py
    ├── test_obs_controller.py
    ├── test_music_mixer.py
    └── test_replay_monitor.py
```

---

## Python Dependencies

```
# requirements.txt

# Browser automation
playwright>=1.44.0

# OBS WebSocket v5 control
obsws-python>=1.7.0

# Video/audio post-processing
ffmpeg-python>=0.2.0          # Pythonic ffmpeg wrapper (subprocess under the hood)

# YouTube upload
google-api-python-client>=2.130.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0

# Configuration & environment
pyyaml>=6.0.1
python-dotenv>=1.0.0

# Utilities
click>=8.1.7                  # CLI interface
rich>=13.7.0                  # Pretty terminal output and progress bars
tenacity>=8.3.0               # Retry logic for OBS connection and uploads
```

**System-level requirements (installed outside Python):**
- OBS Studio >= 30.x (macOS, with built-in obs-websocket v5)
- ffmpeg via Homebrew: `brew install ffmpeg`
- Python >= 3.11

---

## Configuration File (config.yaml)

```yaml
obs:
  host: "localhost"
  port: 4455
  password: ""             # Or loaded from .env
  scene_name: "Replay"    # OBS scene that has the browser window as source

browser:
  headless: false          # Must be false — OBS captures the visible window
  window_width: 1920
  window_height: 1080
  playback_speed: 1        # 1 = normal; future: support for 2x fast-forward

music:
  folder: "./music"
  volume: 0.15             # Background music volume (0.0–1.0)
  loop: true               # Loop music if replay is longer than one track

output:
  raw_dir: "./output/raw"
  final_dir: "./output/final"
  filename_template: "replay_{replay_id}_{timestamp}"

youtube:
  enabled: false
  privacy: "private"       # public | private | unlisted
  title_template: "Yu-Gi-Oh! Replay — {replay_id}"
  description: ""
  category_id: "20"        # Gaming category
  tags: ["yugioh", "duelingbook", "replay"]
```

---

## Full Architecture — Module-by-Module

### 1. `main.py` — CLI Entry Point

Built with `click`. Acepta una URL de replay o un ID y ejecuta el pipeline completo.

```
Usage:
  python main.py record --url "https://www.duelingbook.com/replay?id=12345678"
  python main.py record --id 12345678
  python main.py record --id 12345678 --upload
  python main.py postprocess --video ./output/raw/replay_12345678.mkv
```

Responsabilidades:
- Parsear argumentos
- Cargar config via `utils/config_loader.py`
- Instanciar y llamar `recorder/pipeline.py`

---

### 2. `recorder/pipeline.py` — Orchestrator

Coordinador central que secuencia cada paso:

```
1. Validar URL del replay
2. Conectar a OBS via obs_controller
3. Abrir browser y navegar a la URL via browser.py
4. Posicionar/redimensionar ventana para encajar en la captura de OBS
5. Esperar a que el replay cargue completamente (DOM ready state)
6. Iniciar grabación OBS
7. Hacer clic en el botón play en el browser
8. Hacer polling para detectar el fin del replay via replay_monitor.py
9. Detener grabación OBS — capturar la ruta del archivo de salida
10. Cerrar browser
11. Llamar a music_mixer.postprocess(raw_video, output_path)
12. Opcionalmente llamar a youtube_uploader.upload(final_video)
```

---

### 3. `recorder/browser.py` — Playwright Browser Automation

Usa `playwright.sync_api` (API síncrona, más simple para este flujo secuencial).

Responsabilidades clave:
- Lanzar Chromium en modo headed (ventana visible requerida para captura OBS)
- Navegar a la URL del replay
- Esperar a que la página alcance estado listo verificando la variable JS `ready === true` via `page.evaluate()`
- Hacer clic en `#play_btn` para iniciar la reproducción
- Exponer el objeto `page` a `replay_monitor.py` para polling

Gestión de ventana en macOS:
- Después de lanzar, usar AppleScript para traer el browser al frente
- Establecer posición y tamaño fijos de ventana coincidiendo con la configuración de OBS

**Nota sobre fuente de captura OBS:**
Se usará **Window Capture** de la ventana Chromium controlada por Playwright. El browser corre en modo headed (visible) y OBS captura esa ventana específica.

---

### 4. `recorder/replay_monitor.py` — Detección de Fin de Replay

Este es el problema técnico más crítico del proyecto.

**Cómo terminan los replays de duelingbook:**

- `replay_arr` es un array JS de acciones pendientes. Cuando `replay_arr.length === 0`, el replay terminó.
- Todos los botones de reproducción (`#play_btn`, `#pause_replay_btn`, `#fast_btn`) quedan `disabled` al final.
- Se renderiza un mensaje de "Duel Over" en el DOM.

**Estrategia de detección — polling multi-señal:**

```python
def wait_for_replay_end(page, poll_interval=2.0, timeout=7200):
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Señal 1: replay_arr vacío
        arr_empty = page.evaluate(
            "() => typeof replay_arr !== 'undefined' && replay_arr.length === 0"
        )
        # Señal 2: botón play deshabilitado
        btn_disabled = page.evaluate(
            "() => { const b = document.querySelector('#play_btn'); return b ? b.disabled : false; }"
        )
        # Señal 3: texto "Duel Over" visible
        duel_over = page.evaluate(
            "() => document.body.innerText.includes('Duel Over')"
        )
        # Requiere al menos 2 de 3 señales para evitar falsos positivos
        if sum([arr_empty, btn_disabled, duel_over]) >= 2:
            return True
        time.sleep(poll_interval)
    raise TimeoutError("El replay no terminó dentro del tiempo límite.")
```

**Casos borde a manejar:**
- La página puede no haber cargado JS cuando empieza el polling — verificar `ready` primero
- `replay_arr` puede no existir hasta que comience la reproducción — usar guards con `typeof`
- Modo fast-forward cambia el timing — el monitor sigue funcionando porque verifica estado final
- Errores de red a mitad del replay — detectar estado estancado si la longitud no disminuye

---

### 5. `recorder/obs_controller.py` — Control OBS WebSocket

Usa `obsws-python` (SDK para obs-websocket protocolo v5, integrado en OBS 28+).

```python
import obsws_python as obs

class OBSController:
    def __init__(self, host, port, password):
        self.client = obs.ReqClient(host=host, port=port, password=password)

    def start_recording(self):
        self.client.start_record()

    def stop_recording(self) -> str:
        resp = self.client.stop_record()
        return resp.output_path   # OBS retorna la ruta absoluta del archivo guardado

    def get_status(self) -> dict:
        resp = self.client.get_record_status()
        return {
            "active": resp.output_active,
            "paused": resp.output_paused,
            "bytes": resp.output_bytes,
        }

    def switch_scene(self, scene_name: str):
        self.client.set_current_program_scene(scene_name)

    def disconnect(self):
        self.client.disconnect()
```

**Configuración requerida en OBS (documentada en README):**
- OBS debe estar corriendo antes de que el script inicie
- Habilitar WebSocket: Tools → WebSocket Server Settings → Enable, puerto 4455
- Crear escena "Replay" con fuente "Window Capture" apuntando al browser Chromium
- Formato de salida: MKV (seguro ante crashes; puede remuxearse a MP4 después)

**Retry logic con `tenacity`:**
```python
@retry(stop=stop_after_attempt(5), wait=wait_fixed(2))
def connect_with_retry(host, port, password):
    return obs.ReqClient(host=host, port=port, password=password)
```

---

### 6. `postprocess/music_mixer.py` — Música de Fondo con ffmpeg

**Comando ffmpeg central (mezcla audio original + música de fondo):**

```bash
ffmpeg \
  -i input_video.mkv \
  -stream_loop -1 -i background_music.mp3 \
  -filter_complex \
    "[0:a]volume=1.0[orig];
     [1:a]volume=0.15[music];
     [orig][music]amix=inputs=2:duration=first:dropout_transition=3[aout]" \
  -map 0:v \
  -map "[aout]" \
  -c:v copy \
  -c:a aac \
  -shortest \
  output_video.mp4
```

Flags clave:
- `-stream_loop -1` — repite la música indefinidamente para cubrir replays largos
- `duration=first` — la duración del audio de salida coincide con el video
- `-c:v copy` — sin re-encodeo del video; rápido y sin pérdida de calidad
- `dropout_transition=3` — fade-out de 3 segundos al terminar

**Selección de música:**
```python
def pick_music(music_folder: str) -> str:
    """Selecciona aleatoriamente un archivo de música de la carpeta."""
    supported = [".mp3", ".wav", ".flac", ".m4a", ".ogg"]
    files = [f for f in Path(music_folder).iterdir() if f.suffix.lower() in supported]
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos de música en {music_folder}")
    return str(random.choice(files))
```

---

### 7. `postprocess/youtube_uploader.py` — Subida Opcional a YouTube

Usa `google-api-python-client` con OAuth 2.0.

**Flujo de autenticación:**
- Primera ejecución: abre browser para consentimiento OAuth, guarda token en `~/.dbreplay_youtube_token.json`
- Ejecuciones siguientes: carga token guardado, auto-refresca si expiró

**Subida con protocolo resumable** (requerido para archivos > 5MB):

```python
from googleapiclient.http import MediaFileUpload

def upload_video(service, file_path, title, description, tags, privacy, category_id):
    body = {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": category_id},
        "status": {"privacyStatus": privacy},
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Progreso de subida: {int(status.progress() * 100)}%")
    return response["id"]
```

**Advertencia de cuota:** YouTube Data API v3 tiene cuota predeterminada de 10,000 unidades/día. Cada subida cuesta 1,600 unidades (~6 subidas/día por proyecto).

---

## Fases de Desarrollo

### Fase 1 — Fundación (Días 1–2)
**Objetivo:** Esqueleto del proyecto, configuración y conectividad con OBS.

1. Crear estructura de directorios del proyecto
2. Crear `requirements.txt` e instalar dependencias
3. Crear `config.yaml` con defaults y `.env.example`
4. Implementar `utils/config_loader.py` y `utils/logger.py`
5. Implementar `recorder/obs_controller.py`
6. Escribir `tests/test_obs_controller.py` — verificar connect, start, stop, status
7. Test manual: asegurar que OBS inicia/detiene grabación via Python

**Entregable:** `python main.py` conecta a OBS y alterna grabación.

---

### Fase 2 — Automatización del Browser (Días 3–4)
**Objetivo:** Abrir una URL de replay, esperar carga, hacer clic en play.

1. Implementar `recorder/browser.py` usando Playwright sync API
2. Manejar posicionamiento de ventana del browser en macOS
3. Esperar a que `ready === true` antes de intentar reproducir
4. Hacer clic en `#play_btn`
5. Escribir `tests/test_browser.py`

**Entregable:** Script abre replay de duelingbook e inicia reproducción automáticamente.

---

### Fase 3 — Detección de Fin de Replay (Días 5–6)
**Objetivo:** Detectar confiablemente cuándo termina el replay.

1. Implementar `recorder/replay_monitor.py` con polling multi-señal
2. Testear con replays de diferente duración
3. Manejar casos borde: demoras de carga, disponibilidad de variables JS, stalls de red
4. Agregar timeout configurable y logging por ciclo de poll

**Entregable:** Script imprime "Replay terminado" en el momento correcto consistentemente.

---

### Fase 4 — Pipeline de Grabación Completo (Días 7–8)
**Objetivo:** Grabación end-to-end con OBS.

1. Implementar `recorder/pipeline.py` uniendo browser + OBS + monitor
2. Configurar escena OBS con fuente Window Capture (setup documentado)
3. Testear la secuencia completa: lanzar → grabar → detectar fin → detener
4. Manejar cleanup en errores (detener grabación, cerrar browser)

**Entregable:** Un archivo `.mkv` crudo del replay se produce automáticamente.

---

### Fase 5 — Mezcla de Música (Días 9–10)
**Objetivo:** Agregar música de fondo a la grabación cruda.

1. Implementar `postprocess/music_mixer.py`
2. Agregar archivos de música a la carpeta `./music/`
3. Testear comando ffmpeg con diferentes formatos de música y duraciones de replay
4. Validar que el archivo de salida reproduce correctamente con audio mezclado

**Entregable:** Un `.mp4` final con música de fondo se produce a partir de la grabación cruda.

---

### Fase 6 — CLI y Manejo de Errores (Días 11–12)
**Objetivo:** Herramienta lista para producción.

1. Implementar `main.py` completo con `click`
2. Agregar display de progreso con `rich` y reporte de estado
3. Agregar manejo integral de errores: OBS no corriendo, fallo de carga de página, errores ffmpeg
4. Escribir test de integración end-to-end
5. Escribir `README.md` con instrucciones de setup

**Entregable:** Herramienta CLI completamente funcional y amigable para el usuario.

---

### Fase 7 — Subida a YouTube (Opcional, Días 13–14)
**Objetivo:** Flujo de grabación-y-subida en un comando.

1. Configurar proyecto en Google Cloud, habilitar YouTube Data API v3
2. Configurar credenciales OAuth 2.0 (`client_secrets.json`)
3. Implementar `postprocess/youtube_uploader.py`
4. Agregar flag `--upload` al CLI
5. Testear subida con un video no listado

**Entregable:** `python main.py record --id 12345678 --upload` produce y sube un video.

---

## Desafíos Técnicos y Soluciones

### Desafío 1 — OBS Window Capture en macOS
**Problema:** macOS requiere permiso explícito de Screen Recording para OBS. Si la ventana del browser está detrás de otra ventana, la captura puede ser negra.

**Solución:** Lanzar Chromium en pantalla completa y configurar OBS antes de correr el script. Alternativamente, usar "Display Capture" en lugar de "Window Capture" para capturar la pantalla completa.

**Requisito de permiso macOS:** Dar acceso de Screen Recording a OBS en System Settings → Privacy & Security → Screen Recording.

---

### Desafío 2 — Confiabilidad de la Detección de Fin de Replay
**Problema:** `replay_arr` puede no existir inmediatamente al cargar, o puede estar brevemente vacío antes de que se carguen los datos del replay.

**Solución:** El loop de polling primero verifica que `ready === true` antes de depender de `replay_arr.length === 0`. El enfoque multi-señal (requiriendo 2 de 3) previene falsos positivos. Un delay inicial de 5 segundos tras hacer clic en play protege adicionalmente.

---

### Desafío 3 — Ruta de Salida de Grabación OBS
**Problema:** OBS escribe grabaciones a un directorio que elige (configurado en OBS). El script Python necesita conocer la ruta exacta.

**Solución:** `stop_record()` en obs-websocket v5 retorna `output_path` en su respuesta — la ruta absoluta del archivo guardado. Sin necesidad de adivinanza.

---

### Desafío 4 — Posicionamiento de Ventana del Browser para Captura OBS
**Problema:** Para Window Capture, OBS necesita identificar la ventana exacta a capturar por nombre o proceso.

**Solución:** Usar perfil de Chromium dedicado con título de ventana fijo. O configurar OBS con "Display Capture" de la pantalla principal y recortar a la región del browser usando configuración de Transform en OBS.

---

### Desafío 5 — Audio del Juego vs. Música de Fondo
**Problema:** Los replays incluyen efectos de sonido. Agregar música debe preservar el audio del juego.

**Solución:** El filtro `amix` de ffmpeg mezcla ambos streams. El audio del juego se preserva a volumen completo (`volume=1.0`). La música se agrega a volumen menor (`volume=0.15`). Si el usuario quiere suprimir el audio del juego, `volume=0.0` lo logra — hacerlo opción de config.

---

### Desafío 6 — Sincronización: OBS Iniciado Antes de que el Replay Empiece
**Problema:** OBS tarda un momento en inicializar la grabación después de llamar `start_record()`. Si el browser hace clic en play inmediatamente, los primeros segundos del replay pueden perderse.

**Solución:** Después de llamar `start_recording()`, hacer polling en `get_record_status()` hasta que `output_active === true` antes de hacer clic en play en el browser.

---

### Desafío 7 — El Tiempo de Carga del Replay Varía
**Problema:** Algunos replays pueden ser grandes y tardar tiempo para que el motor JS cargue todos los datos antes de que `replay_arr` se pueble.

**Solución:** Antes de hacer clic en play, esperar a que `#play_btn` esté habilitado (no disabled) usando `page.wait_for_selector("#play_btn:not([disabled])")`.

---

### Desafío 8 — ffmpeg No en PATH
**Problema:** En macOS, ffmpeg instalado via Homebrew está en `/opt/homebrew/bin/ffmpeg` (Apple Silicon) o `/usr/local/bin/ffmpeg` (Intel). Python subprocess puede no encontrarlo.

**Solución:** Usar `shutil.which("ffmpeg")` para localizar ffmpeg al inicio y lanzar un error claro si no se encuentra. Documentar prominentemente el requisito `brew install ffmpeg`.

---

## Configuración Requerida de OBS Studio

Pasos manuales requeridos antes de correr el script:

1. Instalar OBS Studio desde obsproject.com
2. Dar permiso de Screen Recording: System Settings → Privacy & Security → Screen Recording → Habilitar para OBS
3. Abrir OBS → Tools → WebSocket Server Settings → Enable WebSocket server, puerto 4455
4. Establecer contraseña y agregarla a `.env` como `OBS_WEBSOCKET_PASSWORD=tucontraseña`
5. Crear nueva escena llamada "Replay"
6. Agregar fuente "Window Capture" — seleccionar ventana del browser Chromium (o usar Display Capture)
7. Configurar output de OBS: Settings → Output → Recording → path a `./output/raw`, formato MKV
8. Configurar OBS Video → Base Resolution 1920x1080, Output Resolution 1920x1080
9. Correr el script con OBS abierto

---

## Variables de Entorno (.env)

```
OBS_WEBSOCKET_PASSWORD=tu_contraseña_obs_aqui
YOUTUBE_CLIENT_SECRETS_PATH=./client_secrets.json
```

---

## Mejoras Futuras (Post-MVP)

- Procesamiento por lotes: aceptar lista de IDs de replay desde archivo de texto o CSV
- Marcadores de capítulo automáticos usando detección de número de turno desde el DOM
- Generación de miniatura desde screenshot de un estado específico del juego via Playwright
- Notificación por webhook de Discord cuando una grabación termina
- Soporte para modo fast-forward 2x para reducir tiempo de grabación en replays largos
- Base de datos (SQLite) para rastrear replays grabados y evitar duplicados
