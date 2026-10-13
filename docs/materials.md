# Catálogo internacional y procedencia

El catálogo objetivo es **internacional**. El proyecto público distribuye tres
materiales sintéticos para reproducir ejemplos. La versión 2 permite importar
bibliotecas XML del usuario y consultarlas por familia, texto, categoría,
fabricante y región, conservando su procedencia. Importar no significa validar
científicamente las propiedades ni atribuirles la licencia del código.

## Archivos analizados en esta entrega

Los seis XML aportados declaran `Version="9.0"` y `Release="22"`. No constituyen un
catálogo documentado de INSUL 10 por el hecho de acompañarse de un folleto v10.

| Familia | Registros recibidos |
| --- | ---: |
| Materiales | 1077 |
| Perfiles | 273 |
| Vidrios | 86 |
| Revestimientos de suelo | 588 |
| Absorbentes | 380 |
| Núcleos | 30 |
| Total | 2434 |

La séptima familia del editor es montantes; no se recibió un XML de esa familia.
Su importador genérico no se presenta como verificado frente a un archivo real.
Se conservan duplicados por nombre y 187 filas con nombre vacío mediante etiquetas
identificables; no se inventan productos para rellenarlas.

De los archivos inspeccionados, **718 registros** cumplen el filtro de entrada de
placa isótropa: 696 materiales y 22 vidrios. La elegibilidad solo indica que se
pueden interpretar ciertas propiedades y comprobar sus rangos; no demuestra que
sean medidas fiables ni que una placa infinita represente ese producto.

## Propiedades, unidades y datos originales

El importador conserva nombre de archivo, SHA-256, identificador original,
posición del registro, versión del documento, campos originales y observaciones.
Los identificadores derivados del contenido y la posición permiten repetir una
importación sin duplicar las mismas filas y mantener filas distintas de igual
nombre. La persistencia local emplea JSON estricto y escritura atómica.

En la estructura 9.0/22 inspeccionada, espesor se expresa en metros, densidad en
kg/m³ y módulo de Young en Pa. El editor muestra mm y GPa cuando corresponde;
las conversiones no cambian los valores originales conservados. Los campos de
otras versiones necesitan revisión antes de atribuirles las mismas unidades.

La biblioteca distingue:

- Propiedades de placa isótropa que pueden alimentar el modelo admitido.
- Constituyentes de sistemas compuestos, perfiles, núcleos y laminados que requieren
  modelos distintos; conservar sus datos no autoriza reducirlos a una placa simple.
- Espectros de origen, que no se tratan automáticamente como mediciones.
- Campos de interpretación pendiente, conservados como datos originales.

**`Absorption/Properties/Damping` no se convierte en resistividad al flujo.** No se
ha verificado un esquema que documente esa correspondencia. Para usar un relleno
Miki se exige resistividad explícita en Pa·s/m² y espesor. La unidad de resistividad
sí está confirmada en la guía: Rayl/m equivale a Pa·s/m². No se confunde con el
factor de pérdidas estructural adimensional de una placa.

Los registros de materiales, vidrios, núcleos y absorbentes contienen valores
`Measurement/Source = XXX` y curvas de ejemplo constantes; no son un banco de
validación experimental. El texto `Measured` en ciertos revestimientos no aporta
por sí solo laboratorio, montaje, incertidumbre o informe de ensayo.

## Biblioteca local y publicación

La selección de archivo de biblioteca sigue este orden:

1. La variable `NOIZ_CATALOG_PATH`, si está definida.
2. `local_data/catalog.json` existente en el directorio de ejecución.
3. Ese archivo existente en la raíz del checkout al ejecutar desde sus fuentes.
4. La ubicación de datos del usuario: `%LOCALAPPDATA%/NoizTransmission/catalog.json`
   en Windows o `$XDG_DATA_HOME/noiz-transmission/catalog.json` en Linux, con el
   valor predeterminado `~/.local/share` para `XDG_DATA_HOME`.

`local_data/` está excluido de Git. La distribución pública contiene código,
pruebas con datos sintéticos y ejemplos propios; excluye los XML y la biblioteca
comercial importada. Un paquete de trabajo privado para el usuario puede contener
su biblioteca portátil. Los proyectos que incorporan copias de registros también
contienen esos datos: revisar su procedencia antes de publicarlos como ejemplos.

MIT cubre el código y los datos sintéticos propios. No cambia las condiciones de
los datos importados. La importación local permanece utilizable sin publicar los
archivos originales dentro del repositorio.

## Incorporación de propiedades verificadas

Para convertir una entrada en un registro científicamente defendible se requiere:

1. Fabricante, producto, código, región, revisión y fecha de la ficha.
2. Fuente primaria con páginas/tablas identificadas y condiciones de uso.
3. Procedencia por propiedad: unidad original, conversión, método, condiciones,
   rango/tolerancia e incertidumbre disponible.
4. Separación de valores declarados, medidos, estimados y ausentes.
5. Historial de revisiones; los proyectos anteriores conservan sus entradas.

El importador registra la procedencia del archivo, pero no completa automáticamente
esa investigación por propiedad. La guía INSUL advierte además que algunos módulos
de Young cambiaron con los algoritmos v9/v10: un parámetro de una base de predicción
no es necesariamente una propiedad medida transferible sin revisión.

## Material frente a sistema ensayado

Un sistema constructivo exige composición, dimensiones, fijaciones, juntas,
soportes, rellenos y condiciones de borde. Un perfil aporta geometría, y un
montante aporta dimensiones; ninguno define por sí solo la transmisión estructural.
La curva y el índice de una pared ensayada pertenecen al espécimen y montaje,
no a un material aislado. Véanse [validación](validation.md) y
[referencias v2](v2-reference-review.md).
