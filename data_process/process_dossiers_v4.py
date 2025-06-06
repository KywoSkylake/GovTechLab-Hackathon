# process_dossiers_v4.py
import os
import json
import sqlite3
import hashlib
import logging
import argparse
import re
from datetime import datetime

# --- Configuration for Logging ---
# Sets up logging to file and console for better tracking and debugging.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("dossier_processing.log"),
        logging.StreamHandler()
    ]
)

# --- Data-Driven Parsing Configuration ---
# This dictionary makes it easy to add or modify keywords for action extraction
# without changing the core parsing logic. The order matters for precedence.
ACTION_PATTERNS = {
    "Publication": r"Publié au Mémorial",
    "Dispense du second vote": r"Dispense du second vote",
    "Second vote": r"Second vote",
    "Premier vote": r"Premier vote",
    "Retrait du rôle": r"Retrait du rôle",
    "Rapport de commission": r"Rapport (?:complémentaire )?de commission",
    "Prise de position": r"Prise de position",
    "Avis": r"Avis (?:de|du)",
    "Dépôt": r"Déposé par",
    "Nomination de rapporteur": r"Rapporteur(s)?:",
}

def setup_database(db_name):
    """Sets up the database, dropping old tables for a clean run."""
    logging.info(f"Setting up database: {db_name}")
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    # Drop tables to ensure a fresh start
    cursor.execute("DROP TABLE IF EXISTS Activities")
    cursor.execute("DROP TABLE IF EXISTS Dossiers")

    cursor.execute("""
    CREATE TABLE Dossiers (
        dossier_id TEXT PRIMARY KEY,
        title TEXT,
        first_activity_date DATE,
        last_activity_date DATE,
        final_status TEXT,
        total_duration_days INTEGER,
        file_name TEXT
    )""")

    cursor.execute("""
    CREATE TABLE Activities (
        activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dossier_id TEXT,
        activity_date DATE NOT NULL,
        activity_text TEXT,
        activity_link TEXT,
        activity_hash TEXT UNIQUE,
        action TEXT,
        actor TEXT,
        rapporteur TEXT,
        vote_outcome TEXT,
        publication_source TEXT,
        publication_number TEXT,
        publication_page TEXT,
        FOREIGN KEY (dossier_id) REFERENCES Dossiers (dossier_id)
    )""")
    conn.commit()
    return conn

def clean_text(text):
    """General purpose text cleaner."""
    if not text:
        return ""
    # Standardize whitespace and remove leading/trailing spaces
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned

