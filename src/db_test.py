from sqlalchemy import create_engine, text

# Connection string format: postgresql://user:password@host:port/database_name
DB_URL = "postgresql://postgres:postgres_admin_password@localhost:5432/silverbell"

def test_connection():
    print("Attempting to connect to the PostGIS container...")
    try:
        # Create the SQLAlchemy engine
        engine = create_engine(DB_URL)
        
        # Open a connection and execute a raw SQL query
        with engine.connect() as conn:
            # We ask the database to return its spatial extension version
            result = conn.execute(text("SELECT PostGIS_Version();"))
            version = result.scalar()
            
        print("\n✅ Connection Successful!")
        print(f"Spatial Engine Active: {version}")
        
    except Exception as e:
        print("\n❌ Connection Failed. Check if Docker is running.")
        print(f"Error details: {e}")

if __name__ == "__main__":
    test_connection()