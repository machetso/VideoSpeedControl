# Ghid de utilizare VideoSpeedControl

VideoSpeedControl îți oferă control deplin asupra vitezei unui clip video. Împarte în secțiuni un clip înregistrat în slow motion nativ – de exemplu o GoPro la 240 fps sau o înregistrare cu încetinitorul a unui telefon – și dă fiecărei secțiuni propria rată de cadre: accelerează începutul, continuă cu un slow motion extrem, treci la timp real și încheie din nou în slow motion.

- **Fără pierderi** nu necesită deloc recodare: fiecare cadru original este păstrat și se schimbă doar timpul de redare al acestuia, astfel încât aplicația creează un clip cu rată de cadre variabilă practic instantaneu și fără nicio pierdere de calitate.
- **Recodare Smart** recodează doar secțiunile a căror rată de cadre diferă de rata de cadre de ieșire, în același codec ca sursa, ceea ce păstrează exportul rapid.
- **Recodare** codează întregul clip într-un codec la alegerea ta, cu același control deplin asupra vitezei și ratei de cadre de ieșire.

Aplicația salvează editările de viteză ale fiecărui clip, astfel încât îți poți relua lucrul mai târziu – sau poți codifica același clip în codecuri diferite pentru a le compara, ajutat de numele de fișier generate automat, cu opțiuni de denumire. De asemenea, poți aduna mai multe clipuri – sau mai multe versiuni ale aceluiași clip – într-o listă batch și le poți exporta pe toate dintr-o dată.

**Cuprins**

1. Pornire rapidă
2. Fereastra principală
3. Încărcarea clipurilor și informațiile despre clip
4. Previzualizare și decupare
5. Setări de ieșire
6. Secțiuni de viteză
7. Recodare Smart
8. Codare de test și estimări de timp
9. Export și lista batch
10. Convertirea videoclipurilor
11. AV2 (experimental)
12. Scurtături de tastatură
13. Sfaturi și depanare
14. Licență și mulțumiri

## 1. Pornire rapidă

1. Pornește VideoSpeedControl și trage unul sau mai multe fișiere video în fereastră (sau fă clic pe **Adaugă fișiere…**).
2. Alege modul de **Procesare** în *Setări de ieșire*, în dreapta. **Fără pierderi** este implicit și cel mai rapid.
3. Alege o **Rată de cadre** de ieșire. Lista derulantă arată cu cât mai lent (sau mai rapid) rulează clipul și cât de lung devine, de ex. *„25 fps (PAL) – de 9,6× mai lent, 1:12 min"*.
4. Apasă **Space** în fila *Previzualizare & decupare* pentru a vedea rezultatul.
5. Deschide fila **Export**, alege un folder și fă clic pe **Pornește exportul**.

![Fereastra principală](images/overview.png)

### Cum funcționează aici slow motion

O cameră de 240 fps înregistrează 240 de imagini pe secundă. Redate la 240 fps, acestea sunt timp real. Redate la 25 fps, aceleași 240 de imagini durează 9,6 secunde: clipul este **de 9,6× mai lent** – fără nicio imagine nouă sau lipsă. Asta face modul *Fără pierderi*. Doar când vrei o viteză care nu se potrivește cu rata de cadre (de ex. de 20× mai lent la 25 fps) trebuie ca imaginile să fie sărite sau calculate, ceea ce înseamnă recodare.

## 2. Fereastra principală

- **Lista de clipuri (sus):** fiecare fișier încărcat, cu dispozitivul, codecul, rezoluția, rata de cadre, durata, ieșirea aleasă și o estimare a timpului și a dimensiunii exportului.
- **File (jos, stânga):** *Previzualizare & decupare*, *Codare de test*, *Informații clip*, *Export*.
- **Setări de ieșire (jos, dreapta):** tot ce ține de ieșirea clipului selectat, cu un rezumat în partea de jos.
- **Ajutor** (capătul din dreapta al barei de instrumente): acest ghid (**F1**), ghidul ca PDF și *Despre*.

Fiecare clip are propriile setări. **Aplică la toate clipurile** copiază setările de ieșire ale clipului selectat la toate celelalte (decupările și secțiunile de viteză rămân per clip).

## 3. Încărcarea clipurilor și informațiile despre clip

