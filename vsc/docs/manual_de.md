# VideoSpeedControl – Benutzerhandbuch

VideoSpeedControl gibt dir die volle Kontrolle über die Geschwindigkeit eines Videoclips. Teile einen Clip, der in nativer Zeitlupe aufgenommen wurde – zum Beispiel eine GoPro mit 240 fps oder die Zeitlupenaufnahme eines Smartphones –, in Abschnitte und gib jedem Abschnitt seine eigene Bildrate: den Anfang beschleunigen, danach extreme Zeitlupe, dann Echtzeit und zum Schluss wieder Zeitlupe.

- **Verlustfrei** braucht überhaupt keine Neukodierung: Jedes Original-Frame bleibt erhalten, nur seine Abspielzeit ändert sich. So erzeugt die App einen Clip mit variabler Bildrate praktisch sofort und ohne Qualitätsverlust.
- **Smart neu kodieren** kodiert nur die Abschnitte neu, deren Bildrate von der Ausgabe-Bildrate abweicht, und zwar im selben Codec wie die Quelle. Das hält den Export schnell.
- **Neu kodieren** kodiert den ganzen Clip in einem Codec deiner Wahl, mit derselben vollen Kontrolle über Tempo und Ausgabe-Bildrate.

Die App speichert die Tempo-Bearbeitungen jedes Clips, sodass du deine Arbeit später fortsetzen kannst – oder denselben Clip in verschiedenen Codecs kodieren und vergleichen, unterstützt durch automatisch erzeugte Dateinamen mit Benennungsoptionen. Du kannst außerdem viele Clips – oder mehrere Versionen desselben Clips – in einer Batch-Liste sammeln und alle auf einmal exportieren.

**Inhalt**

1. Schnellstart
2. Das Hauptfenster
3. Clips laden und Clip-Informationen
4. Vorschau und Zuschnitt
5. Ausgabeeinstellungen
6. Tempo-Abschnitte
7. Smart neu kodieren
8. Test-Encode und Zeitschätzungen
9. Export und die Batch-Liste
10. Videos konvertieren
11. AV2 (experimentell)
12. Tastenkürzel
13. Tipps und Problemlösungen
14. Lizenz und Danksagung

## 1. Schnellstart

1. Starte VideoSpeedControl und ziehe eine oder mehrere Videodateien ins Fenster (oder klicke auf **Dateien hinzufügen …**).
2. Wähle rechts in den *Ausgabeeinstellungen* die **Verarbeitung**. **Verlustfrei** ist die Standardeinstellung und die schnellste.
3. Wähle eine Ausgabe-**Bildrate**. Die Auswahlliste zeigt, wie viel langsamer (oder schneller) der Clip läuft und wie lang er wird, z. B. *„25 fps (PAL) – 9,6× langsamer, 1:12 min“*.
4. Drücke im Reiter *Vorschau & Zuschnitt* die **Leertaste**, um das Ergebnis anzusehen.
5. Öffne den Reiter **Export**, wähle einen Ordner und klicke auf **Export starten**.

![Das Hauptfenster](images/overview.png)

### So funktioniert Zeitlupe hier

Eine Kamera mit 240 fps nimmt 240 Bilder pro Sekunde auf. Mit 240 fps abgespielt ist das Echtzeit. Mit 25 fps abgespielt dauern dieselben 240 Bilder 9,6 Sekunden: Der Clip läuft **9,6× langsamer** – ohne ein einziges neues oder fehlendes Bild. Genau das macht *Verlustfrei*. Nur wenn du ein Tempo willst, das nicht zur Bildrate passt (z. B. 20× langsamer bei 25 fps), müssen Bilder übersprungen oder berechnet werden, und das bedeutet Neukodierung.

## 2. Das Hauptfenster

- **Clip-Liste (oben):** jede geladene Datei mit Gerät, Codec, Auflösung, Bildrate, Länge, der gewählten Ausgabe und einer Schätzung für Exportdauer und Dateigröße.
- **Reiter (unten links):** *Vorschau & Zuschnitt*, *Test-Encode*, *Clip-Infos*, *Export*.
- **Ausgabeeinstellungen (unten rechts):** alles zur Ausgabe des gewählten Clips, mit einer Zusammenfassung am unteren Rand.
- **Hilfe** (rechtes Ende der Werkzeugleiste): dieses Handbuch (**F1**), das Handbuch als PDF und *Info*.

Jeder Clip hat seine eigenen Einstellungen. **Auf alle Clips anwenden** kopiert die Ausgabeeinstellungen des gewählten Clips auf alle anderen (Zuschnitt und Tempo-Abschnitte bleiben pro Clip).

## 3. Clips laden und Clip-Informationen

Ziehe Dateien oder Ordner ins Fenster oder nutze **Dateien hinzufügen …**. Jedes Format, das FFmpeg lesen kann, funktioniert. Nach dem Laden scannt die App den Clip (genaue Frame-Zeiten und Keyframes) und erstellt im Hintergrund eine kleine Vorschaukopie (*„schnelle Vorschau 45 %“* neben der Frame-Nummer).

