"""
Script de arranque para Windows.

La política WindowsProactorEventLoopPolicy debe establecerse ANTES de que
Uvicorn cree su event loop. Colocarla en main.py es demasiado tarde porque
Uvicorn instancia el loop en el proceso raíz antes de importar la aplicación.

Uso:
    uv run python run.py
    uv run python run.py --reload    # para desarrollo con hot-reload
"""

import sys
import asyncio

# ── CRÍTICO EN WINDOWS ────────────────────────────────────────────────────────
# SelectorEventLoop (defecto en Windows) no soporta subprocesos asíncronos.
# Playwright necesita lanzar Chromium como subproceso → NotImplementedError.
# ProactorEventLoop sí lo soporta y debe fijarse ANTES de que Uvicorn inicie.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    reload = "--reload" in sys.argv
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
        log_level="info",
    )