def convert_date_format(date_str, input_format="%d.%m.%Y"):
    """Converts date from DD.MM.YYYY to YYYY-MM-DD, handling potential errors."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, input_format).strftime("%Y-%m-%d")
    except ValueError:
        logging.warning(f"Could not parse date: '{date_str}'. Skipping.")
        return None

def parse_activity_details(activity_text, dossier_id):
    """
    Parses a single activity text to extract structured details using regex and configured patterns.
    """
    details = {
        "activity_event_date": None, "action": None, "actor": None, "rapporteur": None,
        "vote_outcome": None, "publication_source": None, "publication_number": None, "publication_page": None
    }

    # 1. Extract embedded date first, as it's often the most precise
    date_match = re.search(r"\(((\d{1,2}[.-]\d{1,2}[.-]\d{4})|(\d{4}-\d{2}-\d{2}))\)", activity_text)
    if date_match:
        # Normalize date format (DD.MM.YYYY) before conversion
        date_str = date_match.group(1).replace('-', '.')
        details["activity_event_date"] = convert_date_format(date_str)

    # 2. Extract Action using the ACTION_PATTERNS dictionary for maintainability
    for action_type, pattern in ACTION_PATTERNS.items():
        if re.search(pattern, activity_text, re.IGNORECASE):
            details["action"] = action_type
            break  # Stop after the first, most specific match is found

    # 3. Extract Rapporteur
    # This regex is more resilient; the title (Monsieur/Madame) is optional.
    rapporteur_match = re.search(r"Rapporteur(?:s)?\s*:\s*(?:(?:Monsieur|Madame|M\.)\s*)?([A-Z][\w\s'-]+)", activity_text, re.IGNORECASE)
    if rapporteur_match:
        details["rapporteur"] = clean_text(rapporteur_match.group(1))

    # 4. Extract Vote Outcome
    vote_match = re.search(r"vote constitutionnel\s*\((.*?)\)", activity_text, re.IGNORECASE)
    if vote_match:
        details["vote_outcome"] = clean_text(vote_match.group(1))
    
    # 5. Extract Publication Details
    pub_match = re.search(r"Publié au (Mémorial [A-Z\d]+)(?:\s*n°\s*([\w\s./-]+))?(?: en page\s*(\d+))?", activity_text, re.IGNORECASE)
    if pub_match:
        details["publication_source"], details["publication_number"], details["publication_page"] = [clean_text(p) if p else None for p in pub_match.groups()]
        
    # 6. Extract Actor (e.g., the commission or council giving an opinion)
    # Example: "Avis du Conseil d'Etat" -> Actor: "Conseil d'Etat"
    if details["action"] == "Avis":
        actor_match = re.search(r"Avis (?:du|de la|de l'|des)\s*([^(\n]+)", activity_text, re.IGNORECASE)
        if actor_match:
            details["actor"] = clean_text(actor_match.group(1))

    return details


def process_and_insert_data(conn, file_name, json_content):
    """Processes a single JSON file, unfurls multi-part events, and inserts into the database."""
    cursor = conn.cursor()
    dossier_id = json_content.get("dossier_id")
    if not dossier_id:
        logging.warning(f"Skipping file {file_name}: no dossier_id found.")
        return

    processed_hashes = set()

    for activity in json_content.get("activities", []):
        original_date = convert_date_format(activity.get("date"))
        if not original_date:
            continue

        activity_type_raw = activity.get("type", "")
        activity_link = activity.get("link")

        # Unfurling Logic: Split activities that are numbered lists (e.g., "1) ... 2) ...")
        # The regex looks for a number followed by a parenthesis, capturing everything until the next one or the end.
        sub_events = re.split(r'\n\s*\d+\)\s*', '\n' + activity_type_raw)[1:]
        if not sub_events:
            sub_events = [activity_type_raw] # Treat as a single event if not a numbered list

        for event_text in sub_events:
            event_text = event_text.strip()
            if not event_text:
                continue

            # Create a unique hash for the activity to prevent duplicates
            activity_hash = hashlib.md5(f"{dossier_id}{original_date}{event_text}".encode()).hexdigest()
            if activity_hash in processed_hashes:
                continue
            processed_hashes.add(activity_hash)

            # Parse structured details from the individual event text
            details = parse_activity_details(event_text, dossier_id)
            final_date = details.get("activity_event_date") or original_date

            try:
                cursor.execute("""
                    INSERT INTO Activities (
                        dossier_id, activity_date, activity_text, activity_link, activity_hash,
                        action, actor, rapporteur, vote_outcome, publication_source, publication_number, publication_page
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    dossier_id, final_date, event_text, activity_link, activity_hash,
                    details["action"], details["actor"], details["rapporteur"], details["vote_outcome"],
                    details["publication_source"], details["publication_number"], details["publication_page"]
                ))
            except sqlite3.IntegrityError:
                # This catches duplicates from previous runs (hash already exists in DB)
                logging.debug(f"Skipping duplicate activity for dossier {dossier_id} (hash: {activity_hash[:8]}...).")
            except Exception as e:
                logging.error(f"Error inserting activity for dossier {dossier_id}: {e}")

    conn.commit()