Der Reiter **Clip-Infos** listet alles zur Datei auf: Container, Codec und Profil, Auflösung und Seitenverhältnis, Drehung, Bildrate, Anzahl der Frames, Keyframe-Abstand, Pixelformat, Chroma-Unterabtastung, Bittiefe, Farbraum (SDR / HLG / PQ), Datenrate, Aufnahmegerät und -datum sowie Ton.

![Clip-Infos](images/clip_info.png)

### Zeitlupe vom Smartphone

Smartphones wie das Google Pixel nehmen Zeitlupe z. B. mit 240 fps auf, speichern sie aber als 30-fps-Datei, die bereits langsam abgespielt wird. VideoSpeedControl liest die Aufnahmerate aus der Datei und behandelt **240 fps als Original**: Tempo und „× langsamer“ beziehen sich immer auf Echtzeit. Die Clip-Liste zeigt z. B. *„240 (Zeitlupe, Datei 29,97)“*.

### Gespeicherte Vorschauen

Die Frame-Liste, die Miniaturen der Zeitleiste, die kleine Vorschaukopie zum Scrubben und die Keyframe-Analyse von Smart neu kodieren werden im Cache-Ordner gespeichert (Linux *~/.cache/VideoSpeedControl/previews*, Windows *%LOCALAPPDATA%\VideoSpeedControl\previews*). Ein erneut geöffneter Clip ist fast sofort bereit, statt noch einmal gescannt und dekodiert zu werden – auch nach dem Umbenennen oder Verschieben, denn er wird an seinem Inhalt erkannt. Die Vorschau wird in kleinen Teilen gespeichert; ist einer beschädigt, wird nur dieser Teil neu erzeugt.

Zwei Minuten nach dem Start – und nur, solange nichts Aufwendiges läuft – werden Vorschauen gelöscht, die niemand mehr braucht: Eine Vorschau bleibt erhalten, solange ihr Clip in der Liste oder in der Batch-Liste ist oder eine Clip-Speed-Treatment-Datei (.cst) hat. Der Cache bleibt unter 2 GB.

## 4. Vorschau und Zuschnitt

![Vorschau, Tempo-Abschnitte und die Zusammenfassung](images/sections.png)

### Sich bewegen

- Klicke oder ziehe in der **Zeitleiste** (Miniaturen mit Keyframe-Markierungen darunter), nutze das Feld für die **Frame-Nummer** oder die Schaltflächen und Tasten: **◀ 1 / 1 ▶** (**←/→**) ein Frame, **− 🔑 / + 🔑** (**Umschalt+←/→**) vorheriger / nächster Keyframe, **⏮ / ⏭** (**Pos1/Ende**) erster / letzter Frame, Mausrad.
- Beim Ziehen kommt das Bild aus der kleinen Vorschaukopie – sofort. Ruht der Cursor einen Moment, ersetzt das scharfe Frame in voller Größe es.
- **Einpassen / 100 % / 200 %** zoomt das Bild; zum Verschieben ziehen, per Doppelklick umschalten.

### Vorschau abspielen

**▶ Vorschau abspielen** (oder **Leertaste**) spielt die Ausgabe mit der gewählten Bildrate und dem gewählten Tempo ab – in reduzierter Größe und ohne Kodierung, sodass es sofort startet. Es wird von der Abspielposition bis zum Endpunkt abgespielt. Bewegungsinterpolation und RIFE werden als einfache Überblendung gezeigt (sie sind für Echtzeit zu langsam). Kann der Computer nicht schnell genug dekodieren (z. B. 240 fps in Echtzeit), weist ein Hinweis darauf hin, dass die Vorschau langsamer läuft, als der Export laufen wird.

### Zuschnitt (Anfang / Ende)

**Anfang setzen (I)** und **Ende setzen (O)** markieren das erste und das letzte Frame der Ausgabe; **Zuschnitt löschen** entfernt sie. Die abgedunkelten Teile der Zeitleiste werden nicht exportiert.

Im Modus **Verlustfrei** und **Smart neu kodieren** **rasten** Anfangs- und Endpunkt **an Keyframes ein**. Ein gelber Hinweis erklärt, warum: Nur Keyframes sind vollständige Bilder; alle anderen Frames speichern nur die Unterschiede zu ihren Nachbarn und lassen sich nicht anzeigen, wenn der Keyframe davor weggeschnitten ist. Wähle *Neu kodieren* für Frame-genaue Schnitte.

## 5. Ausgabeeinstellungen

### Verarbeitung

