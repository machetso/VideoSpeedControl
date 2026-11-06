; *** Inno Setup version 6.x Klingon messages (VideoSpeedControl, 2026-11-06) ***
;
; Klingon (tlhIngan Hol), Latin transliteration as standardised by Marc Okrand.
; Case matters: a b ch D e gh H I j l m n ng o p q Q r S t tlh u v w y '
;
; Vocabulary (consistent with i18n/tlh.json of VideoSpeedControl):
;   Setup = jomwI', install = jom, installation = jomghach, uninstall = jomHa',
;   Uninstall (program) = jomHa'wI', file = ghItlh, folder/directory = 'aplo',
;   program/application = ghun, computer = De'wI', disk/drive = De' jengva',
;   path = He, shortcut = He nom, Start menu = Start DuHmey tetlh,
;   registry = pat De' tetlh, registry key = pat De' tetlh ngaQHa'moHwI',
;   settings = ghuHmey, component = 'ay', task = Qu', user = lo'wI',
;   administrator = loHwI', password = mu' pegh, code = ngoq, version = Segh,
;   source = Hal, download = Suq, extract = lel, archive = ghItlh ngaSwI',
;   OK = luq, Cancel = yImev, Yes = HIja', No = ghobe', Next = veb,
;   Back = yIchegh, Install = yIjom, Browse = yInej, Finish = yIrInmoH

[LangOptions]
; The following three entries are very important. Be sure to read and
; understand the '[LangOptions] section' topic in the help file.
LanguageName=tlhIngan Hol
; Klingon has no official Windows LCID; $0C00 = LOCALE_CUSTOM_DEFAULT.
; The user selects this language in the "Select Setup Language" dialog.
LanguageID=$0C00
LanguageCodePage=0
; If the language you are translating to requires special font faces or
; sizes, uncomment any of the following entries and change them accordingly.
;DialogFontName=
;DialogFontSize=9
;DialogFontBaseScaleWidth=7
;DialogFontBaseScaleHeight=15
;WelcomeFontName=Segoe UI
;WelcomeFontSize=14

[Messages]

; *** Application titles
SetupAppTitle=jomwI'
SetupWindowTitle=jomwI' - %1
UninstallAppTitle=jomHa'wI'
UninstallAppFullTitle=%1 jomHa'wI'

; *** Misc. common
InformationTitle=De'
ConfirmTitle=yI'ol
ErrorTitle=Qagh

; *** SetupLdr messages
SetupLdrStartupMessage=%1 jom jomwI'. bItaH DaneH'a'?
LdrCannotCreateTemp=ghItlh ratlhbe'bogh chenmoHlaHbe' jomwI'. mevpu' jomwI'
LdrCannotExecTemp=ratlhbe'bogh 'aplo'Daq ghItlh chu'laHbe' jomwI'. mevpu' jomwI'
HelpTextNote=

