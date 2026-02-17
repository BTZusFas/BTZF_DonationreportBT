#!/usr/bin/env python3

import json
import re
import requests
import os
from openai import OpenAI
import csv


class Config:
    def __init__(self, file_path='config.json'):
        self.config = self.load_config(file_path)
    
    def load_config(self, file_path):
        base_path = os.path.dirname(os.path.abspath(__file__))  # Das Verzeichnis des aktuellen Skripts
        config_path = os.path.join(base_path, file_path)
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Die Konfigurationsdatei {config_path} wurde nicht gefunden.")
        
        with open(config_path, 'r') as config_file:
            return json.load(config_file)

config = Config()


def main():
    # Initialisierung
    drsnr = config.config['GENERAL']['DRSNR']
    text = btapi_get_text_by_drsnr(drsnr, "Gesetzentwurf")
    text = cleanup_raw_text(text)
    prepared_text = replace_markers_with_placeholders(text)
    export_text_to_txt(prepared_text)
    
    if config.config['GENERAL']['PREPARE_ONLY']:
        print("Vorbereitung ausgeführt. Für weitere Analysen PREPARE_ONLY auf false setzen.")
        return
    else:
        table_sections = process_donationreport(prepared_text)


        # Ergebnis in CSV-Datei im selben Ordner wie das Skript schreiben
        print("Konvertiere Ergebnis zu CSV...")
        all_rows = _flatten_spenden_results(table_sections)
        output_path = json_to_csv(all_rows)
        print(f"Ergebnis wurde nach {output_path} exportiert ({len(all_rows)} Zeilen).")

def _flatten_spenden_results(results: list) -> list:
    """Flacht die Liste von {'Spenden': [...]} zu einer einfachen Zeilenliste ab."""
    rows = []
    for r in results:
        if r and isinstance(r, dict) and "Spenden" in r:
            rows.extend(r["Spenden"])
        elif r and isinstance(r, dict):
            # Fallback: Einzelnes Objekt (Partei, Name, ...) direkt als Zeile
            rows.append(r)
    return rows


def process_donationreport(text):
    # Verarbeitet den Spendenbericht und gibt das Ergebnis als String zurück
    # 0. Fließtext bereinigen (unnötige Zeilenumbrüche entfernen)
    
    results = []
    table_sections = extract_all_table_sections(text)
    print(f"Gefundene Tabellen: {len(table_sections)}")
    table_count = 1
    for table_section in table_sections:
        print(f"Verarbeite Tabelle {table_count} von {len(table_sections)}...")
        messages = generate_prompt(config.config['PROMPTS']['MES_DONATIONREPORT'], table_section)
        result = get_openai_completion_json(messages)
        #result = "Testdatensatz"
        #print(result)
        results.append(result)
        table_count += 1
    return results

def btapi_get_text_by_drsnr(drsnr,doctyp):
    # Fragt den Volltext einer Drucksache anhand der Drucksachennummer ab. 
    
    text = ""
    try:
        
        url = config.config['BTAPI']['base_url'] + config.config['BTAPI']['endpoint_drstext']
        bt_api_key = config.config['BTAPI']['bt_api_key']
        
        params = {
            "apikey": bt_api_key,
            "f.dokumentnummer" : drsnr,
        }
        
        request_response = requests.get(url, params=params)
        
        if request_response.status_code == 200:
            data = request_response.json()
            if data['numFound'] == 1:
                text = data['documents'][0]['text']
                if text == "":
                    print("Fehler: Kein Text enthalten.")
            elif data['numFound'] > 1:
                print("Fehler: Abfrage ergab mehrere Dokumente")
            else:
                print("Fehler: Text konnte nicht ermittelt werden.")
        else:
            print(f"Fehler: {request_response.text}")
    except Exception as e:
        print( f"FEHLER -> '{e}'")
    
    return text


def cleanup_raw_text(text):
    """
    Bereinigt den Fließtext: geschützte Leerzeichen durch normale ersetzen,
    unnötige Zeilenumbrüche entfernen.

    - Geschütztes Leerzeichen (U+00A0) wird durch normales Leerzeichen ersetzt.
    - Ein Zeilenumbruch wird entfernt (Zeilen mit Leerzeichen verbunden),
      wenn die nächste Zeile keine Leerzeile ist und die aktuelle nicht mit € endet.

    So bleiben Absatzgrenzen (Leerzeilen) und Zeilenenden nach Euro-Beträgen erhalten.
    """
    if not text:
        return text
    # Geschützte Leerzeichen durch normale ersetzen
    text = text.replace("\u00a0", " ")
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        while (
            i + 1 < len(lines)
            and lines[i + 1].strip() != ""
            and not line.rstrip().endswith("€")
        ):
            line = (line.rstrip() + "" + lines[i + 1].lstrip()) if line else lines[i + 1]
            i += 1
        result.append(line)
        i += 1
    return "\n".join(result)


def _load_markers_config():
    """Liest TABLE_START_MARKER und STOPPHRASES aus der über Config geladenen config.json."""
    markers = config.config.get("MARKERS", {})

    # Start-Marker
    start_markers = markers.get("TABLE_START_MARKERS")

    # Stop-Marker
    stop_markers = markers.get("TABLE_STOP_MARKERS")

    return start_markers, stop_markers