| Modus | Was passiert | Was du ändern kannst |
|---|---|---|
| **Verlustfrei** | Jedes Frame bleibt unberührt; nur seine Abspielzeit ändert sich. Sekunden statt Minuten, kein Qualitätsverlust. | Bildrate, Container, Tempo-Abschnitte, Zuschnitt (an Keyframes) |
| **Smart neu kodieren** | Kopiert den Clip und kodiert nur die Abschnitte neu, die du markierst – siehe Kapitel 7. | Tempo-Abschnitte mit eigener Ausgabe-Bildrate, Qualität und Preset der neu kodierten Teile, Container |
| **Neu kodieren** | Der ganze Clip wird neu kodiert. | Alles: Codec, Größe, Tempo, Bildrate, Interpolation |

Nur die Einstellungen, die der gewählte Modus nutzen kann, sind aktiviert.

**Easy / Pro** (oben in den Ausgabeeinstellungen): *Easy* blendet die Codec-Details aus – den Codec selbst, Profil, Preset, Qualität, Chroma und Bittiefe. Smart neu kodieren verwendet dann immer den Quellcodec und Neu kodieren immer **AV1 (schnell)**, jeweils mit Standard-Preset und Standard-Qualität. In Easy wird außerdem jede Tempoänderung zwischen Abschnitten automatisch **geglättet** (0,5 s, siehe Kapitel 6) – die Schalter *Weich hinein / Weich hinaus* erscheinen nur in Pro. *Pro* zeigt alle Einstellungen (die Bilder in diesem Handbuch zeigen Pro). Beim Wechsel zu Easy werden die Easy-Einstellungen auf alle Clips angewendet.

- Wenn du **Smart neu kodieren** wählst, wird jeder Tempo-Abschnitt, dessen Bildrate von seiner Ausgabe-Bildrate abweicht, zum Neukodieren markiert; Abschnitte, die bereits damit laufen, bleiben kopiert (die Häkchen kannst du in der Tabelle ändern).
- Beim Wechsel von Smart zu **Neu kodieren** wird wieder AV1 (schnell) gewählt.

![Ausgabeeinstellungen im Modus Neu kodieren](images/settings_reencode.png)

### Bildrate und Tempo

- **Bildrate:** die Standardraten (23,976 … 120 fps) plus die eigene Rate des Clips, gekennzeichnet mit *(Original)*. Jeder Eintrag zeigt die Verlangsamung und die Ausgabelänge, wenn jedes Frame erhalten bleibt.
- **Tempo** (Neu kodieren): *Verlustfrei* verwendet jedes Frame einmal. *Benutzerdefiniert* legt ein beliebiges Tempo fest (z. B. 0,05× = 20× langsamer) – schneller als das verlustfreie Tempo überspringt Frames, langsamer berechnet Zwischenbilder (siehe *Interpolation*). *Voreinstellungen …* bietet gängige Werte an.
- Die Zeile darunter zeigt die **Ausgabelänge** und wie viel langsamer oder schneller sie als das Original ist.

### Codec und Container

Die Codec-Liste ist gegliedert in **Verlustfrei** (FFV1, Ut Video, MagicYUV, HuffYUV, H.264 / HEVC / VP9 / AV1 / AV2 verlustfrei, QuickTime Animation, Bildsequenzen), **Verlustbehaftet** (H.264, HEVC, AV1, VP9, ProRes, DNxHR, CineForm, MJPEG, AV2) und **Hardware** (NVIDIA, Intel, AMD – nur angeboten, wenn ein Test-Encode auf deinem Computer funktioniert hat). Jeder Eintrag hat einen Tooltip, der erklärt, wofür er gut ist. Die **Container**-Liste bietet nur Formate an, die den gewählten Codec aufnehmen können. Wenn du zu *Neu kodieren* wechselst, ist **AV1 (SVT-AV1, schnell)** vorgewählt – kleine Dateien bei guter Qualität; *AV1 (libaom, beste Qualität)* komprimiert etwas besser, ist aber viel langsamer.

### Preset

Wie lange der Encoder nach der besten Kompression sucht. Bei gleicher Qualitätseinstellung ergibt ein langsameres Preset eine **kleinere Datei** und dauert **länger**; die sichtbare Qualität ändert sich kaum. Jeder Eintrag sagt, was er tut, z. B. *„veryslow – am langsamsten, kleinste Datei“*. (Bei CineForm heißt die Zeile *Kompression* – dort ist es eine Qualitätsstufe.)

### Qualität

Benannte Stufen, die für jeden Codec ungefähr dasselbe bedeuten; der eigene Zahlenwert des Codecs steht in Klammern:

| Stufe | Bedeutung |
|---|---|
| Visuell verlustfrei | Kein sichtbarer Unterschied, selbst im Standbild. Große Dateien. |
| Hoch (Standard) | Kaum sichtbarer Verlust – gut für Weiterbearbeitung und Archivierung. |
| Gut | Streaming-Qualität (YouTube, Netflix): gut zum Ansehen. |
| Mittel | Verluste bei genauem Hinsehen sichtbar, z. B. in feinen Details oder dunklen Bereichen. |
| Kleine Datei | Deutlich sichtbare Verluste – für Vorschauen oder zum schnellen Versenden. |

