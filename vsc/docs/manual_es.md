# Guía del usuario de VideoSpeedControl

VideoSpeedControl te da control total sobre la velocidad de un clip de vídeo. Divide en secciones un clip grabado en cámara lenta nativa – por ejemplo, una GoPro a 240 fps o la grabación en cámara lenta de un teléfono – y da a cada sección su propia frecuencia de fotogramas: acelera el principio, sigue con una cámara lenta extrema, pasa a tiempo real y termina de nuevo en cámara lenta.

- **Sin pérdida** no necesita recodificar nada: se conservan todos los fotogramas originales y solo cambia su tiempo de reproducción, de modo que la app crea un clip de frecuencia de fotogramas variable en un instante y sin ninguna pérdida de calidad.
- **Recodificación Smart** recodifica solo las secciones cuya frecuencia de fotogramas difiere de la de salida, con el mismo códec que el original, lo que mantiene rápida la exportación.
- **Recodificar** codifica el clip completo con el códec que elijas, con el mismo control total sobre la velocidad y la frecuencia de fotogramas de salida.

La app guarda las ediciones de velocidad de cada clip, así que puedes retomar tu trabajo más tarde – o codificar el mismo clip con distintos códecs para compararlos, con la ayuda de nombres de archivo generados automáticamente con opciones de nomenclatura. También puedes reunir muchos clips – o varias versiones del mismo clip – en una lista de lotes y exportarlos todos de una vez.

**Contenido**

1. Inicio rápido
2. La ventana principal
3. Cargar clips e información del clip
4. Vista previa y recorte
5. Ajustes de salida
6. Secciones de velocidad
7. Recodificación Smart
8. Codificación de prueba y estimaciones de tiempo
9. Exportación y lista de lotes
10. Convertir vídeos
11. AV2 (experimental)
12. Atajos de teclado
13. Consejos y solución de problemas
14. Licencia y créditos

## 1. Inicio rápido

1. Inicia VideoSpeedControl y arrastra uno o más archivos de vídeo a la ventana (o haz clic en **Añadir archivos…**).
2. Elige el modo de **Procesamiento** en los *Ajustes de salida*, a la derecha. **Sin pérdida** es el predeterminado y el más rápido.
3. Elige unos **Fotogramas por segundo** de salida. La lista desplegable muestra cuánto más lento (o más rápido) se reproduce el clip y cuánto durará, p. ej. *"25 fps (PAL) – 9,6× más lento, 1:12 min"*.
4. Pulsa **Espacio** en la pestaña *Vista previa y recorte* para ver el resultado.
5. Abre la pestaña **Exportar**, elige una carpeta y haz clic en **Iniciar exportación**.

![La ventana principal](images/overview.png)

### Cómo funciona aquí la cámara lenta

Una cámara de 240 fps graba 240 imágenes por segundo. Reproducidas a 240 fps, es tiempo real. Reproducidas a 25 fps, esas mismas 240 imágenes duran 9,6 segundos: el clip es **9,6× más lento** – sin una sola imagen nueva ni que falte ninguna. Esto es lo que hace *Sin pérdida*. Solo cuando quieres una velocidad que no encaja con la frecuencia de fotogramas (p. ej. 20× más lento a 25 fps) hay que omitir o calcular imágenes, lo que implica recodificar.

## 2. La ventana principal

- **Lista de clips (arriba):** cada archivo cargado con su dispositivo, códec, resolución, frecuencia de fotogramas, duración, la salida elegida y una estimación del tiempo de exportación y del tamaño.
- **Pestañas (abajo a la izquierda):** *Vista previa y recorte*, *Codificación de prueba*, *Info del clip*, *Exportar*.
- **Ajustes de salida (abajo a la derecha):** todo lo relativo a la salida del clip seleccionado, con un resumen al final.
- **Ayuda** (extremo derecho de la barra de herramientas): esta guía (**F1**), la guía en PDF y *Acerca de*.

Cada clip tiene sus propios ajustes. **Aplicar a todos los clips** copia los ajustes de salida del clip seleccionado a todos los demás (los recortes y las secciones de velocidad se mantienen por clip).

## 3. Cargar clips e información del clip

