# Probar Noiz Transmission V6.1 en Windows

La ventana se abre en tu ordenador. Esta entrega contiene código y un lanzador
`.cmd`; todavía no contiene un instalador `.exe`.

## Descargar y abrir

1. Descarga el [ZIP V6.1 desde GitHub](https://github.com/oscargit010502/Noiz-Transmission/archive/refs/heads/codex/noiz-transmission-v6-1.zip)
   y selecciona **Extraer todo**. La carpeta del proyecto debe contener `INICIAR_NOIZ.cmd`, `pyproject.toml`,
   `uv.lock`, `examples` y `src`. Usa una carpeta nueva para conservar tus versiones anteriores.
2. Instala **uv** siguiendo sus
   [instrucciones oficiales para Windows](https://docs.astral.sh/uv/getting-started/installation/).
   Cierra y vuelve a abrir las ventanas de terminal después de instalarlo.
3. Haz doble clic en **`INICIAR_NOIZ.cmd`**. La primera ejecución necesita Internet
   para descargar Python 3.13 y dependencias. Las siguientes reutilizan `.venv`.

**Desde 0.5.1, este ZIP incluye los 3.629 registros de los ocho XML.** Aparecen
automáticamente en **Biblioteca…**, Products, Frame e Infill. No necesitas un
paquete personal, importar archivos ni copiar `local_data` para tener la base.
La carpeta `src/noiz_transmission/data/catalog/` contiene el recurso comprimido,
su manifiesto y la atribución de los datos. No edites el archivo comprimido;
usa **Biblioteca… → Crear copia editable** para personalizar un material.

En PowerShell, dentro de la carpeta extraída, también puedes ejecutar:

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --locked --extra desktop
uv run --locked --extra desktop noiz-transmission
```

La aplicación configura la instalación por copia tanto en el proyecto como en el lanzador.
Esto evita el error **396** de OneDrive con vínculos permanentes. Si tu instalación
anterior quedó incompleta, cierra Noiz y repite los comandos anteriores en la
carpeta extraída de V6; uv completará las dependencias. No necesitas borrar el
catálogo ni tus proyectos.

No uses `/workspace/...` en tu PC: esa es la ubicación de la copia en la nube.

## Probar el motor V6

1. Abre `examples/v6_single.noiz.json` y pulsa **F5**. En **Dimensiones y
   condiciones de cálculo…** comprueba que está seleccionado el modo de tamaño
   finito. Ancho y alto intervienen en la corrección de la curva difusa.
2. Conserva el resultado en Comparación. Cambia el ancho, calcula y compara:
   la corrección depende del área y del perímetro del elemento.
3. Ajusta las pérdidas adicionales de borde del panel si dispones de ese dato.
   Su valor cero inicial evita sumar pérdidas de montaje a materiales que ya
   las incluyen. No es una propiedad que se pueda deducir de una fotografía.
4. Prueba `v6_double.noiz.json`, `v6_triple.noiz.json` y `v6_quad.noiz.json`.
   Son ejemplos sintéticos de hojas independientes, sin puentes por montantes.
5. Vuelve a calcular un proyecto idéntico para comprobar la reutilización del
   resultado. Cambiar dimensiones, pérdidas o material exige un cálculo nuevo.
6. Consulta **Ayuda → Modelo e hipótesis…** y los informes: las bandas próximas
   a la primera resonancia requieren un modelo modal que aún no está resuelto.

Los archivos anteriores se abren con el modelo infinito que usaban. Para estudiar
el efecto de V6, cambia explícitamente el modelo en condiciones de cálculo y
guarda una copia. Los archivos nuevos usan esquema 4; V5 no puede leer ese esquema.
La corrección verificada es Davy, no Sewell. No hay todavía una tolerancia
experimental demostrada para Noiz; consulta [evidencia V6](docs/v6-evidence.md).

## Interfaz V6.1

Los controles y las listas ocupan menos espacio vertical. El gráfico no permite
zoom, desplazamiento ni cambios manuales de ejes; el programa ajusta las escalas
al calcular. Las casillas de la leyenda permiten ocultar y mostrar curvas.

El gráfico conserva ejes de igual longitud, incluso al cambiar su tamaño, y
muestra las leyendas a la derecha. El selector **Rw / STC** cambia el índice y
su curva de referencia ajustada al resultado actual. STC utiliza
el procedimiento legado 32/8 descrito en [criterios de clasificación](docs/v4-ratings.md),
con alcance provisional; no es una conversión de Rw. IIC y Ln,w requieren el motor
de impacto pendiente; L’nT,w corresponde a recintos y no es el mismo índice.

La tabla superior tiene encabezados contrastados y valores centrados. Se conservan
los controles Qt compactos de V4. El render usa proporciones reales por defecto,
mejora la transparencia y reutiliza la imagen mientras no cambie la vista.
**Recorte** descubre la cavidad; **Detalle** amplía el espesor para inspeccionarlo
sin cambiar el proyecto. Arrastrar hacia la izquierda gira a la izquierda;
arrastrar hacia arriba gira hacia arriba. **Restablecer vista** recupera la cámara.

Frame ofrece ahora los catálogos **Connections y Studs**. Seleccionar una conexión
carga las cotas declaradas; si fija la separación de montantes, ese control queda
bloqueado. **Biblioteca → Referencias** muestra enlaces documentales cuando el
registro los contiene. Los ocho XML de esta entrega no incluyen enlaces legibles
a drawings/BIM: no se atribuye precisión de fabricante a las geometrías esquemáticas.

Conserva tu carpeta anterior y sus materiales propios. Si utilizabas una biblioteca
portátil, copia su carpeta `local_data` a la carpeta nueva: V6 la combina con
la base integrada sin sobrescribirla al abrir. Si hay varios catálogos portátiles,
se elige `catalog-v5.json`, luego `catalog-v3.json` y luego `catalog.json`.
Si configuraste `NOIZ_CATALOG_PATH`, esa variable selecciona una biblioteca aislada;
para recuperar la carga normal en PowerShell ejecuta
`Remove-Item Env:NOIZ_CATALOG_PATH -ErrorAction SilentlyContinue` antes de iniciar.
Los proyectos anteriores y sus variantes se abren en V6 conservando su catálogo
y propiedades. La migración conserva también la elección del modelo anterior.

## Recorrido para comprobar la V5

1. Abre **`examples/v3_single.noiz.json`** con **Abrir…**. En Wall → Single →
   Panel 1 → Layer 1 encontrarás una placa sintética de 12,5 mm y 10 kg/m².
2. En Products selecciona un material. Comprueba que **Thickness** cambia al
   espesor nominal y que puedes editarlo. Usa Search, Category y Manufacturer
   para filtrar; filtrar por sí solo no reasigna el producto.
3. Selecciona **Layer 2**, actívala y elige su producto. **Quantity** admite de
   1 a 10 placas. Desactivar una Layer la excluye de la composición sin borrar
   sus ajustes. Cada Panel dispone de seis Layer.
4. Cambia a **Double → Frame 1**. Ajusta Cavity Width y selecciona un Infill.
   El relleno necesita una resistividad al flujo explícita con fuente conocida.
   **Quantity = 0** lo retira de la vista y del cálculo. Un Stud conserva sus
   dimensiones para edición, pero su puente estructural aún no se calcula.
   Para calcular hojas independientes elige el Frame independiente.
5. Prueba **Triple** y **Quad**: Quad intercala cuatro Panel y tres Frame. Al
   volver a Single se recuperan sus ajustes. **Guardar** conserva también las
   variantes inactivas; puedes comprobarlo cerrando y volviendo a abrir el archivo.
6. **Leak** permite activar Slit o Aperture y configurar dimensiones, posición
   y solución. Gomperts y Mechel se conservan, pero el cálculo está pendiente.
   Para probar una aproximación disponible elige **Área abierta ideal**: usa
   únicamente el área del hueco, sin efecto de profundidad o posición.
7. Pulsa **Calcular** o **F5**. El cálculo se ejecuta en segundo plano y se puede
   cancelar. Si editas durante el cálculo, el resultado anterior no se presenta
   como vigente. Triple/Quad con absorbentes pueden requerir varios minutos.
8. Arrastra la vista **3D** para rotarla, usa la rueda para zoom y ajusta Opacidad.
   El selector **2D · corte** muestra la sección. Debajo aparecen fc o f₀ y masa;
   arriba, la descripción y la tabla en octavas.
9. **Chart** y **Tables** muestran los tercios de octava. Arrastra el separador
   horizontal o pulsa **Ocultar gráfica** para dar más espacio a los controles.
   El cuadrado mantiene su forma; las casillas de la leyenda ocultan curvas sin
   borrar resultados. El contorno Rw abarca 100–3150 Hz y STC 125–4000 Hz.
   No se dibujan curvas de flancos ni de ISO 10140.
   En **Comparación**, guarda el resultado actual, cambia una entrada y recalcula.
   Las comparaciones se exportan aparte mediante CSV; no se guardan en el proyecto.
10. Usa **Archivo → Exportar → Informe HTML…** o **Datos CSV…**. El informe
    incluye condiciones, advertencias y procedencia y se abre en un navegador.

En **Dimensiones…** puedes elegir campo difuso o
incidencia normal. Rw y STC solo se muestran para campo difuso. Las dimensiones describen
el elemento y permiten calcular la proporción de fuga; no convierten el modelo de
placa infinita en una simulación de tamaño finito.

Para revisar específicamente el render V5, abre **`examples/v4_visual_demo.noiz.json`**,
conservado para comparar la misma geometría entre versiones.
Wall → Double contiene dos placas, absorbente y un montante metálico U sintético.
Alterna 3D/2D y arrastra la vista. La variante Roof → Single del mismo archivo
muestra una chapa trapezoidal. Es un ejemplo de geometría: el cálculo acústico
de montantes y chapas perfiladas sigue pendiente. Usa `v3_single.noiz.json` para
comprobar un cálculo compatible: **Rw 29 dB / STC 28** antes de editar sus entradas.

La ventana admite un mínimo de 1024×620 píxeles lógicos; en ese tamaño, algunas
páginas avanzadas necesitan desplazamiento. Se recomienda 1280×720 o superior.

## Probar los otros elementos

| Modo | Recorrido y resultado disponible |
| --- | --- |
| Ceiling | Controles Panel/Frame equivalentes a Wall, con vista horizontal |
| Floor | Hasta Triple; Floor cover permite filtrar por base ligera, pesada o CLT. Floor Covering muestra ΔL declarado, no Ln del suelo completo |
| Roof | Single/Double, Rainfall Laboratory/Natural y Facing en Single; la predicción de lluvia está pendiente |
| Glazing | Hasta Quad, sin Leak; Frame permite elegir aire, argón o criptón |
| Porous | Selecciona absorbente, espesor y resistividad; calcula TL del medio poroso Miki |

Floor y Roof abren con su excitación propia, todavía pendiente. Puedes seleccionar
explícitamente transmisión aérea para estudiar las hojas compatibles; un
revestimiento de suelo o unión estructural no soportado debe retirarse de esa
configuración. La aplicación explica los bloqueos al calcular.

Noiz todavía no reproduce las soluciones Gomperts/Mechel, los puentes de Stud,
la clasificación de impacto, el ruido de lluvia ni la precisión publicada para
INSUL. Los controles guardados no acreditan que esos modelos estén implementados.

## Prueba sin interfaz

```powershell
uv run noiz assembly examples/v3_single.noiz.json --output-dir artifacts/single
uv run noiz assembly examples/v3_quad.noiz.json --output-dir artifacts/quad
uv run noiz assembly examples/v3_porous.noiz.json --output-dir artifacts/porous
Start-Process artifacts/single/report.html
```

Cada cálculo crea `report.html`, `spectra.csv` y `result.json`. El ejemplo Quad
utiliza incidencia normal para una prueba más rápida y no genera Rw. Los ejemplos
son sintéticos y no caracterizaciones de productos comerciales.

Para ejecutar las pruebas del desarrollo:

```powershell
uv sync --locked --all-extras
uv run pytest -W error
```

## Dónde están las carpetas y GitHub

```text
Noiz-Transmission/
├── INICIAR_NOIZ.cmd     Lanzador Windows
├── src/noiz_transmission/
│   ├── core/            Motor físico y clasificación
│   ├── application/     Proyectos, variantes y exportaciones
│   ├── catalog/         Importación y biblioteca local
│   ├── data/            Catálogo integrado y ejemplos sintéticos
│   ├── adapters/        Contrastes con Phonometry
│   └── ui/              Interfaz de escritorio
├── local_data/          Catálogo personal; excluido de Git
├── examples/            Proyectos compatibles y demostración visual sintética
├── tests/               Pruebas automáticas
├── validation/          Casos matemáticos
├── docs/                Teoría, alcance y fuentes
└── .github/workflows/   CI para Windows y Linux
```

El código V5 se publica en
[`codex/noiz-transmission-v5`](https://github.com/oscargit010502/Noiz-Transmission/tree/codex/noiz-transmission-v5).
Abre ese enlace para ver las carpetas. En la portada del repositorio, cambia
**main** por esa rama. También puedes descargar **Code → Download ZIP**.
Las versiones anteriores siguen en las ramas `codex/noiz-transmission-v2` y
`codex/noiz-transmission-v3` y `codex/noiz-transmission-v4`. La rama V5 actualizada
incluye la base convertida; tus modificaciones locales no se publican automáticamente.

En Codex, la copia está en `/workspace/Noiz-Transmission`. Las comprobaciones de
esta entrega se realizan en Linux, incluida la interfaz Qt sin pantalla. Windows
tiene CI preparada, pero aquí no se ha verificado la ejecución nativa del `.cmd`.
