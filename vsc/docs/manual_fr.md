# Guide d’utilisation de VideoSpeedControl

VideoSpeedControl te donne un contrôle total sur la vitesse d’un clip vidéo. Découpe un clip enregistré en ralenti natif – par exemple une GoPro à 240 fps ou un ralenti de téléphone – en sections et donne à chaque section sa propre fréquence d’images : accélère le début, enchaîne avec un ralenti extrême, passe en temps réel, puis termine à nouveau au ralenti.

- **Sans perte** ne demande aucun réencodage : chaque image d’origine est conservée et seule sa durée de lecture change. L’app crée donc un clip à fréquence d’images variable en un rien de temps et sans aucune perte de qualité.
- **Réencodage smart** ne réencode que les sections dont la fréquence d’images diffère de la fréquence d’images de sortie, dans le même codec que la source, ce qui garde l’export rapide.
- **Réencoder** encode le clip entier dans le codec de ton choix, avec le même contrôle total sur la vitesse et la fréquence d’images de sortie.

L’app enregistre les modifications de vitesse de chaque clip, tu peux donc reprendre ton travail plus tard – ou encoder le même clip dans différents codecs pour les comparer, aidé par des noms de fichier générés automatiquement avec des options de nommage. Tu peux aussi rassembler de nombreux clips – ou plusieurs versions du même clip – dans une liste de lot et tous les exporter d’un seul coup.

**Sommaire**

1. Démarrage rapide
2. La fenêtre principale
3. Chargement des clips et infos du clip
4. Aperçu et coupe
5. Réglages de sortie
6. Sections de vitesse
7. Réencodage smart
8. Encodage de test et estimations de durée
9. Export et liste de lot
10. Convertir des vidéos
11. AV2 (expérimental)
12. Raccourcis clavier
13. Astuces et dépannage
14. Licence et crédits

## 1. Démarrage rapide

1. Lance VideoSpeedControl et glisse un ou plusieurs fichiers vidéo dans la fenêtre (ou clique sur **Ajouter des fichiers…**).
2. Choisis le mode de **Traitement** dans les *Réglages de sortie* à droite. **Sans perte** est le mode par défaut et le plus rapide.
3. Choisis une **Fréquence d’images** de sortie. La liste déroulante indique de combien le clip est plus lent (ou plus rapide) et quelle durée il atteint, p. ex. *« 25 fps (PAL) – 9,6× plus lent, 1:12 min »*.
4. Appuie sur **Espace** dans l’onglet *Aperçu et coupe* pour voir le résultat.
5. Ouvre l’onglet **Export**, choisis un dossier et clique sur **Démarrer l’export**.

![La fenêtre principale](images/overview.png)

### Comment fonctionne le ralenti ici

Une caméra de 240 fps enregistre 240 images par seconde. Lues à 240 fps, c’est du temps réel. Lues à 25 fps, les mêmes 240 images durent 9,6 secondes : le clip est **9,6× plus lent** – sans une seule image nouvelle ni manquante. C’est ce que fait le mode *Sans perte*. Ce n’est que si tu veux une vitesse qui ne correspond pas à la fréquence d’images (p. ex. 20× plus lent à 25 fps) que des images doivent être supprimées ou calculées, ce qui implique un réencodage.

## 2. La fenêtre principale

- **Liste des clips (en haut) :** chaque fichier chargé avec son appareil, son codec, sa résolution, sa fréquence d’images, sa durée, la sortie choisie et une estimation de la durée et de la taille de l’export.
- **Onglets (en bas à gauche) :** *Aperçu et coupe*, *Encodage de test*, *Infos du clip*, *Export*.
- **Réglages de sortie (en bas à droite) :** tout ce qui concerne la sortie du clip sélectionné, avec un récapitulatif en bas.
- **Aide** (à l’extrémité droite de la barre d’outils) : ce guide (**F1**), le guide en PDF et *À propos*.

Chaque clip a ses propres réglages. **Appliquer à tous les clips** copie les réglages de sortie du clip sélectionné sur tous les autres (les coupes et les sections de vitesse restent propres à chaque clip).

## 3. Chargement des clips et infos du clip

