# Noiz Transmission

Aplicación open source de escritorio para estudiar el aislamiento acústico de
**elementos constructivos**. Motor físico independiente, biblioteca con procedencia,
editor de composición y resultados reproducibles. Orientada a Windows, desarrollada
también en Linux con Python, PySide6, NumPy, SciPy y PyQtGraph.

**Versión 0.2.0 · prototipo científico.** La V2 incorpora hojas múltiples, rigidez,
amortiguamiento y cámaras. La exactitud respecto a sistemas comerciales todavía
requiere validación experimental; los resultados no equivalen a un ensayo.

## Abrir la aplicación

Instala [uv](https://docs.astral.sh/uv/getting-started/installation/), extrae el
proyecto y, en Windows, ejecuta **`INICIAR_NOIZ.cmd`**. También puedes usar una
terminal dentro de la carpeta:

```shell
uv sync --locked --extra desktop
uv run --locked --extra desktop noiz-transmission
```

La primera ejecución descarga Python 3.13 y dependencias si faltan. Consulta la
[guía de Windows](PROBAR_EN_WINDOWS.md) para probar cálculos, importar tus materiales
y encontrar las carpetas. Todavía no se distribuye un instalador `.exe`.

## Qué cambia en V2

- Editor de una, dos o tres hojas, hasta seis capas por hoja: material, espesor,
  densidad, módulo de Young, Poisson, amortiguamiento y número de placas.
- Cámaras con profundidad, absorbente y resistividad al flujo explícita; esquema
  en sección y axonometría. Los parámetros ocupan el área principal y los
  resultados se pueden redimensionar u ocultar.
- Biblioteca XML con búsqueda y filtros por familia, categoría, fabricante y
  país; propiedades originales, unidades y procedencia visibles. Creación de
  materiales propios y copias editables.
- Cálculo en segundo plano, curva y tabla por tercios de octava de 50–5000 Hz,
  hasta seis comparaciones, guardado de proyectos y exportación CSV/HTML.
- Proyectos V2 con copias completas de las propiedades utilizadas; apertura de
  proyectos V1 con aviso del cambio de modelo físico.

El motor utiliza matrices de transferencia para placas isotrópicas infinitas y
cámaras independientes. Incluye flexión, pérdidas, relleno poroso Miki y una
abertura ideal expresada en porcentaje de área. Las capas de una hoja comparten
movimiento, con suma de rigideces individuales; esto no representa una placa
compuesta adherida. Los detalles están en [teoría y supuestos](docs/theory.md).

Los nombres Muro, Cielorraso, Suelo, Cubierta, Vidrio y Puerta identifican el
elemento: todos calculan **transmisión aérea**. Los puentes por montantes, perfiles
estructurales, laminados, núcleos acoplados, impacto, lluvia, STC/IIC y flancos
necesitan modelos específicos. Las configuraciones no soportadas se conservan
para edición y se bloquean al calcular. Rw es orientativo y provisional; la
incidencia normal no genera Rw. No se calcula aislamiento entre recintos ISO 12354.

## Materiales y datos locales

`Importar XML…` incorpora Material, Profile, Glazing, Floor Cover, Absorption y
Core; conserva los campos originales y señala propiedades incompletas. Importar
un registro no demuestra que sea físicamente válido ni compatible con el motor.
El campo `Damping` de absorbentes no se convierte automáticamente en resistividad.

El código público incluye ejemplos sintéticos. Los catálogos importados quedan
en el almacenamiento del usuario o en `local_data/catalog.json` si existe junto
al proyecto; `NOIZ_CATALOG_PATH` permite elegir otra ruta. `local_data/` está
excluido de Git y de las distribuciones públicas. Los datos de terceros conservan
sus propios derechos y no adquieren la licencia MIT del código.

INSUL 10 y las capturas aportadas son referencias funcionales. Noiz Transmission
es independiente de Marshall Day Acoustics y no reproduce su código ni atribuye
a su propio modelo la precisión publicada para INSUL.

## Reproducir sin interfaz

```shell
uv sync --locked
uv run noiz assembly examples/double_leaf.noiz.json --output-dir artifacts/v2
uv run noiz catalog import ruta/Materials_INSUL.xml ruta/Absorption_INSUL.xml
```

El cálculo genera `result.json`, `spectra.csv` y `report.html`. Una cámara con
resonancias estrechas puede requerir más tiempo de integración; el solver exige
convergencia antes de entregar la curva. El flujo original permanece disponible
mediante `noiz predict examples/single_panel.noiz.json --output-dir artifacts/v1`.

## Cinco componentes

| Componente | Ubicación |
| --- | --- |
| Motor físico y clasificación | `src/noiz_transmission/core/` |
| Biblioteca y materiales | `src/noiz_transmission/catalog/`, `data/` |
| Escritorio y servicios | `src/noiz_transmission/ui/`, `application/` |
| Banco de verificación | `tests/`, `validation/`, `adapters/` |
| Documentación reproducible | `docs/` |

```shell
uv sync --locked --all-extras
uv run pytest -W error
uv run ruff check .
uv run python -m build --installer uv
```

En Linux sin pantalla usa `QT_QPA_PLATFORM=offscreen uv run pytest -W error`.
La CI configura Windows y Linux; su definición no sustituye una ejecución nativa
verificada. Los extras incluyen escritorio, herramientas de desarrollo y
Phonometry para contrastes independientes.

- [Arquitectura](docs/architecture.md) y [hoja de ruta](docs/roadmap.md)
- [Validación](docs/validation.md), [fuentes](docs/sources.md) y [revisión INSUL/XML](docs/v2-reference-review.md)
- [Materiales](docs/materials.md), [reproducibilidad](docs/reproducibility.md) y [contribuciones](CONTRIBUTING.md)

Código bajo [licencia MIT](LICENSE), conservando la atribución original. PySide6
y otras dependencias mantienen sus licencias; cualquier futuro ejecutable debe
incluir los avisos correspondientes.