; *** Startup error messages
LastErrorMessage=%1.%n%nQagh %2: %3
SetupFileMissing=jomghach 'aplo'Daq ghItlh %1 tu'lu'be'. Qay' yIQaQmoH pagh ghun velqa' chu' yISuq.
SetupFileCorrupt=jomwI' ghItlhmey QIHlu'pu'. ghun velqa' chu' yISuq.
SetupFileCorruptOrWrongVer=jomwI' ghItlhmey QIHlu'pu', pagh jomwI' Segh vam lumuvlaHbe'. Qay' yIQaQmoH pagh ghun velqa' chu' yISuq.
InvalidParameter=ra'meH tlheghDaq DuH lughbe'bogh ngeHlu'pu':%n%n%1
SetupAlreadyRunning=DaH Qap jomwI'.
WindowsVersionNotSupported=De'wI'lIj Windows Segh lo'laHbe' ghun vam.
WindowsServicePackRequired=%1 Service Pack %2 pagh Segh chu'qu' poQ ghun vam.
NotOnThisPlatform=%1Daq Qapbe' ghun vam.
OnlyOnThisPlatform=%1Daq ghun vam chu'nISlu'.
OnlyOnTheseArchitectures=De'wI' yab Seghmey tlha'boghvaD chenmoHlu'pu'bogh Windows SeghmeyDaq neH ghun vam jomlaHlu':%n%n%1
WinVersionTooLowError=%1 Segh %2 pagh Segh chu'qu' poQ ghun vam.
WinVersionTooHighError=%1 Segh %2 pagh Segh chu'qu'Daq ghun vam jomlaHbe'lu'.
AdminPrivilegesRequired=ghun vam DajomDI', loHwI' pong lo'taHvIS bI'elpu'nIS.
; 'Power Users group' is an outdated term but should still be translated, not dropped or modernized
PowerUserPrivilegesRequired=ghun vam DajomDI', loHwI' pong pagh "Power Users" ghom ghot pong lo'taHvIS bI'elpu'nIS.
; 'instance' may also be translated as 'copy'
SetupAppRunningError=DaH Qap %1 'e' tu' jomwI'.%n%nDaH Hoch velqa'meyDaj tISoQmoH, ghIq bItaHmeH luq yIHot, pagh bImejmeH yImev yIHot.
UninstallAppRunningError=DaH Qap %1 'e' tu' jomHa'wI'.%n%nDaH Hoch velqa'meyDaj tISoQmoH, ghIq bItaHmeH luq yIHot, pagh bImejmeH yImev yIHot.

