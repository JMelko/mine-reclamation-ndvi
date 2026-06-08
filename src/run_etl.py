import os
import numpy as np
import geopandas as gpd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# Import the database models we built earlier
from db_setup import VegetationStat, PermitBoundary 

# --- 1. Database Connection Setup ---
DB_URL = "postgresql://postgres:postgres_admin_password@localhost:5432/silverbell"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

def load_boundary_to_db(session, geojson_path, site_name):
    """Loads the spatial polygon into PostGIS if it doesn't already exist."""
    print(f"Checking spatial warehouse for {site_name} boundary...")
    exists = session.query(PermitBoundary).filter_by(site_name=site_name).first()
    
    if not exists:
        gdf = gpd.read_file(geojson_path)
        # Convert the geometry to WKT (Well-Known Text) for PostGIS ingestion
        geom_wkt = gdf.geometry.iloc[0].wkt 
        
        boundary = PermitBoundary(site_name=site_name, geom=f"SRID=4326;{geom_wkt}")
        session.add(boundary)
        session.commit()
        print(f"✅ Inserted {site_name} vector geometry into PostGIS.")
    else:
        print(f"Boundary for {site_name} already exists in database.")

def calculate_indices(red_band, nir_band):
    """Calculates both NDVI and SAVI matrices."""
    # Suppress divide-by-zero warnings for barren pixels
    np.seterr(divide='ignore', invalid='ignore')
    
    # 1. Standard NDVI
    ndvi = (nir_band - red_band) / (nir_band + red_band)
    
    # 2. Desert-Calibrated SAVI (L = 0.5 for arid regions)
    L = 0.5
    savi = ((nir_band - red_band) / (nir_band + red_band + L)) * (1.0 + L)
    
    return ndvi, savi

def extract_and_load_stats(session, array, valid_mask, year, index_type):
    """Categorizes pixels and loads the statistics directly into the database."""
    pixel_area_m2 = 100 
    valid_pixels = array[valid_mask]
    total_valid = len(valid_pixels)
    
    # Sonoran Desert Thresholds
    barren = valid_pixels[valid_pixels < 0.05]
    sparse = valid_pixels[(valid_pixels >= 0.05) & (valid_pixels < 0.15)]
    canopy = valid_pixels[valid_pixels >= 0.15]
    
    categories = [
        ("Barren/Disturbed (<0.05)", barren),
        ("Sparse Scrub (0.05-0.15)", sparse),
        ("Established Canopy (>0.15)", canopy)
    ]
    
    for name, pixels in categories:
        count = len(pixels)
        hectares = (count * pixel_area_m2) / 10000
        percentage = (count / total_valid) * 100 if total_valid > 0 else 0
        
        # Create the ORM Object
        stat_record = VegetationStat(
            year=year,
            index_type=index_type,
            classification=name,
            pixel_count=count,
            area_hectares=round(hectares, 2),
            percentage=round(percentage, 2)
        )
        # Stage it for insertion
        session.add(stat_record)
        
    print(f"✅ Staged {index_type} metrics for {year}.")

def run_pipeline():
    session = Session()
    # 1. Ensure our spatial boundary is in the database
    load_boundary_to_db(session, "../data/raw/silverbell_aoi.geojson", "Silverbell Mine")
    
    # NOTE: For brevity in this script, we are mocking the STAC API fetch and masking. 
    # In your actual codebase, you will insert your `stackstac` and `rasterio.mask` logic here
    # inside a loop like: `for year in range(2020, 2026):`
    
    print("\n[MOCK] Commencing multi-year API fetch and processing (2020-2025)...")
    
    # Simulating the multi-year loop processing
    for year in range(2020, 2026):
        print(f"\n--- Processing Year: {year} ---")
        
        # Simulating masked arrays (you will replace this with real masked STAC data)
        mock_red = np.random.uniform(0.05, 0.3, 1000)
        mock_nir = np.random.uniform(0.1, 0.4, 1000)
        valid_mask = ~np.isnan(mock_red)
        
        # 2. Calculate both indices
        ndvi_array, savi_array = calculate_indices(mock_red, mock_nir)
        
        # 3. Extract and load into the database via SQLAlchemy
        extract_and_load_stats(session, ndvi_array, valid_mask, year, "NDVI")
        extract_and_load_stats(session, savi_array, valid_mask, year, "SAVI")
    
    # 4. Commit all staged data to the database at once
    try:
        session.commit()
        print("\n🚀 SUCCESS: All multi-year data committed to PostGIS Warehouse!")
    except Exception as e:
        session.rollback()
        print(f"Database insertion failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    run_pipeline()