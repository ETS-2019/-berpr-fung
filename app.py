import datetime as dt
import json
from typing import Any

import streamlit as st

st.set_page_config(page_title="Prüf-App Gewerbeanlagen (OVE E 8101)", layout="wide")

st.title("Prüf-App für elektrische Gewerbeanlagen")
st.caption("Arbeitsvorlage für wiederkehrende Prüfungen inkl. Anlagenbuch")

with st.expander("Rechtlicher Hinweis", expanded=False):
    st.warning(
        "Diese App ist eine Vorlage für Dokumentation und Ablauf. "
        "Die fachliche und rechtliche Verantwortung für Normkonformität "
        "(z. B. OVE E 8101, OVE E 8101-6-6, Arbeitnehmerschutz) "
        "liegt bei der befugten Elektrofachkraft.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1) Anlagendaten")
    company = st.text_input("Unternehmen / Betreiber")
    site = st.text_input("Standort")
    plant_name = st.text_input("Bezeichnung der Anlage")
    asset_id = st.text_input("Anlagen-ID")

with col2:
    st.subheader("2) Prüfungsdaten")
    inspector = st.text_input("Prüfer:in")
    inspection_date = st.date_input("Prüfdatum", value=dt.date.today())
    next_due = st.date_input("Nächster Prüftermin")
    inspection_type = st.selectbox(
        "Prüfart",
        ["Erstprüfung", "Wiederkehrende Prüfung", "Anlassbezogene Prüfung"],
    )

st.subheader("3) Prüfkatalog")

check_items = [
    "Sichtprüfung: Beschädigungen, Erwärmungsspuren, korrekte Kennzeichnung",
    "Schutz gegen elektrischen Schlag (Schutzleiter/PE, Abschaltbedingungen)",
    "Fehlerstrom-Schutzeinrichtungen (RCD/FI) vorhanden und geprüft",
    "Schutz- und Potentialausgleich vorhanden und dokumentiert",
    "Überstromschutz (LS, Sicherungen, Selektivität plausibel)",
    "Isolationsmessung / Schleifenimpedanz / Niederohmigkeit durchgeführt",
    "Verteiler, Betriebsmittel, Leitungsführung normgerecht",
    "Dokumentation, Schaltpläne, Beschriftungen aktuell",
]

results: list[dict[str, Any]] = []

for idx, item in enumerate(check_items, start=1):
    c1, c2, c3 = st.columns([5, 2, 3])
    with c1:
        st.write(f"**{idx}.** {item}")
    with c2:
        status = st.selectbox(
            "Status",
            ["OK", "Mangel", "N/A"],
            key=f"status_{idx}",
            label_visibility="collapsed",
        )
    with c3:
        note = st.text_input(
            "Bemerkung",
            key=f"note_{idx}",
            label_visibility="collapsed",
            placeholder="Bemerkung / Messwert",
        )
    results.append({"position": idx, "kriterium": item, "status": status, "bemerkung": note})

st.subheader("4) Mängelliste")
defects_count = st.number_input("Anzahl Mängel", min_value=0, max_value=50, value=0, step=1)

defects: list[dict[str, Any]] = []
for i in range(defects_count):
    st.markdown(f"**Mangel {i + 1}**")
    d1, d2, d3 = st.columns(3)
    with d1:
        title = st.text_input("Kurzbeschreibung", key=f"defect_title_{i}")
    with d2:
        priority = st.selectbox("Priorität", ["niedrig", "mittel", "hoch"], key=f"defect_priority_{i}")
    with d3:
        due = st.date_input("Behebungsfrist", key=f"defect_due_{i}", value=dt.date.today())
    details = st.text_area("Details / Maßnahme", key=f"defect_details_{i}")
    defects.append({
        "titel": title,
        "prioritaet": priority,
        "behebungsfrist": due.isoformat(),
        "details": details,
    })

ok_count = sum(1 for r in results if r["status"] == "OK")
defect_status_count = sum(1 for r in results if r["status"] == "Mangel")

if defect_status_count == 0 and all(d["prioritaet"] != "hoch" for d in defects):
    overall = "GRÜN"
elif defect_status_count <= 2 and all(d["prioritaet"] != "hoch" for d in defects):
    overall = "GELB"
else:
    overall = "ROT"

st.subheader("5) Ergebnis")
if overall == "GRÜN":
    st.success(f"Gesamtbewertung: {overall}")
elif overall == "GELB":
    st.warning(f"Gesamtbewertung: {overall}")
else:
    st.error(f"Gesamtbewertung: {overall}")

anlagebuch = {
    "meta": {
        "erstellt_am": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "standard": "OVE/ÖNORM E 8101 (Arbeitsvorlage)",
    },
    "anlage": {
        "unternehmen": company,
        "standort": site,
        "bezeichnung": plant_name,
        "anlagen_id": asset_id,
    },
    "pruefung": {
        "pruefer": inspector,
        "pruefdatum": inspection_date.isoformat(),
        "naechster_termin": next_due.isoformat(),
        "pruefart": inspection_type,
        "gesamtbewertung": overall,
        "ok_positionen": ok_count,
        "mangel_positionen": defect_status_count,
    },
    "pruefkatalog": results,
    "maengel": defects,
}

st.subheader("6) Anlagenbuch exportieren")
json_data = json.dumps(anlagebuch, ensure_ascii=False, indent=2)

md_lines = [
    "# Anlagenbuch",
    "",
    f"- **Unternehmen:** {company}",
    f"- **Standort:** {site}",
    f"- **Anlage:** {plant_name}",
    f"- **Anlagen-ID:** {asset_id}",
    f"- **Prüfer:in:** {inspector}",
    f"- **Prüfdatum:** {inspection_date.isoformat()}",
    f"- **Nächster Termin:** {next_due.isoformat()}",
    f"- **Prüfart:** {inspection_type}",
    f"- **Gesamtbewertung:** {overall}",
    "",
    "## Prüfkatalog",
]

for row in results:
    md_lines.append(f"- [{row['status']}] {row['kriterium']} — {row['bemerkung']}")

md_lines.append("\n## Mängel")
if defects:
    for d in defects:
        md_lines.append(
            f"- **{d['titel']}** (Priorität: {d['prioritaet']}, Frist: {d['behebungsfrist']})\\n"
            f"  - {d['details']}"
        )
else:
    md_lines.append("- Keine Mängel erfasst.")

md_data = "\n".join(md_lines)

st.download_button(
    label="Anlagenbuch als JSON herunterladen",
    data=json_data.encode("utf-8"),
    file_name=f"anlagenbuch_{asset_id or 'anlage'}.json",
    mime="application/json",
)

st.download_button(
    label="Anlagenbuch als Markdown herunterladen",
    data=md_data.encode("utf-8"),
    file_name=f"anlagenbuch_{asset_id or 'anlage'}.md",
    mime="text/markdown",
)

st.info("Tipp: JSON-Export kann später in CMMS/CAFM-Systeme importiert werden.")
