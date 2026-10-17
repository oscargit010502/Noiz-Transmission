# Reproducción del entorno y los resultados

## Instalación y escritorio V5 (0.5.0)

Se requiere Python 3.13 o 3.14 y `uv`. `pyproject.toml` define extras y `uv.lock`
fija versiones y hashes. Desde PowerShell, en el checkout:

```powershell
uv sync --locked --all-extras
uv run --locked --extra desktop noiz-transmission
```

La configuración V5 usa `link-mode = "copy"` para instalar dependencias mediante
copia. `INICIAR_NOIZ.cmd` también define `UV_LINK_MODE=copy`; evita los enlaces
permanentes que OneDrive puede rechazar con el error 396. Si se ejecutan comandos
desde un checkout anterior o una configuración externa fuerza otro modo, puede
usarse `$env:UV_LINK_MODE = "copy"` en esa sesión de PowerShell. No hace falta
borrar proyectos o materiales para cambiar el modo de instalación.

El extra de escritorio usa PySide6 Essentials 6.10 y PyQtGraph. Actualizar estas
bibliotecas requiere volver a comprobar su compatibilidad; no se parchea una
instalación externa para hacerla pasar. Phonometry 3.3.0 se instala mediante el
extra de validación. Usar todos los extras evita omitir sus contrastes.

Los comandos de CLI funcionan también en Linux. `QT_QPA_PLATFORM=offscreen`
permite pruebas técnicas sin pantalla, pero no ofrece una sesión interactiva ni
sustituye probar la aplicación de forma nativa en Windows.

## Ejemplo reproducible sin datos comerciales

```powershell
uv run noiz assembly examples/v3_single.noiz.json --output-dir artifacts/v3/single
uv run noiz assembly examples/v3_quad.noiz.json --output-dir artifacts/v3/quad
uv run noiz assembly examples/v3_glazing.noiz.json --output-dir artifacts/v3/glazing
uv run noiz assembly examples/v3_porous.noiz.json --output-dir artifacts/v3/porous
```

Los ejemplos contienen propiedades sintéticas o supuestas y no requieren XML
comerciales. Quad emplea incidencia normal y relleno con resistividad supuesta
10000 Pa·s/m²; Glazing usa incidencia normal y cámara de argón de 16 mm.
Sus curvas normales no reciben Rw. Cada comando produce resultados estructurados
y exportaciones legibles en su directorio. El modelo es `transfer-matrix-plate-1`,
con flexión, pérdidas, cámaras y promedio energético en bandas exactas de
50 a 5000 Hz.

El editor admite hasta cuatro hojas (tres para Floor, dos para Roof), seis capas
por hoja, cantidades de 1 a 10 y cámaras entre hojas consecutivas. Los ejemplos
`v3_*.noiz.json` usan esquema 3. El histórico
`examples/double_leaf.noiz.json` conserva esquema V2 y se migra al cargar; puede
guardarse desde V3 para obtener el esquema nuevo. El nombre
`transfer-matrix-plate-1` se mantiene entre V2/V3: registrar la versión/commit
es necesario para fijar la implementación.
Para usar Miki se introducen explícitamente espesor de absorbente y resistividad
al flujo en Pa·s/m². Si parte de las bandas está fuera del ajuste, el resultado
conserva la advertencia. Los campos de bastidor o perfil no habilitan una física
inexistente; las configuraciones no admitidas se rechazan al calcular.

`examples/v3_workspace.noiz.json` permite abrir variantes ya configuradas en el
escritorio; el CLI calcula únicamente su composición activa. También se incluye
`examples/v3_double.noiz.json` para dos hojas independientes.

Para probar las ampliaciones desde la interfaz:

1. En Wall, seleccionar Quad y configurar cuatro hojas y tres cámaras
   independientes; una capa desactivada no participa en cálculo ni representación.
2. En Single, activar Facing y especificar espesor, cantidad y resistividad.
   Porous utiliza sus propios espesor y resistividad, sin la placa sólida.
3. En Glazing Double, seleccionar hojas independientes sin montantes y un gas en
   Frame 1. Argón, kriptón y xenón usan gas puro ideal a 20 °C y 101325 Pa.
   No combinar gas noble con absorbente Miki.
4. En Leak, para obtener un cálculo disponible elegir expresamente área abierta
   ideal (`open_area`); Gomperts y Mechel se conservan como configuración pero
   rechazan la predicción.
