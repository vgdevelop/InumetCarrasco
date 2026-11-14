# Tiempo GrowerLabs — INUMET

Plataforma para recopilar, conservar y visualizar telemetría meteorológica
pública de INUMET. Incluye una web interactiva para todas las estaciones y
mantiene el recolector de escritorio original de Carrasco.

## Plataforma web

La arquitectura usa tres servicios:

- `api`: FastAPI sirve la web y una API pública de solo lectura.
- `collector`: consulta periódicamente INUMET y guarda observaciones nuevas.
- `db`: PostgreSQL dedicado, interno y persistente.

La clave primaria `(station_key, variable_id, observed_at)` impide duplicar una
observación aunque INUMET la entregue en múltiples consultas. La base de datos
no publica puertos al host.

Las dependencias Linux necesarias para construir sin acceso a PyPI están
versionadas en `vendor/wheels`. Deben regenerarse deliberadamente cuando cambie
`requirements-web.txt`.

### Inicio con Docker

```powershell
Copy-Item .env.example .env
# Reemplace POSTGRES_PASSWORD por un secreto aleatorio antes de continuar.
docker compose config
docker compose up -d --build
```

La web queda en `http://127.0.0.1:8002`. Para un despliegue interno, configure
`BIND_ADDRESS` con la interfaz autorizada y publique únicamente la API mediante
un proxy TLS.

Variables principales:

| Variable | Predeterminado | Propósito |
|---|---:|---|
| `POSTGRES_PASSWORD` | obligatorio | Credencial interna de PostgreSQL |
| `BIND_ADDRESS` | `127.0.0.1` | Dirección de escucha del API |
| `PUBLIC_PORT` | `8002` | Puerto HTTP interno |
| `COLLECT_INTERVAL_SECONDS` | `300` | Intervalo de captura, mínimo 60 s |

Endpoints:

- `/health`: salud de API y base.
- `/api/status`: estado de recolección y cantidad de registros.
- `/api/stations`: estaciones con observaciones disponibles.
- `/api/stations/{id}/variables`: variables disponibles por estación.
- `/api/latest?station={id}`: último valor de cada variable.
- `/api/series?station={id}&variables=47,25&hours=24`: series históricas.

## Recolector de escritorio Carrasco

El comando histórico sigue disponible para Carrasco (OMM `86580`, OACI
`SUMU`). Descarga, normaliza y exporta los datos a JSON, Excel y gráficas PNG.

### Funcionalidades del CLI

- Identifica Carrasco mediante códigos estables y tolera cambios menores de nombre.
- Normaliza observaciones y fechas del dataset público de INUMET.
- Genera un JSON filtrado, un libro Excel con varias hojas y gráficas PNG.
- Incluye resúmenes estadísticos y datos en formato ancho para análisis o Power BI.
- Funciona en Windows, macOS y Linux con Python 3.10 o posterior.

### Instalación del CLI

```powershell
git clone https://github.com/vgdevelop/InumetCarrasco.git
cd InumetCarrasco
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS o Linux, active el entorno con `source .venv/bin/activate`.

### Uso del CLI

```powershell
python script.py
```

Opciones disponibles:

```text
--output RUTA     Directorio base de salida (predeterminado: output)
--timeout SEG     Tiempo máximo para la solicitud HTTP (predeterminado: 30)
--no-show         No abre automáticamente el archivo Excel al finalizar
```

En Windows también puede utilizarse el lanzador incluido:

```powershell
.\Inumet.ps1 -Output output -Timeout 30 -NoShow
```

Cada ejecución crea un directorio independiente:

```text
output/YYYY-MM-DD_HH-MM-SS/
├── carrasco_YYYY-MM-DD_HH-MM-SS.json
├── carrasco_YYYY-MM-DD_HH-MM-SS.xlsx
└── graficas/
    └── *.png
```

## Desarrollo

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
```

## Fuente y limitaciones

Los datos pertenecen al servicio público del [Instituto Uruguayo de
Meteorología (INUMET)](https://www.inumet.gub.uy/). Este proyecto no es un
producto oficial de INUMET y depende de la disponibilidad y estructura de su
fuente pública.

Los datos pueden contener faltantes, demoras o revisiones de origen. La
plataforma conserva la primera observación recibida para una combinación de
estación, variable y timestamp, y registra cada ejecución del recolector.