def _apply_markers_with_flexible_whitespace(result: str, markers: list, replacement: str) -> str:
    """
    Ersetzt alle Vorkommen der gegebenen Marker im Text durch den Replacement-String.

    Logik:
    - Regex-Ersetzung mit flexiblem Whitespace für im Marker vorkommende Leerzeichen.
    - Zusätzlich eine Literal-Ersetzung als Fallback.
    """
    for phrase in markers:
        if not phrase or not isinstance(phrase, str):
            continue
        phrase = phrase.strip()
        if not phrase:
            continue

        # Regex-Ersetzung (flexibles Whitespace)
        try:
            pattern = re.escape(phrase).replace(r"\ ", r"\s+")
            result = re.sub(pattern, replacement, result)
        except re.error:
            pass

        # Literal-Ersetzung für exakte Treffer, die die Regex nicht erwischt hat
        result = result.replace(phrase, replacement)

    return result


def replace_markers_with_placeholders(text):
    """
    Ersetzt im gesamten Text:
    - alle Start-Markers durch TABLESTART
    - alle Stop-Markers durch TABLESTOP
    Gibt den modifizierten Text zurück.
    """
    table_start_markers, stop_markers = _load_markers_config()
    if not text:
        return text

    result = text

    placeholders = config.config['PLACEHOLDERS']

    if table_start_markers:
        result = _apply_markers_with_flexible_whitespace(result, table_start_markers, placeholders['TABLE_START_PLACEHOLDER'])

    if stop_markers:
        result = _apply_markers_with_flexible_whitespace(result, stop_markers, placeholders['TABLE_STOP_PLACEHOLDER'])

    return result

def extract_all_table_sections(text):
    """
    Extrahiert alle Tabellen: jeweils den Text zwischen einem TABLESTART
    und dem darauffolgenden TABLESTOP.

    Die Platzhalter selbst sind nicht in den Rückgabewerten enthalten.

    Returns:
        list[str]: Liste der Tabelleninhalte (eine pro TABLESTART–TABLESTOP-Paar).
                   Leere Liste, wenn kein TABLESTART vorkommt.
    """

    placeholders = config.config['PLACEHOLDERS']
    if not text:
        return []
    sections = []
    pos = 0
    while True:
        pos_start = text.find(placeholders['TABLE_START_PLACEHOLDER'], pos)
        if pos_start == -1:
            break
        start_content = pos_start + len(placeholders['TABLE_START_PLACEHOLDER'])
        pos_stop = text.find(placeholders['TABLE_STOP_PLACEHOLDER'], start_content)
        if pos_stop == -1:
            # Kein TABLESTOP: Inhalt bis Textende
            section = text[start_content:].strip()
            if section:
                sections.append(section)
            break
        section = text[start_content:pos_stop].strip()
        sections.append(section)
        pos = pos_stop + len(placeholders['TABLE_STOP_PLACEHOLDER'])
    return sections

def generate_prompt(prompt, text):
    #Ersetzt den Platzhalter text in den Prompts mit dem übergebenen Text
    filled_messages = []
    try:
        for message in prompt:
            if 'content' in message and isinstance(message['content'], str):
                message_copy = message.copy()
                message_copy['content'] = message_copy['content'].format(text=text)
                filled_messages.append(message_copy)
            else:
                filled_messages.append(message)
        return filled_messages
    except Exception as e:
        print(f"FEHLER -> '{e}'")
        return ""

def get_openai_completion_json(messages):
    #Erzeugt eine OpenAI Completion und gibt die Antwort als JSON zurück
    api_key = config.config['OPENAI']['openai_api_key']
    temperature = config.config['OPENAI']['openai_temp']
    model = config.config['OPENAI']['openai_model']
    client = OpenAI(api_key=api_key)

    print(f"LLM analysiert Tabelleninhalt, this might take a while...")

    try:
        response = client.chat.completions.create(
            messages=messages,
            model=model,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "Spendentabelle",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "Spenden": {
                                "type": "array",
                                "description": "Liste aller Spendenzeilen der Tabelle",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "Partei": {"type": "string"},
                                        "Name": {"type": "string"},
                                        "Anschrift": {"type": "string"},
                                        "Betrag": {"type": "string"}
                                    },
                                    "required": ["Partei", "Name", "Anschrift", "Betrag"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["Spenden"],
                        "additionalProperties": False
                    }
                }
            })
        response_content = response.choices[0].message.content
        #print(response_content)
        response_content = response_content.replace("```", "")
        response_content = response_content.strip()
        resultjson = json.loads(response_content)
        if not response_content:
            print("FEHLER: Leere Antwort erhalten")
            return None
        return resultjson
    except json.JSONDecodeError as e:
        print(f"FEHLER beim Parsen der JSON-Antwort -> '{e}'")
        print(f"Antwort-Content: {response_content[:200] if 'response_content' in locals() else 'N/A'}")
        return None
    except Exception as e:
        print(f"FEHLER -> '{e}'")
        return None

def json_to_csv(data: dict | list) -> str:

    base_path = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_path, "donationreport_result.csv")
    # Zeilen extrahieren
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.values()
    else:
        raise TypeError("'data' muss ein dict oder list sein.")

    if not rows:
        raise ValueError("Keine Zeilen zum Schreiben vorhanden.")

    # Spalten aus erstem Eintrag ableiten
    fieldnames = list(rows[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)

    return output_path

def export_text_to_txt(text):
    base_path = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_path, "donationreport_prepared.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Vorbereiteter Rohtext wurde nach {output_path} exportiert.")

if __name__ == "__main__":
    main()