Glisse des fichiers ou des dossiers dans la fenêtre, ou utilise **Ajouter des fichiers…**. Tout format que FFmpeg sait lire fonctionne. Après le chargement, l’app analyse le clip (temps exacts des images et images clés) et construit en arrière-plan une petite copie d’aperçu (*« aperçu rapide 45 % »* à côté du numéro d’image).

L’onglet **Infos du clip** liste tout ce qui concerne le fichier : conteneur, codec et profil, résolution et format d’image, rotation, fréquence d’images, nombre d’images, intervalle des images clés, format de pixel, sous-échantillonnage de la chrominance, profondeur de bits, espace colorimétrique (SDR / HLG / PQ), débit, appareil et date d’enregistrement, et son.

![Infos du clip](images/clip_info.png)

### Ralenti du téléphone

Les téléphones comme le Google Pixel enregistrent le ralenti à p. ex. 240 fps mais le stockent dans un fichier de 30 fps qui est déjà lu lentement. VideoSpeedControl lit la fréquence d’enregistrement dans le fichier et considère **240 fps comme l’original** : les vitesses et les « × plus lent » se rapportent toujours au temps réel. La liste des clips affiche p. ex. *« 240 (ralenti, fichier 29,97) »*.

### Aperçus enregistrés

La liste des images, les miniatures de la timeline, la petite copie d’aperçu utilisée pour le défilement et l’analyse des images clés du réencodage smart sont enregistrées dans le dossier de cache (Linux *~/.cache/VideoSpeedControl/previews*, Windows *%LOCALAPPDATA%\VideoSpeedControl\previews*). Un clip rouvert est prêt presque aussitôt, au lieu d’être analysé et décodé à nouveau – même après l’avoir renommé ou déplacé, car il est reconnu à son contenu. L’aperçu est enregistré en petits morceaux ; si l’un est endommagé, seul ce morceau est refait.

Deux minutes après le démarrage – et seulement tant que rien de lourd ne tourne – les aperçus dont personne n’a plus besoin sont supprimés : un aperçu est conservé tant que son clip est dans la liste, dans la liste de lot, ou possède un fichier Clip Speed Treatment (.cst). Le cache est maintenu sous 2 Go.

## 4. Aperçu et coupe

![Aperçu, sections de vitesse et récapitulatif](images/sections.png)

### Se déplacer

- Clique ou glisse dans la **timeline** (miniatures avec des repères d’images clés en dessous), utilise la zone du **numéro d’image**, ou les boutons et les touches : **◀ 1 / 1 ▶** (**←/→**) une image, **− 🔑 / + 🔑** (**Maj+←/→**) image clé précédente / suivante, **⏮ / ⏭** (**Début/Fin**) première / dernière image, molette de la souris.
- Pendant que tu glisses, l’image vient de la petite copie d’aperçu – instantanément. Quand le curseur se repose un instant, l’image nette en taille réelle la remplace.
- **Ajuster / 100 % / 200 %** zoome l’image ; glisse pour la déplacer, double-clique pour basculer.

### Lire l’aperçu

**▶ Lire l’aperçu** (ou **Espace**) lit la sortie à la fréquence d’images et à la vitesse choisies – en taille réduite et sans encodage, donc elle démarre aussitôt. La lecture va du curseur jusqu’au point de sortie. L’interpolation de mouvement et RIFE sont montrées sous forme de simple fondu (elles sont trop lentes pour le temps réel). Si l’ordinateur ne décode pas assez vite (p. ex. 240 fps en temps réel), une remarque indique que l’aperçu est plus lent que ne le sera l’export.

### Coupe (entrée / sortie)

**Définir l’entrée (I)** et **Définir la sortie (O)** marquent la première et la dernière image de la sortie ; **Effacer la coupe** les supprime. Les parties assombries de la timeline ne sont pas exportées.

En mode **Sans perte** et **Réencodage smart**, les points d’entrée et de sortie **s’alignent sur les images clés**. Une indication jaune en explique la raison : seules les images clés sont des images complètes ; toutes les autres n’enregistrent que les différences avec leurs voisines et ne peuvent plus être affichées une fois l’image clé qui les précède coupée. Choisis *Réencoder* pour des coupes précises à l’image.

## 5. Réglages de sortie

### Traitement

