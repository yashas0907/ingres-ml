import pandas as pd
import pymongo
import os

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "ingres_db"

def setup_database():
    try:
        # Load your CSV
        df = pd.read_csv("india_groundwater_2022.csv")
        
        # FORCE the columns to these names, regardless of what's in the CSV
        df.columns = ['state', 'district_name', 'block_name', 'extraction', 'category']
        
        # Clean the data: Remove spaces and make lowercase for easier searching
        df['district_name'] = df['district_name'].str.strip().str.lower()
        df['block_name'] = df['block_name'].str.strip().str.lower()

        client = pymongo.MongoClient(MONGODB_URI)
        db = client[DB_NAME]

        # Ingest assessments
        db.assessments.drop()
        db.assessments.insert_many(df.to_dict("records"))
        print("✅ Assessments data ingested to MongoDB!")

        # Load Trend Data
        try:
            df_trends = pd.read_csv("india_groundwater_trends.csv")
            df_trends['State'] = df_trends['State'].str.strip().str.lower()

            db.state_trends.drop()
            db.state_trends.insert_many(df_trends.to_dict("records"))
            print("✅ Trend data ingested to MongoDB!")
        except Exception as trend_e:
            print(f"⚠️ Trend data skip: {trend_e}")

        client.close()
        print("✅ MongoDB Database REBUILT with clean names!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    setup_database()