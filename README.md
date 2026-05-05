# Prüf-App für elektrische Gewerbeanlagen (OVE/ÖNORM E 8101)

Diese kleine Streamlit-App unterstützt bei der **strukturierten Erfassung einer Anlagenprüfung** und der **Erstellung eines Anlagenbuchs**.

## Funktionen

- Stammdaten der Anlage erfassen
- Prüfprotokoll mit typischen Prüfkategorien nach OVE E 8101-Logik (Sichtprüfung, Schutzmaßnahmen, Messungen, Dokumentation)
- Mängel inkl. Frist und Priorität erfassen
- Automatische Risikobewertung (Ampel)
- Anlagenbuch als **JSON** oder **Markdown** herunterladen

> Hinweis: Die App ist eine Arbeitsvorlage und ersetzt keine rechtsverbindliche Fachplanung/Normauslegung.

## Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Dann im Browser öffnen (typisch `http://localhost:8501`).

## Dateien

- `app.py` – Streamlit-App
- `requirements.txt` – Abhängigkeiten
