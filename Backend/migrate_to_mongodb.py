import sqlite3
import pymongo
import os
import pandas as pd
import certifi
from urllib.parse import urlsplit, urlunsplit

# Database path configuration
DB_PATH = os.path.join(os.path.dirname(__file__), "ingres.db")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGODB_DB_NAME", "ingres_db")


def redact_mongodb_uri(uri):
    try:
        parts = urlsplit(uri)
        if "@" not in parts.netloc:
            return uri
        host = parts.netloc.split("@", 1)[1]
        return urlunsplit((parts.scheme, f"***:***@{host}", parts.path, parts.query, parts.fragment))
    except Exception:
        return "<redacted>"


def create_indexes(collection, df):
    cols = list(df.columns)
    state_col = next((c for c in cols if "state" in c.lower()), None)
    dist_col = next((c for c in cols if "district" in c.lower()), None)
    extract_col = next((c for c in cols if "extract" in c.lower() or "stage" in c.lower()), None)
    cat_col = next((c for c in cols if "categor" in c.lower()), None)

    for col in [state_col, dist_col, extract_col, cat_col]:
        if col:
            collection.create_index(col)

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"SQLite database not found at {DB_PATH}")
        return

    mongo_client = None
    print(f"Connecting to MongoDB at {redact_mongodb_uri(MONGODB_URI)}...")
    try:
        mongo_client = pymongo.MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            tlsCAFile=certifi.where(),
        )
        # Force a connection attempt
        mongo_client.server_info()
        db = mongo_client[DB_NAME]
    except Exception as e:
        print(f"Could not connect to MongoDB: {e}")
        print("Falling back to mock migration (printing data)...")
        db = None

    sqlite_conn = sqlite3.connect(DB_PATH)

    # Migrate assessments
    print("Migrating assessments...")
    df_assessments = pd.read_sql("SELECT * FROM assessments", sqlite_conn)
    if db is not None:
        db.assessments.drop()
        if not df_assessments.empty:
            db.assessments.insert_many(df_assessments.to_dict("records"))
            create_indexes(db.assessments, df_assessments)
            print(f"Successfully migrated {len(df_assessments)} assessment records.")
    else:
        print(f"Would migrate {len(df_assessments)} assessment records.")

    # Migrate state_trends
    print("Migrating state_trends...")
    df_trends = pd.read_sql("SELECT * FROM state_trends", sqlite_conn)
    if db is not None:
        db.state_trends.drop()
        if not df_trends.empty:
            db.state_trends.insert_many(df_trends.to_dict("records"))
            create_indexes(db.state_trends, df_trends)
            print(f"Successfully migrated {len(df_trends)} trend records.")
    else:
        print(f"Would migrate {len(df_trends)} trend records.")

    sqlite_conn.close()
    if mongo_client:
        mongo_client.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