| Mode | Ce qui se passe | Ce que tu peux modifier |
|---|---|---|
| **Sans perte** | Chaque image reste intacte ; seule sa durée de lecture change. Des secondes au lieu de minutes, aucune perte de qualité. | Fréquence d’images, conteneur, sections de vitesse, coupe (aux images clés) |
| **Réencodage smart** | Copie le clip et ne réencode que les sections que tu marques – voir le chapitre 7. | Sections de vitesse avec leur propre fréquence d’images de sortie, qualité et préréglage des parties réencodées, conteneur |
| **Réencoder** | Le clip entier est encodé à nouveau. | Tout : codec, taille, vitesse, fréquence d’images, interpolation |

Seuls les réglages que le mode choisi peut utiliser sont activés.

**Easy / Pro** (en haut des réglages de sortie) : *Easy* masque les détails du codec – le codec lui-même, le profil, le préréglage, la qualité, la chroma et la profondeur de bits. Le réencodage smart utilise alors toujours le codec de la source et Réencoder toujours **AV1 (rapide)**, chacun avec son préréglage et sa qualité par défaut. En Easy, chaque changement de vitesse entre des sections est aussi **adouci** automatiquement (0,5 s, voir chapitre 6) – les interrupteurs *Douceur en entrée / en sortie* n’apparaissent qu’en Pro. *Pro* affiche tous les réglages (les images de ce guide montrent Pro). Passer en Easy applique les réglages Easy à tous les clips.

- Choisir **Réencodage smart** marque pour le réencodage chaque section de vitesse dont la fréquence d’images diffère de sa fréquence d’images de sortie ; les sections qui sont déjà lues à cette fréquence restent copiées (tu peux modifier les coches dans le tableau).
- Passer de Smart à **Réencoder** sélectionne à nouveau AV1 (rapide).

![Réglages de sortie en mode Réencoder](images/settings_reencode.png)

### Fréquence d’images et vitesse

- **Fréquence d’images :** les fréquences standard (23,976 … 120 fps) plus la fréquence propre du clip, marquée *(original)*. Chaque entrée indique le ralentissement et la durée de sortie quand toutes les images sont conservées.
- **Vitesse** (Réencoder) : *Sans perte* utilise chaque image une fois. *Personnalisée* définit une vitesse quelconque (p. ex. 0,05× = 20× plus lent) – plus rapide que la vitesse sans perte, des images sont supprimées ; plus lent, des images intermédiaires sont calculées (voir *Interpolation*). *Préréglages…* propose des valeurs courantes.
- La ligne en dessous indique la **durée de sortie** et de combien elle est plus lente ou plus rapide que l’original.

### Codec et conteneur

La liste des codecs est regroupée en **Sans perte** (FFV1, Ut Video, MagicYUV, HuffYUV, H.264 / HEVC / VP9 / AV1 / AV2 sans perte, QuickTime Animation, séquences d’images), **Avec perte** (H.264, HEVC, AV1, VP9, ProRes, DNxHR, CineForm, MJPEG, AV2) et **Matériel** (NVIDIA, Intel, AMD – proposés seulement si un encodage de test sur ton ordinateur a fonctionné). Chaque entrée a une infobulle qui explique à quoi elle sert. La liste des **conteneurs** ne propose que les formats qui peuvent contenir le codec choisi. Quand tu passes à *Réencoder*, **AV1 (SVT-AV1, rapide)** est présélectionné – petits fichiers à bonne qualité ; *AV1 (libaom, meilleure qualité)* compresse un peu mieux mais est bien plus lent.

### Préréglage

Combien de temps l’encodeur cherche la meilleure compression. À réglage de qualité égal, un préréglage plus lent donne un **fichier plus petit** et prend **plus de temps** ; la qualité visible change à peine. Chaque entrée indique ce qu’elle fait, p. ex. *« veryslow – le plus lent, fichier le plus petit »*. (Pour CineForm, la ligne s’appelle *Compression* – c’est ici un niveau de qualité.)

### Qualité

Des niveaux nommés qui signifient à peu près la même chose pour chaque codec ; la valeur propre au codec est indiquée entre parenthèses :

