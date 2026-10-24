# Prüf-App für elektrische Anlagen in Österreich

Streamlit-Arbeitsanwendung mit getrenntem Datenmodell, Prüf-Engine, versionierter Speicherung und Berichtsexport. Eine neue oder unvollständige Prüfung erhält **keine positive Gesamtbewertung**.

## Start

Python 3.11 oder 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Die Anwendung ist für den lokalen Einzelplatzbetrieb vorgesehen. Nicht ungeprüft öffentlich bereitstellen: Benutzeranmeldung, Rechteverwaltung und Mandantentrennung sind nicht implementiert. Die lokale SQLite-Datenbank liegt standardmäßig in `data/inspections.sqlite3`; `INSPECTION_DB` kann einen anderen Pfad vorgeben. Bei Hosting ist ein dauerhaftes Volume erforderlich. Automatische Sicherung ist standardmäßig aktiv. JSON-Backups enthalten die vollständigen Daten einschließlich Fotos und können wieder eingelesen werden. Datenbank und Backups enthalten personenbezogene Prüfungsdaten und gehören nicht in Git.

## Ablauf

1. Stammdaten, Errichtungsjahr, Netzsystem, Prüfumfang, Gerät, Prüfer und begründeten nächsten Termin erfassen.
2. Tatsächlich anwendbare Normausgabe, Rechtsgrundlage, Fundstellen und fachliche Freigabe des Regelprofils dokumentieren. Die Ausgabe 2025 ist vorbelegt, ihre Anwendbarkeit wird dadurch nicht behauptet.
3. Anlage → Verteiler / Unterverteiler → raumweise Messpunkte aufbauen. Stromkreise dienen als Zuordnung; Verteiler haben einen eigenen Prüfkatalog.
4. Schutzorgane, RCDs und ihre Prüfpläne erfassen. Messpunkte können für L1/L2/L3 kopiert werden; Messwerte werden dabei geleert.
5. Messwerte manuell oder über CSV-Vorschau mit expliziter Spaltenzuordnung übernehmen. Mehrere manuelle Mängel je Messpunkt und Foto-Nachweise sind möglich.
6. Offene Prüfschritte, Plausibilität und Mängel bearbeiten. Ergebnis und Arbeitsstand exportieren; gespeicherte Revisionen lassen sich wieder laden.

## Bewertungsregeln und Grenzen

- Standardstatus ist **Nicht geprüft**. N/A erfordert eine Begründung. Ausschließlich ausgenommene Messungen sind kein positiver Nachweis.
- Vollständigkeit und Mängelschwere sind getrennt. S1 = leichter Mangel, S2 = erheblicher Mangel, S3 = kritisch. S2/S3 erzeugen ROT, S1 GELB. Ohne Mangel, aber mit offenen Prüfungen: GRAU. GRÜN setzt vollständige Erfassung ohne offene Mängel voraus. Diese Zuordnung ist eine App-Regel, keine selbstständige normative Risikobeurteilung.
- Zs und Zi sowie die getrennten gemessenen Ik-Werte werden je Messpunkt geführt. Optional wird ein fehlender Ik nur im Ergebnis aus U0/Z berechnet und als berechnet gekennzeichnet; Rohdaten bleiben unverändert.
- LS/FI-LS B/C/D: Ia-Rechenhilfe mit 5/10/20 × In. Für D02, NH, MCCB und sonstige Geräte ist Ia aus der geeigneten Herstellerkennlinie für die dokumentierte Zeit anzugeben. Ein freigegebener Name/Fundstelle ist eine dokumentierte fachliche Eingabe, keine automatisierte Prüfung der Quelle.
- `Normal`: Zsmax = U0/Ia, Ikmin = Ia. `Mit 2/3 Reserve`: Zsmax = (2/3)×U0/Ia, Ikmin = 1,5×Ia. Die Reserve wirkt konsistent auf beide Darstellungen. Strenge Grenzen (< bzw. >) sind gemäß bisheriger Anforderung voreingestellt; das Vergleichsverfahren ist im Regelprofil sichtbar.
- **Zi hat einen eigenen Ia-, Zeit- und Quellen-Nachweis**. Die Zs-Abschaltbedingung wird nicht automatisch auf den Kurzschlussschutz übertragen.
- Automatische Impedanz-/Ik-Bewertung ist auf fachlich freigegebene **TN-Profile** beschränkt. TT/IT benötigen zusätzliche Nachweise und bleiben offen. Ausschaltvermögen wird nicht allein durch die Messung am Endpunkt nachgewiesen; ein dort bereits überschrittener eingetragener Wert erzeugt jedoch einen kritischen Befund.
- Riso und RPE benötigen dokumentiertes Messverfahren, Grenzen und Fundstelle; Riso zusätzlich die Prüfspannung. Keine pauschale RPE-Grenze wird als allgemeingültige Normregel geliefert.
- RCD: Typ, Zeitverhalten, IΔN sowie einzelne Prüfungen nach Stromform, Faktor und Polarität. Zeitprüfung und Rampenprüfung sind getrennt; eine Rampenprüfung benötigt keine erfundene Auslösezeit. Erwartete Auslösung/Nichtauslösung, Zeitgrenze und optionaler Strombereich werden pro Schritt mit Fundstelle freigegeben. AC erfordert AC, A AC+A, B/B+ AC+A+B/DC als minimale Stromformabdeckung gemäß bisheriger Anforderung. Dies ersetzt **keinen vollständigen normativen Prüfplan**; dessen Vollständigkeit ist gesondert zu bestätigen. Typ F bleibt bis zu einem belegten Regelprofil offen. Keine pauschalen 250-ms-/Prozentwerte sind fest eingebaut.
- Das Typ-AC-Verbot für Neuanlage/Änderung/Erweiterung wird bei Ausgabe 2025 als Befund geführt; Bestand wird getrennt betrachtet.
- FEHLER/WARNUNG erzeugen automatische Mängel mit stabiler Identität aus Bezug + Regel. Wiederholte Bewertung dupliziert sie nicht. Positiver Wiederholungsnachweis setzt „Behoben“, erneuter Fehler „Offen“. Fehlende Messwerte oder Ausnahmen beweisen keine Behebung. Manuelle Mängel bleiben unabhängig erhalten.
- Jede Speicherung erzeugt eine wiederherstellbare Revision mit Prüfsumme und Änderungsverlauf. Das ist **keine digitale Signatur, kein manipulationssicheres Archiv und keine Mehrbenutzer-Konfliktlösung**.