**Benutzerdefiniert …** lässt dich den eigenen Wert des Codecs eingeben. Eine Stufe tiefer macht die Datei etwa 30–50 % kleiner.

### Chroma und Bittiefe

- **Chroma-Unterabtastung:** 4:4:4 (volle Farbdetails – VFX, High-End), 4:2:2 (Broadcast-TV), 4:2:0 (Streaming, Netflix, YouTube). Es werden nur Kombinationen angeboten, die der Codec unterstützt.
- **Bittiefe:** 8 Bit oder 10 Bit. *Wie Quelle* behält, was der Clip hat.

### Auflösung, Seitenverhältnis und Skalierung

- **Auflösung:** Quellgröße beibehalten, Voreinstellungen von 480p bis DCI 4K (einschließlich 9:16 und 1:1) oder benutzerdefiniert.
- **Seitenverhältnis:** die Originalproportionen beibehalten (im Bild einpassen) oder eine Bildgröße / ein Seitenverhältnis erzwingen; **Anpassung** entscheidet zwischen schwarzen Balken (Pad), Abschneiden (Crop) oder Strecken.
- **Skalierung:** das Skalierungsverfahren mit Bewertungen für Qualität und Geschwindigkeit – Lanczos ist am schärfsten, Area am saubersten bei starker Verkleinerung.

### Interpolation

Wird verwendet, wenn das Tempo langsamer als das verlustfreie Tempo ist und neue Zwischenbilder gebraucht werden:

- **Frame-Duplizierung** – wiederholt Bilder; die Bewegung ruckelt. Am schnellsten.
- **Frame-Überblendung** – blendet Nachbarn ineinander über; weich, aber mit Geisterbildern.
- **Bewegungsinterpolation (minterpolate)** – berechnet echte Zwischenbilder auf der CPU; gut für langsame, gleichmäßige Bewegung. Sehr langsam.
- **RIFE (KI)** – neuronales Netz auf der Grafikkarte (Vulkan, auch integrierte Grafik); deutlich bessere Bewegung. Arbeitet mit 8-Bit-RGB. Nicht zusammen mit Tempo-Abschnitten oder AV2 verfügbar.

### Ton

Die Schaltfläche **Ton** direkt unter *Verarbeitung* schaltet den Ton mit einem Klick ein oder aus: **🔊 Ton an – Tonhöhe bleibt** (Standard) oder **🔇 Ton aus**. Bei eingeschaltetem Ton nimmt die App die erste Tonspur des Clips und dehnt oder staucht sie auf die neue Länge des Videos – die **Tonhöhe bleibt gleich**, es gibt also keine tiefen oder piepsigen Stimmen. Tempo-Abschnitte bekommen jeweils ihren eigenen Dehnungsfaktor, sodass der Ton jedem Abschnitt folgt. Sehr starke Zeitlupe macht Sprache schwer verständlich (sie ist einfach 10× langsamer), behält aber ihre Tonhöhe.

**Zeitlupe vom Smartphone:** Smartphones speichern den Ton eines Zeitlupen-Clips wie bei einem Tonband verlangsamt – er klingt tief. VideoSpeedControl bringt ihn zuerst auf seine echte Tonhöhe und Echtzeit-Länge zurück und dehnt ihn dann auf das Video.

Der Ton wird hinzugefügt, nachdem das Video fertig ist, sodass ein **verlustfreies** Video verlustfrei bleibt; nur die Tonspur wird kodiert (AAC in MP4 / MOV / MKV, Opus in WebM, PCM in AVI / MXF). Bildsequenzen und AV2-Dateien (FFmpeg kann AV2 noch nicht verarbeiten) bleiben ohne Ton – die Schaltfläche ist dann ausgegraut, und ihr Tooltip nennt den Grund.

## 6. Tempo-Abschnitte

Tempo-Abschnitte geben Teilen eines Clips ihre eigene Bildrate – zum Beispiel der Sprung in Zeitlupe, der Anlauf in Echtzeit, die Landung 8× schneller.

1. Bewege die Abspielposition zum ersten Frame und klicke auf **Abschnittsanfang [** (Taste **[**).
2. Gehe zum letzten Frame und klicke auf **Abschnittsende ]** (Taste **]**). Ein gestrichelter Rahmen markiert den Bereich.
3. Wähle die Bildrate (von 23,976 fps bis **8× schneller** als das Original) und klicke auf **Abschnitt hinzufügen**.

**Schneller:** Überspringe Schritt 1. Ohne markierten Anfang beginnt **Abschnittsende ]** den Abschnitt direkt nach dem vorherigen Abschnitt – oder am Anfang des Clips (Zuschnitt), wenn es keinen gibt –, sodass Abschnitte lückenlos aufeinander folgen. Innerhalb eines vorhandenen Abschnitts beginnt er am Anfang dieses Abschnitts (der Abschnitt wird geteilt).

