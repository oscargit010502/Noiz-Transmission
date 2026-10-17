# Geometría y procedencia del catálogo V5

La vista del elemento debe distinguir entre **dimensiones declaradas en el XML**,
**geometría comprobada con un plano** y **representación esquemática**. Un nombre
comercial permite identificar un producto, pero no define sus labios, pliegues,
perforaciones, tornillos, clips o piezas elásticas. La selección del producto no
convierte una representación esquemática en un objeto BIM validado.

## Auditoría de los archivos recibidos

Inspección realizada el **16 de octubre de 2026** sobre los ocho archivos
facilitados para V5. Se contabilizaron **3.629 registros XML**:

| Archivo | Versión / release declarados | Registros |
| --- | --- | ---: |
| Insul Materials.xml | 10.0 / 8 | 1.575 |
| Insul Absorption.xml | 10.0 / 8 | 523 |
| Insul Connections.xml | 10.0 / 8 | 387 |
| Insul Flooring.xml | 10.0 / 8 | 669 |
| Insul Glazing.xml | 10.0 / 7 | 80 |
| Insul Profile.xml | 10.0 / 7 | 281 |
| Insul Studs.xml | 10.0 / 7 | 69 |
| Insul Cores.xml | 10.0 / 7 | 45 |

Hay **238 valores distintos del campo Manufacturer**, incluido el valor vacío
y las etiquetas genéricas; no son necesariamente 238 fabricantes diferentes.
Los archivos contienen identificadores GUID, nombres comerciales y propiedades,
pero **ninguna URL legible de fabricante, plano, ficha técnica u objeto BIM**.
La URL `http://www.insul.co.nz` que aparece en la cabecera es el espacio de
nombres XML, no un enlace de documentación del producto. Tampoco se recibieron
archivos CAD/BIM ni campos con coordenadas de una malla.

Algunos campos `Remarks/Open` y `Remarks/Technical` contienen cadenas opacas.
Se conservan como datos de procedencia; no se interpretan como planos ni se
afirma conocer su contenido. Dos nombres de revestimiento terminan en `.pdf`,
pero no contienen una dirección desde la que descargar ese documento.
`Source=Measured` y `Lab=True` en los 669 revestimientos son declaraciones del
catálogo, no informes de laboratorio adjuntos o comprobados por Noiz.

El XML de absorción contiene un carácter de control U+0001 dentro de un nombre.
La reparación limitada de importación sustituye ese carácter por «�» al mostrar
el nombre, conserva el texto original en los campos de procedencia y mantiene
la huella del archivo original; no modifica propiedades numéricas. Los archivos
originales y el catálogo comercial permanecen separados del código público y de
sus ejemplos sintéticos. El catálogo del usuario pertenece al paquete personal.

## Dimensiones que sí aportan los XML

Los valores dimensionales siguientes están expresados en **metros** en estos
archivos. La interfaz los presenta en milímetros. La inspección comparó campos
de registros con el mismo GUID en los catálogos anteriores: las variantes
10.0/7 y 10.0/8 no justifican un cambio automático de unidades.

| Familia y campos | Información utilizable | Información que no aportan |
| --- | --- | --- |
| Stud: `Properties/StudDepth`, `StudWidth`, `StudSpacing`, `MaterialThickness` | Profundidad, anchura, separación y espesor declarados | Contorno C/U/CH, labios, radios de plegado o perforaciones |
| Connection: `Properties/StudDepth`, `StudWidth`, `CavityWidth`, `definedStudSpacing`, `braceSpacing` | Dimensiones globales del conjunto y separaciones declaradas | Geometría detallada del clip, canal o aislador; una cavidad mayor que el montante no define la forma de la pieza intermedia |
| Profile: `Profile/RibL`, `RibH`, `RibW`, `RibV` | Paso, altura y anchuras de cresta/valle para el perfil periódico admitido | Espesor y masa de la chapa; deben proceder del material |
| Material/Glazing: `SideA/Thickness`, `Core/Thickness`, `SideB/Thickness` | Espesores declarados para las partes que correspondan al tipo del material | Activación automática de todos los campos: algunos tipos contienen valores auxiliares que no describen una capa física activa |

Los 69 registros Stud tienen el campo `Type` vacío: 48 son `MetalFrame` y 21
son `TimberFrame`. La categoría metálica no basta para distinguir una C de una
U. El perfil metálico abierto empleado como representación genérica debe seguir
identificado como esquemático cuando no exista un plano contrastado.