5. Guardar tras cambiar entre configuraciones y reabrir: V3 conserva las variantes
   por elemento/número de hojas, incluida la activa. El cálculo CLI del archivo
   utiliza solo la variante activa, pero valida todo el documento.

Floor y Roof inician las excitaciones de impacto y lluvia, cuyos modelos todavía
no están implementados. Sus parámetros pueden revisarse y guardarse. Solo al
seleccionar explícitamente transmisión aérea —sin Floor Cover— se utiliza el
modelo aéreo del elemento. Floor Covering muestra ΔL declarado del catálogo,
separado del resultado de la construcción; Predicted no genera curva.

## Importar una biblioteca XML local

En la interfaz se pueden seleccionar los XML desde la biblioteca. El flujo por
comandos es:

```powershell
uv run noiz catalog import "C:\mis-materiales\Material_INSUL10.xml" "C:\mis-materiales\Absorption_INSUL10.xml"
```

Se pueden indicar varios archivos; repetir el mismo contenido no duplica sus
registros. Las ubicaciones y el orden de selección del archivo local están
explicados en [materials.md](materials.md). Para elegir explícitamente una
biblioteca portátil desde PowerShell:

```powershell
$env:NOIZ_CATALOG_PATH = Join-Path (Get-Location) "local_data\catalog-v5.json"
uv run --locked noiz catalog import "C:\mis-materiales\Insul Materials.xml" "C:\mis-materiales\Insul Connections.xml"
uv run --locked --extra desktop noiz-transmission
```

V5 admite ocho familias, incluidas Connections. El catálogo personal preparado
con los ocho XML de esta entrega contiene 3.629 registros. Sin la variable
anterior, la búsqueda portátil prioriza `catalog-v5.json`, después
`catalog-v3.json` y finalmente `catalog.json`. Cambiar de catálogo no reescribe
las copias de registros contenidas en los proyectos guardados.

`local_data/` está excluido de Git. Los XML y datos comerciales importados no se
incluyen en la distribución pública. Un archivo privado de trabajo puede contener
la biblioteca del usuario; debe distinguirse del paquete público de fuentes.

## Compatibilidad con V1 y V2

El comando anterior sigue disponible sin cambiar las ecuaciones históricas:

```powershell
uv run noiz materials
uv run noiz predict examples/single_panel.noiz.json --output-dir artifacts/v1
```

Esta ruta usa `mass-law-1`, puntos centrales nominales y el proyecto JSON v1.
Al abrir ese proyecto en el escritorio V3 se migra a una composición con notas
sobre el cambio de modelo y los supuestos añadidos. El nuevo resultado puede
cambiar por flexión y promedio en banda. Para reproducir el cálculo antiguo usar
la ruta V1, no exigir igualdad al modelo de placas/cámaras.

V3 también acepta los archivos de composición V2. Agrega explícitamente capas
activas, cantidad de absorbente uno, gas aire y los controles nuevos desactivados;
la excitación conserva transmisión aérea, incluso si la geometría era Floor o
Roof. La carga no reescribe los originales.

## Pruebas y construcción

