import sqlite3
import pymongo
import os
import certifi

def check():
    db_path = "ingres.db"
    print("--- Checking SQLite ---")
    if os.path.exists(db_path):
        print(f"SQLite file exists at {db_path}, size: {os.path.getsize(db_path)} bytes")
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print("Tables in SQLite:", tables)
            for table_name_tuple in tables:
                t_name = table_name_tuple[0]
                cursor.execute(f"SELECT COUNT(*) FROM {t_name}")
                cnt = cursor.fetchone()[0]
                print(f"  Table '{t_name}' row count: {cnt}")
            conn.close()
        except Exception as e:
            print("Error reading SQLite:", e)
    else:
        print(f"SQLite file does not exist at {db_path}")

    print("\n--- Checking MongoDB ---")
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGODB_DB_NAME", "ingres_db")
    print(f"Attempting to connect to MongoDB: {mongodb_uri} (DB: {db_name})")
    try:
        client = pymongo.MongoClient(mongodb_uri, serverSelectionTimeoutMS=2000, tlsCAFile=certifi.where())
        print("MongoDB server info:", client.server_info())
        db = client[db_name]
        print("Collections:", db.list_collection_names())
        for coll_name in db.list_collection_names():
            print(f"  Collection '{coll_name}' count: {db[coll_name].count_documents({})}")
        client.close()
    except Exception as e:
        print("Error connecting to MongoDB:", e)

if __name__ == "__main__":
    check()