| Niveau | Signification |
|---|---|
| Visuellement sans perte | Aucune différence visible, même sur une image fixe. Fichiers gros. |
| Haute (par défaut) | Presque aucune perte visible – idéal pour la suite du montage et l’archivage. |
| Bonne | Qualité streaming (YouTube, Netflix) : suffisante pour regarder. |
| Moyenne | Pertes visibles de près, p. ex. dans les détails fins ou les zones sombres. |
| Petit fichier | Pertes nettement visibles – pour des aperçus ou un envoi rapide. |

**Personnalisée…** te permet de saisir la valeur propre au codec. Descendre d’un niveau rend le fichier environ 30 à 50 % plus petit.

### Chroma et profondeur de bits

- **Sous-échantillonnage de la chrominance :** 4:4:4 (détail de couleur complet – VFX, haut de gamme), 4:2:2 (télévision broadcast), 4:2:0 (streaming, Netflix, YouTube). Seules les combinaisons prises en charge par le codec sont proposées.
- **Profondeur de bits :** 8 bits ou 10 bits. *Comme la source* conserve ce que le clip possède.

### Résolution, format et mise à l’échelle

- **Résolution :** conserver la taille de la source, des préréglages de 480p à DCI 4K (y compris 9:16 et 1:1) ou une taille personnalisée.
- **Format :** conserver les proportions d’origine (ajuster dans le cadre) ou imposer une taille de cadre / un format d’image ; **Ajustement** choisit entre des bandes noires (remplissage), le recadrage (découpe) ou l’étirement.
- **Mise à l’échelle :** la méthode de rééchantillonnage avec des notes de qualité et de vitesse – Lanczos est la plus nette, Area la plus propre pour une forte réduction.

### Interpolation

Utilisée quand la vitesse est plus lente que la vitesse sans perte et que de nouvelles images intermédiaires sont nécessaires :

- **Duplication d’images** – répète des images ; le mouvement saccade. Le plus rapide.
- **Fondu d’images** – fond les images voisines en fondu enchaîné ; fluide mais avec des images fantômes.
- **Interpolation de mouvement (minterpolate)** – calcule de vraies images intermédiaires sur le CPU ; bon pour les mouvements lents et réguliers. Très lent.
- **RIFE (IA)** – réseau de neurones sur la carte graphique (Vulkan, aussi les graphiques intégrés) ; mouvement nettement meilleur. Fonctionne en RVB 8 bits. Indisponible avec des sections de vitesse ou l’AV2.

### Son

Le bouton **Son** juste sous *Traitement* active ou coupe le son en un clic : **🔊 Son activé – hauteur conservée** (par défaut) ou **🔇 Son coupé**. Avec le son activé, l’app prend la première piste audio du clip et l’étire ou la comprime à la nouvelle durée de la vidéo – la **hauteur reste la même**, il n’y a donc ni voix graves ni voix aiguës. Les sections de vitesse reçoivent chacune leur propre facteur d’étirement, le son suit donc chaque section. Un ralenti très fort rend la parole difficile à comprendre (elle est simplement 10× plus lente), mais elle garde sa hauteur.

**Ralenti du téléphone :** les téléphones enregistrent le son d’un clip au ralenti ralenti comme une bande magnétique – il sonne grave. VideoSpeedControl lui rend d’abord sa vraie hauteur et sa vraie durée en temps réel, puis l’étire à la vidéo.

Le son est ajouté une fois la vidéo terminée, une vidéo **sans perte** reste donc sans perte ; seule la piste audio est encodée (AAC en MP4 / MOV / MKV, Opus en WebM, PCM en AVI / MXF). Les séquences d’images et les fichiers AV2 (FFmpeg ne gère pas encore l’AV2) restent sans son – le bouton est alors grisé et son infobulle en donne la raison.

## 6. Sections de vitesse

Les sections de vitesse donnent à des parties d’un clip leur propre fréquence d’images – par exemple le saut au ralenti, l’élan en temps réel, la réception 8× plus rapide.

1. Place le curseur sur la première image et clique sur **Début de section [** (touche **[**).
2. Place-toi sur la dernière image et clique sur **Fin de section ]** (touche **]**). Un cadre en pointillés marque la plage.
3. Choisis la fréquence d’images (de 23,976 fps jusqu’à **8× plus rapide** que l’original) et clique sur **Ajouter la section**.

