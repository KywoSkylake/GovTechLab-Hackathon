import requests
import json
import sqlite3
import os
from datetime import datetime
import re

# --- Configuration ---
GITHUB_REPO_OWNER = "your_username"
GITHUB_REPO_NAME = "your_repo_name"
FOLDER_PATH = "path/to/your/json_files"
DATABASE_NAME = "dossier_activities_v2.db" # New DB name for new schema

def get_repo_files_data():
    # (Same as before)
    if FOLDER_PATH:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{FOLDER_PATH}"
    else:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents"
    print(f"Fetching file list from: {api_url}")
    response = requests.get(api_url)
    response.raise_for_status()
    return response.json()

def download_json_content(file_url):
    # (Same as before)
    print(f"Downloading: {file_url}")
    response = requests.get(file_url)
    response.raise_for_status()
    return response.json()

def convert_date_format(date_str, input_format="%d.%m.%Y"):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, input_format).strftime("%Y-%m-%d")
    except ValueError:
        print(f"Warning: Could not parse date '{date_str}' with format '{input_format}'.")
        return None

def clean_text(text_str):
    if not text_str:
        return ""
    boilerplate = [
        r"Bouton graphique servant à afficher ou cacher tous les éléments de la liste qui précède",
        r"Show more",
        r"Voir moins"
    ]
    cleaned_str = text_str
    for pattern in boilerplate:
        cleaned_str = re.sub(pattern, "", cleaned_str, flags=re.IGNORECASE)
    cleaned_str = re.sub(r'\s+', ' ', cleaned_str).strip()
    return cleaned_str