Trage fișiere sau foldere în fereastră ori folosește **Adaugă fișiere…**. Funcționează orice format pe care FFmpeg îl poate citi. După încărcare, aplicația scanează clipul (momentele exacte ale cadrelor și keyframe-urile) și construiește în fundal o mică copie de previzualizare (*„previzualizare rapidă 45 %"* lângă numărul cadrului).

Fila **Informații clip** listează tot ce ține de fișier: container, codec și profil, rezoluție și raport de aspect, rotație, rată de cadre, număr de cadre, intervalul dintre keyframe-uri, format de pixel, subeșantionare chroma, adâncime de biți, spațiu de culoare (SDR / HLG / PQ), rată de biți, dispozitiv și dată de înregistrare, precum și sunet.

![Informații clip](images/clip_info.png)

### Slow motion pe telefon

Telefoane precum Google Pixel înregistrează slow motion la, de exemplu, 240 fps, dar îl stochează ca fișier de 30 fps care deja rulează încet. VideoSpeedControl citește rata de înregistrare din fișier și consideră **240 fps drept original**: vitezele și „× mai lent" se raportează întotdeauna la timpul real. Lista de clipuri arată de ex. *„240 (slow-mo, fișier 29,97)"*.

### Previzualizări stocate

Lista de cadre, miniaturile din cronologie, mica copie de previzualizare folosită la derulare și analiza keyframe-urilor pentru recodarea Smart sunt stocate în folderul cache (Linux *~/.cache/VideoSpeedControl/previews*, Windows *%LOCALAPPDATA%\VideoSpeedControl\previews*). Un clip deschis din nou este gata aproape imediat, în loc să fie scanat și decodat încă o dată – chiar și după redenumire sau mutare, deoarece este recunoscut după conținut. Previzualizarea este stocată în bucăți mici; dacă una este deteriorată, doar acea bucată se face din nou.

La două minute după pornire – și doar cât timp nu rulează nimic greu – sunt șterse previzualizările de care nu mai are nevoie nimeni: o previzualizare rămâne cât timp clipul ei se află în listă, în lista batch sau are un fișier Clip Speed Treatment (.cst). Cache-ul este ținut sub 2 GB.

## 4. Previzualizare și decupare

![Previzualizare, secțiuni de viteză și rezumat](images/sections.png)

### Deplasarea

- Fă clic sau glisează în **cronologie** (miniaturi cu marcaje de keyframe sub ele), folosește caseta cu **numărul cadrului** ori butoanele și tastele: **◀ 1 / 1 ▶** (**←/→**) un cadru, **− 🔑 / + 🔑** (**Shift+←/→**) keyframe-ul anterior / următor, **⏮ / ⏭** (**Home/End**) primul / ultimul cadru, rotița mouse-ului.
- Cât timp glisezi, imaginea provine din mica copie de previzualizare – instantaneu. Când cursorul stă o clipă pe loc, cadrul clar, la dimensiune completă, îl înlocuiește.
- **Potrivire / 100 % / 200 %** mărește imaginea; glisează pentru a o deplasa, dublu clic pentru a comuta.

### Redarea previzualizării

**▶ Redă previzualizarea** (sau **Space**) redă ieșirea la rata de cadre și viteza alese – la dimensiune redusă și fără codare, deci pornește imediat. Redarea merge de la cursor până la punctul de sfârșit. Interpolarea mișcării și RIFE sunt afișate ca simplă amestecare (sunt prea lente pentru timp real). Dacă computerul nu poate decoda destul de repede (de ex. 240 fps în timp real), o notă spune că previzualizarea rulează mai lent decât va rula exportul.

### Decupare (început / sfârșit)

**Setează începutul (I)** și **Setează sfârșitul (O)** marchează primul și ultimul cadru al ieșirii; **Șterge decuparea** le elimină. Părțile estompate ale cronologiei nu sunt exportate.

În modurile **Fără pierderi** și **Recodare Smart**, punctele de început și de sfârșit se **aliniază la keyframe-uri**. O indicație galbenă explică de ce: doar keyframe-urile sunt imagini complete; toate celelalte cadre stochează doar diferențele față de vecinii lor și nu pot fi afișate odată ce keyframe-ul dinaintea lor a fost tăiat. Alege *Recodare* pentru tăieturi exacte la nivel de cadru.

## 5. Setări de ieșire

### Procesare

| Mod | Ce se întâmplă | Ce poți schimba |
|---|---|---|
| **Fără pierderi** | Fiecare cadru rămâne neatins; se schimbă doar timpul său de redare. Secunde în loc de minute, fără pierdere de calitate. | Rata de cadre, container, secțiuni de viteză, decupare (la keyframe-uri) |
| **Recodare Smart** | Copiază clipul și recodează doar secțiunile pe care le marchezi – vezi capitolul 7. | Secțiuni de viteză cu propria rată de cadre de ieșire, calitatea și presetarea părților recodate, container |
| **Recodare** | Întregul clip este codat din nou. | Totul: codec, dimensiune, viteză, rată de cadre, interpolare |

Sunt activate doar setările pe care modul ales le poate folosi.

**Easy / Pro** (sus, în setările de ieșire): *Easy* ascunde detaliile codecului – codecul însuși, profilul, presetarea, calitatea, chroma și adâncimea de biți. Recodarea Smart folosește atunci întotdeauna codecul sursei, iar recodarea întotdeauna **AV1 (rapid)**, fiecare cu presetarea și calitatea implicite. În Easy, fiecare schimbare de viteză dintre secțiuni este de asemenea **netezită** automat (0,5 s, vezi capitolul 6) – comutatoarele *Intrare lină / Ieșire lină* apar doar în Pro. *Pro* arată toate setările (imaginile din acest ghid arată Pro). Trecerea la Easy aplică setările Easy la toate clipurile.

- Alegerea **Recodare Smart** marchează pentru recodare fiecare secțiune de viteză a cărei rată de cadre diferă de rata ei de cadre de ieșire; secțiunile care rulează deja la aceasta rămân copiate (poți schimba bifele în tabel).
- Trecerea de la Smart la **Recodare** selectează din nou AV1 (rapid).

![Setări de ieșire în modul Recodare](images/settings_reencode.png)

### Rata de cadre și viteza

- **Rată de cadre:** ratele standard (23,976 … 120 fps) plus rata proprie a clipului, marcată *(original)*. Fiecare intrare arată încetinirea și durata ieșirii când fiecare cadru este păstrat.
- **Viteză** (Recodare): *Fără pierderi* folosește fiecare cadru o singură dată. *Personalizat…* setează orice viteză (de ex. 0,05× = de 20× mai lent) – mai rapid decât viteza fără pierderi sare cadre, mai lent calculează cadre intermediare (vezi *Interpolare*). *Presetări…* oferă valori uzuale.
- Linia de dedesubt arată **durata de ieșire** și cu cât este mai lentă sau mai rapidă decât originalul.

### Codec și container

Lista de codecuri este grupată în **Fără pierderi** (FFV1, Ut Video, MagicYUV, HuffYUV, H.264 / HEVC / VP9 / AV1 / AV2 fără pierderi, QuickTime Animation, secvențe de imagini), **Cu pierderi** (H.264, HEVC, AV1, VP9, ProRes, DNxHR, CineForm, MJPEG, AV2) și **Hardware** (NVIDIA, Intel, AMD – oferite doar dacă o codare de test pe computerul tău a reușit). Fiecare intrare are un tooltip care explică la ce este bună. Lista **Container** oferă doar formatele care pot conține codecul ales. Când treci la *Recodare*, este preselectat **AV1 (SVT-AV1, rapid)** – fișiere mici la calitate bună; *AV1 (libaom, cea mai bună calitate)* comprimă puțin mai bine, dar este mult mai lent.

### Presetare

Cât timp caută codificatorul cea mai bună compresie. La aceeași setare de calitate, o presetare mai lentă dă un **fișier mai mic** și durează **mai mult**; calitatea vizibilă se schimbă puțin. Fiecare intrare spune ce face, de ex. *„veryslow – cel mai lent, cel mai mic fișier"*. (Pentru CineForm rândul se numește *Compresie* – acolo este un nivel de calitate.)

### Calitate

Niveluri denumite care înseamnă aproximativ același lucru pentru fiecare codec; valoarea proprie a codecului este afișată între paranteze:

| Nivel | Semnificație |
|---|---|
| Vizual fără pierderi | Nicio diferență vizibilă, nici măcar într-un cadru static. Fișiere mari. |
| Înaltă (implicit) | Aproape nicio pierdere vizibilă – bună pentru editare ulterioară și arhivare. |
| Bună | Calitate de streaming (YouTube, Netflix): potrivită pentru vizionare. |
| Medie | Pierderi vizibile la o privire atentă, de ex. în detalii fine sau zone întunecate. |
| Fișier mic | Pierderi clar vizibile – pentru previzualizări sau trimitere rapidă. |

**Personalizat…** îți permite să introduci valoarea proprie a codecului. Un nivel mai jos face fișierul cu aproximativ 30–50 % mai mic.

### Chroma și adâncimea de biți

- **Subeșantionare chroma:** 4:4:4 (detaliu de culoare complet – VFX, nivel înalt), 4:2:2 (televiziune), 4:2:0 (streaming, Netflix, YouTube). Sunt oferite doar combinațiile pe care codecul le acceptă.
- **Adâncime de biți:** 8 biți sau 10 biți. *Ca sursa* păstrează ce are clipul.

### Rezoluție, aspect și scalare

- **Rezoluție:** păstrează dimensiunea sursei, presetări de la 480p până la DCI 4K (inclusiv 9:16 și 1:1) sau personalizat.
- **Aspect:** păstrează proporțiile originale (potrivit în cadru) sau impune o dimensiune de cadru / un raport de aspect; **Potrivire** decide între benzi negre (completare), tăiere (crop) sau întindere.
- **Scalare:** metoda de reeșantionare, cu evaluări de calitate și viteză – Lanczos este cea mai clară, Area cea mai curată pentru reduceri puternice.

### Interpolare

Folosită când viteza este mai lentă decât viteza fără pierderi și sunt necesare imagini intermediare noi:

- **Duplicarea cadrelor** – repetă imaginile; mișcarea sacadează. Cea mai rapidă.
- **Amestecarea cadrelor** – estompează încrucișat vecinii; fluent, dar cu imagini fantomă.
- **Interpolarea mișcării (minterpolate)** – calculează imagini intermediare reale pe procesor; bună pentru mișcare lentă și uniformă. Foarte lentă.
- **RIFE (AI)** – rețea neuronală pe placa video (Vulkan, inclusiv grafică integrată); mișcare clar mai bună. Funcționează pe RGB pe 8 biți. Nu este disponibilă împreună cu secțiunile de viteză sau cu AV2.

### Sunet

Butonul **Sunet** de chiar sub *Procesare* pornește sau oprește sunetul cu un singur clic: **🔊 Sunet pornit – tonalitate păstrată** (implicit) sau **🔇 Sunet oprit**. Cu sunetul pornit, aplicația ia prima pistă audio a clipului și o întinde sau o comprimă la noua lungime a videoclipului – **tonalitatea rămâne aceeași**, deci nu apar voci grave sau piţigăiate. Secțiunile de viteză primesc fiecare propriul factor de întindere, astfel încât sunetul urmează fiecare secțiune. Un slow motion foarte puternic face vorbirea greu de înțeles (este pur și simplu de 10× mai lentă), dar își păstrează tonalitatea.

**Slow motion pe telefon:** telefoanele stochează sunetul unui clip slow motion încetinit ca o bandă de magnetofon – sună grav. VideoSpeedControl îl readuce mai întâi la tonalitatea lui reală și la lungimea în timp real, apoi îl întinde la video.

Sunetul este adăugat după ce videoclipul este gata, deci un videoclip **fără pierderi** rămâne fără pierderi; se codează doar pista audio (AAC în MP4 / MOV / MKV, Opus în WebM, PCM în AVI / MXF). Secvențele de imagini și fișierele AV2 (FFmpeg nu poate încă lucra cu AV2) rămân fără sunet – butonul este atunci estompat, iar tooltip-ul său spune de ce.

## 6. Secțiuni de viteză

Secțiunile de viteză dau unor părți ale unui clip propria rată de cadre – de exemplu săritura în slow motion, elanul în timp real, aterizarea de 8× mai rapidă.

1. Mută cursorul pe primul cadru și fă clic pe **Început de secțiune [** (tasta **[**).
2. Mută-te pe ultimul cadru și fă clic pe **Sfârșit de secțiune ]** (tasta **]**). Un cadru întrerupt marchează intervalul.
3. Alege rata de cadre (de la 23,976 fps până la **de 8× mai rapid** decât originalul) și fă clic pe **Adaugă secțiune**.

**Mai rapid:** sari peste pasul 1. Fără un început marcat, **Sfârșit de secțiune ]** pornește secțiunea imediat după secțiunea dinaintea ei – sau la începutul clipului (decupare) dacă nu există niciuna – astfel încât secțiunile se succed fără goluri. În interiorul unei secțiuni existente, pornește de la începutul acelei secțiuni (secțiunea este împărțită).