Arrastra archivos o carpetas a la ventana, o usa **Añadir archivos…**. Funciona cualquier formato que FFmpeg pueda leer. Tras la carga, la app analiza el clip (tiempos exactos de los fotogramas y keyframes) y crea en segundo plano una pequeña copia de vista previa (*"vista previa rápida 45 %"*, junto al número de fotograma).

La pestaña **Info del clip** enumera todo sobre el archivo: contenedor, códec y perfil, resolución y relación de aspecto, rotación, frecuencia de fotogramas, número de fotogramas, intervalo de keyframes, formato de píxel, submuestreo de croma, profundidad de bits, espacio de color (SDR / HLG / PQ), tasa de bits, dispositivo y fecha de grabación, y audio.

![Info del clip](images/clip_info.png)

### Cámara lenta del teléfono

Teléfonos como el Google Pixel graban cámara lenta a, por ejemplo, 240 fps, pero la guardan como un archivo de 30 fps que ya se reproduce despacio. VideoSpeedControl lee la frecuencia de grabación del archivo y trata **240 fps como el original**: las velocidades y los "× más lento" se refieren siempre al tiempo real. La lista de clips muestra, p. ej., *"240 (cámara lenta, archivo 29.97)"*.

### Vistas previas guardadas

La lista de fotogramas, las miniaturas de la línea de tiempo, la pequeña copia de vista previa usada para desplazarse por el vídeo y el análisis de keyframes de la recodificación Smart se guardan en la carpeta de caché (Linux *~/.cache/VideoSpeedControl/previews*, Windows *%LOCALAPPDATA%\VideoSpeedControl\previews*). Un clip abierto de nuevo está listo casi al instante, en lugar de analizarse y decodificarse otra vez – también después de renombrarlo o moverlo, porque se reconoce por su contenido. La vista previa se guarda en partes pequeñas; si una está dañada, solo se rehace esa parte.

Dos minutos después del inicio – y solo mientras no se esté ejecutando nada pesado – se borran las vistas previas que ya no hacen falta: una vista previa se conserva mientras su clip esté en la lista, en la lista de lotes o tenga un archivo Clip Speed Treatment (.cst). La caché se mantiene por debajo de 2 GB.

## 4. Vista previa y recorte

![Vista previa, secciones de velocidad y el resumen](images/sections.png)

### Desplazarse por el clip

- Haz clic o arrastra en la **línea de tiempo** (miniaturas con marcas de keyframe debajo), usa el cuadro del **número de fotograma**, o los botones y teclas: **◀ 1 / 1 ▶** (**←/→**) un fotograma, **− 🔑 / + 🔑** (**Shift+←/→**) keyframe anterior / siguiente, **⏮ / ⏭** (**Inicio/Fin**) primer / último fotograma, la rueda del ratón.
- Mientras arrastras, la imagen viene de la pequeña copia de vista previa – al instante. Cuando el cursor se detiene un momento, el fotograma nítido a tamaño completo la sustituye.
- **Ajustar / 100 % / 200 %** amplía la imagen; arrastra para desplazarla, doble clic para alternar.

### Reproducir la vista previa

**▶ Reproducir vista previa** (o **Espacio**) reproduce la salida con la frecuencia de fotogramas y la velocidad elegidas – a tamaño reducido y sin codificar, así que empieza al instante. Se reproduce desde el cursor hasta el punto de salida. La interpolación de movimiento y RIFE se muestran como una simple mezcla (son demasiado lentas para tiempo real). Si el ordenador no puede decodificar lo bastante rápido (p. ej. 240 fps en tiempo real), un aviso indica que la vista previa se reproduce más lenta de lo que lo hará la exportación.

### Recorte (entrada / salida)

**Marcar entrada (I)** y **Marcar salida (O)** marcan el primer y el último fotograma de la salida; **Borrar recorte** los quita. Las partes atenuadas de la línea de tiempo no se exportan.

En los modos **Sin pérdida** y **Recodificación Smart**, los puntos de entrada y salida **se ajustan a keyframes**. Un aviso amarillo explica por qué: solo los keyframes son imágenes completas; los demás fotogramas guardan solo las diferencias con sus vecinos y no se pueden mostrar una vez cortado el keyframe que los precede. Elige *Recodificar* para cortes exactos al fotograma.

## 5. Ajustes de salida

### Procesamiento