```powershell
uv run --locked --all-extras pytest
uv run --locked --all-extras ruff check .
uv run --locked --all-extras python -m build --installer uv
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
- Definición de bandas y espectro incidente; V2/V3 suponen potencia uniforme por Hz.
- Curvas, diagnósticos, Rw provisional, STC con su identificador de procedimiento
  y todas las advertencias.
- Versión de herramientas de contraste y tolerancias numéricas.

Los comandos siguientes ayudan a registrar versiones sin volcar credenciales:

```powershell
uv run python --version
uv pip freeze
git rev-parse HEAD
```

Los archivos V3 usan `schema_version: 3`, `model_name`, un objeto `project` activo
y una lista opcional `variants` a nivel superior. Cada variante contiene un
proyecto completo y tiene una clave única de elemento/número de hojas. Conservan
propiedades editadas y registros de origen por separado; actualizar el catálogo
no modifica una composición guardada. No se admiten variantes anidadas ni claves
ambiguas. Los archivos V1/V2 mantienen sus propios esquemas históricos y se
migran al leer. Los informes son cálculos, no mediciones experimentales.

La geometría ancho/alto no produce modos finitos, pero sí determina el área
relativa de una fuga geométrica. La masa calculada suma placas activas, sin
estructura ni absorbente de cámara/Facing; Porous no infiere masa de resistividad.
Conservar estas definiciones permite comparar correctamente ejecuciones.

## Entorno en la nube

Cada tarea en la nube ya trabaja en un entorno aislado. Usar el checkout existente
y no crear un worktree salvo petición explícita. La instalación repetible respeta
archivos de usuario y usa el lockfile. No requiere API keys, servidores remotos ni
base de datos: los proyectos y catálogos son locales.

La descarga de dependencias necesita los índices y artefactos correspondientes.
Mantener TLS, firmas y hashes verificados. Si una referencia no se puede abrir,
registrar la limitación sin declararla consultada. La guía INSUL v10 sí pudo
consultarse en las sesiones V2/V3; véase [la revisión V3](v3-reference-review.md).

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

## Reproducción de la interfaz V4

V4 conserva los archivos de esquema 3 y los ejemplos físicos V3. El selector
Rw/STC no modifica las entradas ni recalcula la curva. Los informes conservan
ambos valores y el identificador `STC-legacy-32-8-whole-dB-v1` cuando es aplicable.
Las dimensiones documentadas de ventana son píxeles lógicos de Qt: a escala
150%, 1280×720 lógicos ocupan 1920×1080 píxeles físicos, antes del marco del SO.
En Linux sin pantalla puede verificarse la escala en procesos separados mediante
`QT_SCALE_FACTOR=1.5 QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_v4.py`.

## Reproducción de la interfaz V5

V5 mantiene las ecuaciones del motor y el esquema 3. Los ejemplos físicos V3 y
`examples/v4_visual_demo.noiz.json` continúan siendo útiles: el último contiene
materiales sintéticos para inspeccionar geometría, no un sistema comercial
validado acústicamente.

Para comprobar los cambios visuales:

1. Abrir `examples/v3_single.noiz.json`, calcular y alternar **Rw / STC**. La curva
   TL no cambia; el contorno de referencia sí: Rw utiliza 100–3150 Hz y STC
   legado 32/8 utiliza 125–4000 Hz. No se extrapolan extremos. La leyenda aparece
   a la derecha y sus casillas permiten ocultar cada curva. Una predicción sin
   clasificación disponible no dibuja una referencia inventada.
2. Redimensionar la ventana o mover el separador entre editor y resultados. El
   área interior de los ejes debe conservar anchura y altura iguales. Esto no
   implica que un Hz equivalga gráficamente a un dB: los ejes mantienen escala
   logarítmica y lineal respectivamente. No hay curvas de flancos o ISO 10140.
3. Comprobar la tabla superior: encabezados de 63 Hz a 4 kHz y la fila completa
   de TL con un decimal. Sus números siguen siendo el promedio energético de
   tres bandas de tercio de octava, no la media aritmética de tres niveles dB.
4. Abrir `examples/v4_visual_demo.noiz.json` y alternar **3D · rotar / 2D · corte**.
   Sin **Detalle**, las dimensiones usan proporciones reales. Activarlo amplía
   solo el espesor mostrado e indica el factor. **Recorte** descubre parcialmente
   la cámara; desactivarlo muestra las caras completas. Ninguno cambia las
   dimensiones físicas guardadas ni el resultado acústico.
5. Rotar, soltar, cambiar opacidad y redimensionar. La vista reduce su resolución
   durante el arrastre y vuelve a la resolución estática al soltar, según DPR y
   límite de memoria. Reexponer la misma escena reutiliza su imagen en caché.
6. En Biblioteca, revisar **Conexiones / sistemas de montaje** y **Referencias**.
   Las referencias aparecen solo si el registro contiene una URL explícita.
   Los ocho XML de esta entrega no contienen enlaces legibles a planos o BIM;
   el catálogo no debe presentar sus herrajes como geometría comercial verificada.

En Linux, las pruebas específicas pueden ejecutarse sin pantalla:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked --all-extras pytest tests/test_ui_v5_chart.py tests/test_v5_render.py tests/test_catalog_v5.py tests/test_v5_connections.py tests/test_catalog_ui_v5.py
```

La prueba del gráfico comprueba también escalas de 125% y 150% en procesos
separados. Estas comprobaciones automatizadas no sustituyen una revisión de
Windows con el escalado y los controladores de la máquina del usuario. El estado
de la entrega se documenta en [release-v5.md](release-v5.md); las fuentes
geométricas y sus límites, en [v5-geometry-sources.md](v5-geometry-sources.md).
