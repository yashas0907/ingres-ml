import pandas as pd
import sqlite3

def setup_database():
    try:
        # Load your CSV
        df = pd.read_csv("india_groundwater_2022.csv")
        
        # FORCE the columns to these names, regardless of what's in the CSV
        df.columns = ['state', 'district_name', 'block_name', 'extraction', 'category']
        
        # Clean the data: Remove spaces and make lowercase for easier searching
        df['district_name'] = df['district_name'].str.strip().str.lower()
        df['block_name'] = df['block_name'].str.strip().str.lower()

        conn = sqlite3.connect("ingres.db")
        df.to_sql("assessments", conn, if_exists="replace", index=False)

        # Load Trend Data
        try:
            df_trends = pd.read_csv("india_groundwater_trends.csv")
            df_trends['State'] = df_trends['State'].str.strip().str.lower()
            df_trends.to_sql("state_trends", conn, if_exists="replace", index=False)
            print("✅ Trend data ingested!")
        except Exception as trend_e:
            print(f"⚠️ Trend data skip: {trend_e}")

        conn.close()
        print("✅ Database REBUILT with clean names!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    setup_database()