def parse_activity_details(type_raw, type_cleaned, dossier_id):
    """
    Parses various details from the activity type string.
    Returns a dictionary of extracted fields.
    """
    extracted = {
        "activity_event_date": None,
        "projected_event_date": None,
        "rapporteur_name": None,
        "vote_outcome": None,
        "publication_source": None,
        "publication_number": None,
        "publication_page": None,
        "old_title": None,
        "new_title": None,
        "extracted_action_detail": None # A more specific action if identifiable
    }

    # 1. Extract embedded dates (e.g., from Avis, Dépêche)
    #    Pattern: (dd.mm.yyyy) or (dd-mm-yyyy)
    date_in_parentheses_match = re.search(r"\(((\d{1,2}[.-]\d{1,2}[.-]\d{4})|(\d{4}-\d{2}-\d{2}))\)", type_raw) # handles dd.mm.yyyy, dd-mm-yyyy, yyyy-mm-dd in ()
    if date_in_parentheses_match:
        date_str_group = date_in_parentheses_match.group(1)
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str_group): # yyyy-mm-dd format
             extracted["activity_event_date"] = convert_date_format(date_str_group, input_format="%Y-%m-%d")
        else: # dd.mm.yyyy or dd-mm-yyyy, try to normalize separator
            date_str_normalized = date_str_group.replace('-', '.')
            extracted["activity_event_date"] = convert_date_format(date_str_normalized)


    # 2. Extract projected date
    projected_date_match = re.search(r"Date prévisionnelle .*?:\s*(\d{1,2}[.-]\d{1,2}[.-]\d{4})", type_raw, re.IGNORECASE)
    if projected_date_match:
        date_str = projected_date_match.group(1).replace('.', '-')
        extracted["projected_event_date"] = convert_date_format(date_str, input_format="%d-%m-%Y")

    # 3. Extract Rapporteur
    rapporteur_match = re.search(r"Rapporteur(?:s)?\s*:\s*(?:Monsieur|Madame|M\.)\s*([^\n(]+)", type_raw, re.IGNORECASE)
    if rapporteur_match:
        extracted["rapporteur_name"] = rapporteur_match.group(1).strip()
    else:
        simple_rapporteur_match = re.search(r"^- Rapporteur\s*:\s*(?:Monsieur|Madame|M\.)\s*([^\n(]+)", type_cleaned, re.IGNORECASE)
        if simple_rapporteur_match:
             extracted["rapporteur_name"] = simple_rapporteur_match.group(1).strip()


    # 4. Extract Vote Outcome
    vote_match = re.search(r"vote constitutionnel\s*\((.*?)\)", type_raw, re.IGNORECASE)
    if vote_match:
        extracted["vote_outcome"] = vote_match.group(1).strip()
        extracted["extracted_action_detail"] = "Vote constitutionnel"


    # 5. Extract Publication Details
    pub_match = re.search(r"Publié au (Mémorial [A-Z\d]+)(?:\s*n°\s*([\w\s./-]+))?(?: en page\s*(\d+))?", type_raw, re.IGNORECASE)
    if pub_match:
        extracted["publication_source"] = pub_match.group(1).strip() if pub_match.group(1) else None
        extracted["publication_number"] = pub_match.group(2).strip() if pub_match.group(2) else None
        extracted["publication_page"] = pub_match.group(3).strip() if pub_match.group(3) else None
        extracted["extracted_action_detail"] = "Publication au Mémorial"

    # 6. Extract Title Change
    if "changement d'intitulé" in type_cleaned.lower():
        extracted["extracted_action_detail"] = "Changement d'intitulé"
        old_title_match = re.search(r"Ancien intitulé\s*:\s*(.*?)(?:\n\s*\nNouvel intitulé|\Z)", type_raw, re.DOTALL | re.IGNORECASE)
        if old_title_match:
            extracted["old_title"] = clean_text(old_title_match.group(1))

        new_title_match = re.search(r"Nouvel intitulé\s*:\s*(.*?)(?:\n\s*\n|\Z)", type_raw, re.DOTALL | re.IGNORECASE)
        if new_title_match:
            extracted["new_title"] = clean_text(new_title_match.group(1))
            
    # 7. Simple Action keyword extraction (can be expanded)
    if not extracted["extracted_action_detail"]:
        if type_cleaned.lower().startswith("déposé"):
            extracted["extracted_action_detail"] = "Dépôt"
        elif "avis de" in type_cleaned.lower() or "avis du conseil" in type_cleaned.lower() :
            extracted["extracted_action_detail"] = "Avis"
        elif "amendements gouvernementaux" in type_cleaned.lower():
            extracted["extracted_action_detail"] = "Amendements gouvernementaux"
        elif "amendements adoptés" in type_cleaned.lower():
            extracted["extracted_action_detail"] = "Amendements adoptés"
        elif "renvoyé en commission" in type_cleaned.lower():
            extracted["extracted_action_detail"] = "Renvoi en commission"


    return extracted

