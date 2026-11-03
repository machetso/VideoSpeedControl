# VideoSpeedControl für Android – Anleitung

Mit VideoSpeedControl bestimmst du, welche Stellen eines Videos in Zeitlupe, in normaler Geschwindigkeit oder schneller laufen. Die App ist für Zeitlupen-Aufnahmen gemacht – etwa die 240-fps-Zeitlupe eines Smartphones –, funktioniert aber mit jedem Video. Du markierst **Clip Sections** (Abschnitte), gibst jedem eine eigene Geschwindigkeit und speicherst das Ergebnis als neues Video. Das Original wird nie verändert.

Diese Anleitung erklärt alles kurz und den **Pro**-Modus ausführlich.

**Inhalt**

1. Easy und Pro
2. Schnellstart
3. Der Bildschirm
4. Bilder, Bildraten und Geschwindigkeit
5. Genau positionieren
6. Clip Sections im Pro-Modus
7. Zuschnitt
8. Export: verlustfrei, Smart, neu kodieren
9. Ton
10. Batch-Liste
11. Clip Speed Treatments
12. Das Menü hinter dem Logo
13. Tipps und Problemlösungen
14. Lizenz und Hinweise zu Drittsoftware

## 1. Easy und Pro

Die App hat zwei Modi. Du kannst jederzeit wechseln – über das **Easy / Pro**-Abzeichen neben dem App-Namen, den Schalter in der Speichern-Karte oder im Menü hinter dem Logo. Deine Abschnitte und Einstellungen bleiben erhalten.

- **Easy** (Standard) zeigt nur, was du für schnelle Ergebnisse brauchst: Clip Sections mit einer einfachen Videogeschwindigkeit („4× langsamer“), die gelben Klammern auf der Zeitleiste zum Zuschneiden und **Video speichern**. Jeder Geschwindigkeitswechsel wird automatisch weich. Smart behält den Codec des Originals, beim Neu-Kodieren wählt die App den Codec und eine hohe Qualität.
- **Pro** ergänzt alles für genaues Arbeiten: Bildnummern und Bildraten, Keyframe-Tasten, Abschnitts-Anfang und -Ende an der Abspielposition, weiche Übergänge je Grenze, die Zuschnitt-Karte, die Auswahl, welche Teile Smart neu kodiert, Codec, Qualität und Auflösung beim Neu-Kodieren, eine Geschwindigkeit für das Neu-Kodieren ohne Abschnitte und das Speichern von Änderungen in einen Eintrag der Batch-Liste.

## 2. Schnellstart

1. Tippe auf **Clip wählen** und such dir ein Video aus – am besten eine Zeitlupen-Aufnahme. Die Galerie der App zeigt den Kamera-Ordner, das neueste Video zuerst; **Andere Dateien …** öffnet jede andere Datei.
2. Geh mit der Abspielposition dorthin, wo ein Abschnitt enden soll, und tippe auf **Ende ]**. Der erste Abschnitt beginnt am Anfang des Clips, jeder weitere direkt nach dem vorherigen.
3. Tippe den Abschnitt in der Liste (oder auf der Zeitleiste) an und wähle seine Geschwindigkeit.
4. Zieh die gelben Klammern auf der Zeitleiste, um Anfang und Ende wegzuschneiden.
5. Prüfe das Ergebnis mit **▶ Vorschau abspielen** und tippe dann auf **Video speichern**. Das Video erscheint in *Movies/VideoSpeedControl*.

## 3. Der Bildschirm

Von oben nach unten:

- **Kopfzeile** – das Logo (öffnet das Menü), das **Easy / Pro**-Abzeichen und **＋ Clip** für das nächste Video. Hat der aktuelle Clip ungespeicherte Abschnitte, fragt die App, ob er zuerst in die Batch-Liste soll.
- **Vorschau** – das aktuelle Bild. Wisch seitlich über das Bild, um Bild für Bild zu gehen.
- **Zeitleiste** – Bilder aus dem Clip mit den Clip Sections (farbig, mit ihrer Geschwindigkeit beschriftet), ihren Grenzen, den weichen Übergängen, den gelben Zuschnitt-Klammern, den Keyframe-Strichen unter dem Streifen und der Abspielposition.
- **Steuerung** – Vorschau abspielen, Länge und Geschwindigkeit der Ausgabe, der Magnet 🧲 und die Tasten zum Bewegen im Clip.
- **Clip Sections** – die Abschnittsliste und der Abschnitts-Editor.
- **Zuschnitt** (Pro) – Anfangs- und Endpunkt als Bildnummern.
- **Speichern / Export** – Modus, Bildrate, Codec und die Speichern-Tasten.
- **Batch-Liste** – Videos, die noch gespeichert werden oder schon gespeichert sind.
- **Clip Speed Treatment** – deine Bearbeitung als Datei speichern und laden.
- **Clip-Infos** – Angaben zur Aufnahme: Gerät, Datum, Größe, Codec, Bildrate, Zeitlupen-Faktor, Ton.