Abschnitte erscheinen als blaue Bänder in der Zeitleiste und in der Tabelle darunter, in der du ihre Bildrate ändern, zu ihnen springen (Klick) oder sie entfernen (✕) kannst. Alles außerhalb von Abschnitten läuft in **Echtzeit**. Ein neuer Abschnitt, der sich mit einem vorhandenen überschneidet, hat Vorrang.

- **Einen Abschnitt bearbeiten:** Klicke ihn in der Zeitleiste oder in der Tabelle an, um ihn auszuwählen. **Anfang = Abspielposition** / **Ende = Abspielposition** verschieben sein erstes / letztes Frame zur Abspielposition; die Bildrate änderst du in der Tabelle.
- **Eine Grenze verschieben:** Die Grenzen zwischen Abschnitten (und zwischen einem Abschnitt und Echtzeit) sind weiße Linien mit einem Griff unterhalb der Miniaturen. Ziehe eine Grenze, um einen Abschnitt zu verlängern und seinen Nachbarn zu verkürzen; das Bild zeigt beim Ziehen das Frame an der Grenze. Ein Ziehen ist ein Rückgängig-Schritt.
- **Weiche Übergänge:** Setze das Häkchen bei **Weich hinein** / **Weich hinaus** in der Tabelle, damit sich das Tempo gleichmäßig ändert, statt zu springen – z. B. von 9,6× Zeitlupe zu Echtzeit. Die Änderung dauert **0,5 s** der Ausgabe und ist auf die Grenze zentriert (kürzer, wenn ein Abschnitt zu kurz ist); die Zeitleiste zeigt sie als dunkles Feld mit einer schrägen Linie (steigend = schneller werdend). Es funktioniert in jedem Verarbeitungsmodus; bei Smart neu kodieren wird der Übergang neu kodiert, wenn ein angrenzender Abschnitt neu kodiert wird.

- **Magnetischer Cursor 🧲:** Wenn du in die Nähe eines Abschnitts ziehst, rastet der Cursor auf dem Frame direkt danach ein (um nahtlos fortzufahren) oder – während du ein Ende markierst – auf dem Frame direkt vor dem nächsten Abschnitt. Klicke auf 🧲, um das auszuschalten.
- **Abschnitte löschen** (rechts) entfernt nach Rückfrage alle Abschnitte.
- **↶ Rückgängig** (**Strg+Z**) und **↷ Wiederholen** (**Strg+Umschalt+Z** oder **Strg+Y**) gehen durch jede Änderung an den Abschnitten zurück und vor – Hinzufügen, Ändern, Verschieben, Entfernen, Löschen, Laden – bis zu 200 Schritte, getrennt für jeden Clip. Die Zahl auf der Schaltfläche zeigt, wie viele Schritte du zurück (oder vor) gehen kannst; fahre mit der Maus darüber, um zu sehen, welche Änderung rückgängig gemacht wird.

### Ein Clip Speed Treatment (.cst) speichern und laden

**Clip Speed Treatment speichern …** in der Werkzeugleiste (**Strg+S**) speichert die Abschnitte, den Zuschnitt und die Ausgabeeinstellungen des aktuellen Clips als *Clip-Speed-Treatment*-Datei (`.cst`). Standardmäßig wird sie in *Dokumente/VideoSpeedControl/Clip Speed Treatments* angeboten – die Android-App speichert ebenfalls dort. **Clip Speed Treatment laden …** (**Strg+L**) – oder das Ablegen einer `.cst` auf dem Fenster – lädt sie wieder. Die Android-App liest und schreibt dieselben Dateien.

Ein Treatment gehört zu genau einem Video: Es speichert einen Fingerabdruck des Dateiinhalts und lässt sich nur auf dieses Video laden. Der Dateiname spielt keine Rolle – auch eine umbenannte oder verschobene Kopie passt weiterhin. Ist das Video noch nicht in der Liste, liegt aber noch dort, wo es beim Speichern war, wird es automatisch hinzugefügt. Ein Treatment lässt sich nie auf ein anderes Video laden, weil seine Frame-Nummern nicht passen würden.

Wie Abschnitte exportiert werden, hängt vom Verarbeitungsmodus ab:

- **Verlustfrei:** Jedes Frame bleibt mit seiner eigenen Abspielzeit erhalten – eine Datei mit **variabler Bildrate**. Abschnitte können an jedem Frame beginnen. Läuft in allen gängigen Playern; Schnittprogramme bevorzugen eine konstante Bildrate. Sehr schnelle Abschnitte (z. B. 1920 fps) zwingen Player dazu, so viele Frames pro Sekunde zu dekodieren – wähle dort Neukodierung für flüssige Wiedergabe.
- **Neu kodieren:** Der ganze Clip wird in die gewählte **konstante Bildrate** umgewandelt; schnelle Abschnitte überspringen Bilder, langsame bekommen Zwischenbilder.
- **Smart neu kodieren:** siehe nächstes Kapitel.