def setup_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS Activities") # Drop if rerunning with schema changes
    cursor.execute("DROP TABLE IF EXISTS Dossiers")   # Drop if rerunning with schema changes

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Dossiers (
        dossier_id TEXT PRIMARY KEY,
        first_activity_date DATE,
        last_activity_date DATE,
        total_activities INTEGER,
        file_name TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Activities (
        activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dossier_id TEXT,
        activity_date DATE,                     -- Original activity date
        activity_type_raw TEXT,
        activity_type_cleaned TEXT,
        activity_description TEXT,
        activity_link TEXT,
        extracted_action_detail TEXT,           -- Parsed specific action
        activity_event_date DATE,               -- Date embedded in type (e.g., date of an Avis document)
        projected_event_date DATE,              -- Projected date (e.g., "Date prévisionnelle")
        rapporteur_name TEXT,
        vote_outcome TEXT,
        publication_source TEXT,
        publication_number TEXT,
        publication_page TEXT,
        old_title TEXT,
        new_title TEXT,
        FOREIGN KEY (dossier_id) REFERENCES Dossiers (dossier_id)
    )
    """)
    conn.commit()
    return conn

def process_and_insert_json_data(conn, file_name, json_content):
    cursor = conn.cursor()
    dossier_id = json_content.get("dossier_id")

    if not dossier_id:
        print(f"Skipping file {file_name}: no dossier_id.")
        return

    activities_data = json_content.get("activities", [])
    if not activities_data:
        print(f"No activities for dossier {dossier_id} in {file_name}.")
        return

    activity_dates = [convert_date_format(act.get("date")) for act in activities_data if act.get("date")]
    activity_dates_valid = [d for d in activity_dates if d]
    first_date = min(activity_dates_valid) if activity_dates_valid else None
    last_date = max(activity_dates_valid) if activity_dates_valid else None

    try:
        cursor.execute("""
        INSERT OR REPLACE INTO Dossiers (dossier_id, first_activity_date, last_activity_date, total_activities, file_name)
        VALUES (?, ?, ?, ?, ?)
        """, (dossier_id, first_date, last_date, len(activities_data), file_name))
    except Exception as e:
        print(f"Error inserting dossier {dossier_id}: {e}")
        conn.rollback()
        return

    for activity in activities_data:
        sql_activity_date = convert_date_format(activity.get("date"))
        type_raw = activity.get("type", "")
        type_cleaned = clean_text(type_raw) if type_raw else "" # Ensure clean_text handles empty
        description = clean_text(activity.get("description", ""))
        link = activity.get("link")

        # Handle empty type field - use description or mark as "Misc/Link"
        if not type_cleaned and description:
             # Could try to infer action from description if it's a known entity type
            type_cleaned = f"Description: {description[:50]}" # Placeholder
        elif not type_cleaned and not description and link:
            type_cleaned = "Document Link Only"


        parsed_details = parse_activity_details(type_raw, type_cleaned, dossier_id)

        try:
            cursor.execute("""
            INSERT INTO Activities (
                dossier_id, activity_date, activity_type_raw, activity_type_cleaned,
                activity_description, activity_link, extracted_action_detail,
                activity_event_date, projected_event_date, rapporteur_name, vote_outcome,
                publication_source, publication_number, publication_page,
                old_title, new_title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dossier_id, sql_activity_date, type_raw, type_cleaned,
                description, link, parsed_details["extracted_action_detail"],
                parsed_details["activity_event_date"], parsed_details["projected_event_date"],
                parsed_details["rapporteur_name"], parsed_details["vote_outcome"],
                parsed_details["publication_source"], parsed_details["publication_number"],
                parsed_details["publication_page"], parsed_details["old_title"],
                parsed_details["new_title"]
            ))
        except Exception as e:
            print(f"Error inserting activity for dossier {dossier_id} (date: {activity.get('date')}): {e}")
            print(f"Problematic type_raw: {type_raw[:100]}") # Log problematic part

    conn.commit()
    print(f"Successfully processed dossier {dossier_id} from {file_name}")


def main():
    conn = setup_database()

    # --- Process local JSON files (example_dossier_6666.json, example_dossier_6675.json) ---
    # Save the first JSON example as 'example_dossier_6666.json'
    # Save the second JSON example as 'example_dossier_6675.json'
    example_files = ['6666.json', '6675.json']

    for example_file_name in example_files:
        try:
            with open(example_file_name, 'r', encoding='utf-8') as f:
                json_data_content = json.load(f)
            process_and_insert_json_data(conn, example_file_name, json_data_content)
        except FileNotFoundError:
            print(f"Error: {example_file_name} not found. Please create it with the sample JSON.")
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {example_file_name}.")
        except Exception as e:
            print(f"An unexpected error occurred with local file {example_file_name}: {e}")
    # --- End local file processing ---

    conn.close()
    print(f"--- Process finished. Data stored in {DATABASE_NAME} ---")
    print(f"To view the data, open '{DATABASE_NAME}' with an SQLite browser.")
    print("Example queries:")
    print("SELECT * FROM Dossiers;")
    print("SELECT dossier_id, activity_date, extracted_action_detail, rapporteur_name, vote_outcome FROM Activities WHERE rapporteur_name IS NOT NULL OR vote_outcome IS NOT NULL;")
    print("SELECT dossier_id, activity_date, activity_event_date, projected_event_date FROM Activities WHERE activity_event_date IS NOT NULL OR projected_event_date IS NOT NULL;")

if __name__ == "__main__":
    main()