**Plus rapide :** saute l’étape 1. Sans début marqué, **Fin de section ]** démarre la section juste après la section précédente – ou au début du clip (coupe) s’il n’y en a pas – les sections s’enchaînent donc sans trous. Dans une section existante, elle démarre au début de cette section (la section est scindée).

Les sections apparaissent comme des bandes bleues dans la timeline et dans le tableau en dessous, où tu peux modifier leur fréquence d’images, y aller (clic) ou les supprimer (✕). Tout ce qui est en dehors des sections est lu en **temps réel**. Une nouvelle section qui en chevauche une existante l’emporte.

- **Modifier une section :** clique dessus dans la timeline ou dans le tableau pour la sélectionner. **Début = tête de lecture** / **Fin = tête de lecture** déplacent sa première / dernière image jusqu’au curseur ; la fréquence d’images se change dans le tableau.
- **Déplacer une limite :** les limites entre les sections (et entre une section et le temps réel) sont des lignes blanches avec une poignée sous les miniatures. Glisse une limite pour allonger une section et raccourcir sa voisine ; l’image montre le cadre à la limite pendant que tu glisses. Un glissement compte pour une étape d’annulation.
- **Transitions douces :** coche **Douceur en entrée** / **Douceur en sortie** dans le tableau pour que la vitesse change progressivement au lieu de sauter – p. ex. d’un ralenti 9,6× au temps réel. Le changement dure **0,5 s** de la sortie et est centré sur la limite (plus court si une section est trop courte) ; la timeline l’affiche comme un champ sombre avec une ligne oblique (montante = de plus en plus rapide). Il fonctionne dans chaque mode de traitement ; en réencodage smart, la transition est réencodée quand une section voisine l’est.

- **Curseur magnétique 🧲 :** quand tu glisses près d’une section, le curseur s’aimante sur l’image qui la suit (pour continuer sans rupture) ou – pendant que tu marques une fin – sur l’image juste avant la section suivante. Clique sur 🧲 pour le désactiver.
- **Effacer les sections** (à droite) supprime toutes les sections après confirmation.
- **↶ Annuler** (**Ctrl+Z**) et **↷ Rétablir** (**Ctrl+Maj+Z** ou **Ctrl+Y**) reculent et avancent à travers chaque modification des sections – ajout, modification, déplacement, suppression, effacement, chargement – jusqu’à 200 étapes, séparément pour chaque clip. Le nombre sur le bouton indique combien d’étapes tu peux reculer (ou avancer) ; survole-le pour voir quelle modification il annule.

### Enregistrer et charger un Clip Speed Treatment (.cst)

**Enregistrer un Clip Speed Treatment…** dans la barre d’outils (**Ctrl+S**) enregistre les sections, la coupe et les réglages de sortie du clip actuel dans un fichier *Clip Speed Treatment* (`.cst`). Il est proposé par défaut dans *Documents/VideoSpeedControl/Clip Speed Treatments* – l’app Android y enregistre aussi. **Charger un Clip Speed Treatment…** (**Ctrl+L**) – ou le dépôt d’un `.cst` sur la fenêtre – le recharge. L’app Android lit et écrit les mêmes fichiers.

Un traitement appartient à une seule vidéo : il enregistre une empreinte du contenu du fichier et ne se charge que sur cette vidéo. Le nom du fichier n’a pas d’importance – une copie renommée ou déplacée correspond toujours. Si la vidéo n’est pas encore dans la liste mais se trouve toujours là où elle était lors de l’enregistrement, elle est ajoutée automatiquement. Un traitement ne se charge jamais sur une autre vidéo, car ses numéros d’images ne correspondraient pas.

La façon dont les sections sont exportées dépend du mode de traitement :

- **Sans perte :** chaque image est conservée avec sa propre durée de lecture – un fichier à **fréquence d’images variable**. Les sections peuvent commencer à n’importe quelle image. Il est lu par tous les lecteurs courants ; les logiciels de montage préfèrent une fréquence d’images constante. Des sections très rapides (p. ex. 1920 fps) font décoder autant d’images par seconde aux lecteurs – choisis le réencodage pour une lecture fluide dans ce cas.
- **Réencoder :** le clip entier est converti à la **fréquence d’images constante** choisie ; les sections rapides suppriment des images, les lentes reçoivent des images intermédiaires.
- **Réencodage smart :** voir le chapitre suivant.

