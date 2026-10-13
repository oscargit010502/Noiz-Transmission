# Reproducción del entorno y los resultados

## Instalación y escritorio

Se requiere Python 3.13 o 3.14 y `uv`. `pyproject.toml` define extras y `uv.lock`
fija versiones y hashes. Desde PowerShell, en el checkout:

```powershell
uv sync --locked --all-extras
uv run noiz-transmission
```

El extra de escritorio usa PySide6 Essentials 6.10 y PyQtGraph. Actualizar estas
bibliotecas requiere volver a comprobar su compatibilidad; no se parchea una
instalación externa para hacerla pasar. Phonometry 3.3.0 se instala mediante el
extra de validación. Usar todos los extras evita omitir sus contrastes.

Los comandos de CLI funcionan también en Linux. `QT_QPA_PLATFORM=offscreen`
permite pruebas técnicas sin pantalla, pero no ofrece una sesión interactiva ni
sustituye probar la aplicación de forma nativa en Windows.

## Ejemplo v2 sin datos comerciales

```powershell
uv run noiz assembly examples/double_leaf.noiz.json --output-dir artifacts/v2
```

El ejemplo contiene placas sintéticas independientes y no requiere los XML
importados. Produce resultados estructurados y exportaciones legibles en el
directorio indicado. El modelo es `transfer-matrix-plate-1`, con flexión, pérdidas,
cámaras y promedio energético en bandas exactas de 50 a 5000 Hz.

El editor admite una a tres hojas, hasta seis capas por hoja y cámaras entre ellas.
Para usar Miki se introducen explícitamente espesor de absorbente y resistividad
al flujo en Pa·s/m². Si parte de las bandas está fuera del ajuste, el resultado
conserva la advertencia. Los campos de bastidor o perfil no habilitan una física
inexistente; las configuraciones no admitidas se rechazan al calcular.

## Importar una biblioteca XML local

En la interfaz se pueden seleccionar los XML desde la biblioteca. El flujo por
comandos es:

```powershell
uv run noiz catalog import "C:\mis-materiales\Materials_INSUL.xml" "C:\mis-materiales\Absorption_INSUL.xml"
```

Se pueden indicar varios archivos; repetir el mismo contenido no duplica sus
registros. Las ubicaciones y el orden de selección del archivo local están
explicados en [materials.md](materials.md). Para elegir explícitamente una
biblioteca portátil desde PowerShell:

```powershell
$env:NOIZ_CATALOG_PATH = Join-Path (Get-Location) "local_data\catalog.json"
uv run noiz catalog import "C:\mis-materiales\Materials_INSUL.xml"
uv run noiz-transmission
```

`local_data/` está excluido de Git. Los XML y datos comerciales importados no se
incluyen en la distribución pública. Un archivo privado de trabajo puede contener
la biblioteca del usuario; debe distinguirse del paquete público de fuentes.

## Compatibilidad con v1

El comando anterior sigue disponible sin cambiar las ecuaciones históricas:

```powershell
uv run noiz materials
uv run noiz predict examples/single_panel.noiz.json --output-dir artifacts/v1
```

Esta ruta usa `mass-law-1`, puntos centrales nominales y el proyecto JSON v1.
Al abrir ese proyecto en el escritorio v2 se migra a una composición con notas
sobre el cambio de modelo y los supuestos añadidos. El nuevo resultado puede
cambiar por flexión y promedio en banda. Para reproducir el cálculo antiguo usar
la ruta v1, no exigir igualdad al modelo v2.

## Pruebas y construcción

```powershell
uv run pytest
uv run ruff check .
uv run python -m build --installer uv
```

El banco incluye pruebas matemáticas, contraste Phonometry y verificaciones de
persistencia/importación/interfaz. El número y resultado concretos de pruebas
se consultan en los logs de esa ejecución. La construcción produce un paquete
Python; no equivale a un instalador Windows validado.

## Expediente reproducible

Conservar, como mínimo:

- Commit o versión, `uv.lock`, Python, sistema operativo y arquitectura.
- JSON de entrada, esquema, modelo, propiedades editadas y copias de registros
  de catálogo; procedencia y SHA-256 de los archivos importados utilizados.
- Condiciones del aire, incidencia, límite angular y composición en orden.
- Definición de bandas y espectro incidente; v2 supone potencia uniforme por Hz.
- Curvas, diagnósticos, Rw provisional y todas las advertencias.
- Versión de herramientas de contraste y tolerancias numéricas.

Los comandos siguientes ayudan a registrar versiones sin volcar credenciales:

```powershell
uv run python --version
uv pip freeze
git rev-parse HEAD
```

Los proyectos v2 usan `schema_version: 2`, `model_name` y un objeto `project`.
Conservan propiedades actuales y registros de origen por separado, de modo que
una edición no falsifica el dato original. El JSON v1 mantiene su propio esquema.
Los informes son resultados calculados, no mediciones experimentales.

La geometría ancho/alto se guarda, pero no influye en el modelo infinito. La masa
mostrada suma placas, sin estructura ni absorbente. Conservar estas definiciones
permite interpretar correctamente un informe o comparar dos ejecuciones.

## Entorno en la nube

Cada tarea en la nube ya trabaja en un entorno aislado. Usar el checkout existente
y no crear un worktree salvo petición explícita. La instalación repetible respeta
archivos de usuario y usa el lockfile. No requiere API keys, servidores remotos ni
base de datos: los proyectos y catálogos son locales.

La descarga de dependencias necesita los índices y artefactos correspondientes.
Mantener TLS, firmas y hashes verificados. Si una referencia no se puede abrir,
registrar la limitación sin declararla consultada. La guía INSUL v10 sí pudo
consultarse en la sesión v2, según [sources.md](sources.md).

## Distribución y licencias

Código y ejemplos propios conservan MIT. Las dependencias conservan sus licencias;
PyQtGraph es MIT y PySide6 Essentials publica opciones LGPL/GPL que deben revisarse
para la distribución concreta. El paquete debe identificar componentes y preservar
avisos/textos aplicables. Una distribución LGPL requiere revisar, entre otros
puntos, sustitución de bibliotecas y obligaciones de fuentes/modificaciones.

El instalador de Windows y su inventario necesitan revisión específica antes de
publicarse. La licencia MIT de la raíz no relicencia Qt ni catálogos de terceros.
Publicar un entorno de Codex tampoco publica automáticamente cambios en GitHub:
la publicación del código tiene su propio commit, rama y envío al repositorio.