Secțiunile apar ca benzi albastre în cronologie și în tabelul de sub ea, unde le poți schimba rata de cadre, poți sări la ele (clic) sau le poți elimina (✕). Tot ce se află în afara secțiunilor rulează în **timp real**. O secțiune nouă care se suprapune peste una existentă câștigă.

- **Editarea unei secțiuni:** fă clic pe ea în cronologie sau în tabel pentru a o selecta. **Început = cursor de redare** / **Sfârșit = cursor de redare** mută primul / ultimul ei cadru la cursor; rata de cadre se schimbă în tabel.
- **Mutarea unei limite:** limitele dintre secțiuni (și dintre o secțiune și timpul real) sunt linii albe cu un mâner sub miniaturi. Trage o limită pentru a face o secțiune mai lungă și vecina ei mai scurtă; imaginea arată cadrul de la limită cât timp tragi. O tragere este un pas de anulare.
- **Tranziții line:** bifează **Intrare lină** / **Ieșire lină** în tabel pentru ca viteza să se schimbe uniform, în loc să sară – de ex. de la slow motion de 9,6× la timp real. Schimbarea durează **0,5 s** din ieșire și este centrată pe limită (mai scurtă dacă o secțiune este prea scurtă); cronologia o arată ca un câmp întunecat cu o linie oblică (urcătoare = devine mai rapid). Funcționează în fiecare mod de procesare; în recodarea Smart, tranziția este recodată când o secțiune vecină cu ea este recodată.