| Modo | Qué ocurre | Qué puedes cambiar |
|---|---|---|
| **Sin pérdida** | Cada fotograma queda intacto; solo cambia su tiempo de reproducción. Segundos en lugar de minutos, sin pérdida de calidad. | Frecuencia de fotogramas, contenedor, secciones de velocidad, recorte (en keyframes) |
| **Recodificación Smart** | Copia el clip y recodifica solo las secciones que marques – véase el capítulo 7. | Secciones de velocidad con sus propios fotogramas por segundo de salida, calidad y preajuste de las partes recodificadas, contenedor |
| **Recodificar** | Todo el clip se codifica de nuevo. | Todo: códec, tamaño, velocidad, frecuencia de fotogramas, interpolación |

Solo están activados los ajustes que el modo elegido puede usar.

**Easy / Pro** (arriba de los ajustes de salida): *Easy* oculta los detalles del códec – el propio códec, perfil, preajuste, calidad, croma y profundidad de bits. La recodificación Smart usa entonces siempre el códec original y Recodificar siempre **AV1 (rápido)**, cada uno con su preajuste y calidad predeterminados. En Easy, además, todo cambio de velocidad entre secciones se **suaviza** automáticamente (0,5 s, véase el capítulo 6) – los interruptores *Entrada suave / Salida suave* solo aparecen en Pro. *Pro* muestra todos los ajustes (las imágenes de esta guía muestran Pro). Al cambiar a Easy se aplican los ajustes de Easy a todos los clips.

- Al elegir **Recodificación Smart** se marca para recodificar toda sección de velocidad cuya frecuencia de fotogramas difiera de sus fotogramas por segundo de salida; las secciones que ya se reproducen a esa frecuencia se siguen copiando (puedes cambiar las marcas en la tabla).
- Al pasar de Smart a **Recodificar** se vuelve a seleccionar AV1 (rápido).

![Ajustes de salida en modo Recodificar](images/settings_reencode.png)

### Frecuencia de fotogramas y velocidad

- **Fotogramas por segundo:** las frecuencias estándar (23,976 … 120 fps) más la propia del clip, marcada como *(original)*. Cada entrada muestra la ralentización y la duración de salida cuando se conservan todos los fotogramas.
- **Velocidad** (Recodificar): *Sin pérdida* usa cada fotograma una vez. *Personalizado…* fija cualquier velocidad (p. ej. 0,05× = 20× más lento) – una velocidad mayor que la velocidad sin pérdida omite fotogramas, una menor calcula fotogramas intermedios (véase *Interpolación*). *Preajustes…* ofrece valores habituales.
- La línea de debajo muestra la **duración de salida** y cuánto más lenta o más rápida es que la original.

### Códec y contenedor

La lista de códecs está agrupada en **Sin pérdida** (FFV1, Ut Video, MagicYUV, HuffYUV, H.264 / HEVC / VP9 / AV1 / AV2 sin pérdida, QuickTime Animation, secuencias de imágenes), **Con pérdida** (H.264, HEVC, AV1, VP9, ProRes, DNxHR, CineForm, MJPEG, AV2) y **Hardware** (NVIDIA, Intel, AMD – solo se ofrecen si una codificación de prueba en tu ordenador funcionó). Cada entrada tiene una descripción emergente que explica para qué sirve. La lista de **contenedores** solo ofrece formatos que pueden contener el códec elegido. Al cambiar a *Recodificar*, se preselecciona **AV1 (SVT-AV1, rápido)** – archivos pequeños con buena calidad; *AV1 (libaom, máxima calidad)* comprime un poco mejor, pero es mucho más lento.

### Preajuste

Cuánto tiempo busca el codificador la mejor compresión. Con el mismo ajuste de calidad, un preajuste más lento da un **archivo más pequeño** y tarda **más**; la calidad visible apenas cambia. Cada entrada dice lo que hace, p. ej. *"veryslow – el más lento, archivo más pequeño"*. (Para CineForm la fila se llama *Compresión* – ahí es un nivel de calidad.)

### Calidad

Niveles con nombre que significan más o menos lo mismo para todos los códecs; el número propio del códec se muestra entre paréntesis:

