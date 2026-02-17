# BTZF_DonationreportBT
Kleines Python-Projekt, um die Einzelspenden an die Parteien des Bundestags zu extrahieren und als CSV zu exportieren.

Konfiguration:

In der Datei config.json sind alle notwendigen Konfigurationen hinterlegt. Zum Start eines neuen Analyse-Laufs müssen folgende Konfigurationen geprüft und ggf. aktualisiert werden:

GENERAL -> DRSNR
Hier die aktuelle Drucksachennummer des Rechenschaftsberichts hinterlegen

GENERAL -> PREPARE_ONLY
Wenn hier true gesetzt ist, wird nur die Vorbereitung des Drucksachetextes durchgeführt und das Ergebnis in der Datei donationreport_prepared.txt gespeichert. So kann vor der eigentlichen Analyse einer neuen Drucksache geprüft werden, ob alle Tabellen korrekt erkannt werden.
Für die weitere Verarbeitung muss PREPARE_ONLY auf false gesetzt werden. 

BTAPI -> bt_api_key
Prüfen, ob der Key aktuell ist. Der jeweils aktuelle Key kann unter https://dip.bundestag.de/%C3%BCber-dip/hilfe/api#content eingesehen werden.

MARKERS
Prüfen, ob die Marker für Start und Ende der Tabellen für alle Parteien passend sind und ggf. weitere ergänzen. Hierfür kann mit PREPARE_ONLY = true zunächst ein Vorbereitungslauf durchgeführt werden (s.o.).

OPENAI -> openai_api_key
Prüfen, ob der korrekte API Key eingetragen ist, ggf. aktualisieren.

PLACEHOLDERS
Die Platzhalter für Start/Ende der Tabellen können bei Bedarf angepasst werden, müssen aber Phrasen sein, die nicht anderweitig im Volltext der Drucksache vorkommen. 


Ablauf des Skripts: 

Vorbereitung
1. Abruf des Volltextes der angegebenen Drucksache aus der API des Bundestags (Endpoint: drucksache-text)
2. Bereinigung des Volltextes: Löschen von unnötigen Zeilenumbrüchen und geschützten Leerzeichen
3. Ersetzen der Start- und Stop-Marker durch die angegebenen Platzhalter.
4. Export des bereinigten Textes in Datei donationreport_prepared.txt. Die Datei dient nur zur Prüfung und Debugging, sie wird vom Skript danach nicht mehr verwendet. Hier kann kontrolliert werden, ob alle Tabellen von einem Start-Platzhalter und einem Stop-Platzhalter eingeschlossen sind. 

Analyse 
5. Extraktion des Inhaltes zwischen einem Start- und dem darauffolgenden Stop-Platzhalter
6. Erstellen des Prompts und der Completion durch LLM (aktuell: OpenAI, GPT-5.1). Es wird ein JSON-Objekt zurückgegeben, dass die einzelne Tabellenzeilen enthält. 
	Ausgabe-Strukur:
		Spenden {
			"Partei" : Kürzel der Partei, ermittelt aus den Kopfzeilen
			"Name" : Name des Spendenden im Format Name, Vorname (wenn zutreffend, sonst wie angegeben) 
			"Anschrift" : Anschrift des Spendenden
			"Betrag" : Betrag als Dezimalzahl ohne Tausendertrennzeichen und Währungszeichen
		}
    Hinweis: Dieser Schritt kann ein paar Minuten dauern, nicht ungeduldig werden ;)
7. Umwandlung des JSON Objekts und Export als CSV nach donationreport_result.csv
