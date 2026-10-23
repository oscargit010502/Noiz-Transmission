# Noiz Transmission

Aplicación open source de escritorio para estudiar el aislamiento acústico de
**elementos constructivos**, con motor físico independiente, materiales con
procedencia y resultados reproducibles. Python, PySide6, NumPy, SciPy y PyQtGraph.

**Versión 0.6.1 · interfaz compacta y gráfico de consulta · prototipo científico.** Los **3.629 registros**
ya vienen incluidos en la descarga de GitHub y aparecen al iniciar, sin importar XML.
Se conservan las mejoras de V5 en la vista en perspectiva y
el corte 2D con proporciones reales, recorte opcional y transparencia por profundidad.
El gráfico tiene ejes de igual longitud, leyenda a la derecha y la curva de
referencia ajustada Rw o STC. Incorpora los ocho catálogos actualizados, incluidas
las conexiones. La exactitud respecto a sistemas comerciales todavía
requiere validación experimental; los resultados no equivalen a un ensayo.

![Editor V6.1 con controles compactos y curva de referencia Rw](docs/images/workbench-v6.1.png)

## Descargar y abrir

El código V6.1 está en la rama
[`codex/noiz-transmission-v6-1`](https://github.com/oscargit010502/Noiz-Transmission/tree/codex/noiz-transmission-v6-1).
Selecciona esa rama y usa **Code → Download ZIP**. Extrae el ZIP, instala [uv](https://docs.astral.sh/uv/getting-started/installation/)
y ejecuta **`INICIAR_NOIZ.cmd`** en Windows. Desde la carpeta del proyecto:

```shell
uv sync --locked --extra desktop
uv run --locked --extra desktop noiz-transmission
```

La primera ejecución descarga Python 3.13 y dependencias si faltan. La
[guía de Windows](PROBAR_EN_WINDOWS.md) explica cómo probar cada control y dónde
están las carpetas. Esta entrega contiene código y lanzador; no un instalador `.exe`.

## Cambios en V6.1

- Controles nativos grises y azules, texto compacto y listas de productos de 8 pt.
- Dimensiones del montante junto al buscador; avisos agrupados y más espacio para
  listas y resultados. El contador de productos comparte la cabecera de la lista.
- Gráficos sin zoom, desplazamiento ni menú para modificar ejes. La aplicación
  ajusta las escalas al calcular; la leyenda conserva las casillas de visibilidad.
- Se mantienen el gráfico cuadrado, las referencias Rw/STC y el catálogo integrado.

Esta actualización modifica la interfaz; conserva el motor y las limitaciones
acústicas de V6, incluidos los puentes estructurales por montantes pendientes.
Consulta las [notas de V6.1](docs/release-v6.1.md).

## Modelo incorporado en V6

- Modo de tamaño finito para **Single, Double, Triple y Quad** de hojas
  independientes. La integración difusa usa el límite angular dependiente de
  área y perímetro publicado por Hansen a partir de Davy.
- Pérdidas adicionales de borde por panel, separadas del factor de pérdidas de
  las capas. El valor inicial es cero: un material con pérdidas de montaje ya
  incluidas no debe recibirlas por segunda vez.
- Diagnóstico de la primera frecuencia propia simplemente apoyada y avisos
  de las bandas fuera de la región de aplicación de la aproximación.
- Optimización del cálculo angular y reutilización de resultados idénticos en
  la interfaz. Se conserva la búsqueda de resonancias y el control de convergencia.
  En el caso Quad documentado: **112,08 → 19,98 s (5,61×)** con la misma curva
  del modelo anterior; véase el [benchmark](validation/v6-performance.md).
- Proyectos con esquema 4 que guardan el modelo y las pérdidas de borde;
  los proyectos anteriores se abren con el modelo infinito que utilizaban.
- Referencias con páginas y ecuaciones consultadas de Hansen, Vér/Beranek y
  Barron, y comprobaciones independientes. Véanse
  [física V6](docs/v6-physics.md) y [evidencia](docs/v6-evidence.md).

La corrección implementada es **Davy**, no Sewell. Tampoco resuelve todos los
modos estructurales de baja frecuencia. La extensión a varias hojas es una
aproximación de ingeniería cuya precisión experimental todavía debe establecerse;
no se declara equivalencia con INSUL ni un margen de error comercial.

## Interfaz y biblioteca

- Ejes del gráfico físicamente cuadrados al redimensionar la ventana o el separador;
  leyenda lateral con casillas para mostrar u ocultar cada curva.
- Referencia **Rw / STC** ajustada al resultado actual. Sin curvas de flancos ni
  límite de laboratorio ISO 10140. Comparaciones conservadas al cambiar el índice.
- Tabla superior de octavas con cabecera contrastada y valores centrados en negrita;
  se mantienen los controles Qt compactos y las propiedades plegables de V4.
- Proporciones reales por defecto en 3D y 2D. **Recorte** expone la cavidad;
  **Detalle** amplía espesores únicamente en la representación.
- Caché de geometría e imagen, render adaptado al DPI y transparencia por píxel.
  Las conexiones sin planos se muestran como esquemas o envolventes identificadas.
- **Connections y Studs** seleccionables en Frame, con las dimensiones y restricciones
  declaradas. La biblioteca conserva procedencia y permite consultar referencias.
- Instalación mediante copia para evitar el conflicto de vínculos permanentes de
  uv con OneDrive. El lanzador Windows activa esta opción automáticamente.

## Controles del elemento

- **Wall y Ceiling:** Single / Double / Triple / Quad; Panel y Frame intercalados,
  Facing en Single y Leak. Quad tiene cuatro paneles y tres Frames interiores.
- **Panel:** seis pestañas Layer, activación individual, Thickness en mm y
  Quantity de 1 a 10. Elegir un producto carga su espesor nominal, que se puede
  modificar. Búsqueda por nombre y filtros de categoría y fabricante.
- **Frame:** cámara, montante, dimensiones, separación e Infill. Quantity = 0
  retira el absorbente del cálculo y de la vista, conservando su selección.
- **Floor:** hasta Triple, Floor cover antes de Panel 1 y pestaña Floor Covering
  para consultar curvas ΔL importadas, filtradas por base ligera, pesada o CLT.
- **Roof:** Single/Double y controles Rainfall. **Glazing:** hasta Quad, sin Leak,
  con selección de gas de cámara. **Porous:** espesor y resistividad de la capa.
- Vista 3D con arrastre para rotar, rueda para zoom y opacidad; corte 2D con
  materiales diferenciados. Tabla superior en octavas, descripción, masa y fc/f₀.
- Chart y Tables en tercios de octava, hasta seis comparaciones, gráfica
  redimensionable y ocultable, exportación CSV/HTML y cálculo cancelable.
- Guardado con propiedades completas y variantes de los distintos modos y
  topologías; apertura de proyectos anteriores. Las comparaciones se exportan aparte.

## Qué calcula y qué queda pendiente

| Función | Estado en V6 |
| --- | --- |
| Transmisión aérea de 1–4 hojas isotrópicas independientes | Matrices de transferencia, flexión, pérdidas de borde y corrección angular de tamaño finito opcional |
| Cámaras de aire y absorbente poroso | Modelo Miki, con resistividad explícita |
| Cámaras de argón y criptón | Propagación acústica con propiedades de gas ideal; sin Miki en esos gases |
| Facing poroso exterior y elemento Porous | Modelo Miki; no representan un revestimiento sólido adherido |
| Leak de área abierta ideal | Combina transmisiones por área; no usa profundidad ni posición |
| Gomperts / Mechel, uniones por montantes | Controles y datos conservados; cálculo bloqueado por modelo pendiente |
| Impacto Ln,w/IIC y ruido de lluvia | Controles disponibles; predicción pendiente |
| Floor Covering medido | Consulta de ΔL declarado en catálogo; no calcula el Ln del suelo completo |
| Rw / STC | Clasificaciones provisionales de la curva difusa; STC utiliza el procedimiento legado 32/8, identificado en informes; sin clasificación en incidencia normal |

No se calcula aislamiento entre recintos, flancos ni uniones de ISO 12354.
El núcleo de placa conserva una aproximación de onda plana, complementada en V6
por una corrección de radiación finita. Las capas de una hoja comparten movimiento,
con suma de rigideces individuales: no es un modelo de laminado adherido ni un
modelo modal completo de placa finita. Una cámara con resonancias estrechas puede
tardar; el solver exige convergencia antes de entregar la curva. Consulta
[teoría y supuestos](docs/theory.md) y [validación](docs/validation.md).

INSUL 10 es una referencia funcional y bibliográfica. Noiz Transmission es
independiente de Marshall Day Acoustics y no atribuye a su modelo los márgenes de
error publicados para INSUL. Las opciones pendientes no sustituyen silenciosamente
sus modelos por otras fórmulas.

## Materiales y datos locales

**Importar XML…** admite Material, Profile, Glazing, Floor Cover, Absorption,
Core, Stud y Connection; conserva campos originales, unidades, identificadores y SHA-256.
Los ocho XML actualizados aportados contienen **3.629 registros**. Importar un
registro no demuestra su validez experimental ni su compatibilidad con el motor.
El `Damping` de absorbentes no se convierte automáticamente en resistividad.

Desde **0.5.1**, el catálogo se distribuye como recurso del programa en
`src/noiz_transmission/data/catalog/catalog-v5.json.gz`, junto con su manifiesto
de procedencia. Está incluido en el ZIP de GitHub y en el paquete Python. Se carga
sin conexión, sin necesitar los XML originales ni escribir en la instalación.
Los materiales propios de la biblioteca local se combinan con la base; si comparten
identificador, se conserva la versión del usuario. Reimportar el mismo XML no duplica
los registros. **Importar XML…** queda disponible para ampliaciones futuras.

`NOIZ_CATALOG_PATH` es una selección explícita de una biblioteca aislada y excluye
la base integrada. Sin esa variable, las bibliotecas portátiles `catalog-v5.json`,
`catalog-v3.json` y `catalog.json` se reconocen en ese orden. Los datos de terceros
conservan su procedencia y derechos: véase el [aviso del catálogo](src/noiz_transmission/data/catalog/NOTICE.md).

Los nuevos XML no contienen enlaces legibles a drawings o BIM. Las dimensiones
de catálogo no acreditan una sección exacta de fabricante; las geometrías sin
verificar se identifican en la vista. Consulta la [auditoría de fuentes](docs/v5-geometry-sources.md).
V6 conserva la edición y visualización de V5. Los modelos acústicos de uniones,
impacto y lluvia siguen pendientes.

## Reproducir sin interfaz

```shell
uv sync --locked
uv run noiz assembly examples/v6_single.noiz.json --output-dir artifacts/v6
uv run noiz assembly examples/v6_quad.noiz.json --output-dir artifacts/quad
uv run noiz catalog import ruta/Material_INSUL10.xml ruta/Stud_INSUL10.xml
```

Cada cálculo genera `result.json`, `spectra.csv` y `report.html`. Los ejemplos V6
usan materiales sintéticos y guardan las condiciones de cálculo. Los ejemplos
anteriores permanecen disponibles para reproducibilidad.

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
verificada. Phonometry se instala como extra para contrastes independientes.

- [Arquitectura](docs/architecture.md) y [hoja de ruta](docs/roadmap.md)
- [Entrega V5 y comprobaciones realizadas](docs/release-v5.md) y [criterios Rw/STC](docs/v4-ratings.md)
- [Actualización 0.5.1: materiales integrados](docs/catalog-native.md)
- [Entrega V4 anterior](docs/release-v4.md)
- [Entrega V3 anterior](docs/release-v3.md)
- [Validación](docs/validation.md), [fuentes](docs/sources.md) y [revisión INSUL 10/XML](docs/v3-reference-review.md)
- [Materiales](docs/materials.md), [reproducibilidad](docs/reproducibility.md) y [contribuciones](CONTRIBUTING.md)

Código bajo [licencia MIT](LICENSE). PySide6 y las demás dependencias mantienen
sus licencias; un futuro ejecutable debe incluir los avisos correspondientes.