## 4. Bilder, Bildraten und Geschwindigkeit

Ein Video besteht aus vielen Einzelbildern. Pro zeigt Bildnummern und Bildraten – deshalb hier kurz, wie sie zusammenhängen:

- Die **Aufnahme-Bildrate** gibt an, wie viele Bilder pro Sekunde die Kamera aufgenommen hat – 240 fps bei einer 240-fps-Zeitlupe. Smartphones speichern solche Clips so, dass sie mit etwa 30 fps abgespielt werden; die App liest die echte Aufnahme-Bildrate aus der Datei.
- Die **Bildrate eines Abschnitts** gibt an, wie viele dieser Bilder pro Sekunde gezeigt werden. Mit der Aufnahme-Bildrate läuft der Abschnitt in **Echtzeit**; mit 30 fps läuft eine 240-fps-Aufnahme **8× langsamer**; über der Aufnahme-Bildrate läuft er **schneller**.
- Die **Ausgabe-Bildrate** ist die Bildrate des gespeicherten Videos (24 bis 120 fps). Sie spielt bei Smart und beim Neu-Kodieren eine Rolle – siehe Abschnitt 8.

Pro listet die Bildraten mit der Geschwindigkeit daneben; *(Original)* kennzeichnet die Aufnahme-Bildrate, also Echtzeit. Easy zeigt nur die Geschwindigkeit („4× langsamer“, „Echtzeit“); dort kennzeichnet *(Original)* die Geschwindigkeit, bei der jedes aufgenommene Bild genau einmal mit der Ausgabe-Bildrate gezeigt wird – die Zeitlupe, wie das Handy sie aufgenommen hat.

## 5. Genau positionieren

Pro zeigt über den Steuertasten eine Zeile wie: *Frame 812 / 2400 · Keyframe · Quelle 3,38 s · Ausgabe 9,20 s*. *Quelle* ist die Zeit in der Originalaufnahme, *Ausgabe* die Zeit im gespeicherten Video (oder *weggeschnitten*, wenn das Bild außerhalb des Zuschnitts liegt).

Die Tasten von links nach rechts:

- **|◀** erstes Bild, **▶|** letztes Bild
- **− 🔑 / 🔑 +** vorheriger / nächster **Keyframe** (Pro) – warum Keyframes wichtig sind, steht in Abschnitt 7
- **◀ 1 / 1 ▶** ein Bild zurück / vor

Auf der Zeitleiste **tippst** du, um die Abspielposition zu setzen (und den Abschnitt dort auszuwählen), und **ziehst**, um durch den Clip zu fahren. Wischen über das Vorschaubild bewegt Bild für Bild, feiner als die Zeitleiste.

Der **Magnet 🧲** lässt die Abspielposition an Abschnittsgrenzen einrasten, wenn sie in die Nähe kommt – praktisch, um den nächsten Abschnitt genau dort beginnen zu lassen, wo der vorherige endet. Antippen schaltet ihn ein oder aus.

Während die App die Bilder zum Durchfahren vorbereitet, zeigt ein dünner Balken auf der Zeitleiste den Fortschritt. Clips, die du erneut öffnest, sind fast sofort bereit – die App bewahrt diese Vorschauen eine Weile auf (siehe Abschnitt 12).

## 6. Clip Sections im Pro-Modus

**Neue Abschnitte laufen mit** legt die Bildrate des nächsten Abschnitts fest, den du hinzufügst.

**Abschnitt hinzufügen.** Geh zum letzten Bild des Abschnitts und tippe auf **Ende ]**. Ohne markierten Anfang beginnt der Abschnitt direkt nach dem vorherigen – der erste am Anfang des Clips. Für den nächsten Abschnitt gehst du also einfach weiter und tippst wieder auf **Ende ]**. Tippe nur dann zuerst auf **[ Anfang**, wenn ein Abschnitt woanders beginnen soll; **Abbrechen** verwirft einen markierten Anfang. Innerhalb eines bestehenden Abschnitts teilt **Ende ]** ihn. Bilder zwischen den Abschnitten laufen in Echtzeit.