| Nivel | Significado |
|---|---|
| Visualmente sin pérdida | Sin diferencia visible ni siquiera en un fotograma fijo. Archivos grandes. |
| Alta (predeterminada) | Casi sin pérdida visible – buena para seguir editando y para archivar. |
| Buena | Calidad de streaming (YouTube, Netflix): suficiente para ver. |
| Media | Pérdidas visibles al mirar de cerca, p. ej. en detalles finos o zonas oscuras. |
| Archivo pequeño | Pérdidas claramente visibles – para vistas previas o para enviar rápido. |

**Personalizado…** te permite introducir el valor propio del códec. Bajar un nivel hace el archivo aproximadamente un 30–50 % más pequeño.

### Croma y profundidad de bits

- **Submuestreo de croma:** 4:4:4 (detalle de color completo – VFX, gama alta), 4:2:2 (televisión profesional), 4:2:0 (streaming, Netflix, YouTube). Solo se ofrecen las combinaciones que admite el códec.
- **Profundidad de bits:** 8 bits o 10 bits. *Como el original* conserva lo que tiene el clip.

### Resolución, aspecto y escalado

- **Resolución:** mantén el tamaño original, preajustes desde 480p hasta DCI 4K (incluidos 9:16 y 1:1) o personalizada.
- **Aspecto:** mantén las proporciones originales (ajustar dentro del encuadre) o fuerza un tamaño de encuadre / relación de aspecto; **Ajuste** decide entre barras negras (relleno), recorte (cortar) o estiramiento.
- **Escalado:** el método de remuestreo con valoraciones de calidad y velocidad – Lanczos es el más nítido, Area el más limpio para reducciones fuertes.

### Interpolación

Se usa cuando la velocidad es más lenta que la velocidad sin pérdida y se necesitan nuevas imágenes intermedias:

- **Duplicación de fotogramas** – repite imágenes; el movimiento se entrecorta. Lo más rápido.
- **Mezcla de fotogramas** – fundido cruzado entre vecinos; suave, pero con fantasmas.
- **Interpolación de movimiento (FFmpeg minterpolate)** – calcula imágenes intermedias reales en la CPU; buena para movimientos lentos y uniformes. Muy lenta.
- **Interpolación con IA (RIFE)** – red neuronal en la tarjeta gráfica (Vulkan, también gráficos integrados); un movimiento claramente mejor. Funciona en RGB de 8 bits. No disponible junto con secciones de velocidad ni con AV2.

### Sonido

El botón **Sonido**, justo debajo de *Procesamiento*, activa o desactiva el sonido con un clic: **🔊 Sonido activado – tono conservado** (predeterminado) o **🔇 Sonido desactivado**. Con el sonido activado, la app toma la primera pista de audio del clip y la estira o comprime a la nueva duración del vídeo – el **tono se mantiene igual**, así que no hay voces graves ni chillonas. Cada sección de velocidad recibe su propio factor de estiramiento, de modo que el sonido sigue a cada sección. Una cámara lenta muy fuerte hace difícil entender el habla (simplemente va 10× más lenta), pero conserva su tono.

**Cámara lenta del teléfono:** los teléfonos guardan el sonido de un clip en cámara lenta ralentizado como una cinta – suena grave. VideoSpeedControl primero lo devuelve a su tono real y a su duración en tiempo real, y luego lo estira al vídeo.

El sonido se añade después de terminar el vídeo, así que un vídeo **sin pérdida** sigue siendo sin pérdida; solo se codifica la pista de audio (AAC en MP4 / MOV / MKV, Opus en WebM, PCM en AVI / MXF). Las secuencias de imágenes y los archivos AV2 (FFmpeg aún no admite AV2) se quedan sin sonido – el botón aparece entonces en gris, y su descripción emergente explica por qué.

## 6. Secciones de velocidad

Las secciones de velocidad dan a partes de un clip su propia frecuencia de fotogramas – por ejemplo, el salto en cámara lenta, la carrerilla en tiempo real, el aterrizaje 8× más rápido.

1. Mueve el cursor al primer fotograma y haz clic en **Inicio de sección [** (tecla **[**).
2. Ve al último fotograma y haz clic en **Fin de sección ]** (tecla **]**). Un marco discontinuo señala el rango.
3. Elige la frecuencia de fotogramas (desde 23,976 fps hasta **8× más rápido** que el original) y haz clic en **Añadir sección**.