; *** Startup questions
PrivilegesRequiredOverrideTitle=jomwI' jom Dotlh yIwIv
PrivilegesRequiredOverrideInstruction=jom Dotlh yIwIv
PrivilegesRequiredOverrideText1=Hoch lo'wI'vaD %1 jomlaHlu' (loHwI' DuHmey poQ), pagh SoHvaD neH.
PrivilegesRequiredOverrideText2=SoHvaD neH %1 jomlaHlu', pagh Hoch lo'wI'vaD (loHwI' DuHmey poQ).
PrivilegesRequiredOverrideAllUsers=&Hoch lo'wI'vaD yIjom
PrivilegesRequiredOverrideAllUsersRecommended=&Hoch lo'wI'vaD yIjom (chuplu')
PrivilegesRequiredOverrideCurrentUser=&jIHvaD neH yIjom
PrivilegesRequiredOverrideCurrentUserRecommended=&jIHvaD neH yIjom (chuplu')

; *** Misc. errors
ErrorCreatingDir='aplo' "%1" chenmoHlaHbe' jomwI'
ErrorTooManyFilesInDir='aplo' "%1"Daq ghItlh chenmoHlaHbe'lu', ghItlhmey law'qu' ngaSmo'

; *** Setup common messages
ExitSetupTitle=jomwI'vo' yImej
ExitSetupMessage=jomghach rInbe'. DaH bImejchugh, ghun jombe'lu'.%n%nlatlh poHDaq jomwI' Dachu'qa'laH, jomghach DarInmoHmeH.%n%njomwI'vo' Damej'a'?
AboutSetupMenuItem=jomwI' &De'...
AboutSetupTitle=jomwI' De'
AboutSetupMessage=%1 %2%n%3%n%n%1 juH Daq (Web):%n%4
AboutSetupNote=
TranslatorNote=

; *** Buttons
ButtonBack=< yI&chegh
ButtonNext=&veb >
ButtonInstall=yI&jom
ButtonOK=luq
ButtonCancel=yImev
ButtonYes=&HIja'
ButtonYesToAll=HIja' - Ho&chvaD
ButtonNo=&ghobe'
ButtonNoToAll=gho&be' - HochvaD
ButtonFinish=yI&rInmoH
ButtonBrowse=yI&nej...
ButtonWizardBrowse=yIn&ej...
ButtonNewFolder='aplo' chu' yI&chenmoH

; *** "Select Language" dialog messages
SelectLanguageTitle=jomwI' Hol yIwIv
SelectLanguageLabel=jomghach qaStaHvIS Hol Dalo'bogh yIwIv.

; *** Common wizard text
ClickNext=bItaHmeH veb yIHot, pagh jomwI'vo' bImejmeH yImev yIHot.
BeveledLabel=
BrowseDialogTitle='aplo' yInej
BrowseDialogLabel=bIng tetlhDaq 'aplo' yIwIv, ghIq luq yIHot.
NewFolderName='aplo' chu'

; *** "Welcome" wizard page
WelcomeLabel1=[name] jomwI' - nuqneH
WelcomeLabel2=De'wI'lIjDaq [name/ver] jom ghun vam.%n%nbItaHpa' Hoch latlh ghunmey DaSoQmoH 'e' chuplu'.

; *** "Password" wizard page
WizardPassword=mu' pegh
PasswordLabel1=jomghach vam Qan mu' pegh.
PasswordLabel3=mu' pegh yInob, ghIq bItaHmeH veb yIHot. mu' peghmeyDaq ngutlh tIn ngutlh mach je pIm.
PasswordEditLabel=&mu' pegh:
IncorrectPassword=mu' pegh DaghItlhpu'bogh lughbe'. yInIDqa'.

; *** "License Agreement" wizard page
WizardLicense=chaw' mab
LicenseLabel=bItaHpa', De' potlh tlha'bogh yIlaD.
LicenseLabel3=chaw' mab tlha'bogh yIlaD. jomghach DataHpa', mab vam mu'mey DalajnIS.
LicenseAccepted=mab vI&laj
LicenseNotAccepted=mab vIlaj&Qo'

; *** "Information" wizard pages
WizardInfoBefore=De'
InfoBeforeLabel=bItaHpa', De' potlh tlha'bogh yIlaD.
InfoBeforeClickLabel=jomwI' DataHmeH bIghuHDI', veb yIHot.
WizardInfoAfter=De'
InfoAfterLabel=bItaHpa', De' potlh tlha'bogh yIlaD.
InfoAfterClickLabel=jomwI' DataHmeH bIghuHDI', veb yIHot.

; *** "User Information" wizard page
WizardUserInfo=lo'wI' De'
UserInfoDesc=De'lIj yIghItlh.
UserInfoName=lo'wI' &pong:
UserInfoOrg=&ghom:
UserInfoSerial=mI'mey &tlhegh:
UserInfoNameRequired=pong DaghItlhnIS.

; *** "Select Destination Location" wizard page
WizardSelectDir=ghoSmeH Daq yIwIv
SelectDirDesc=nuqDaq [name] jomlu'nIS?
SelectDirLabel3='aplo' tlha'boghDaq [name] jom jomwI'.
SelectDirBrowseLabel=bItaHmeH, veb yIHot. latlh 'aplo' DawIv DaneHchugh, yInej yIHot.
DiskSpaceGBLabel=De' jengva'Daq [gb] GB chIm (puSbe') poQlu'.
DiskSpaceMBLabel=De' jengva'Daq [mb] MB chIm (puSbe') poQlu'.
CannotInstallToNetworkDrive=mIr De' jengva'Daq jomlaHbe' jomwI'.
CannotInstallToUNCPath=UNC HeDaq jomlaHbe' jomwI'.
InvalidPath=He naQ, De' jengva' ngutlh ghajbogh, DaghItlhnIS; vam rur:%n%nC:\App%n%npagh UNC He, vam rur:%n%n\\server\share
InvalidDrive=De' jengva' pagh UNC Daq DawIvpu'bogh tu'lu'be' pagh naw'laHbe'lu'. latlh yIwIv.
DiskSpaceWarningTitle=De' jengva'Daq chIm yapbe'
DiskSpaceWarning=jommeH %1 KB chIm (puSbe') poQ jomwI', 'ach %2 KB chIm neH ghaj De' jengva' DawIvpu'bogh.%n%nvabDot bItaH DaneH'a'?
DirNameTooLong='aplo' pong pagh He tIqqu'.
InvalidDirName='aplo' pong lughbe'.
BadDirName32='aplo' pongmeyDaq ngutlhmey tlha'bogh pagh lo'laHbe'lu':%n%n%1
DirExistsTitle='aplo' tu'lu'
DirExists='aplo':%n%n%1%n%nDaH tu'lu'. vabDot 'aplo'vetlhDaq Dajom DaneH'a'?
DirDoesntExistTitle='aplo' tu'lu'be'
DirDoesntExist='aplo':%n%n%1%n%ntu'lu'be'. 'aplo' chenmoHlu' DaneH'a'?

; *** "Select Components" wizard page
WizardSelectComponents='ay'mey tIwIv
SelectComponentsDesc=nuq 'ay'mey jomlu'nIS?
SelectComponentsLabel2='ay'mey DajomneHbogh tIwIv; 'ay'mey DajomneHbe'bogh tIwIvHa'. bItaHmeH bIghuHDI', veb yIHot.
; don't translate 'Full' as 'Normal' or 'Default'
FullInstallation=jomghach naQ
; don't translate 'Compact' as 'Minimal' or 'Default'
CompactInstallation=jomghach mach
CustomInstallation=jomghach DawIvbogh
NoUninstallWarningTitle='ay'mey tu'lu'
NoUninstallWarning=De'wI'lIjDaq 'ay'mey tlha'bogh jomlu'pu' 'e' tu' jomwI':%n%n%1%n%n'ay'meyvetlh DawIvHa'chugh, jomHa'lu'be'.%n%nvabDot bItaH DaneH'a'?
ComponentSize1=%1 KB
ComponentSize2=%1 MB
ComponentsDiskSpaceGBLabel=DaH wIvlu'bogh De' jengva'Daq [gb] GB (puSbe') poQ.
ComponentsDiskSpaceMBLabel=DaH wIvlu'bogh De' jengva'Daq [mb] MB (puSbe') poQ.

; *** "Select Additional Tasks" wizard page
WizardSelectTasks=Qu'mey latlh tIwIv
SelectTasksDesc=nuq Qu'mey latlh ta'lu'nIS?
SelectTasksLabel2=[name] jomtaHvIS jomwI', Qu'mey latlh ta' DaneHbogh tIwIv, ghIq veb yIHot.

; *** "Select Start Menu Folder" wizard page
WizardSelectProgramGroup=Start DuHmey tetlh 'aplo' yIwIv
SelectStartMenuFolderDesc=nuqDaq ghun Hemey nom lan jomwI'?
SelectStartMenuFolderLabel3=Start DuHmey tetlh 'aplo' tlha'boghDaq ghun Hemey nom chenmoH jomwI'.
SelectStartMenuFolderBrowseLabel=bItaHmeH, veb yIHot. latlh 'aplo' DawIv DaneHchugh, yInej yIHot.
MustEnterGroupName='aplo' pong DaghItlhnIS.
GroupNameTooLong='aplo' pong pagh He tIqqu'.
InvalidGroupName='aplo' pong lughbe'.
BadGroupName='aplo' pongDaq ngutlhmey tlha'bogh pagh lo'laHbe'lu':%n%n%1
NoProgramGroupCheck2=Start DuHmey tetlh 'aplo' yIchen&moHQo'

; *** "Ready to Install" wizard page
WizardReady=jommeH ghuH
ReadyLabel1=DaH De'wI'lIjDaq [name] jom 'e' taghmeH ghuH jomwI'.
ReadyLabel2a=jomghach DataHmeH yIjom yIHot, pagh ghuHmey DanuDmeH pagh DachoHmeH yIchegh yIHot.
ReadyLabel2b=jomghach DataHmeH yIjom yIHot.
ReadyMemoUserInfo=lo'wI' De':
ReadyMemoDir=ghoSmeH Daq:
ReadyMemoType=jomghach Segh:
ReadyMemoComponents='ay'mey wIvlu'pu'bogh:
ReadyMemoGroup=Start DuHmey tetlh 'aplo':
ReadyMemoTasks=Qu'mey latlh:

; *** TDownloadWizardPage wizard page and DownloadTemporaryFile
DownloadingLabel2=ghItlhmey Suqlu'lI'...
ButtonStopDownload=Suqghach yI&mev
StopDownload=Suqghach Damev DaneHbej'a'?
ErrorDownloadAborted=Suqghach mevlu'pu'
ErrorDownloadFailed=Suqghach Qapbe': %1 %2
ErrorDownloadSizeFailed=tIn Suqghach Qapbe': %1 %2
ErrorProgress=ghoSghach lughbe': %1 vo' %2
ErrorFileSize=ghItlh tIn lughbe': %1 pIHlu'pu', %2 tu'lu'pu'

; *** TExtractionWizardPage wizard page and ExtractArchive
ExtractingLabel=ghItlhmey lellu'lI'...
ButtonStopExtraction=lelghach yI&mev
StopExtraction=lelghach Damev DaneHbej'a'?
ErrorExtractionAborted=lelghach mevlu'pu'
ErrorExtractionFailed=lelghach Qapbe': %1

; *** Archive extraction failure details
ArchiveIncorrectPassword=mu' pegh lughbe'
ArchiveIsCorrupted=ghItlh ngaSwI' QIHlu'pu'
ArchiveUnsupportedFormat=ghItlh ngaSwI' Segh lo'laHbe'lu'

; *** "Preparing to Install" wizard page
WizardPreparing=jommeH ghuHlI'
PreparingDesc=De'wI'lIjDaq [name] jommeH ghuHlI' jomwI'.
PreviousInstallNotCompleted=ghun vorgh jomghach/teqghach rInbe'. jomghachvetlh DarInmoHmeH De'wI'lIj Dataghqa'moHnIS.%n%nDe'wI'lIj Dataghqa'moHpu'DI', [name] jomghach DarInmoHmeH jomwI' yIchu'qa'.
CannotContinue=taHlaHbe' jomwI'. bImejmeH yImev yIHot.
ApplicationsFound=ghItlhmey chu'moHnISbogh jomwI' lo' ghunmey tlha'bogh. ghunmeyvetlh SoQmoH jomwI' nIteb 'e' Dachaw' 'e' chuplu'.
ApplicationsFound2=ghItlhmey chu'moHnISbogh jomwI' lo' ghunmey tlha'bogh. ghunmeyvetlh SoQmoH jomwI' nIteb 'e' Dachaw' 'e' chuplu'. jomghach rInDI', ghunmey taghqa'moH 'e' nID jomwI'.
CloseApplications=nIteb ghunmey tI&SoQmoH
DontCloseApplications=ghunmey tISoQmoH&Qo'
ErrorCloseApplications=nIteb Hoch ghunmey SoQmoHlaHbe' jomwI'. bItaHpa', ghItlhmey chu'moHnISbogh jomwI' lo'bogh Hoch ghunmey DaSoQmoH 'e' chuplu'.
PrepareToInstallNeedsRestart=De'wI'lIj taghqa'moHnIS jomwI'. De'wI'lIj Dataghqa'moHpu'DI', [name] jomghach DarInmoHmeH jomwI' yIchu'qa'.%n%nDaH Dataghqa'moH DaneH'a'?

; *** "Installing" wizard page
WizardInstalling=jomlI'
InstallingLabel=De'wI'lIjDaq [name] jomtaHvIS jomwI', yIloS.

; *** "Setup Completed" wizard page
FinishedHeadingLabel=[name] jomwI' rInmoHlu'lI'
FinishedLabelNoIcons=De'wI'lIjDaq [name] jompu' jomwI'.
FinishedLabel=De'wI'lIjDaq [name] jompu' jomwI'. Hemey nom jomlu'pu'bogh DawIvDI', ghun taghmoHlaHlu'.
ClickFinish=jomwI'vo' bImejmeH yIrInmoH yIHot.
FinishedRestartLabel=[name] jomghach DarInmoHmeH, De'wI'lIj taghqa'moHnIS jomwI'. DaH taghqa'moHlu' DaneH'a'?
FinishedRestartMessage=[name] jomghach DarInmoHmeH, De'wI'lIj taghqa'moHnIS jomwI'.%n%nDaH taghqa'moHlu' DaneH'a'?
ShowReadmeCheck=HIja', README ghItlh vIlegh vIneH
YesRadio=&HIja', DaH De'wI' yItaghqa'moH
NoRadio=&ghobe', tugh De'wI' vItaghqa'moH
; used for example as 'Run MyProg.exe'
RunEntryExec=%1 yIchu'
; used for example as 'View Readme.txt'
RunEntryShellExec=%1 yIlegh

; *** "Setup Needs the Next Disk" stuff
ChangeDiskTitle=De' jengva' veb poQ jomwI'
SelectDiskLabel2=De' jengva' %1 yIlan 'ej luq yIHot.%n%nDe' jengva' vam ghItlhmey latlh 'aplo'Daq tu'laHlu'chugh - bIng 'aplo' 'aghlu'bogh Daq ghobe' - He lugh yIghItlh pagh yInej yIHot.
PathLabel=&He:
FileNotInDir2="%2"Daq ghItlh "%1" tu'laHbe'lu'. De' jengva' lugh yIlan pagh latlh 'aplo' yIwIv.
SelectDirectoryLabel=De' jengva' veb Daq yIngu'.

; *** Installation phase messages
SetupAborted=jomghach rInbe'.%n%nQay' yIQaQmoH 'ej jomwI' yIchu'qa'.
AbortRetryIgnoreSelectAction=ta' yIwIv
AbortRetryIgnoreRetry=yI&nIDqa'
AbortRetryIgnoreIgnore=Qagh yI&buSHa' 'ej yItaH
AbortRetryIgnoreCancel=jomghach yImev
RetryCancelSelectAction=ta' yIwIv
RetryCancelRetry=yI&nIDqa'
RetryCancelCancel=yImev

; *** Installation status messages
StatusClosingApplications=ghunmey SoQmoHlu'lI'...
StatusCreateDirs='aplo'mey chenmoHlu'lI'...
StatusExtractFiles=ghItlhmey lellu'lI'...
StatusDownloadFiles=ghItlhmey Suqlu'lI'...
StatusCreateIcons=Hemey nom chenmoHlu'lI'...
StatusCreateIniEntries=INI Dochmey chenmoHlu'lI'...
StatusCreateRegistryEntries=pat De' tetlh Dochmey chenmoHlu'lI'...
StatusRegisterFiles=ghItlhmey qonlu'lI'...
StatusSavingUninstall=jomHa'meH De' choqlu'lI'...
StatusRunProgram=jomghach rInmoHlu'lI'...
StatusRestartingApplications=ghunmey taghqa'moHlu'lI'...
StatusRollback=choHmey choHHa'lu'lI'...

; *** Misc. errors
ErrorInternal2=qoD Qagh: %1
ErrorFunctionFailedNoCode=%1 Qapbe'
ErrorFunctionFailed=%1 Qapbe'; ngoq %2
ErrorFunctionFailedWithMessage=%1 Qapbe'; ngoq %2.%n%3
ErrorExecutingProgram=ghItlh chu'laHbe'lu':%n%1

; *** Registry errors
ErrorRegOpenKey=pat De' tetlh ngaQHa'moHwI' poSmoHtaHvIS Qagh:%n%1\%2
ErrorRegCreateKey=pat De' tetlh ngaQHa'moHwI' chenmoHtaHvIS Qagh:%n%1\%2
ErrorRegWriteKey=pat De' tetlh ngaQHa'moHwI'Daq ghItlhtaHvIS Qagh:%n%1\%2

; *** INI errors
ErrorIniEntry=ghItlh "%1"Daq INI Doch chenmoHtaHvIS Qagh.

; *** File copying errors
FileAbortRetryIgnoreSkipNotRecommended=ghItlh vam yI&juS (chuplu'be')
FileAbortRetryIgnoreIgnoreNotRecommended=Qagh yI&buSHa' 'ej yItaH (chuplu'be')
SourceIsCorrupted=Hal ghItlh QIHlu'pu'
SourceDoesntExist=Hal ghItlh "%1" tu'lu'be'
SourceVerificationFailed=Hal ghItlh 'olghach Qapbe': %1
VerificationSignatureDoesntExist=qI'ghach ghItlh "%1" tu'lu'be'
VerificationSignatureInvalid=qI'ghach ghItlh "%1" lughbe'
VerificationKeyNotFound=ngaQHa'moHwI' Sovbe'lu'bogh lo' qI'ghach ghItlh "%1"
VerificationFileNameIncorrect=ghItlh pong lughbe'
VerificationFileTagIncorrect=ghItlh per lughbe'
VerificationFileSizeIncorrect=ghItlh tIn lughbe'
VerificationFileHashIncorrect=ghItlh Hash lughbe'
ExistingFileReadOnly2=ghItlh tu'lu'bogh tamlaHbe'lu', "laD neH" per ghajmo'.
ExistingFileReadOnlyRetry="laD neH" per yI&teq 'ej yInIDqa'
ExistingFileReadOnlyKeepExisting=ghItlh tu'lu'bogh yI&pol
ErrorReadingExistingDest=ghItlh tu'lu'bogh laD 'e' nIDtaHvIS Qagh tu'lu':
FileExistsSelectAction=ta' yIwIv
FileExists2=DaH tu'lu' ghItlh.
FileExistsOverwriteExisting=ghItlh tu'lu'bogh yI&tam
FileExistsKeepExisting=ghItlh tu'lu'bogh yI&pol
FileExistsOverwriteOrKeepAll=&ghoHmey vebvaD vam yIta'
ExistingFileNewerSelectAction=ta' yIwIv
ExistingFileNewer2=ghItlh tu'lu'bogh chu' law', ghItlh jom 'e' nIDbogh jomwI' chu' puS.
ExistingFileNewerOverwriteExisting=ghItlh tu'lu'bogh yI&tam
ExistingFileNewerKeepExisting=ghItlh tu'lu'bogh yI&pol (chuplu')
ExistingFileNewerOverwriteOrKeepAll=&ghoHmey vebvaD vam yIta'
ErrorChangingAttr=ghItlh tu'lu'bogh permey choH 'e' nIDtaHvIS Qagh tu'lu':
ErrorCreatingTemp=ghoSmeH 'aplo'Daq ghItlh chenmoH 'e' nIDtaHvIS Qagh tu'lu':
ErrorReadingSource=Hal ghItlh laD 'e' nIDtaHvIS Qagh tu'lu':
ErrorCopying=ghItlh velqa' chenmoH 'e' nIDtaHvIS Qagh tu'lu':
ErrorDownloading=ghItlh Suq 'e' nIDtaHvIS Qagh tu'lu':
ErrorExtracting=ghItlh ngaSwI' lel 'e' nIDtaHvIS Qagh tu'lu':
ErrorReplacingExistingFile=ghItlh tu'lu'bogh tam 'e' nIDtaHvIS Qagh tu'lu':
; 'RestartReplace' is an internal name, you may keep it as is
ErrorRestartReplace=RestartReplace Qapbe':
ErrorRenamingTemp=ghoSmeH 'aplo'Daq ghItlh pong choH 'e' nIDtaHvIS Qagh tu'lu':
ErrorRegisterServer=DLL/OCX qonlaHbe'lu': %1
ErrorRegSvr32Failed=RegSvr32 Qapbe'; mejmeH ngoq %1
ErrorRegisterTypeLib=Seghmey De' ghItlh qonlaHbe'lu': %1

; *** Uninstall display name markings
; used for example as 'My Program (32-bit)'
UninstallDisplayNameMark=%1 (%2)
; used for example as 'My Program (32-bit, All users)'
UninstallDisplayNameMarks=%1 (%2, %3)
UninstallDisplayNameMark32Bit=32-bit
UninstallDisplayNameMark64Bit=64-bit
UninstallDisplayNameMarkAllUsers=Hoch lo'wI'
UninstallDisplayNameMarkCurrentUser=DaH lo'wI'

; *** Post-installation errors
ErrorOpeningReadme=README ghItlh poSmoH 'e' nIDtaHvIS Qagh tu'lu'.
ErrorRestartingComputer=De'wI' taghqa'moHlaHbe' jomwI'. ghopDu' lo'taHvIS vam yIta'.

; *** Uninstaller messages
UninstallNotFound=ghItlh "%1" tu'lu'be'. jomHa'laHbe'lu'.
UninstallOpenError=ghItlh "%1" poSmoHlaHbe'lu'. jomHa'laHbe'lu'
UninstallUnsupportedVer=jomHa'meH qonta' ghItlh "%1" Segh Sovbe' jomHa'wI' Segh vam. jomHa'laHbe'lu'
UninstallUnknownEntry=jomHa'meH qonta'Daq Doch Sovbe'lu'bogh (%1) tu'lu'pu'
ConfirmUninstall=%1 'ej Hoch 'ay'meyDaj Dateqchu' DaneHbej'a'?
UninstallOnlyOnWin64=64-bit WindowsDaq neH jomghach vam jomHa'laHlu'.
OnlyAdminCanUninstall=loHwI' DuHmey ghajbogh lo'wI' neH jomghach vam jomHa'laH.
UninstallStatusLabel=De'wI'lIjvo' %1 teqlu'taHvIS, yIloS.
UninstalledAll=De'wI'lIjvo' %1 teqlu'pu'; Qap.
UninstalledMost=%1 jomHa'ghach rInpu'.%n%n'ay'mey 'op teqlaHbe'lu'. ghopDu' lo'taHvIS teqlaHlu'.
UninstalledAndNeedsRestart=%1 jomHa'ghach DarInmoHmeH, De'wI'lIj taghqa'moHnISlu'.%n%nDaH Dataghqa'moH DaneH'a'?
UninstallDataCorrupted=ghItlh "%1" QIHlu'pu'. jomHa'laHbe'lu'

; *** Uninstallation phase messages
ConfirmDeleteSharedFileTitle=ghItlh tay' Dateq'a'?
ConfirmDeleteSharedFile2=DaH ghItlh tay' tlha'bogh lo' pagh ghun 'e' 'ang pat. ghItlh tay' vam teq jomHa'wI' DaneH'a'?%n%nghItlh vam lo'taHchugh ghunmey 'op 'ej teqlu'chugh, chaq ghunmeyvetlh Qapchu'be'. DaSovbejbe'chugh, ghobe' yIwIv. patlIjDaq ghItlh DapolDI', pagh QIH qaS.
SharedFileNameLabel=ghItlh pong:
SharedFileLocationLabel=Daq:
WizardUninstalling=jomHa'ghach Dotlh
StatusUninstalling=%1 jomHa'lu'lI'...

; *** Shutdown block reasons
ShutdownBlockReasonInstallingApp=%1 jomlu'lI'.
ShutdownBlockReasonUninstallingApp=%1 jomHa'lu'lI'.

; The custom messages below aren't used by Setup itself, but if you make
; use of them in your scripts, you'll want to translate them.

[CustomMessages]

NameAndVersion=%1 Segh %2
AdditionalIcons=Hemey nom latlh:
CreateDesktopIcon=&Desktop Daq He nom yIchenmoH
CreateQuickLaunchIcon=&Quick Launch Daq He nom yIchenmoH
ProgramOnTheWeb=%1 Web Daq
UninstallProgram=%1 yIjomHa'
LaunchProgram=%1 yItaghmoH
AssocFileExtension=%1 %2 ghItlh pong Dor je tI&rar
AssocingFileExtension=%1 %2 ghItlh pong Dor je rarlu'lI'...
AutoStartProgramGroupDescription=taghghach:
AutoStartProgram=%1 yItaghmoH nIteb
AddonHostProgramNotFound='aplo' DawIvpu'bogh Daq %1 tu'laHbe'lu'.%n%nvabDot bItaH DaneH'a'?