- **Cursor magnetic 🧲:** când tragi aproape de o secțiune, cursorul se aliniază la cadrul imediat următor ei (pentru a continua fără întrerupere) sau – cât timp marchezi un sfârșit – la cadrul imediat dinaintea secțiunii următoare. Fă clic pe 🧲 pentru a-l dezactiva.
- **Șterge secțiunile** (dreapta) elimină toate secțiunile, după ce întreabă.
- **↶ Anulează** (**Ctrl+Z**) și **↷ Refă** (**Ctrl+Shift+Z** sau **Ctrl+Y**) merg înapoi și înainte prin fiecare modificare a secțiunilor – adăugare, schimbare, mutare, eliminare, ștergere, încărcare – până la 200 de pași, separat pentru fiecare clip. Numărul de pe buton arată câți pași poți face înapoi (sau înainte); ține cursorul deasupra pentru a vedea ce modificare anulează.

### Salvarea și încărcarea unui Clip Speed Treatment (.cst)

**Salvează Clip Speed Treatment…** din bara de instrumente (**Ctrl+S**) salvează secțiunile, decuparea și setările de ieșire ale clipului curent ca fișier *Clip Speed Treatment* (`.cst`). Este oferit implicit în *Documents/VideoSpeedControl/Clip Speed Treatments* – aplicația Android salvează și ea acolo. **Încarcă Clip Speed Treatment…** (**Ctrl+L**) – sau aruncarea unui `.cst` peste fereastră – îl încarcă din nou. Aplicația Android citește și scrie aceleași fișiere.