**Abschnitt bearbeiten.** Tippe ihn in der Liste oder auf der Zeitleiste an. Der Abschnitts-Editor zeigt:

- **Bildrate** – seine Geschwindigkeit.
- **Anfang = Abspielposition / Ende = Abspielposition** – eine Grenze auf das aktuelle Bild setzen.
- **Weicher Übergang hinein / hinaus** – statt zu springen, ändert sich die Geschwindigkeit gleichmäßig über 0,5 s, mittig um die Grenze (in Easy ist jeder Wechsel weich). Der Schalter ist aus, wenn auf der anderen Seite dieselbe Geschwindigkeit gilt.
- **Abschnitt entfernen** und **Fertig** zum Schließen des Editors.

Du kannst eine **Grenze** auch auf der Zeitleiste **ziehen** (sie hat einen kleinen Griff); die Vorschau folgt ihr.

**↶ Rückgängig / ↷ Wiederholen** merken sich bis zu 200 Schritte je Clip; die Tasten zeigen, wie viele es sind, und Pro zeigt die **letzte Änderung**. **Abschnitte löschen** entfernt nach einer Rückfrage alle Abschnitte – auch das lässt sich rückgängig machen.

## 7. Zuschnitt

In Easy schneidest du mit den gelben Klammern auf der Zeitleiste. Pro hat zusätzlich die Karte **Zuschnitt**: **Anfang setzen** und **Ende setzen** an der Abspielposition, **Zurücksetzen** für den ganzen Clip, und den Bereich als Bildnummern.

Verlustfrei und Smart können nur an **Keyframes** schneiden (die Striche unter der Zeitleiste). Nur Keyframes sind vollständige Bilder; alle anderen Bilder speichern nur die Unterschiede zu ihren Nachbarn. In diesen Modi rasten Anfang und Ende deshalb am nächsten Keyframe ein. Beim Neu-Kodieren lässt sich an jedem Bild schneiden.

## 8. Export: verlustfrei, Smart, neu kodieren

Den Modus wählst du oben in der Export-Karte.

**Verlustfrei** lässt jedes Bild unverändert und ändert nur, wann es gezeigt wird. Das geht sehr schnell und ohne Qualitätsverlust. Ohne Abschnitte kannst du in Pro die **Bildrate** wählen – jede Auswahl zeigt die sich ergebende Geschwindigkeit und Länge. Mit Abschnitten bestimmen die Abschnitte das Timing, der Rest läuft in Echtzeit. Das gespeicherte Video behält die unterschiedlichen Bildraten seiner Teile: Schnelle Teile einer Zeitlupe behalten ihre hohe Bildrate, die viele Player nicht flüssig zeigen können, und manche Geräte spielen solche Dateien gar nicht ab.

**Smart** kodiert nur die Teile neu, bei denen es nötig ist, und kopiert den Rest unverändert – viel schneller als alles neu zu kodieren, und die kopierten Teile behalten ihre volle Qualität. Pro zeigt:

- **Ausgabe-Bildrate** des gespeicherten Videos.
- **Alles neu kodieren, was nicht mit N fps läuft** – die automatische Auswahl. Jeder Teil, dessen Bildrate von der Ausgabe-Bildrate abweicht, wird auf sie neu kodiert, die anderen werden kopiert.
- Die **Liste der Teile** mit je einem Häkchen – schalte die automatische Auswahl aus, um selbst zu entscheiden. Ein kopierter Teil behält seine eigene Bildrate („läuft evtl. nicht flüssig“).
- **Qualität neu kodierter Teile**.
- Eine Zusammenfassung: wie viele Teile und Bilder neu kodiert werden und die Länge der Ausgabe. Neu kodierte Teile werden bis zum nächsten Keyframe erweitert.

Smart funktioniert mit H.264- und HEVC-Videos, noch nicht mit HDR-Videos (10 Bit). Die neu kodierten Teile haben immer Codec und Größe des Originals – sonst ließen sich die Teile nicht zusammenfügen. Das Ergebnis läuft möglicherweise nicht auf Apple-Geräten.

**Neu kodieren** erzeugt ein komplett neues Video mit konstanter Bildrate: Langsame Teile wiederholen Bilder, schnelle Teile lassen Bilder weg, und das Video läuft überall flüssig. Es nutzt den Hardware-Encoder des Handys und schneidet an jedem Bild. Pro bietet:

- **Ausgabe-Bildrate**.
- **Geschwindigkeit** (nur ohne Abschnitte): *Jedes Bild einmal* zeigt jedes aufgenommene Bild genau einmal mit der Ausgabe-Bildrate; die anderen Einträge legen die Geschwindigkeit direkt fest – langsamer als *Jedes Bild einmal* wiederholt Bilder.
- **Codec**: **AV1 (schnell)** – kleine Dateien, braucht einen Hardware-AV1-Encoder (wird nur angeboten, wenn das Handy einen hat); **AV1 (beste Qualität, langsam)** – der Software-Encoder, deutlich langsamer; **HEVC (H.265)** und **H.264** – laufen fast überall, H.264 sogar auf alten Geräten.
- **Qualität**: Gut, Hoch oder Sehr hoch.
- **Auflösung**: unverändert oder kleiner (2160p bis 480p).
- Eine Zeile mit Größe, Bildanzahl, Länge und ungefährer Bitrate.

Hat das Handy keinen Encoder für den gewählten Codec, die Größe und die Bildrate, sagt dir ein roter Hinweis das schon vor dem Speichern. Wähle dann einen anderen Codec, eine kleinere Auflösung oder eine niedrigere Bildrate.

**Speichern.** **Export** (Easy: *Video speichern*) speichert das Video in *Movies/VideoSpeedControl*. Die Datei erscheint erst, wenn sie vollständig ist; bis dahin zeigt die Karte *Wird noch gespeichert … n %*. Die App arbeitet im Hintergrund weiter – du kannst in andere Apps wechseln. Ist das Video fertig, erscheinen **▶ Abspielen** und **📁 Ordner öffnen**.

## 9. Ton

Der Schalter **Ton** übernimmt den Ton ins gespeicherte Video. Er wird auf die neue Länge jedes Teils gedehnt und behält seine natürliche Tonhöhe – Zeitlupe klingt also nicht tiefer. Smartphones speichern den Ton von Zeitlupen verlangsamt wie ein Tonband; die App stellt zuerst die echte Tonhöhe wieder her.

## 10. Batch-Liste

Sammle mehrere Videos – oder mehrere Versionen desselben Videos – und speichere sie in einem Durchgang.

- **Zur Batch-Liste** (Easy: *Als neue Version hinzufügen*) fügt den aktuellen Clip mit allen Einstellungen hinzu.
- **Batch exportieren (n)** (Easy: *Alle speichern (n)*) speichert alle Einträge, die noch nicht gespeichert sind; gespeicherte werden übersprungen. **Alle abbrechen** stoppt den Vorgang.
- Jeder Eintrag zeigt ein Bild und seinen Modus. **ⓘ** zeigt Dateiname, Einstellungen und Ergebnis; das grüne ▶ spielt das gespeicherte Video ab (grau, wenn die Datei inzwischen gelöscht wurde).
- **Tippe einen Eintrag an**, um ihn in den Editor zu laden. Ändere ihn und tippe auf **✔ Änderungen in diesen Eintrag speichern** (Pro) – oder füge ihn als weitere Version hinzu.
- **Fertige entfernen** räumt die gespeicherten Einträge weg; **✕** entfernt einen einzelnen.

## 11. Clip Speed Treatments

Ein **Clip Speed Treatment** (.cst-Datei) speichert alles, was du für einen Clip vorgesehen hast – Abschnitte, Zuschnitt, Geschwindigkeiten und Export-Einstellungen –, damit du es später noch einmal ändern kannst.

- **Speichern** legt es in *Documents/VideoSpeedControl/Clip Speed Treatments* ab.
- **Laden** öffnet ein Treatment und wendet es an. Es lässt sich nur auf das Video laden, für das es erstellt wurde – die App erkennt das Video an seinem Inhalt, eine umbenannte oder verschobene Datei passt also trotzdem.
- **Teilen** schickt es weiter, zum Beispiel an deinen Computer.

Das Dateiformat ist dasselbe wie in der Desktop-App für Linux und Windows: Du kannst auf dem Handy anfangen und am Computer weitermachen oder umgekehrt.

## 12. Das Menü hinter dem Logo

Tippe oben links auf das Logo.