## 7. Smart neu kodieren

Smart neu kodieren kombiniert beides: In der Abschnittstabelle mit **Neu kodieren** markierte Abschnitte werden mit dem **Quellcodec** und ihrer eigenen **Ausgabe-fps** kodiert; alles andere wird unverändert kopiert. Alle Teile werden zu **einer Datei** zusammengefügt.

![Ausgabeeinstellungen im Modus Smart neu kodieren](images/settings_smart.png)

Das solltest du wissen:

- **Nur für H.264- und HEVC-Material** (z. B. GoPro, Smartphones). Der Codec ist auf den Quellcodec festgelegt – sonst ließen sich die Teile nicht zusammenfügen.
- **Zusammenfügen nur an Keyframes.** Anfangs- und Endpunkte rasten dort ein, und neu kodierte Abschnitte werden automatisch auf die nächsten Keyframes erweitert – die zusätzlichen Frames werden mit dem Tempo neu kodiert, das sie ohnehin haben. Manche Kameras schreiben „offene“ Keyframes, bei denen die folgenden Frames noch von früheren abhängen; die App erkennt sie beim Laden des Clips und fügt dort nicht zusammen.
- **Nicht auf Apple-Geräten abspielbar.** Die zusammengefügte Datei ändert die Decoder-Einstellungen im Stream (MP4-Kennung *hev1* / *avc3*). QuickTime, iPhone, iPad und Final Cut können sie nicht abspielen – VLC, mpv, Windows, Android, Chrome und Firefox können es. Kodiere für Apple stattdessen den ganzen Clip neu.
- Die zuletzt gewählte Ausgabe-Bildrate wird zum Standard für den nächsten neu kodierten Abschnitt.

## 8. Test-Encode und Zeitschätzungen

Der Reiter **Test-Encode** kodiert ein paar Frames (standardmäßig 100) ab der Abspielposition mit genau den Ausgabeeinstellungen. Er zeigt die Kodiergeschwindigkeit, die Dateigröße und eine **Schätzung für den ganzen Clip** und vergleicht Quelle und Ausgabe **nebeneinander** oder mit einem **Wischer** – zoombar auf 100 % und 200 %. Teste an einer bewegten Stelle des Clips für eine sichere Schätzung. Die Schaltfläche *FFmpeg-Befehl* zeigt, was ausgeführt wird.

![Test-Encode mit Nebeneinander-Vergleich](images/test_encode.png)

Schätzungen erscheinen auch in der Clip-Liste. Clips mit denselben Einstellungen teilen sich einen Test, skaliert nach ihrer Größe.

## 9. Export und die Batch-Liste

![Reiter Export mit der Batch-Liste](images/export.png)

- **Speichern in:** neben jeder Quelldatei oder in einen Ordner.
- **Dateiname:** ein Muster mit Platzhaltern – `{name}` Quellname, `{speed}` Tempofaktor, `{slower}` wie viel langsamer, `{fps}` Ausgabe-Bildrate, `{codec}`, `{res}` Ausgabegröße, `{mode}` lossless / smart / reencode, `{n}` Position in der Warteschlange.
- **Wenn die Datei existiert:** Nummer anhängen, überschreiben oder überspringen.
- **Export:** alle Clips, die gewählten Clips oder die **Batch-Liste**.
- Der Fortschritt wird pro Clip und für die ganze Batch-Liste angezeigt; **Abbrechen** stoppt ihn, und unvollständige Dateien werden gelöscht.

### Batch-Liste

**➕ Zur Batch-Liste** (Reiter Vorschau & Zuschnitt) speichert den Clip genau so, wie er in diesem Moment ist – Verarbeitungsmodus, Einstellungen, Zuschnitt und alle Abschnitte – als Eintrag in der Batch-Liste. Die Abschnitte bleiben an ihrem Platz, sodass du denselben Clip mehrfach hinzufügen kannst, z. B. einmal *Verlustfrei* und einmal *Smart neu kodieren*. Spätere Änderungen am Clip ändern bereits vorhandene Einträge in der Liste nicht. Die Liste bleibt nach dem Export erhalten; mit **Aus Liste entfernen** und **Liste leeren** verwaltest du sie. Erfolgreich exportierte Einträge werden als **Fertig** markiert und nicht erneut exportiert, wenn du später auf **Export starten** klickst – es laufen nur Einträge, die seitdem hinzugefügt wurden (oder fehlgeschlagen / abgebrochen sind). Um einen fertigen Eintrag erneut zu exportieren, ändere ihn mit *Diesen Eintrag bearbeiten* oder lösche seine Ausgabedatei. Nutze `{mode}` im Dateinamen, um die Versionen zu unterscheiden.