Un treatment aparține exact unui videoclip: stochează o amprentă a conținutului fișierului și se încarcă doar pe acel videoclip. Numele fișierului nu contează – o copie redenumită sau mutată se potrivește în continuare. Dacă videoclipul nu este încă în listă, dar se află tot unde era când ai salvat, este adăugat automat. Un treatment nu se încarcă niciodată pe un alt videoclip, deoarece numerele lui de cadre nu s-ar potrivi.

Modul în care sunt exportate secțiunile depinde de modul de procesare:

- **Fără pierderi:** fiecare cadru este păstrat cu propriul timp de redare – **un fișier** cu **rată de cadre variabilă**. Secțiunile pot începe la orice cadru. Rulează în toate playerele uzuale; programele de editare preferă o rată de cadre constantă. Secțiunile foarte rapide (de ex. 1920 fps) fac ca playerele să decodeze atâtea cadre pe secundă – alege recodarea pentru o redare fluentă acolo.
- **Recodare:** întregul clip este convertit la **rata de cadre constantă** aleasă; secțiunile rapide sar imagini, cele lente primesc imagini intermediare.
- **Recodare Smart:** vezi capitolul următor.

## 7. Recodare Smart

Recodarea Smart le combină pe amândouă: secțiunile marcate **Recodare** în tabelul de secțiuni sunt codate cu **codecul sursei** la propriul **Fps de ieșire**; tot restul este copiat neschimbat. Toate părțile sunt unite într-**un singur fișier**.

