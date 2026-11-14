# Registro de cambios

## CP-2026-11-14-server-sync

- Incorpora la plataforma web y el recolector de todas las estaciones desde la captura del servidor del 13 de noviembre: API, PostgreSQL, exportación Excel, interfaz y configuración Docker.
- Conserva el recolector original de escritorio y añade dependencias Linux para construcción sin descarga de paquetes.
- Excluye credenciales, respaldos e históricos; el entorno de ejemplo contiene únicamente marcadores.
- Validación: 17 pruebas aprobadas, Ruff sin errores y Gitleaks 8.30.1 sin hallazgos en fuentes, historial y contenido extraído de los paquetes. Código de aplicación contrastado con el contenedor activo durante la captura.
- Publicación de código únicamente; no implica despliegue ni restauración de datos. Reversión: volver al commit base indicado en CHECKPOINT.md.
