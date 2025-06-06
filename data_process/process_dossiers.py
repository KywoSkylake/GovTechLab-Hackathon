# process_dossiers_v3.py
import os
import json
import sqlite3
from datetime import datetime
import re
import hashlib

# --- Configuration ---
# IMPORTANT: Update this path to your local folder containing the JSON files
JSON_FILES_PATH = r"C:\Users\mmosavat\workspace\GovTechLab-Hackathon-1\scrape"
DATABASE_NAME = "dossier_activities_v3.db"

def clean_text(text_str):
    """General purpose text cleaner."""
    if not text_str:
        return ""
    # Clean dossier/sub-id prefixes like '4469/2'
    cleaned_str = re.sub(r"^\d{4,}/\d+\s*\n", "", text_str)
    # Remove known boilerplate
    boilerplate = [
        r"Bouton graphique servant à afficher ou cacher tous les éléments de la liste qui précède",
        r"Show more",
        r"Voir moins"
    ]
    for pattern in boilerplate:
        cleaned_str = re.sub(pattern, "", cleaned_str, flags=re.IGNORECASE)
    # Standardize whitespace
    cleaned_str = re.sub(r'\s+', ' ', cleaned_str).strip()
    return cleaned_str

def parse_activity_details(activity_text, dossier_id):
    """
    Parses a single line of activity text to extract structured details.
    Returns a dictionary of extracted fields.
    """
    # This function is similar to the v2 script but is now applied to each unfurled line
    # (For brevity, this is a condensed version of the previous detailed parsing logic)
    extracted = {
        "activity_event_date": None, "rapporteur_name": None, "vote_outcome": None,
        "publication_source": None, "publication_number": None, "publication_page": None,
        "extracted_action_detail": None
    }
    cleaned_text = clean_text(activity_text)

    # Extract date from parentheses
    date_match = re.search(r"\(((\d{1,2}[.-]\d{1,2}[.-]\d{4})|(\d{4}-\d{2}-\d{2}))\)", activity_text)
    if date_match:
        date_str = date_match.group(1).replace('-', '.')
        extracted["activity_event_date"] = convert_date_format(date_str)

    # Extract Rapporteur
    rapporteur_match = re.search(r"Rapporteur(?:s)?\s*:\s*(?:Monsieur|Madame|M\.)\s*([^\n(]+)", activity_text, re.IGNORECASE)
    if rapporteur_match:
        extracted["rapporteur_name"] = rapporteur_match.group(1).strip()
        extracted["extracted_action_detail"] = "Nomination de rapporteur"

    # Extract Action
    if "Avis de" in cleaned_text or "Avis du" in cleaned_text: extracted["extracted_action_detail"] = "Avis"
    elif "Déposé" in cleaned_text: extracted["extracted_action_detail"] = "Dépôt"
    elif "Premier vote" in cleaned_text: extracted["extracted_action_detail"] = "Premier vote"
    elif "Dispense du second vote" in cleaned_text: extracted["extracted_action_detail"] = "Dispense du second vote"
    elif "Publié au Mémorial" in cleaned_text: extracted["extracted_action_detail"] = "Publication"
    elif "Rapport de commission" in cleaned_text: extracted["extracted_action_detail"] = "Rapport de commission"
    elif "Retrait du rôle" in cleaned_text: extracted["extracted_action_detail"] = "Retrait du rôle"
    elif "Prise de position" in cleaned_text: extracted["extracted_action_detail"] = "Prise de position"

    # Extract vote outcome
    vote_match = re.search(r"vote constitutionnel\s*\((.*?)\)", cleaned_text, re.IGNORECASE)
    if vote_match: extracted["vote_outcome"] = vote_match.group(1).strip()
    
    # Extract publication details
    pub_match = re.search(r"Publié au (Mémorial [A-Z\d]+)(?:\s*n°\s*([\w\s./-]+))?(?: en page\s*(\d+))?", cleaned_text, re.IGNORECASE)
    if pub_match:
        extracted["publication_source"], extracted["publication_number"], extracted["publication_page"] = [p.strip() if p else None for p in pub_match.groups()]

    return extracted

def convert_date_format(date_str, input_format="%d.%m.%Y"):
    """Converts date from DD.MM.YYYY to YYYY-MM-DD."""
    if not date_str: return None
    try:
        return datetime.strptime(date_str, input_format).strftime("%Y-%m-%d")
    except ValueError:
        return None