![Setări de ieșire în modul Recodare Smart](images/settings_smart.png)

Lucruri de știut:

- **Doar pentru material H.264 și HEVC** (de ex. GoPro, telefoane). Codecul este fixat la codecul sursei – altfel părțile nu ar putea fi unite.
- **Îmbinări doar la keyframe-uri.** Punctele de început și de sfârșit se aliniază la ele, iar secțiunile recodate sunt extinse automat până la cele mai apropiate keyframe-uri – cadrele suplimentare sunt recodate la viteza pe care oricum o au. Unele camere scriu keyframe-uri „deschise", la care cadrele următoare încă depind de cele anterioare; aplicația le detectează la încărcarea clipului și nu face îmbinări acolo.
- **Nu poate fi redat pe dispozitive Apple.** Fișierul unit schimbă setările decodorului în interiorul fluxului (eticheta MP4 *hev1* / *avc3*). QuickTime, iPhone, iPad și Final Cut nu îl pot reda – VLC, mpv, Windows, Android, Chrome și Firefox pot. Pentru Apple, recodează în schimb întregul clip.
- Rata de cadre de ieșire aleasă ultima dată devine implicită pentru următoarea secțiune recodată.

## 8. Codare de test și estimări de timp

Fila **Codare de test** codează câteva cadre (implicit 100) de la poziția cursorului, cu setările exacte de ieșire. Arată viteza de codare, dimensiunea fișierului și o **estimare pentru întregul clip** și compară sursa și ieșirea **una lângă alta** sau cu o **cortină** – cu mărire la 100 % și 200 %. Testează într-o parte aglomerată a clipului pentru o estimare sigură. Butonul *Comandă FFmpeg* arată ce se rulează.

![Codare de test cu comparație una lângă alta](images/test_encode.png)

Estimările apar și în lista de clipuri. Clipurile cu aceleași setări împart un test, scalat după dimensiunea lor.

## 9. Export și lista batch

![Fila Export cu lista batch](images/export.png)

- **Salvează în:** lângă fiecare fișier sursă sau într-un folder.
- **Nume fișier:** un șablon cu substituenți – `{name}` numele sursei, `{speed}` factorul de viteză, `{slower}` de câte ori mai lent, `{fps}` rata de cadre de ieșire, `{codec}`, `{res}` dimensiunea ieșirii, `{mode}` lossless / smart / reencode, `{n}` poziția în coadă.
- **Dacă fișierul există:** adaugă un număr, suprascrie sau omite.
- **Export:** toate clipurile, clipurile selectate sau **lista batch**.
- Progresul este afișat per clip și pentru întregul batch; **Anulează** îl oprește, iar fișierele incomplete sunt șterse.

### Lista batch

**➕ Adaugă în batch** (fila Previzualizare & decupare) salvează clipul exact așa cum este în acel moment – mod de procesare, setări, decupare și toate secțiunile – ca intrare în lista batch. Secțiunile rămân pe loc, deci poți adăuga același clip de mai multe ori, de ex. o dată *Fără pierderi* și o dată *Recodare Smart*. Modificările ulterioare ale clipului nu schimbă intrările deja aflate în listă. Lista rămâne după export; **Elimină din listă** și **Golește lista** o gestionează. Intrările exportate cu succes sunt marcate **Gata** și nu sunt exportate din nou când faci clic mai târziu pe **Pornește exportul** – rulează doar intrările adăugate (sau eșuate / anulate) de atunci. Pentru a exporta din nou o intrare gata, modific-o cu *Editează această intrare* sau șterge fișierul ei de ieșire. Folosește `{mode}` în numele fișierului pentru a deosebi versiunile.

