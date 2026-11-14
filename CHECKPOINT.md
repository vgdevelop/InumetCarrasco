# CP-2026-11-14-server-sync

Solicitud: publicar el código recuperado del servidor en una rama nueva, sin secretos. Cambio SDD-0008.

Repositorio: InumetCarrasco. Base: c578be04aabdd554aa26c7bd1b7f8162442ae53d. Rama: checkpoint/2026-11-14-server-sync.

Se revisaron archivos, diferencias, ramas remotas y PRs relacionados; no se encontraron PRs y la rama base no había avanzado. Se seleccionan fuentes, pruebas, configuración con referencias a secretos y paquetes de dependencias. Los dumps, CSV, credenciales y capturas privadas quedan fuera del repositorio.

Validación: 17 pruebas, Ruff correcto, Gitleaks 8.30.1 verificado mediante checksum oficial; sin hallazgos en directorio e historial. Paquetes wheel descomprimidos y escaneados por separado. No se detectaron direcciones privadas en fuentes. Los escaneos reducen riesgo, no constituyen garantía absoluta ni auditoría de vulnerabilidades de las dependencias.

El workflow existente corre con push; su resultado remoto se registra después de publicar. No se cambia main, no se crea PR ni se despliega. El SHA final se registra en la ficha local posterior. Para revertir una instalación futura, usar el commit base y su configuración compatible; esta publicación no toca servidores.