**Más rápido:** omite el paso 1. Sin un inicio marcado, **Fin de sección ]** empieza la sección justo después de la sección anterior – o al inicio del clip (recorte) si no hay ninguna – de modo que las secciones se suceden sin huecos. Dentro de una sección existente empieza en el inicio de esa sección (la sección se divide).

Las secciones aparecen como bandas azules en la línea de tiempo y en la tabla de debajo, donde puedes cambiar su frecuencia de fotogramas, saltar a ellas (clic) o quitarlas (✕). Todo lo que queda fuera de las secciones se reproduce en **tiempo real**. Una sección nueva que se solape con una existente prevalece.

- **Editar una sección:** haz clic en ella en la línea de tiempo o en la tabla para seleccionarla. **Inicio = cabezal** / **Fin = cabezal** mueven su primer / último fotograma al cursor; la frecuencia de fotogramas se cambia en la tabla.
- **Mover un límite:** los límites entre secciones (y entre una sección y el tiempo real) son líneas blancas con un asa bajo las miniaturas. Arrastra un límite para alargar una sección y acortar la vecina; la imagen muestra el fotograma del límite mientras arrastras. Un arrastre es un paso de deshacer.
- **Transiciones suaves:** marca **Entrada suave** / **Salida suave** en la tabla para que la velocidad cambie de forma gradual en lugar de saltar – p. ej. de cámara lenta 9,6× a tiempo real. El cambio dura **0,5 s** de la salida y está centrado en el límite (más corto si una sección es demasiado corta); la línea de tiempo lo muestra como un campo oscuro con una línea inclinada (ascendente = cada vez más rápido). Funciona en todos los modos de procesamiento; en la recodificación Smart la transición se recodifica cuando lo hace una sección contigua.

- **Cursor magnético 🧲:** cuando arrastras cerca de una sección, el cursor se ajusta al fotograma justo después de ella (para continuar sin cortes) o – mientras marcas un final – al fotograma justo antes de la siguiente sección. Haz clic en 🧲 para desactivarlo.
- **Borrar secciones** (a la derecha) quita todas las secciones tras pedir confirmación.
- **↶ Deshacer** (**Ctrl+Z**) y **↷ Rehacer** (**Ctrl+Shift+Z** o **Ctrl+Y**) retroceden y avanzan por cada cambio en las secciones – añadir, modificar, mover, quitar, borrar, cargar – hasta 200 pasos, por separado para cada clip. El número del botón indica cuántos pasos puedes retroceder (o avanzar); pasa el ratón por encima para ver qué cambio deshace.

### Guardar y cargar un Clip Speed Treatment (.cst)

**Guardar Clip Speed Treatment…** en la barra de herramientas (**Ctrl+S**) guarda las secciones, el recorte y los ajustes de salida del clip actual como un archivo *Clip Speed Treatment* (`.cst`). Por defecto se ofrece en *Documentos/VideoSpeedControl/Clip Speed Treatments* – la app de Android también guarda ahí. **Cargar Clip Speed Treatment…** (**Ctrl+L**) – o soltar un `.cst` sobre la ventana – lo carga de nuevo. La app de Android lee y escribe los mismos archivos.

Un Clip Speed Treatment pertenece exactamente a un vídeo: guarda una huella del contenido del archivo y solo se carga en ese vídeo. El nombre del archivo no importa – una copia renombrada o movida sigue coincidiendo. Si el vídeo aún no está en la lista pero sigue donde estaba cuando guardaste, se añade automáticamente. Un Clip Speed Treatment nunca se carga en un vídeo distinto, porque sus números de fotograma no encajarían.

Cómo se exportan las secciones depende del modo de procesamiento:

- **Sin pérdida:** se conserva cada fotograma con su propio tiempo de reproducción – un archivo con **frecuencia de fotogramas variable**. Las secciones pueden empezar en cualquier fotograma. Se reproduce en todos los reproductores habituales; los programas de edición prefieren una frecuencia de fotogramas constante. Las secciones muy rápidas (p. ej. 1920 fps) obligan a los reproductores a decodificar esa cantidad de fotogramas por segundo – elige recodificar para una reproducción fluida en ese caso.
- **Recodificar:** todo el clip se convierte a la **frecuencia de fotogramas constante** elegida; las secciones rápidas omiten imágenes, las lentas reciben imágenes intermedias.
- **Recodificación Smart:** véase el capítulo siguiente.