## Normquellen

- [OVE E 8101:2025-10-01](https://www.ove.at/ove-standardization/normen-produkte/ove-e-8101/)
- [OVE: Änderungen der Ausgabe 2025, u. a. Typ AC](https://www.ove.at/ove-news/details/neue-ausgabe-der-ove-e-8101-ab-1-oktober-verfuegbar/)
- [Offizielles Inhaltsverzeichnis: Teil 6 Prüfung und Dokumentation](https://www.ove.at/fileadmin/userdaten/docs/standardization/OVE-E8101_2025_Inhaltsverzeichnis.pdf)
- [ETV 2020, konsolidiert](https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20011222)

Normausgabe, rechtliche Anwendbarkeit und Errichtungs-/Änderungszeitpunkt sind getrennt zu prüfen. Vollständige kostenpflichtige Normtexte und normativ freigegebene Grenzwerttabellen sind nicht im Repository enthalten. Es wird keine Normkonformität allein durch die Software behauptet.

## Exporte / Importe

- **JSON v2:** vollständiges Projekt, Rohmesswerte, Regeln, automatische Ergebnisse, Mängelverlauf, Fotos und Audit. Import validiert IDs, Zuordnungen, Hierarchie und Messwerte. Alte JSON-Anlagenbücher werden migriert; alte positive Katalogbewertungen werden zur erneuten Prüfung zurückgesetzt.
- **Markdown:** lesbarer Bericht mit Details und echten Zeilenumbrüchen.
- **HTML:** druckbarer Bericht mit Tabellen, Einzelbewertungen und eingebetteten Fotos. Benutzertext wird HTML-escaped.
- **RCD-CSV:** getrennte RCD-Prüfschritte einschließlich Sollwerten, Istwerten und Bewertung.
- **Messwerte-CSV:** UTF-8 mit BOM, Semikolon, stabile Messpunkt-IDs und Einzelbewertungen. Formelanfänge in Textzellen werden neutralisiert.
- **CSV-Import:** Dezimalkomma/-punkt; Vorschau und explizite Spaltenzuordnung. Unbekannte/doppelte IDs und ungültige Zahlen werden zurückgewiesen. Vorhandene Werte werden nur nach ausdrücklicher Auswahl ersetzt. Der Import erfolgt atomar auf einer Kopie.
- **Metrel:** CSV-Zuordnung vorhanden; kein proprietärer Metrel-Dateiparser ohne Beispieldatei.
- **E-Attest:** strukturierte Exportvorbereitung vorhanden, aber keine bestätigte Zielkompatibilität. Für das endgültige Mapping und einen echten Importtest wird die Zielvorlage benötigt. Eine interne CSV wird nicht als validierter E-Attest-Export bezeichnet.
- **Mängelkatalog:** eigene JSON-Liste mit `id`, `title`, `severity` importierbar. Der frühere 467er-Katalog ist nicht verfügbar und wurde nicht erfunden.

Fotos: PNG/JPEG, höchstens 2 MiB je Bild und insgesamt 6 MiB Base64-Daten. JSON-Import höchstens 10 MiB. Für größere Anlagen ist ein separates Anhangsarchiv als nächste Erweiterung sinnvoll.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests prüfen Fehl-Grün, Mängelschwere, Grenzgleichheit, Reserveberechnung, Erhalt gemessener Ik, Plausibilität, Mängelzustandswechsel, RCD-Schritte, offene Normprofile, Importvalidierung, CSV-Konflikte, HTML-Escaping, JSON-Roundtrip, SQLite-Revisionen und Streamlit-Abläufe. GitHub Actions führt sie unter Python 3.11/3.12 aus.

## Dateien

- `domain.py`: Schema, Erzeugung, Validierung, Altformatmigration
- `engine.py`: Fachliche Rechenhilfen, Befunde, Mängel und Gesamtstatus
- `exports.py`: JSON/CSV/Markdown/HTML und Messwerteimport
- `storage.py`: SQLite-Revisionen und Änderungen
- `app.py`: Bedienoberfläche

## Noch notwendige externe Unterlagen

Für eine fachliche Endfreigabe fehlen der vollständige anwendbare Normen-/Hersteller-Regelsatz, das konkrete E-Attest-Zielschema mit Importtest, ggf. eine originale Metrel-Datei sowie der bestehende 467er-Mängelkatalog. Diese Grenzen werden in der App sichtbar gehalten. Der PR bleibt bis zur fachlichen Abnahme ein Entwurf.
