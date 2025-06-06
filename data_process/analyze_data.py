# analyze_data.py
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

DATABASE_NAME = "dossier_activities_v3.db"

def run_analysis():
    """Connects to the DB and runs all statistical analysis functions."""
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        print(f"Successfully connected to {DATABASE_NAME}")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return

    # Load data into pandas DataFrames
    dossiers_df = pd.read_sql_query("SELECT * FROM Dossiers", conn)
    activities_df = pd.read_sql_query("SELECT * FROM Activities", conn)
    conn.close()

    print("\n--- 📊 Overall Statistics ---")
    print(f"Total dossiers processed: {len(dossiers_df)}")
    print(f"Total activities logged: {len(activities_df)}")
    print("\nDossier Final Status Counts:")
    print(dossiers_df['final_status'].value_counts())

    print("\n--- ⏳ Dossier Lifecycle Analysis ---")
    lifecycle_analysis(dossiers_df)
    
    print("\n--- 🧑‍⚖️ Rapporteur Analysis ---")
    rapporteur_analysis(activities_df)

    print("\n--- 🏛️ Activity Flow Analysis ---")
    activity_flow_analysis(activities_df)
    
    print("\n--- ✅ Analysis Complete ---")
    print("Plots have been saved as PNG files in the current directory.")


def lifecycle_analysis(df):
    """Analyzes the duration of dossiers from start to finish."""
    # Filter for completed dossiers with a valid duration
    completed = df[(df['final_status'] == 'Publié') & (df['total_duration_days'].notna())]
    
    if completed.empty:
        print("No completed dossiers with duration found to analyze.")
        return

    avg_duration = completed['total_duration_days'].mean()
    median_duration = completed['total_duration_days'].median()
    
    print(f"Average time to publication: {avg_duration:.0f} days")
    print(f"Median time to publication: {median_duration:.0f} days")
    
    # Plotting the distribution of dossier durations
    plt.figure(figsize=(10, 6))
    sns.histplot(completed['total_duration_days'], bins=30, kde=True)
    plt.title('Distribution of Dossier Duration (Deposit to Publication)')
    plt.xlabel('Duration (Days)')
    plt.ylabel('Number of Dossiers')
    plt.axvline(avg_duration, color='r', linestyle='--', label=f'Mean: {avg_duration:.0f} days')
    plt.axvline(median_duration, color='g', linestyle='-', label=f'Median: {median_duration:.0f} days')
    plt.legend()
    plt.savefig('dossier_duration_distribution.png')
    plt.close()

def rapporteur_analysis(df):
    """Analyzes the activity of rapporteurs."""
    # Filter for activities where a rapporteur is named
    rapporteurs = df[df['rapporteur'].notna()]
    
    if rapporteurs.empty:
        print("No rapporteur data found to analyze.")
        return

    top_10_rapporteurs = rapporteurs['rapporteur'].value_counts().nlargest(10)
    
    print("Top 10 Most Active Rapporteurs:")
    print(top_10_rapporteurs)

    # Plotting top rapporteurs
    plt.figure(figsize=(12, 8))
    sns.barplot(x=top_10_rapporteurs.values, y=top_10_rapporteurs.index, palette='viridis')
    plt.title('Top 10 Most Active Rapporteurs')
    plt.xlabel('Number of Mentions as Rapporteur')
    plt.ylabel('Rapporteur')
    plt.tight_layout()
    plt.savefig('top_rapporteurs.png')
    plt.close()

def activity_flow_analysis(df):
    """Analyzes the common sequences of activities."""
    # This is a simplified version; a true Sankey diagram is more complex
    # Here, we count the most common transitions (e.g., what happens after 'Dépôt'?)
    
    df_sorted = df.sort_values(by=['dossier_id', 'activity_date', 'activity_id'])
    # Create a 'next_action' column by shifting the action column within each dossier group
    df_sorted['next_action'] = df_sorted.groupby('dossier_id')['action'].shift(-1)
    
    # Drop rows with no next action
    transitions = df_sorted.dropna(subset=['action', 'next_action'])
    
    transition_counts = transitions.groupby(['action', 'next_action']).size().reset_index(name='count')
    
    # Get the top 15 most common transitions
    top_transitions = transition_counts.sort_values('count', ascending=False).head(15)
    
    print("Top 15 Most Common Activity Transitions:")
    print(top_transitions.to_string(index=False))

if __name__ == "__main__":
    run_analysis()