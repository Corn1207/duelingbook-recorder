#!/bin/bash
# Cambia al directorio del proyecto
cd "$(dirname "$0")"

# Activa el entorno virtual y ejecuta la app
.venv/bin/python run_app.py