**Dublu clic pe o intrare** din lista batch o deschide din nou: secțiunile, decuparea și setările ei sunt încărcate în Previzualizare & decupare (secțiunile anterioare ale clipului pot fi readuse cu ↶ Anulează). Ești întrebat ce vrei să faci:

- **Altă codare** – schimbă codecul, presetarea, calitatea sau dimensiunea și fă clic pe **➕ Adaugă în batch**: se adaugă o intrare nouă, cea veche rămâne.
- **Editează această intrare** – modifică-o și fă clic pe **✔ Actualizează intrarea batch**: intrarea este înlocuită.

De fiecare dată când adaugi un clip aflat deja în lista batch, VideoSpeedControl întreabă dacă vrei o altă codare și oferă **completări de nume** cu casete de bifat – codec, presetare, calitate și rezoluție, de ex. `jump_x265_slow_high_1920x1080.mp4`. O previzualizare arată numele de fișier rezultat; alegerea ta de casete este reținută.

## 10. Convertirea videoclipurilor

**Convertește videoclipuri…** (bara de instrumente) recodează mai multe videoclipuri deodată – de exemplu un folder cu fișiere AVI / DivX vechi într-un codec modern. Este independent de lista de clipuri și de setările de viteză: fiecare cadru este păstrat o singură dată, durata rămâne aceeași, iar originalele nu sunt niciodată modificate. Adaugă fișiere sau foldere întregi (cu subfoldere, dacă vrei) ori aruncă-le peste fereastră. Fișierele noi merg într-un folder *Converted* lângă fiecare original sau într-un folder ales de tine; fișierele existente nu sunt niciodată suprascrise.

**Easy** (sus, dreapta): codec, nivel de calitate și *Păstrează sunetul* – plus **Smart**.

**Pro** arată toate setările:

| Setare | Ce face |
|---|---|
| **Rată de cadre** | *Original* (fiecare videoclip își păstrează rata) sau o rată din listă. O altă rată păstrează durata: cadrele sunt eliminate sau repetate, niciodată inventate. |
| **Container** | MP4, MOV sau MKV. AV1 nu poate fi stocat în MOV, deci MOV este estompat pentru AV1. |
| **Codec** | AV1 (SVT-AV1 sau libaom), HEVC, H.264. |
| **Imagine** | *Nivel de calitate*, o *valoare proprie de calitate* (CRF-ul codecului), o *rată de date* în kbit/s sau *Smart*. |
| **Sunet** | *Smart*, *Copiază neschimbat*, AAC, Opus, MP3, FLAC sau *Fără sunet*, cu **canale** (ca originalul, mono, stereo, 5.1, 7.1 – niciodată mai multe decât are originalul) și **rata de date a sunetului**. |

Setările sunt **setările generale** pentru fiecare videoclip. Selectează unul sau mai multe videoclipuri și fă clic pe **Setări proprii pentru cele selectate** pentru a le da propriile setări – coloana Setări arată atunci *Proprii: …*; selectează-le din nou mai târziu pentru a le schimba sau fă clic pe **Înapoi la setările generale**. Combinațiile care nu funcționează sunt marcate cu ⚠ în listă (de exemplu copierea sunetului MP3 în MOV), iar conversia așteaptă până când sunt remediate.

### Smart: fișiere mai mici cu aceeași imagine și același sunet

Cu **Smart**, fiecare videoclip este măsurat înainte de a fi convertit: trei mostre scurte sunt codate la mai multe valori de calitate și comparate cu originalul prin **VMAF** (un scor perceptiv de la 0 la 100). Se folosește cel mai mic fișier care încă atinge ținta:

- **Arată la fel** (implicit): nicio diferență vizibilă (VMAF ≥ 96 în medie, fiecare mostră ≥ 94,5).
- **Mai mic, pierderi minime**: vizibil mai mic, o ușoară pierdere doar la o privire atentă (VMAF ≥ 93).

Sunetul este **copiat neschimbat** când containerul îl poate conține – nu se pierde nimic și este alegerea cea mai mică; altfel devine AAC cu aceleași canale și aceeași rată de eșantionare, la o rată de date potrivită cu sursa (de exemplu MP3 96 kbit/s → AAC 80 kbit/s). Coloana Setări arată rezultatul înainte de conversie, de ex. *calitate 27 ≈ 145 kbit/s, ~28 %*. **Măsoară acum** măsoară fără a converti; *Convertește* oricum măsoară mai întâi. Măsurarea durează cam 20 de secunde pentru un videoclip vechi și mic și mai mult pentru HD.