**Doppelklicke einen Eintrag** in der Batch-Liste, um ihn erneut zu öffnen: Seine Abschnitte, sein Zuschnitt und seine Einstellungen werden in Vorschau & Zuschnitt geladen (die vorherigen Abschnitte des Clips lassen sich mit ↶ Rückgängig zurückholen). Du wirst gefragt, was du tun möchtest:

- **Andere Kodierung** – ändere Codec, Preset, Qualität oder Größe und klicke auf **➕ Zur Batch-Liste**: Ein neuer Eintrag wird hinzugefügt, der alte bleibt.
- **Diesen Eintrag bearbeiten** – ändere ihn und klicke auf **✔ Batch-Eintrag aktualisieren**: Der Eintrag wird ersetzt.

Wann immer du einen Clip hinzufügst, der schon in der Batch-Liste ist, fragt VideoSpeedControl, ob du eine andere Kodierung möchtest, und bietet **Namenszusätze** mit Kontrollkästchen an – Codec, Preset, Qualität und Auflösung, z. B. `jump_x265_slow_high_1920x1080.mp4`. Eine Vorschau zeigt den resultierenden Dateinamen; deine Auswahl der Kästchen wird gemerkt.

## 10. Videos konvertieren

**Videos konvertieren …** (Werkzeugleiste) kodiert viele Videos auf einmal neu – zum Beispiel einen Ordner mit alten AVI- / DivX-Dateien in einen modernen Codec. Es ist unabhängig von der Clip-Liste und den Tempo-Einstellungen: Jedes Frame bleibt einmal erhalten, die Länge bleibt gleich, und die Originale werden nie verändert. Füge Dateien oder ganze Ordner hinzu (auf Wunsch mit Unterordnern) oder ziehe sie aufs Fenster. Die neuen Dateien landen in einem Ordner *Converted* neben jedem Original oder in einem Ordner deiner Wahl; vorhandene Dateien werden nie überschrieben.

**Easy** (oben rechts): Codec, Qualitätsstufe und *Ton behalten* – plus **Smart**.

**Pro** zeigt alle Einstellungen:

| Einstellung | Was sie bewirkt |
|---|---|
| **Bildrate** | *Original* (jedes Video behält seine eigene) oder eine Rate aus der Liste. Eine andere Rate behält die Länge: Frames werden weggelassen oder wiederholt, nie erfunden. |
| **Container** | MP4, MOV oder MKV. AV1 lässt sich nicht in MOV speichern, daher ist MOV bei AV1 ausgegraut. |
| **Codec** | AV1 (SVT-AV1 oder libaom), HEVC, H.264. |
| **Bild** | *Qualitätsstufe*, ein *eigener Qualitätswert* (der CRF des Codecs), eine *Datenrate* in kbit/s oder *Smart*. |
| **Ton** | *Smart*, *Unverändert kopieren*, AAC, Opus, MP3, FLAC oder *Kein Ton*, mit **Kanälen** (wie das Original, Mono, Stereo, 5.1, 7.1 – nie mehr, als das Original hat) und der **Ton-Datenrate**. |

Die Einstellungen sind die **allgemeinen Einstellungen** für jedes Video. Wähle ein oder mehrere Videos und klicke auf **Eigene Einstellungen für Auswahl**, um ihnen eigene Einstellungen zu geben – die Spalte Einstellungen zeigt dann *Eigene: …*; wähle sie später erneut aus, um sie zu ändern, oder klicke auf **Zurück zu den allgemeinen Einstellungen**. Kombinationen, die nicht funktionieren, sind in der Liste mit ⚠ markiert (zum Beispiel MP3-Ton unverändert in MOV zu kopieren), und das Konvertieren wartet, bis sie behoben sind.

### Smart: kleinere Dateien bei gleichem Bild und Ton

Mit **Smart** wird jedes Video vor dem Konvertieren gemessen: Drei kurze Proben werden mit mehreren Qualitätswerten kodiert und per **VMAF** (eine Wahrnehmungsbewertung von 0 bis 100) mit dem Original verglichen. Es wird die kleinste Datei verwendet, die das Ziel noch erreicht:

- **Sieht gleich aus** (Standard): kein sichtbarer Unterschied (VMAF ≥ 96 im Durchschnitt, jede Probe ≥ 94,5).
- **Kleiner, minimaler Verlust**: spürbar kleiner, ein leichter Verlust nur bei genauem Hinsehen (VMAF ≥ 93).

Der Ton wird **unverändert kopiert**, wenn der Container ihn aufnehmen kann – nichts geht verloren, und es ist die kleinste Wahl; andernfalls wird er zu AAC mit denselben Kanälen und derselben Abtastrate bei einer zur Quelle passenden Datenrate (zum Beispiel MP3 96 kbit/s → AAC 80 kbit/s). Die Spalte Einstellungen zeigt das Ergebnis vor dem Konvertieren, z. B. *Qualität 27 ≈ 145 kbit/s, ca. 28 %*. **Jetzt messen** misst ohne zu konvertieren; *Umwandeln* misst ohnehin zuerst. Das Messen dauert bei einem kleinen alten Video etwa 20 Sekunden, bei HD länger.

