# Probar Noiz Transmission V2 en Windows

La ventana se abre en tu ordenador. Esta entrega contiene el código y un
lanzador `.cmd`; todavía no contiene un instalador `.exe`.

## Descargar y abrir

1. Descarga el ZIP V2 desde la conversación y selecciona **Extraer todo**. La
   carpeta `Noiz-Transmission` debe contener `INICIAR_NOIZ.cmd`, `pyproject.toml`,
   `uv.lock`, `examples` y `src`.
2. Instala **uv** desde sus [instrucciones oficiales para Windows](https://docs.astral.sh/uv/getting-started/installation/).
   Cierra y vuelve a abrir las ventanas de terminal después de instalarlo.
3. Haz doble clic en **`INICIAR_NOIZ.cmd`**. La primera ejecución necesita Internet
   para descargar Python 3.13 y las dependencias. Las siguientes reutilizan `.venv`.

El paquete **personal** incluye en `local_data/catalog.json` los 2.434 registros
convertidos de tus seis XML. El paquete **source** incluye código y ejemplos
sintéticos; puedes cargar los XML desde **Importar XML…**. Los datos del paquete
personal mantienen su procedencia y derechos originales y están excluidos de Git.

Si prefieres PowerShell, ábrelo dentro de la carpeta extraída y ejecuta:

```powershell
uv sync --locked --extra desktop
uv run --locked --extra desktop noiz-transmission
```

No uses `/workspace/...` en tu PC: esa es la ubicación de la copia en la nube.

## Un recorrido por la V2

1. Abre `examples/double_leaf.noiz.json` con **Abrir…**. Es un ejemplo sintético
   de dos placas de 12,5 mm, densidad 800 kg/m³ y cámara independiente de 100 mm.
   Su masa de placas es **20 kg/m²** y su espesor total **125 mm**.
2. En **Panel 1**, cambia el espesor, duplica una capa o cambia el número de
   placas. La composición y la sección se actualizan; el resultado anterior
   deja de presentarse como vigente.
3. Pulsa **Elegir material…**. Busca un producto, consulta sus propiedades y
   procedencia y selecciónalo. Los productos incompatibles con el modelo
   permanecen consultables en la biblioteca.
4. En **Cámara 1**, ajusta su profundidad. Para usar relleno, elige un absorbente,
   su espesor y una resistividad al flujo con fuente conocida. El `Damping` del
   XML no se interpreta como resistividad. Para probar con aire deja espesor y
   resistividad del absorbente en cero.
5. Pulsa **Calcular** o **F5**. La integración de resonancias puede tardar; puedes
   seguir editando. Si cambias el elemento durante el cálculo, el resultado se
   descarta y debes volver a calcular la nueva configuración.
6. Arrastra el separador encima de las pestañas de resultados o pulsa **Ocultar
   resultados** para ampliar el editor. **Curva** y **Tabla por bandas** muestran
   la misma predicción.
7. En **Comparación**, usa **Guardar resultado actual**, modifica el elemento,
   calcula y guarda otra alternativa. Puedes conservar hasta seis curvas.
8. **Guardar** conserva el proyecto y sus propiedades. **CSV…** e **Informe
   HTML…** exportan resultados y advertencias; el HTML se abre en un navegador.

El modo Suelo calcula transmisión **aérea**, no impacto. Montantes unidos,
revestimientos de suelo y perfiles requieren modelos todavía no implementados:
si se incorporan a la configuración, la aplicación explica por qué no calcula.
Ancho y alto sirven para describir el elemento; el motor usa placas infinitas.

## Prueba sin interfaz

```powershell
uv run noiz assembly examples/single_plate.noiz.json --output-dir artifacts/single
uv run noiz assembly examples/double_leaf.noiz.json --output-dir artifacts/double
Start-Process artifacts/double/report.html
```

Cada cálculo crea `report.html`, `spectra.csv` y `result.json`. Para ejecutar las
pruebas del desarrollo instala también los extras:

```powershell
uv sync --locked --all-extras
uv run pytest -W error
```

## Dónde están las carpetas

```text
Noiz-Transmission/
├── INICIAR_NOIZ.cmd     Lanzador Windows
├── src/noiz_transmission/
│   ├── core/            Motor físico y clasificación
│   ├── application/     Proyectos y exportaciones
│   ├── catalog/         Importación y biblioteca local
│   ├── data/            Ejemplos de materiales sintéticos
│   ├── adapters/        Contrastes con Phonometry
│   └── ui/              Interfaz de escritorio
├── local_data/          Catálogo personal; excluido de Git
├── examples/            Proyectos para probar
├── tests/               Pruebas automáticas
├── validation/          Casos matemáticos
├── docs/                Teoría, alcance y fuentes
└── .github/workflows/   CI para Windows y Linux
```

En Codex, la copia está en `/workspace/Noiz-Transmission`. Para trabajar en tu PC
usa la carpeta extraída del ZIP.

## GitHub y verificación

El código V2 está publicado en la rama
[`codex/noiz-transmission-v2`](https://github.com/oscargit010502/Noiz-Transmission/tree/codex/noiz-transmission-v2).
Abre ese enlace para ver las carpetas; si entras en la portada del repositorio,
selecciona esa rama en el selector que muestra `main`. También puedes descargar
el código desde **Code → Download ZIP**. Tus catálogos están en el paquete
personal de esta conversación y no forman parte de la rama pública.

Las comprobaciones de esta entrega se realizan en Linux, incluida la interfaz
Qt sin pantalla. Windows tiene una configuración de CI preparada, pero todavía
no se ha verificado aquí la ejecución nativa del lanzador `.cmd`.