## 7. Réencodage smart

Le réencodage smart combine les deux : les sections marquées **Réencoder** dans le tableau des sections sont encodées avec le **codec de la source** à leur propre **Fps de sortie** ; tout le reste est copié tel quel. Toutes les parties sont assemblées en **un seul fichier**.

![Réglages de sortie en mode Réencodage smart](images/settings_smart.png)

À savoir :

- **Uniquement pour les séquences H.264 et HEVC** (p. ex. GoPro, téléphones). Le codec est fixé sur le codec de la source – sinon les parties ne pourraient pas être assemblées.
- **Assemblage uniquement aux images clés.** Les points d’entrée et de sortie s’y alignent, et les sections réencodées sont automatiquement élargies jusqu’aux images clés les plus proches – les images supplémentaires sont réencodées à la vitesse qu’elles ont de toute façon. Certaines caméras écrivent des images clés « ouvertes » où les images suivantes dépendent encore des précédentes ; l’app les détecte au chargement du clip et n’assemble pas à cet endroit.
- **Non lisible sur les appareils Apple.** Le fichier assemblé modifie les réglages du décodeur à l’intérieur du flux (balise MP4 *hev1* / *avc3*). QuickTime, iPhone, iPad et Final Cut ne peuvent pas le lire – VLC, mpv, Windows, Android, Chrome et Firefox le peuvent. Pour Apple, réencode plutôt le clip entier.
- La fréquence d’images de sortie choisie en dernier devient la valeur par défaut de la prochaine section réencodée.

## 8. Encodage de test et estimations de durée

L’onglet **Encodage de test** encode quelques images (100 par défaut) à partir de la position du curseur avec exactement les réglages de sortie. Il affiche la vitesse d’encodage, la taille du fichier et une **estimation pour le clip entier**, et compare la source et la sortie **côte à côte** ou avec un **volet** – zoomable à 100 % et 200 %. Teste sur une partie chargée du clip pour une estimation sûre. Le bouton *Commande FFmpeg* montre ce qui est exécuté.

![Encodage de test avec comparaison côte à côte](images/test_encode.png)

Les estimations apparaissent aussi dans la liste des clips. Les clips avec les mêmes réglages partagent un test, mis à l’échelle selon leur taille.

## 9. Export et liste de lot

![Onglet Export avec la liste de lot](images/export.png)

- **Enregistrer dans :** à côté de chaque fichier source, ou un dossier.
- **Nom de fichier :** un modèle avec des variables – `{name}` nom de la source, `{speed}` facteur de vitesse, `{slower}` combien de fois plus lent, `{fps}` fréquence d’images de sortie, `{codec}`, `{res}` taille de sortie, `{mode}` lossless / smart / reencode, `{n}` position dans la file.
- **Si le fichier existe :** ajouter un numéro, écraser ou ignorer.
- **Export :** tous les clips, les clips sélectionnés ou la **liste de lot**.
- La progression est affichée par clip et pour l’ensemble du lot ; **Annuler** l’arrête, et les fichiers incomplets sont supprimés.

### Liste de lot

**➕ Ajouter au lot** (onglet Aperçu et coupe) enregistre le clip exactement tel qu’il est à cet instant – mode de traitement, réglages, coupe et toutes les sections – comme une entrée de la liste de lot. Les sections restent en place, tu peux donc ajouter plusieurs fois le même clip, p. ex. une fois en *Sans perte* et une fois en *Réencodage smart*. Les modifications ultérieures du clip ne changent pas les entrées déjà dans la liste. La liste reste après l’export ; **Retirer de la liste** et **Vider la liste** la gèrent. Les entrées exportées avec succès sont marquées **Terminé** et ne sont pas réexportées quand tu cliques plus tard sur **Démarrer l’export** – seules les entrées ajoutées (ou échouées / annulées) depuis lors sont traitées. Pour exporter à nouveau une entrée terminée, modifie-la avec *Modifier cette entrée*, ou supprime son fichier de sortie. Utilise `{mode}` dans le nom de fichier pour distinguer les versions.

**Double-clique sur une entrée** de la liste de lot pour la rouvrir : ses sections, sa coupe et ses réglages sont chargés dans Aperçu et coupe (les sections précédentes du clip peuvent être récupérées avec ↶ Annuler). On te demande ce que tu veux faire :