Eine Neukodierung kann nie besser sein als ihre Quelle – Smart behält, was da ist, und spart den Platz. Beispiel: Alte DivX-Zeichentrickfilme (368×208, 10 fps) wurden zu AV1-Dateien mit etwa 30–40 % ihrer Größe, wobei der MP3-Ton kopiert wurde.

## 11. AV2 (experimentell)

AV2 ist der Nachfolger von AV1 (AOMedia, Spezifikation 1.0 vom Mai 2026) und bei gleicher Qualität etwa 30 % kleiner. FFmpeg kann AV2 noch nicht verarbeiten, deshalb nutzt die App die AVM-Referenzsoftware. Sie ist ein Forschungswerkzeug und **extrem langsam** – etwa 75 Sekunden pro 1080p-Frame auf einer Laptop-CPU, etwa 20 Sekunden bei 360p –, nutze sie also für kurze Clips und kleine Größen. Test-Encodes verwenden höchstens 5 Frames. Die Ausgabe ist IVF oder WebM; kaum ein Player kann AV2 bisher abspielen. Unter Linux wird der Encoder mit `tools/fetch_avm.py` gebaut; ohne ihn wird AV2 als nicht verfügbar angezeigt.

## 12. Tastenkürzel

| Taste | Aktion |
|---|---|
| F1 | Dieses Benutzerhandbuch |
| Strg+O | Dateien hinzufügen |
| Entf | Die gewählten Clips entfernen |
| Leertaste | Vorschau abspielen / stoppen |
| ← / → | Vorheriges / nächstes Frame |
| Umschalt+← / → | Vorheriger / nächster Keyframe |
| Pos1 / Ende | Erstes / letztes Frame |
| I / O | Anfangs- / Endpunkt setzen |
| [ / ] | Abschnittsanfang / -ende |
| Strg+Z | Die letzte Änderung an den Abschnitten rückgängig machen |
| Strg+Umschalt+Z / Strg+Y | Wiederholen |
| Strg+S | Clip Speed Treatment (.cst) speichern |
| Strg+L | Clip Speed Treatment (.cst) laden |

## 13. Tipps und Problemlösungen

- **Welcher Modus?** Verlustfrei, wann immer die Bildraten passen – es geht sofort und ist perfekt. Smart neu kodieren, wenn nur einige Teile eine konstante Bildrate brauchen. Neu kodieren für eine andere Größe, einen anderen Codec oder eine schnittfreundliche konstante Bildrate.
- **Schnittprogramme und variable Bildrate:** DaVinci Resolve und Premiere kommen mit Dateien mit variabler Bildrate schlecht zurecht. Exportiere zum Schneiden mit Neu kodieren (z. B. ProRes oder DNxHR).
- **Die Vorschau ruckelt:** Sehr hohe Bildraten (240 fps in Echtzeit) brauchen mehr Dekodierleistung, als viele Laptops haben – der Export ist davon nicht betroffen.
- **Kein Hardware-Encoder:** Hardware-Encoder werden nur angeboten, wenn ein Test-Encode auf deinem Computer funktioniert; Software-Encoder funktionieren immer.
- **RIFE ist langsam oder nicht verfügbar:** RIFE braucht eine Vulkan-fähige Grafikkarte; auf integrierter Grafik ist es langsam, ohne Vulkan wird es nicht angeboten.
- **Der Ton ist schwer zu verstehen:** Das ist bei starker Zeitlupe normal – 10× langsamere Sprache behält ihre Tonhöhe, ist aber gedehnt. Schalte den Ton aus (🔇) oder füge später Musik hinzu.
- **Smart neu kodieren ist ausgegraut:** Der Clip ist nicht H.264 / HEVC, die Keyframe-Analyse läuft noch, oder kein Keyframe erlaubt ein Zusammenfügen.

## 14. Lizenz und Danksagung

Copyright © 2026 Alex Vulcu. Konzept, Architektur, Leitung und Kuratierung von Alex Vulcu. Die Umsetzung wurde durch generative KI-Werkzeuge unterstützt. Lizenziert unter der MIT-Lizenz – siehe die Datei LICENSE.

VideoSpeedControl verwendet weitere Open-Source-Software mit eigener Lizenz: **FFmpeg** (GPL-Build, enthält x264 / x265), **Sonic** zum Dehnen des Tons (Apache-2.0, derselbe Algorithmus wie in der Android-App), **Qt / PySide6** (LGPL), **rife-ncnn-vulkan** mit dem RIFE-Modell (MIT) und **AVM**, die AV2-Referenzsoftware (BSD-3-Clause-Clear). Einzelheiten stehen in THIRD_PARTY_NOTICES.md.
