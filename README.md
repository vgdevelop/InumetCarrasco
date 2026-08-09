# INUMET Carrasco

Recolector de telemetría meteorológica pública de INUMET para la estación
Carrasco (OMM `86580`, OACI `SUMU`). Descarga, normaliza y exporta los datos a
JSON, Excel y gráficas PNG.

## Funcionalidades

- Identifica Carrasco mediante códigos estables y tolera cambios menores de nombre.
- Normaliza observaciones y fechas del dataset público de INUMET.
- Genera un JSON filtrado, un libro Excel con varias hojas y gráficas PNG.
- Incluye resúmenes estadísticos y datos en formato ancho para análisis o Power BI.
- Funciona en Windows, macOS y Linux con Python 3.10 o posterior.

## Instalación

```powershell
git clone https://github.com/vgdevelop/InumetCarrasco.git
cd InumetCarrasco
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS o Linux, active el entorno con `source .venv/bin/activate`.

## Uso

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

## Fuente de datos

Los datos pertenecen al servicio público del [Instituto Uruguayo de
Meteorología (INUMET)](https://www.inumet.gub.uy/). Este proyecto no es un
producto oficial de INUMET y depende de la disponibilidad y estructura de su
fuente pública.
