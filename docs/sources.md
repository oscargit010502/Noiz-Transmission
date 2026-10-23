# Fuentes y estado de consulta

La revisión V6 de los tres libros aportados, con páginas, ecuaciones y distinción
entre fuentes consultadas y artículos pendientes, está en
[revisión V6](v6-reference-review.md) y [evidencia V6](v6-evidence.md).

Registro actualizado: **2026-10-13**. Una fuente consultada se distingue de una
referencia localizada cuya lectura primaria sigue pendiente. No se dispone todavía
de estudios experimentales que cuantifiquen el error del motor Noiz.

## Fuentes consultadas

| Fuente | Contenido examinado y uso |
| --- | --- |
| [INSUL v10 User Guide](https://docs.insul.co.nz/v10/) | Portada, alcance y afirmaciones de precisión del fabricante; no son precisión de Noiz |
| [Tabs](https://docs.insul.co.nz/v10/UsingINSUL/Tabs/) y [Panels](https://docs.insul.co.nz/v10/GettingStarted/Panels/) | Organización por elemento, hojas, capas, cámaras y tipos de excitación |
| [Single Panels](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-SinglePanels-Overview/) | Masa, coincidencia, amortiguamiento, cortante y distinción entre capas ligeramente fijadas y placas monolíticas |
| [Double Panels](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-DoublePanels-Overview/) | Separación entre camino aéreo y puentes estructurales; relleno de cámara |
| [Wave-based Glazing](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Glazing-WaveModel/) | Alcance modal finito, marcos, sellos, gases y límite angular; distingue ese modelo del TMM infinito propio |
| [Porous Facing](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Porous-Facing/) | Unidades de resistividad Rayl/m = Pa·s/m² e hipótesis de esqueleto inmóvil |
| [Materials Editor](https://docs.insul.co.nz/v10/UsingINSUL/MaterialsEditor/) y [Item Details](https://docs.insul.co.nz/v10/UsingINSUL/MaterialsEditor-Details/) | Diferencia entre materiales, geometría de perfiles/montantes y modelos de bastidor |
| [Charts & Tables](https://docs.insul.co.nz/v10/UsingINSUL/ChartsTables/), [Calculation Settings](https://docs.insul.co.nz/v10/UsingINSUL/Settings-Calculation/) y [Ratings](https://docs.insul.co.nz/v10/SoundInsulationTheory/Ratings-Airborne/) | Funciones de resultados, parámetros y descripción divulgativa de clasificación |
| [References](https://docs.insul.co.nz/v10/Resources/References/) | Identificadores bibliográficos y normas; leer una lista no equivale a leer sus artículos |
| *INSUL 10 Brochure.pdf* y capturas aportados por el usuario | Distribución funcional y capacidades anunciadas; no contienen las ecuaciones completas del motor |
| XML aportados por el usuario en V2 y V3 | Seis archivos 9.0/22 (2434 registros) y siete archivos 10.0/8 (3242); unidades, campos y procedencia inspeccionados; no son ensayos verificados |
| [Getting Started — Leaks](https://docs.insul.co.nz/v10/GettingStarted/Leaks/) y [Theory — Leaks](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Leaks/) | Controles Slit/Aperture y propiedades de Gomperts/Mechel; referencias identificadas, ecuaciones completas no publicadas |
| [Floors](https://docs.insul.co.nz/v10/GettingStarted/Floors/) y [Impact — Floor Covers](https://docs.insul.co.nz/v10/SoundInsulationTheory/Impact-FloorCovers/) | Measured/Predicted, bases de suelo, significado de ΔL y relación de rigidez dinámica E=s′t |
| [Roofs](https://docs.insul.co.nz/v10/GettingStarted/Roofs/) y [Rain Noise](https://docs.insul.co.nz/v10/SoundInsulationTheory/Rain-Noise/) | Single/Double, lluvia natural/laboratorio, área y tipo de salida; no contienen el modelo completo reproducible |
| [Porous Material](https://docs.insul.co.nz/v10/GettingStarted/PorousMaterial/) | Facing de Single y lámina porosa independiente; controles de espesor y resistividad |
| [Phonometry 3.3.0](https://pypi.org/project/phonometry/3.3.0/) y [metadatos](https://pypi.org/pypi/phonometry/3.3.0/json) | Rueda, licencia, `building/insulation.py` y `materials/porous_absorber.py`; contraste de Rw y Miki |
| [Acoustipy, DBM Model](https://github.com/jakep72/acoustipy/blob/main/docs/Theory/DBM_Model.md) | Correlación Miki, unidades e intervalo del ajuste; coeficiente real 0.0699 frente a 0.070 de Phonometry |
| [Python Acoustics, reflection.py](https://github.com/python-acoustics/python-acoustics/blob/master/acoustics/reflection.py) | Consulta secundaria de impedancia Delany–Bazley; no es el modelo Miki finalmente seleccionado |
| [PySide6 Essentials 6.10.3](https://pypi.org/pypi/PySide6-Essentials/6.10.3/json) y [PyQtGraph 0.14.0](https://pypi.org/pypi/pyqtgraph/0.14.0/json) | Metadatos de versión/licencia y selección de bibliotecas; revisión completa de distribución pendiente |
| [LICENSE](../LICENSE) | MIT del proyecto, copyright original preservado |

La consulta de guía, folleto y fuentes secundarias se desarrolla en
[V2](v2-reference-review.md) y [V3](v3-reference-review.md). V3 incluye inspección
de las imágenes públicas de propiedades de fugas para confirmar unidades y estados
de controles. No se redistribuyen los archivos
originales comerciales como parte del repositorio público.

La rueda de Phonometry 3.3.0 inspeccionada tiene SHA-256:

```text
611276eb89f114984263069bf2c8b67ac212678f57f33735d4e352dab987d517
```

La versión se fija para poder repetir el contraste. Noiz usa sus propias funciones;
la coincidencia con otra implementación no valida físicamente el espécimen ni
certifica cumplimiento normativo. Su [repositorio](https://github.com/jmrplens/phonometry)
está identificado en los metadatos, pero el contraste aquí corresponde a la rueda
3.3.0, no a una rama principal cambiante.

## Bibliografía localizada, sin lectura primaria completa

Se identificaron en la lista de referencias INSUL, entre otras:

- Sharp, B. H. (1978), *Prediction Methods for the Sound Transmission of Building
  Elements*, Noise Control Engineering 11(2), 53–63,
  [doi:10.3397/1.2832099](https://doi.org/10.3397/1.2832099).
- Cremer, L., Heckl, M. y Petersson, B. A. T. (2005), *Structure-borne Sound*, Springer.
- Vigran, T. E. (2008), *Building Acoustics*, Taylor & Francis.
- Ballagh, K. O. (2004), *Accuracy of prediction methods for sound transmission loss*,
  INTER-NOISE, 3095–3102.
- Emms, G., Chung, H. y Ballagh, K. (2021), *Predicting the sound transmission loss
  of finite-sized glazing*, ASNZ, y Emms/Chung (2022), *Accuracy of a prediction
  method for sound transmission loss of glazing*, ASNZ.
- Quirt, J. D. (1983), *Sound transmission through windows II. Double and triple
  glazing*, JASA 74(2), 534–542,
  [doi:10.1121/1.389819](https://doi.org/10.1121/1.389819).

Las referencias específicas localizadas para V3 también están pendientes de
lectura primaria completa:

- Gomperts (1964), *The “sound insulation” of circular and slit-shaped apertures*,
  Acustica 14(1), 1–16; Gomperts y Kihlman (1967), *The sound transmission loss of
  circular and slit-shaped apertures in walls*, Acustica 18(3), 144–150.
- Mechel (1986), *The acoustic sealing of holes and slits in walls*, Journal of
  Sound and Vibration 111(2), 297–336.
- Vér (1971), *Impact Noise Isolation of Composite Floors*, JASA 50(4A), 1043–1050.
- Petersson (1995), *The liquid drop impact as a source of sound and vibration*,
  Building Acoustics 2(4), 585–621.
- Marshall y Palmer (1948), *The Distribution Of Raindrops With Size*, Journal of
  Meteorology 5(4), 165–166.
- Griffin y Ballagh (2012), *A consolidated theory for predicting rain noise*,
  Building Acoustics 19(4), 221–248.

Phonometry identifica además Miki, Y. (1990), *Acoustical properties of porous
materials — Modifications of Delany-Bazley models*, Journal of the Acoustical
Society of Japan (E) 11(1), 19–24, ecuaciones 30–34. El artículo primario no se
consultó en esta sesión; las ecuaciones utilizadas se revisaron en dos fuentes
secundarias y se contrastan algorítmicamente.

Fahy y Gardonio, *Sound and Structural Vibration: Radiation, Transmission and
Response*, continúa como lectura técnica propuesta. Al consultar las obras se
completarán páginas, edición y correspondencia entre ecuaciones e implementación.

## Normas pendientes de revisión primaria

Estos identificadores orientan el trabajo; verificar edición aplicable y disponer
del texto completo antes de declarar conformidad.

| Referencia | Uso y estado |
| --- | --- |
| ISO 717-1:2020 | Clasificación aérea; revisión primaria pendiente, Rw provisional |
| ISO 10140-2:2021 y partes pertinentes | Datos y montaje de ensayo aéreo; necesarias para evidencia experimental |
| ISO 717-2 | Clasificación de impacto; fuera del cálculo actual |
| ASTM E413 y ASTM E90 | STC y ensayo asociado; fuera del cálculo actual |
| ISO 12354-1 y partes pertinentes | Aislamiento entre recintos y caminos laterales; ampliación futura |

Las descripciones y ediciones citadas en una guía comercial no sustituyen la norma.
No se copian textos normativos al repositorio.

## Historial de acceso

Durante V1, el proxy bloqueó las dos direcciones INSUL aportadas. En las sesiones
V2/V3, con el dominio configurado, se abrieron correctamente por HTTPS; el bloqueo
anterior queda como antecedente y ya no impide la revisión funcional.

El catálogo web ISO y la guía oficial de licencias Qt no pudieron consultarse en
la sesión inicial. Las revisiones V2/V3 no acreditan una lectura nueva de esos textos.
La revisión de licencias de las bibliotecas que se empaqueten sigue pendiente antes
de publicar un instalador, independientemente del funcionamiento del código fuente.