- **Autre encodage** – modifie le codec, le préréglage, la qualité ou la taille et clique sur **➕ Ajouter au lot** : une nouvelle entrée est ajoutée, l’ancienne reste.
- **Modifier cette entrée** – modifie-la et clique sur **✔ Mettre à jour l’entrée du lot** : l’entrée est remplacée.

Chaque fois que tu ajoutes un clip déjà présent dans la liste de lot, VideoSpeedControl demande si tu veux un autre encodage et propose des **compléments de nom** avec des cases à cocher – codec, préréglage, qualité et résolution, p. ex. `jump_x265_slow_high_1920x1080.mp4`. Un aperçu montre le nom de fichier obtenu ; ton choix de cases est mémorisé.

## 10. Convertir des vidéos

**Convertir des vidéos…** (barre d’outils) réencode de nombreuses vidéos à la fois – par exemple un dossier de vieux fichiers AVI / DivX vers un codec moderne. C’est indépendant de la liste des clips et des réglages de vitesse : chaque image est conservée une fois, la durée reste la même, et les originaux ne sont jamais modifiés. Ajoute des fichiers ou des dossiers entiers (avec les sous-dossiers si tu veux) ou dépose-les sur la fenêtre. Les nouveaux fichiers vont dans un dossier *Converted* à côté de chaque original, ou dans un dossier de ton choix ; les fichiers existants ne sont jamais écrasés.

**Easy** (en haut à droite) : codec, niveau de qualité et *Garder le son* – plus **Smart**.

**Pro** affiche tous les réglages :

| Réglage | Ce qu’il fait |
|---|---|
| **Fréquence d’images** | *Original* (chaque vidéo garde la sienne) ou une fréquence de la liste. Une autre fréquence conserve la durée : des images sont supprimées ou répétées, jamais inventées. |
| **Conteneur** | MP4, MOV ou MKV. L’AV1 ne peut pas être stocké en MOV, donc MOV est grisé pour l’AV1. |
| **Codec** | AV1 (SVT-AV1 ou libaom), HEVC, H.264. |
| **Image** | *Niveau de qualité*, une *valeur de qualité propre* (le CRF du codec), un *débit* en kbit/s, ou *Smart*. |
| **Son** | *Smart*, *Copier sans modification*, AAC, Opus, MP3, FLAC ou *Pas de son*, avec les **canaux** (comme l’original, mono, stéréo, 5.1, 7.1 – jamais plus que l’original) et le **débit du son**. |

Les réglages sont les **réglages généraux** de chaque vidéo. Sélectionne une ou plusieurs vidéos et clique sur **Réglages propres pour la sélection** pour leur donner leurs propres réglages – la colonne Réglages affiche alors *Propres : …* ; sélectionne-les à nouveau plus tard pour les modifier, ou clique sur **Retour aux réglages généraux**. Les combinaisons qui ne fonctionnent pas sont marquées d’un ⚠ dans la liste (par exemple copier du son MP3 dans du MOV), et la conversion attend qu’elles soient corrigées.

### Smart : des fichiers plus petits avec la même image et le même son

Avec **Smart**, chaque vidéo est mesurée avant d’être convertie : trois courts échantillons sont encodés à plusieurs valeurs de qualité et comparés à l’original par **VMAF** (un score perceptuel de 0 à 100). Le plus petit fichier qui atteint encore l’objectif est utilisé :

- **Identique à l’œil** (par défaut) : aucune différence visible (VMAF ≥ 96 en moyenne, chaque échantillon ≥ 94,5).
- **Plus petit, perte minimale** : nettement plus petit, une légère perte seulement de près (VMAF ≥ 93).

Le son est **copié tel quel** quand le conteneur peut le contenir – rien n’est perdu et c’est le choix le plus petit ; sinon il devient de l’AAC avec les mêmes canaux et la même fréquence d’échantillonnage, à un débit adapté à la source (par exemple MP3 96 kbit/s → AAC 80 kbit/s). La colonne Réglages affiche le résultat avant la conversion, p. ex. *qualité 27 ≈ 145 kbit/s, ~28 %*. **Mesurer maintenant** mesure sans convertir ; *Convertir* mesure de toute façon d’abord. La mesure dure environ 20 secondes pour une petite vieille vidéo et plus longtemps pour du HD.

