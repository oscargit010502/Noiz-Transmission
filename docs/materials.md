# Catálogo internacional y procedencia

El catálogo objetivo es **internacional**. El proyecto público distribuye tres
materiales sintéticos para reproducir ejemplos. La versión 3 permite importar
bibliotecas XML del usuario y consultarlas por familia, texto, categoría,
fabricante y región, conservando su procedencia. Importar no significa validar
científicamente las propiedades ni atribuirles la licencia del código.

## Catálogos recibidos y compatibilidad

Los siete XML de V3 declaran `Version="10.0"`, `Release="8"`:

| Familia | Registros V3 |
| --- | ---: |
| Materiales | 1575 |
| Perfiles | 281 |
| Vidrios | 80 |
| Revestimientos de suelo | 669 |
| Absorbentes | 523 |
| Núcleos | 45 |
| Montantes | 69 |
| **Total** | **3242** |

**1180 registros** cumplen el filtro de entrada de placa isótropa: 1158 materiales
más 22 vidrios. Elegibilidad significa que se interpretan propiedades y rangos;
no acredita un ensayo ni que una placa infinita represente todo ese producto.

El catálogo V2, de versión 9.0/22, contenía 2434 registros en seis familias,
718 elegibles para placa y 187 filas sin nombre. Continúa siendo importable.
Los registros nuevos no sustituyen automáticamente los anteriores: importar el
mismo archivo es idempotente, pero un archivo modificado tiene otra procedencia.
Para evitar mezclar revisiones basta elegir una biblioteca local diferente.

Los montantes nuevos aportan ancho, profundidad, separación y espesor de material;
no aportan rigidez dinámica ni algoritmo de conexión acústica. Las categorías
MetalFrame/TimberFrame sirven para organizar y representar la selección.

## Propiedades, unidades y datos originales

El importador conserva nombre de archivo, SHA-256, identificador original,
posición del registro, versión del documento, campos originales y observaciones.
Los identificadores derivados del contenido y la posición permiten repetir una
importación sin duplicar las mismas filas y mantener filas distintas de igual
nombre. La persistencia local emplea JSON estricto y escritura atómica.

En las estructuras inspeccionadas 9.0/22 y 10.0/8, espesor se expresa en metros, densidad en
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

Los XML V2 incluían valores `Measurement/Source = XXX` y curvas constantes de
relleno. En los XML V3, Material y Glazing no incluyen espectros de ensayo. Los
669 Floor Cover sí contienen curvas `IsolationGain` (ΔL) en 28 bandas entre 20 y
10000 Hz: 616 para base pesada, 40 ligera y 13 CLT. `catalog_spectrum` conserva
magnitud, bandas, tipo de base y observaciones. Ni `Measured` ni `Lab=True`
identifican por sí solos laboratorio, montaje, incertidumbre o informe.

La interfaz filtra los Floor Cover por base y separa su ΔL declarado del TL aéreo.
Una medición para una base no se aplica automáticamente a otra; una curva ausente,
incompatible o de modo Predicted no se transforma en un resultado inventado.

Un nombre de Absorption 10.0/8 contiene un control `U+0001` ilegal en XML 1.0.
El importador repara únicamente su presentación, conserva el hash de los bytes
de origen y los campos originales y registra la observación. Los controles
ilegales en campos físicos se rechazan, igual que DTD/entidades y documentos que
exceden límites de tamaño o complejidad. No se modifica silenciosamente un número.

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
[referencias V3](v3-reference-review.md).