- **Modus** – Easy oder Pro, jeweils mit einer Beschreibung, was er bietet.
- **Sprache** – die App folgt der Sprache des Handys; hier kannst du eine andere wählen (Englisch, Deutsch, Spanisch, Französisch, Rumänisch, Hebräisch, Klingonisch).
- **Ordner** – wo die gespeicherten Videos und die Clip Speed Treatments liegen, jeweils mit **Öffnen**.
- **Vorschauen** – wie viel Platz die gespeicherten Vorschauen belegen, und **Vorschauen löschen**. Die App speichert die Bilder, die sie zum Durchfahren vorbereitet, damit ein erneut geöffneter Clip sofort bereit ist. Vorschauen, die niemand braucht, werden 2 Minuten nach dem Start automatisch gelöscht, wenn die App gerade nichts zu tun hat; zusammen belegen sie höchstens 2 GB.
- **← Zurück** oder **Schließen & zurück zur App** führen zurück zum Editor.

## 13. Tipps und Problemlösungen

- **Das gespeicherte Video ruckelt in manchen Playern.** Verlustfreie Videos und kopierte Smart-Teile behalten ihre Aufnahme-Bildrate. Nutze Smart mit der automatischen Auswahl oder kodiere neu.
- **Das Video läuft nicht auf iPhone oder Mac.** Smart-Exporte laufen möglicherweise nicht auf Apple-Geräten. Kodiere mit HEVC oder H.264 neu.
- **Anfang und Ende springen beim Setzen.** Bei Verlustfrei und Smart rasten sie an Keyframes ein (Abschnitt 7). Beim Neu-Kodieren lässt sich an jedem Bild schneiden.
- **„Die Keyframes dieses Clips werden analysiert …“** – Smart sucht zuerst die Bilder, an denen sich Teile zusammenfügen lassen. Das dauert nach dem Öffnen eines Clips einen Moment.
- **Ein roter Hinweis sagt, das Handy habe keinen Encoder.** Jedes Handy hat andere Video-Encoder. Wähle einen anderen Codec, eine andere Auflösung oder Bildrate – oder Smart statt Neu kodieren bzw. umgekehrt.
- **Das Speichern dauert lange.** Beim Neu-Kodieren wird jedes Bild verarbeitet; AV1 (beste Qualität) ist deutlich langsamer als die anderen Codecs. Verlustfrei ist am schnellsten.
- **Ein Batch-Eintrag schlägt fehl, nachdem die App geschlossen war.** Clips, die über *Öffnen mit* oder *Teilen* aus einer anderen App kommen, sind oft nur lesbar, solange die App läuft. Öffne sie stattdessen über die Galerie von VideoSpeedControl.

## 14. Lizenz und Hinweise zu Drittsoftware

Copyright © 2026 Alex Vulcu. Konzept, Architektur, Leitung und Kuratierung: Alex Vulcu. Bei der Umsetzung wurden generative KI-Werkzeuge eingesetzt.

VideoSpeedControl steht unter der **MIT-Lizenz**. Rechtlich gilt der englische Originaltext:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Sinngemäß: Jeder darf die Software kostenlos nutzen, kopieren, ändern und weitergeben, solange der Copyright-Hinweis und dieser Lizenztext dabei bleiben. Die Software wird ohne jede Gewährleistung bereitgestellt.

Die Android-App nutzt die folgende Open-Source-Software. Sie steht vollständig unter der **Apache License, Version 2.0** (https://www.apache.org/licenses/LICENSE-2.0):

| Software | Wofür |
|---|---|
| AndroidX Media3 (ExoPlayer, Transformer, Effect, Common, UI Compose) – einschließlich **Sonic** (Android Open Source Project, basierend auf Sonic von Bill Cox) | Vorschau-Wiedergabe, Video-Hilfsfunktionen, Dehnen des Tons bei gleicher Tonhöhe |
| Jetpack Compose (UI, Material 3) | die Benutzeroberfläche |
| AndroidX Core, Activity, Lifecycle | Grundfunktionen der App |
| Kotlin-Standardbibliothek und kotlinx.coroutines (JetBrains) | die Programmiersprache und Arbeit im Hintergrund |

Das Copyright dieser Komponenten liegt bei The Android Open Source Project, Google LLC und JetBrains s.r.o. sowie ihren Mitwirkenden. Sie werden „wie besehen“ bereitgestellt, ohne Gewährleistung oder Bedingungen jeglicher Art.

Zum Kodieren und Dekodieren von Videos nutzt die App die in Android eingebauten Codecs; weitere Codec-Software ist nicht enthalten.
