# Probar Noiz Transmission V3 en Windows

La ventana se abre en tu ordenador. Esta entrega contiene código y un lanzador
`.cmd`; todavía no contiene un instalador `.exe`.

## Descargar y abrir

1. Descarga el ZIP **V3** de la conversación y selecciona **Extraer todo**.
   La carpeta `Noiz-Transmission` debe contener `INICIAR_NOIZ.cmd`, `pyproject.toml`,
   `uv.lock`, `examples` y `src`. Usa una carpeta nueva para conservar tu V2.
2. Instala **uv** siguiendo sus
   [instrucciones oficiales para Windows](https://docs.astral.sh/uv/getting-started/installation/).
   Cierra y vuelve a abrir las ventanas de terminal después de instalarlo.
3. Haz doble clic en **`INICIAR_NOIZ.cmd`**. La primera ejecución necesita Internet
   para descargar Python 3.13 y dependencias. Las siguientes reutilizan `.venv`.

El paquete **personal** incluye `local_data/catalog-v3.json` con **3.242 registros**
convertidos de tus siete XML INSUL 10.0/8. El paquete **source** incluye código y
materiales sintéticos; puedes cargar tus XML con **Importar XML…**. Los datos del
paquete personal conservan su procedencia y derechos y están excluidos de Git.
Ese paquete también incluye `local_data/v3_catalog_demo.noiz.json`, una placa de
10 mm tomada del catálogo, para comprobar la selección y el cálculo con esos datos.

En PowerShell, dentro de la carpeta extraída, también puedes ejecutar:

```powershell
uv sync --locked --extra desktop
uv run --locked --extra desktop noiz-transmission
```

No uses `/workspace/...` en tu PC: esa es la ubicación de la copia en la nube.

## Recorrido para comprobar la V3

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
   En **Comparación**, guarda el resultado actual, cambia una entrada y recalcula.
   Las comparaciones se exportan aparte mediante CSV; no se guardan en el proyecto.
10. Usa **Archivo → Exportar → Informe HTML…** o **Datos CSV…**. El informe
    incluye condiciones, advertencias y procedencia y se abre en un navegador.

En **Dimensiones y condiciones de cálculo…** puedes elegir campo difuso o
incidencia normal. Rw solo se muestra para campo difuso. Las dimensiones describen
el elemento y permiten calcular la proporción de fuga; no convierten el modelo de
placa infinita en una simulación de tamaño finito.

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
│   ├── data/            Materiales sintéticos públicos
│   ├── adapters/        Contrastes con Phonometry
│   └── ui/              Interfaz de escritorio
├── local_data/          Catálogo personal; excluido de Git
├── examples/            Proyectos V1, V2 y V3
├── tests/               Pruebas automáticas
├── validation/          Casos matemáticos
├── docs/                Teoría, alcance y fuentes
└── .github/workflows/   CI para Windows y Linux
```

El código V3 se publica en
[`codex/noiz-transmission-v3`](https://github.com/oscargit010502/Noiz-Transmission/tree/codex/noiz-transmission-v3).
Abre ese enlace para ver las carpetas. En la portada del repositorio, cambia
**main** por esa rama. También puedes descargar **Code → Download ZIP**.
La V2 sigue en su rama `codex/noiz-transmission-v2`. Los XML y el catálogo personal
no forman parte de esas ramas públicas.

En Codex, la copia está en `/workspace/Noiz-Transmission`. Las comprobaciones de
esta entrega se realizan en Linux, incluida la interfaz Qt sin pantalla. Windows
tiene CI preparada, pero aquí no se ha verificado la ejecución nativa del `.cmd`.
