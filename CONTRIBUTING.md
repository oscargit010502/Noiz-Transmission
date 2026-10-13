# Contribuir a Noiz Transmission

Trabajamos en español e inglés. Antes de añadir un modelo, propone su dominio de validez,
ecuaciones, fuentes, parámetros identificables y evidencia con la que se podrá contrastar.
Una curva visualmente razonable no demuestra que un modelo prediga un sistema constructivo.

## Desarrollo

1. Instala Python 3.13 y [uv](https://docs.astral.sh/uv/).
2. Ejecuta `uv sync --locked --all-extras` desde el repositorio.
3. Ejecuta `uv run pytest` y `uv run ruff check .` antes de proponer cambios.
   En Linux sin pantalla, usa `QT_QPA_PLATFORM=offscreen uv run pytest`.
4. Abre un pull request que describa comportamiento, límites físicos y verificaciones.

El motor no importa PySide6 ni conoce archivos de proyectos. Las unidades internas son SI;
las conversiones para el editor pertenecen a los servicios. Conserva los proyectos de ejemplo
y la compatibilidad de sus esquemas, o proporciona una migración explícita.

Para modificar dependencias, actualiza `pyproject.toml` y `uv.lock` con `uv lock` y verifica
la instalación bloqueada. La CI está configurada para Windows y Linux; su configuración no
equivale a una ejecución exitosa hasta observar los resultados en GitHub.

## Datos y ciencia

- Separa pruebas matemáticas, comparación independiente y validación experimental.
- Acompaña los datos de fuente, unidades, versión, región, licencia y condiciones de ensayo.
- No atribuyas valores de ejemplo a fabricantes. No incorpores bases de datos comerciales
  sin permiso de redistribución.
- Declara las tolerancias antes de evaluar un conjunto experimental y conserva los fallos.
- No copies código, textos o bases de datos de INSUL; el desarrollo es independiente.

Consulta [validación](docs/validation.md) y [materiales](docs/materials.md).
Las contribuciones de código se reciben bajo la licencia MIT del proyecto. Los datos pueden
tener condiciones distintas y deben declararlas por registro.