Un réencodage ne peut jamais être meilleur que sa source – Smart conserve ce qui existe et économise de l’espace. Exemple : de vieux dessins animés DivX (368×208, 10 fps) sont devenus des fichiers AV1 d’environ 30 à 40 % de leur taille, avec le son MP3 copié.

## 11. AV2 (expérimental)

L’AV2 est le successeur de l’AV1 (AOMedia, spécification 1.0 de mai 2026), environ 30 % plus petit à qualité égale. FFmpeg ne gère pas encore l’AV2, l’app utilise donc le logiciel de référence AVM. C’est un outil de recherche et **extrêmement lent** – environ 75 secondes par image 1080p sur le CPU d’un portable, environ 20 secondes en 360p – utilise-le donc pour des clips courts et de petites tailles. Les encodages de test utilisent au plus 5 images. La sortie est en IVF ou WebM ; presque aucun lecteur ne sait encore lire l’AV2. Sous Linux, l’encodeur est construit avec `tools/fetch_avm.py` ; sans lui, l’AV2 est indiqué comme indisponible.

## 12. Raccourcis clavier

| Touche | Action |
|---|---|
| F1 | Ce guide d’utilisation |
| Ctrl+O | Ajouter des fichiers |
| Suppr | Retirer les clips sélectionnés |
| Espace | Lire / arrêter l’aperçu |
| ← / → | Image précédente / suivante |
| Maj+← / → | Image clé précédente / suivante |
| Début / Fin | Première / dernière image |
| I / O | Définir le point d’entrée / de sortie |
| [ / ] | Début / fin de section |
| Ctrl+Z | Annuler la dernière modification des sections |
| Ctrl+Maj+Z / Ctrl+Y | Rétablir |
| Ctrl+S | Enregistrer un Clip Speed Treatment (.cst) |
| Ctrl+L | Charger un Clip Speed Treatment (.cst) |

## 13. Astuces et dépannage

- **Quel mode ?** Sans perte chaque fois que les fréquences d’images correspondent – c’est instantané et parfait. Réencodage smart quand seules certaines parties ont besoin d’une fréquence d’images constante. Réencoder pour une autre taille, un autre codec ou une fréquence d’images constante adaptée au montage.
- **Logiciels de montage et fréquence d’images variable :** DaVinci Resolve et Premiere gèrent mal les fichiers à fréquence d’images variable. Exporte avec Réencoder (p. ex. ProRes ou DNxHR) pour le montage.
- **L’aperçu saccade :** les fréquences d’images très élevées (240 fps en temps réel) demandent plus de puissance de décodage que n’en ont beaucoup de portables – l’export n’est pas affecté.
- **Pas d’encodeur matériel :** les encodeurs matériels ne sont proposés que si un encodage de test sur ton ordinateur fonctionne ; les encodeurs logiciels fonctionnent toujours.
- **RIFE est lent ou indisponible :** RIFE a besoin d’une carte graphique compatible Vulkan ; sur des graphiques intégrés il est lent, sans Vulkan il n’est pas proposé.
- **Le son est difficile à comprendre :** c’est normal pour un fort ralenti – une parole 10× plus lente garde sa hauteur mais est étirée. Coupe le son (🔇) ou ajoute de la musique plus tard.
- **Réencodage smart est grisé :** le clip n’est pas en H.264 / HEVC, l’analyse des images clés est encore en cours, ou aucune image clé ne permet un assemblage.

## 14. Licence et crédits

Copyright © 2026 Alex Vulcu. Concept, architecture, direction et curation par Alex Vulcu. Réalisation assistée par des outils d’IA générative. Sous licence MIT – voir le fichier LICENSE.

VideoSpeedControl utilise d’autres logiciels open source avec leur propre licence : **FFmpeg** (build GPL, comprend x264 / x265), **Sonic** pour l’étirement du son (Apache-2.0, le même algorithme que l’app Android), **Qt / PySide6** (LGPL), **rife-ncnn-vulkan** avec le modèle RIFE (MIT) et **AVM**, le logiciel de référence AV2 (BSD-3-Clause-Clear). Les détails se trouvent dans THIRD_PARTY_NOTICES.md.