def post_process_dossiers(conn):
    """
    Calculates final status and duration for each dossier using a single, efficient, set-based SQL query.
    This avoids the N+1 query problem and is significantly faster.
    """
    logging.info("Starting post-processing to calculate dossier summaries.")
    cursor = conn.cursor()

    # This single, powerful query updates all dossiers at once.
    update_query = """
    WITH DossierSummary AS (
        SELECT
            dossier_id,
            MIN(activity_date) as first_date,
            MAX(activity_date) as last_date,
            -- Determine final status by prioritizing 'Publication' or 'Retrait'
            -- from the most recent activities. We use MAX on a CASE statement to get the highest priority.
            MAX(CASE
                WHEN action = 'Publication' THEN 3 -- Highest priority
                WHEN action = 'Retrait du rôle' THEN 2 -- Second priority
                ELSE 1 -- Default 'En cours'
            END) as status_code
        FROM Activities
        GROUP BY dossier_id
    )
    UPDATE Dossiers
    SET
        first_activity_date = summary.first_date,
        last_activity_date = summary.last_date,
        -- Use julianday for accurate day calculation in SQLite
        total_duration_days = CAST(julianday(summary.last_date) - julianday(summary.first_date) AS INTEGER),
        final_status = CASE summary.status_code
            WHEN 3 THEN 'Publié'
            WHEN 2 THEN 'Retiré'
            ELSE 'En cours'
        END
    FROM DossierSummary AS summary
    WHERE Dossiers.dossier_id = summary.dossier_id;
    """
    try:
        cursor.execute(update_query)
        conn.commit()
        logging.info(f"Successfully updated summary for {cursor.rowcount} dossiers.")
    except Exception as e:
        logging.error(f"Failed to post-process dossiers: {e}", exc_info=True)


def main(json_path, db_name):
    """Main function to find JSON files, process them, and populate the database."""
    conn = setup_database(db_name)

    logging.info(f"Scanning for JSON files in: {json_path}")
    json_files = [os.path.join(root, file)
                  for root, _, files in os.walk(json_path)
                  for file in files if file.endswith('.json')]

    if not json_files:
        logging.warning("No JSON files found in the specified directory. Exiting.")
        return

    logging.info(f"Found {len(json_files)} JSON files. Starting processing...")

    for i, file_path in enumerate(json_files):
        file_name = os.path.basename(file_path)
        logging.info(f"Processing file {i+1}/{len(json_files)}: {file_name}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            dossier_id = content.get("dossier_id")
            title = content.get("title")
            if not dossier_id:
                logging.warning(f"  -> Skipping {file_name} due to missing 'dossier_id'.")
                continue

            # Insert the dossier first to satisfy foreign key constraints.
            conn.cursor().execute("INSERT OR IGNORE INTO Dossiers (dossier_id, title, file_name) VALUES (?, ?, ?)", (dossier_id, title, file_name))
            conn.commit()

            process_and_insert_data(conn, file_name, content)
        except json.JSONDecodeError:
            logging.error(f"  -> Skipping {file_name} due to a JSON decoding error.")
        except Exception as e:
            logging.error(f"  -> An unexpected error occurred with {file_name}: {e}", exc_info=True)

    logging.info("Initial data insertion complete.")
    post_process_dossiers(conn)

    conn.close()
    logging.info("--- Database processing complete! ---")
    logging.info(f"Data is stored in '{db_name}'.")


if __name__ == "__main__":
    # Use argparse for flexible command-line configuration
    parser = argparse.ArgumentParser(description="Process parliamentary dossier JSON files into a SQLite database.")
    parser.add_argument("json_path", type=str, help="Path to the root folder containing the JSON files.")
    parser.add_argument("--db_name", type=str, default="dossiers_v4.db", help="Name for the output SQLite database file.")
    
    args = parser.parse_args()

    # Check if the provided path exists
    if not os.path.isdir(args.json_path):
        logging.error(f"Error: The specified path '{args.json_path}' does not exist or is not a directory.")
    else:
        main(args.json_path, args.db_name)