El archivo de perfiles contiene 232 registros `Trapezoidal`, 27 `Corrugated`,
13 `CompositeSteelFloor` y 9 `Isotropic`. Un perfil de suelo compuesto requiere
su propia interpretación: no debe tratarse como una chapa trapezoidal validada
solo por tener cuatro campos `Rib`.

### Comprobaciones que impiden inventar dimensiones

- Tres registros metálicos Stud tienen `MaterialThickness` igual a 47 o 75 mm,
  incompatible con su anchura de 36 mm para un perfil abierto de chapa. No se
  corrigen suponiendo dónde debería ir el separador decimal.
- Veintiséis registros metálicos Connection tienen un espesor declarado mayor
  o igual que la mitad de la menor dimensión transversal. Ese valor no permite
  construir la sección de chapa. Las cotas globales pueden seguir mostrándose,
  con la geometría local identificada como no verificada.
- Cuatro registros trapezoidales declaran paso de 203 mm, cresta de 16 mm y valle
  de 189 mm: las dos anchuras suman 205 mm. El modelo periódico de flancos rectos
  no puede generarse con esas cotas sin alterar datos; debe indicarse el problema.
- Los códigos numéricos `Properties/Connection` identifican variantes del
  catálogo. No contienen coordenadas CAD ni una descripción de sus piezas.
  Tampoco autorizan trasladar coeficientes acústicos propietarios al motor.

Por ejemplo, el registro **Kinetics IsoMax Sound Isolation Clip on Steel stud**
declara montante de 90 × 38 mm y cavidad de 125 mm. Esto permite identificar una
separación adicional de 35 mm, pero no reconstruir el clip IsoMax. Su campo
`MaterialThickness=0.045` no debe convertirse en una chapa metálica de 45 mm.
Las dimensiones modificadas por el usuario en una captura de pantalla tampoco
son automáticamente las dimensiones originales del fabricante.

## Fuentes públicas consultadas

Se consultaron estas páginas de la guía pública de INSUL para comprobar el
significado del editor y diferenciar tipos de elementos:

- [Materials Editor — Item Details](https://docs.insul.co.nz/v10/UsingINSUL/MaterialsEditor-Details/):
  distingue perfiles geométricos de materiales y aclara que un perfil no incluye
  la masa ni el espesor del panel.
- [Diagrama de parámetros del perfil](https://docs.insul.co.nz/v10/images/MaterialsEditorProfile.png):
  muestra por separado paso, altura y anchuras de cresta y valle. Se usa como
  referencia de significado; la imagen no se incorpora a la aplicación.
- [Materials Editor — Editing Examples](https://docs.insul.co.nz/v10/UsingINSUL/MaterialsEditor-Editing/):
  describe la asignación de un perfil a un material.
- [Airborne — Metal Frames](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-DoublePanels-MetalFrames/):
  diferencia montantes corrientes, CH, acústicos y correas Z. Publica espesores
  base usuales, pero no sustituye los planos específicos de cada fabricante.

Las siguientes direcciones se identificaron a partir de los nombres de
fabricante, **no de enlaces contenidos en los XML**:

| Fabricante / referencia a consultar | Dirección intentada | Resultado en esta sesión |
| --- | --- | --- |
| Kinetics / IsoMax | <https://kineticsnoise.com/isomax> | Conexión HTTPS rechazada por la política de red del entorno |
| HushFrame | <https://www.hushframe.com/> | Conexión HTTPS rechazada por la política de red del entorno |
| AMC Mecanocaucho | <https://www.mecanocaucho.com/en/> | Conexión HTTPS rechazada por la política de red del entorno |
| CDM Stravitec | <https://cdm-stravitec.com/> | Conexión HTTPS rechazada por la política de red del entorno |

No se inspeccionó el contenido de esos sitios ni se verificó la existencia de
un plano en las rutas intentadas. El resultado de esta revisión es, por tanto,
**cero planos de fabricante y cero objetos BIM comprobados**. Las mejoras de
renderizado deben conservar esta limitación de procedencia; no se presenta una
geometría comercial exacta apoyándose en esas direcciones.

Para validar posteriormente una pieza hacen falta un documento accesible y su
revisión, unidades, cotas y correspondencia con la variante seleccionada. El
registro de evidencia debe separar los datos medidos en ese documento de las
dimensiones editadas por el usuario. La geometría visual comprobada tampoco
valida por sí sola el cálculo acústico del sistema.