O recodare nu poate fi niciodată mai bună decât sursa ei – Smart păstrează ce există și economisește spațiul. Exemplu: desene animate DivX vechi (368×208, 10 fps) au devenit fișiere AV1 de cam 30–40 % din dimensiunea lor, cu sunetul MP3 copiat.

## 11. AV2 (experimental)

AV2 este succesorul lui AV1 (AOMedia, specificația 1.0 din mai 2026), cu aproximativ 30 % mai mic la aceeași calitate. FFmpeg nu poate încă lucra cu AV2, așa că aplicația folosește software-ul de referință AVM. Este un instrument de cercetare și **extrem de lent** – cam 75 de secunde pe cadru 1080p pe un procesor de laptop, cam 20 de secunde la 360p – așa că folosește-l pentru clipuri scurte și dimensiuni mici. Codările de test folosesc cel mult 5 cadre. Ieșirea este IVF sau WebM; aproape niciun player nu poate încă reda AV2. Pe Linux, codificatorul este construit cu `tools/fetch_avm.py`; fără el, AV2 este afișat ca indisponibil.

## 12. Scurtături de tastatură

| Tastă | Acțiune |
|---|---|
| F1 | Acest ghid de utilizare |
| Ctrl+O | Adaugă fișiere |
| Delete | Elimină clipurile selectate |
| Space | Redă / oprește previzualizarea |
| ← / → | Cadrul anterior / următor |
| Shift+← / → | Keyframe-ul anterior / următor |
| Home / End | Primul / ultimul cadru |
| I / O | Setează punctul de început / de sfârșit |
| [ / ] | Început / sfârșit de secțiune |
| Ctrl+Z | Anulează ultima modificare a secțiunilor |
| Ctrl+Shift+Z / Ctrl+Y | Refă |
| Ctrl+S | Salvează Clip Speed Treatment (.cst) |
| Ctrl+L | Încarcă Clip Speed Treatment (.cst) |

## 13. Sfaturi și depanare

- **Ce mod?** Fără pierderi ori de câte ori ratele de cadre se potrivesc – este instantaneu și perfect. Recodare Smart când doar anumite părți au nevoie de o rată de cadre constantă. Recodare pentru o altă dimensiune, alt codec sau o rată de cadre constantă potrivită pentru editare.
- **Programe de editare și rată de cadre variabilă:** DaVinci Resolve și Premiere lucrează prost cu fișierele cu rată de cadre variabilă. Exportă cu Recodare (de ex. ProRes sau DNxHR) pentru editare.
- **Previzualizarea sacadează:** ratele de cadre foarte mari (240 fps în timp real) cer mai multă putere de decodare decât au multe laptopuri – exportul nu este afectat.
- **Niciun codificator hardware:** codificatoarele hardware sunt oferite doar când o codare de test pe computerul tău funcționează; codificatoarele software funcționează întotdeauna.
- **RIFE este lent sau indisponibil:** RIFE are nevoie de o placă video compatibilă Vulkan; pe grafica integrată este lent, fără Vulkan nu este oferit.
- **Sunetul este greu de înțeles:** este normal pentru un slow motion puternic – vorbirea de 10× mai lentă își păstrează tonalitatea, dar este întinsă. Oprește sunetul (🔇) sau adaugă muzică mai târziu.
- **Recodare Smart este estompată:** clipul nu este H.264 / HEVC, analiza keyframe-urilor încă rulează sau niciun keyframe nu permite o îmbinare.

## 14. Licență și mulțumiri

Copyright © 2026 Alex Vulcu. Concept, arhitectură, direcție și curatoriat de Alex Vulcu. Implementare asistată de instrumente de IA generativă. Licențiat sub licența MIT – vezi fișierul LICENSE.

VideoSpeedControl folosește alt software open-source, cu propria licență: **FFmpeg** (build GPL, include x264 / x265), **Sonic** pentru întinderea sunetului (Apache-2.0, același algoritm ca în aplicația Android), **Qt / PySide6** (LGPL), **rife-ncnn-vulkan** cu modelul RIFE (MIT) și **AVM**, software-ul de referință AV2 (BSD-3-Clause-Clear). Detaliile se găsesc în THIRD_PARTY_NOTICES.md.