## 7. Recodificación Smart

La recodificación Smart combina ambas: las secciones marcadas como **Recodificar** en la tabla de secciones se codifican con el **códec original** a sus propios **FPS de salida**; todo lo demás se copia sin cambios. Todas las partes se unen en **un solo archivo**.

![Ajustes de salida en modo Recodificación Smart](images/settings_smart.png)

Cosas que conviene saber:

- **Solo para material H.264 y HEVC** (p. ej. GoPro, teléfonos). El códec queda fijado al del original – de lo contrario las partes no se podrían unir.
- **Solo se une en keyframes.** Los puntos de entrada y salida se ajustan a ellos, y las secciones recodificadas se amplían automáticamente hasta los keyframes más cercanos – los fotogramas adicionales se recodifican a la velocidad que de todos modos tienen. Algunas cámaras escriben keyframes "abiertos", en los que los fotogramas siguientes aún dependen de otros anteriores; la app los detecta al cargar el clip y no une ahí.
- **No se reproduce en dispositivos Apple.** El archivo unido cambia los ajustes del decodificador dentro de la secuencia (etiqueta MP4 *hev1* / *avc3*). QuickTime, iPhone, iPad y Final Cut no pueden reproducirlo – VLC, mpv, Windows, Android, Chrome y Firefox sí. Para Apple, recodifica el clip completo.
- Los últimos FPS de salida que elegiste pasan a ser el valor predeterminado para la siguiente sección recodificada.

## 8. Codificación de prueba y estimaciones de tiempo

La pestaña **Codificación de prueba** codifica unos pocos fotogramas (100 por defecto) desde la posición del cursor con los ajustes de salida exactos. Muestra la velocidad de codificación, el tamaño del archivo y una **estimación para el clip completo**, y compara el original y la salida **lado a lado** o con una **cortinilla** – ampliable al 100 % y al 200 %. Haz la prueba en una parte movida del clip para obtener una estimación segura. El botón *Comando de FFmpeg* muestra lo que se ejecuta.

![Codificación de prueba con comparación lado a lado](images/test_encode.png)

Las estimaciones también aparecen en la lista de clips. Los clips con los mismos ajustes comparten una prueba, escalada según su tamaño.

## 9. Exportación y lista de lotes

![Pestaña Exportar con la lista de lotes](images/export.png)

- **Guardar en:** junto a cada archivo original, o una carpeta.
- **Nombre del archivo:** un patrón con marcadores – `{name}` nombre del original, `{speed}` factor de velocidad, `{slower}` cuántas veces más lento, `{fps}` fotogramas por segundo de salida, `{codec}`, `{res}` tamaño de salida, `{mode}` lossless / smart / reencode, `{n}` posición en la cola.
- **Si el archivo existe:** añadir un número, sobrescribir u omitir.
- **Exportar:** todos los clips, los clips seleccionados o la **lista de lotes**.
- El progreso se muestra por clip y para todo el lote; **Cancelar** lo detiene, y los archivos incompletos se borran.

### Lista de lotes

**➕ Añadir al lote** (pestaña Vista previa y recorte) guarda el clip exactamente tal como está en ese momento – modo de procesamiento, ajustes, recorte y todas las secciones – como una entrada de la lista de lotes. Las secciones se quedan donde están, así que puedes añadir el mismo clip varias veces, p. ej. una vez en *Sin pérdida* y otra en *Recodificación Smart*. Los cambios posteriores en el clip no modifican las entradas que ya están en la lista. La lista se mantiene después de la exportación; **Quitar de la lista** y **Vaciar lista** la gestionan. Las entradas exportadas correctamente se marcan como **Hecho** y no se vuelven a exportar al hacer clic más tarde en **Iniciar exportación** – solo se ejecutan las entradas añadidas (o que fallaron / se cancelaron) desde entonces. Para exportar de nuevo una entrada terminada, modifícala con *Editar esta entrada* o borra su archivo de salida. Usa `{mode}` en el nombre del archivo para distinguir las versiones.

