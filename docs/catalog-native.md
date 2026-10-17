# Catálogo nativo · actualización 0.5.1

La descarga de GitHub y el wheel incluyen los **3.629 registros** de los ocho XML
aportados. Abrir Noiz Transmission carga los productos sin importación, red ni
archivos externos. La edición 0.5.0 los separaba en un paquete personal; esta
actualización corrige esa distribución y mantiene la rama V5.

## Archivos y funcionamiento

- `src/noiz_transmission/data/catalog/catalog-v5.json.gz`: instantáneas completas
  de los registros, comprimidas. Es un recurso de la aplicación, no una caché.
- `manifest.json`: cantidades por familia, nombres y SHA-256 de los ocho XML y
  huella del JSON descomprimido, comprobada al cargar.
- `NOTICE.md`: procedencia y separación entre la licencia del código y los datos.

Se distribuyen 1.575 materiales, 523 absorbentes, 669 revestimientos de suelo,
80 vidrios, 281 perfiles, 45 núcleos, 69 montantes y 387 conexiones. Las propiedades,
campos originales, identificadores y advertencias se conservan; no cambian las
restricciones físicas ni se certifican los datos por estar precargados.

La base se lee mediante `importlib.resources`, tanto desde una descarga de fuentes
como desde un paquete Python instalado. No depende del directorio actual ni se
descomprime en la carpeta de instalación. Abrir la biblioteca no crea ni reemplaza
archivos del usuario. Un recurso incompleto o dañado produce un error explícito.

Las entradas locales se combinan por identificador con la base. La versión local
tiene prioridad en caso de coincidencia y los materiales propios se conservan.
Guardar desde Biblioteca utiliza la ruta local existente; el recurso integrado
no se modifica. Una importación repetida del mismo XML es idempotente.

`NOIZ_CATALOG_PATH` continúa siendo una selección explícita de una biblioteca
aislada. Para incluir la base, elimina esa variable. `noiz catalog list` muestra
la biblioteca combinada; `noiz catalog list --input ARCHIVO` inspecciona únicamente
el archivo indicado. Los proyectos sintéticos existentes siguen siendo reproducibles.

## Actualizar la base como desarrollador

```shell
uv run python tools/build_catalog.py --output src/noiz_transmission/data/catalog XML1 XML2 XML3 XML4 XML5 XML6 XML7 XML8
```

El script lee los XML sin modificarlos, valida los registros y genera JSON
comprimido determinista con manifiesto. No atribuye una licencia nueva a los datos.
Las personalizaciones del usuario deben hacerse en Biblioteca, no con este script.

## Verificación

Las pruebas específicas comprueban las ocho familias, procedencia, primer inicio
sin biblioteca externa, ausencia de escritura en la instalación, conservación de
materiales propios y selección explícita de una biblioteca alternativa. Se verifica
también el inicio desde el wheel instalado fuera del repositorio.

Comprobación de esta actualización: **675 pruebas aprobadas con `-W error`**,
Ruff y `git diff --check` correctos. Wheel 0.5.1 instalado fuera del checkout:
inicio Qt con usuario nuevo, 3.629 entradas, 1.575 productos en Wall, 456 entradas
de Frame y 523 absorbentes, sin archivo local de biblioteca ni importación.
Verificado en Linux/Qt offscreen; la ejecución nativa de Windows queda pendiente.