def setup_database():
    """Sets up the database, adding a unique hash column for deduplication."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    # Drop tables for a clean run if schema changes
    cursor.execute("DROP TABLE IF EXISTS Activities")
    cursor.execute("DROP TABLE IF EXISTS Dossiers")
    
    cursor.execute("""
    CREATE TABLE Dossiers (
        dossier_id TEXT PRIMARY KEY,
        first_activity_date DATE,
        last_activity_date DATE,
        final_status TEXT, -- e.g., 'Publié', 'Retiré'
        total_duration_days INTEGER,
        file_name TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE Activities (
        activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dossier_id TEXT,
        activity_date DATE,
        activity_text TEXT,
        activity_description TEXT,
        activity_link TEXT,
        activity_hash TEXT UNIQUE, -- For deduplication
        action TEXT,
        rapporteur TEXT,
        vote_outcome TEXT,
        publication_source TEXT,
        publication_number TEXT,
        publication_page TEXT,
        FOREIGN KEY (dossier_id) REFERENCES Dossiers (dossier_id)
    )""")
    conn.commit()
    return conn

def process_and_insert_data(conn, file_name, json_content):
    """Processes a single JSON file, unfurls multi-events, and handles duplicates."""
    cursor = conn.cursor()
    dossier_id = json_content.get("dossier_id")
    if not dossier_id: return

    # Temporary set to hold hashes for the current file to avoid self-duplication
    processed_hashes_this_file = set()

    for activity in json_content.get("activities", []):
        original_date = convert_date_format(activity.get("date"))
        if not original_date: continue # Skip activities without a valid date

        activity_type_raw = activity.get("type", "")
        activity_description = activity.get("description", "")
        activity_link = activity.get("link")

        # ** Unfurling Logic for Multi-Event Activities **
        # Check for patterns like '1) ... 2) ...'
        sub_events = re.findall(r"\d+\)\s(.*?)(?=\s*\d+\)|$)", activity_type_raw, re.DOTALL)

        if not sub_events:
            # If no numbered list, treat the whole type as a single event
            sub_events = [activity_type_raw]

        for event_text in sub_events:
            if not event_text.strip(): continue

            cleaned_event_text = clean_text(event_text)
            
            # ** Deduplication Logic **
            # Create a hash of the core content
            activity_hash = hashlib.md5(f"{dossier_id}{original_date}{cleaned_event_text}".encode()).hexdigest()
            
            # Skip if we've already processed this exact event in this file or a previous run
            if activity_hash in processed_hashes_this_file:
                continue
            
            processed_hashes_this_file.add(activity_hash)

            # Parse details from the specific event text
            details = parse_activity_details(event_text, dossier_id)
            
            # Use the embedded date if found, otherwise fallback to the main activity date
            final_date = details.get("activity_event_date") or original_date

            try:
                cursor.execute("""
                    INSERT INTO Activities (
                        dossier_id, activity_date, activity_text, activity_description, activity_link, activity_hash,
                        action, rapporteur, vote_outcome, publication_source, publication_number, publication_page
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    dossier_id, final_date, event_text.strip(), activity_description, activity_link, activity_hash,
                    details["extracted_action_detail"], details["rapporteur_name"], details["vote_outcome"],
                    details["publication_source"], details["publication_number"], details["publication_page"]
                ))
            except sqlite3.IntegrityError:
                # This catches duplicates from previous runs if the hash already exists in the DB
                pass # Silently skip duplicates
            except Exception as e:
                print(f"Error inserting activity for dossier {dossier_id}: {e}")
    conn.commit()

def post_process_dossiers(conn):
    """Calculates final status and duration for each dossier after all data is inserted."""
    cursor = conn.cursor()
    cursor.execute("SELECT dossier_id FROM Dossiers")
    all_dossier_ids = [row[0] for row in cursor.fetchall()]

    for dossier_id in all_dossier_ids:
        cursor.execute("""
            SELECT MIN(activity_date), MAX(activity_date), action
            FROM Activities
            WHERE dossier_id = ?
            ORDER BY activity_date DESC
        """, (dossier_id,))
        rows = cursor.fetchall()
        
        first_date_str, last_date_str = None, None
        final_status = 'En cours' # Default status

        # Find first and last dates
        cursor.execute("SELECT MIN(activity_date), MAX(activity_date) FROM Activities WHERE dossier_id = ?", (dossier_id,))
        dates = cursor.fetchone()
        if dates:
            first_date_str, last_date_str = dates

        # Determine final status
        cursor.execute("SELECT action FROM Activities WHERE dossier_id = ? ORDER BY activity_date DESC, activity_id DESC LIMIT 10", (dossier_id,))
        last_actions = [row[0] for row in cursor.fetchall()]
        if 'Publication' in last_actions:
            final_status = 'Publié'
        elif 'Retrait du rôle' in last_actions:
            final_status = 'Retiré'
        
        duration = None
        if first_date_str and last_date_str:
            duration = (datetime.strptime(last_date_str, "%Y-%m-%d") - datetime.strptime(first_date_str, "%Y-%m-%d")).days

        cursor.execute("""
            UPDATE Dossiers
            SET first_activity_date = ?, last_activity_date = ?, final_status = ?, total_duration_days = ?
            WHERE dossier_id = ?
        """, (first_date_str, last_date_str, final_status, duration, dossier_id))
    conn.commit()


def main():
    """Main function to find JSON files, process them, and populate the database."""
    conn = setup_database()
    
    print(f"Scanning for JSON files in: {JSON_FILES_PATH}")
    json_files = [os.path.join(root, file)
                  for root, _, files in os.walk(JSON_FILES_PATH)
                  for file in files if file.endswith('.json')]
    
    print(f"Found {len(json_files)} JSON files. Starting processing...")

    for i, file_path in enumerate(json_files):
        file_name = os.path.basename(file_path)
        print(f"Processing file {i+1}/{len(json_files)}: {file_name}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            # Initial insert into Dossiers table to establish the primary key
            conn.cursor().execute("INSERT OR IGNORE INTO Dossiers (dossier_id, file_name) VALUES (?, ?)", (content.get("dossier_id"), file_name))
            conn.commit()

            process_and_insert_data(conn, file_name, content)
        except json.JSONDecodeError:
            print(f"  -> Skipping {file_name} due to JSON decoding error.")
        except Exception as e:
            print(f"  -> An unexpected error occurred with {file_name}: {e}")

    print("Initial data insertion complete. Running post-processing...")
    post_process_dossiers(conn)

    conn.close()
    print("--- Database processing complete! ---")
    print(f"Data is stored in '{DATABASE_NAME}'. You can now run the analysis script.")

if __name__ == "__main__":
    main()