**Haz doble clic en una entrada** de la lista de lotes para abrirla de nuevo: sus secciones, recorte y ajustes se cargan en Vista previa y recorte (las secciones anteriores del clip se pueden recuperar con ↶ Deshacer). Se te pregunta qué quieres hacer:

- **Otra codificación** – cambia el códec, el preajuste, la calidad o el tamaño y haz clic en **➕ Añadir al lote**: se añade una entrada nueva y la antigua se conserva.
- **Editar esta entrada** – modifícala y haz clic en **✔ Actualizar entrada del lote**: la entrada se sustituye.

Siempre que añadas un clip que ya está en la lista de lotes, VideoSpeedControl pregunta si quieres otra codificación y ofrece **añadidos al nombre** con casillas – códec, preajuste, calidad y resolución, p. ej. `jump_x265_slow_high_1920x1080.mp4`. Una vista previa muestra el nombre de archivo resultante; tu elección de casillas se recuerda.

## 10. Convertir vídeos

**Convertir vídeos…** (barra de herramientas) recodifica muchos vídeos a la vez – por ejemplo, una carpeta de archivos AVI / DivX antiguos a un códec moderno. Es independiente de la lista de clips y de los ajustes de velocidad: se conserva cada fotograma una vez, la duración no cambia y los originales nunca se modifican. Añade archivos o carpetas enteras (con subcarpetas si quieres) o suéltalos sobre la ventana. Los archivos nuevos van a una carpeta *Converted* junto a cada original, o a una carpeta que elijas; los archivos existentes nunca se sobrescriben.

**Easy** (arriba a la derecha): códec, nivel de calidad y *Conservar el sonido* – más **Smart**.

**Pro** muestra todos los ajustes:

| Ajuste | Qué hace |
|---|---|
| **Fotogramas por segundo** | *Original* (cada vídeo conserva los suyos) o una frecuencia de la lista. Otra frecuencia mantiene la duración: se omiten o repiten fotogramas, nunca se inventan. |
| **Contenedor** | MP4, MOV o MKV. AV1 no se puede guardar en MOV, por lo que MOV aparece en gris para AV1. |
| **Códec** | AV1 (SVT-AV1 o libaom), HEVC, H.264. |
| **Imagen** | *Nivel de calidad*, un *valor de calidad propio* (el CRF del códec), una *tasa de datos* en kbit/s o *Smart*. |
| **Sonido** | *Smart*, *Copiar sin cambios*, AAC, Opus, MP3, FLAC o *Sin sonido*, con **canales** (como el original, mono, estéreo, 5.1, 7.1 – nunca más de los que tiene el original) y la **tasa de datos del sonido**. |

Los ajustes son los **ajustes generales** para cada vídeo. Selecciona uno o más vídeos y haz clic en **Ajustes propios para la selección** para darles sus propios ajustes – la columna Ajustes muestra entonces *Propios: …*; vuelve a seleccionarlos más tarde para cambiarlos, o haz clic en **Volver a los ajustes generales**. Las combinaciones que no funcionan se marcan con ⚠ en la lista (por ejemplo, copiar sonido MP3 a MOV), y la conversión espera hasta que se corrijan.

### Smart: archivos más pequeños con la misma imagen y el mismo sonido

Con **Smart**, cada vídeo se mide antes de convertirlo: se codifican tres muestras cortas con varios valores de calidad y se comparan con el original mediante **VMAF** (una puntuación perceptual de 0 a 100). Se usa el archivo más pequeño que aún alcanza el objetivo:

- **Se ve igual** (predeterminado): sin diferencia visible (VMAF ≥ 96 de media, cada muestra ≥ 94,5).
- **Más pequeño, pérdida mínima**: claramente más pequeño, con una ligera pérdida solo al mirar de cerca (VMAF ≥ 93).

El sonido se **copia sin cambios** cuando el contenedor puede contenerlo – no se pierde nada y es la opción más pequeña; si no, pasa a AAC con los mismos canales y la misma frecuencia de muestreo, con una tasa de datos adaptada al original (por ejemplo, MP3 96 kbit/s → AAC 80 kbit/s). La columna Ajustes muestra el resultado antes de convertir, p. ej. *calidad 27 ≈ 145 kbit/s, ~28 %*. **Medir ahora** mide sin convertir; *Convertir* mide primero de todos modos. La medición tarda unos 20 segundos para un vídeo antiguo pequeño y más para HD.

Una recodificación nunca puede ser mejor que su origen – Smart conserva lo que hay y ahorra el espacio. Ejemplo: unos dibujos animados antiguos en DivX (368×208, 10 fps) pasaron a archivos AV1 de aproximadamente el 30–40 % de su tamaño con el sonido MP3 copiado.

## 11. AV2 (experimental)

AV2 es el sucesor de AV1 (AOMedia, especificación 1.0 de mayo de 2026), aproximadamente un 30 % más pequeño con la misma calidad. FFmpeg aún no admite AV2, así que la app usa el software de referencia AVM. Es una herramienta de investigación y **extremadamente lenta** – unos 75 segundos por fotograma 1080p en la CPU de un portátil, unos 20 segundos a 360p – así que úsalo para clips cortos y tamaños pequeños. Las codificaciones de prueba usan como máximo 5 fotogramas. La salida es IVF o WebM; apenas ningún reproductor puede reproducir AV2 todavía. En Linux el codificador se compila con `tools/fetch_avm.py`; sin él, AV2 aparece como no disponible.

## 12. Atajos de teclado

| Tecla | Acción |
|---|---|
| F1 | Esta guía del usuario |
| Ctrl+O | Añadir archivos |
| Supr | Quitar los clips seleccionados |
| Espacio | Reproducir / detener la vista previa |
| ← / → | Fotograma anterior / siguiente |
| Shift+← / → | Keyframe anterior / siguiente |
| Inicio / Fin | Primer / último fotograma |
| I / O | Marcar punto de entrada / salida |
| [ / ] | Inicio / fin de sección |
| Ctrl+Z | Deshacer el último cambio en las secciones |
| Ctrl+Shift+Z / Ctrl+Y | Rehacer |
| Ctrl+S | Guardar Clip Speed Treatment (.cst) |
| Ctrl+L | Cargar Clip Speed Treatment (.cst) |

## 13. Consejos y solución de problemas

- **¿Qué modo elegir?** Sin pérdida siempre que las frecuencias de fotogramas encajen – es instantáneo y perfecto. Recodificación Smart cuando solo algunas partes necesitan una frecuencia de fotogramas constante. Recodificar para otro tamaño, otro códec o una frecuencia de fotogramas constante apta para edición.
- **Programas de edición y frecuencia de fotogramas variable:** DaVinci Resolve y Premiere manejan mal los archivos de frecuencia de fotogramas variable. Exporta con Recodificar (p. ej. ProRes o DNxHR) para editar.
- **La vista previa se entrecorta:** las frecuencias de fotogramas muy altas (240 fps en tiempo real) necesitan más potencia de decodificación de la que tienen muchos portátiles – la exportación no se ve afectada.
- **Sin codificador por hardware:** los codificadores por hardware solo se ofrecen cuando una codificación de prueba en tu ordenador funciona; los codificadores por software siempre funcionan.
- **RIFE es lento o no está disponible:** RIFE necesita una tarjeta gráfica compatible con Vulkan; con gráficos integrados es lento, y sin Vulkan no se ofrece.
- **El sonido es difícil de entender:** es normal con una cámara lenta fuerte – el habla 10× más lenta conserva su tono, pero está estirada. Desactiva el sonido (🔇) o añade música más tarde.
- **Recodificación Smart aparece en gris:** el clip no es H.264 / HEVC, el análisis de keyframes sigue en marcha o ningún keyframe permite unir.

## 14. Licencia y créditos

Copyright © 2026 Alex Vulcu. Concepto, arquitectura, dirección y curaduría de Alex Vulcu. Implementación asistida por herramientas de IA generativa. Con licencia MIT License – véase el archivo LICENSE.

VideoSpeedControl usa otro software de código abierto con su propia licencia: **FFmpeg** (compilación GPL, incluye x264 / x265), **Sonic** para estirar el sonido (Apache-2.0, el mismo algoritmo que la app de Android), **Qt / PySide6** (LGPL), **rife-ncnn-vulkan** con el modelo RIFE (MIT) y **AVM**, el software de referencia de AV2 (BSD-3-Clause-Clear). Los detalles están en THIRD_PARTY_NOTICES.md.
