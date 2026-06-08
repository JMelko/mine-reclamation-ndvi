import requests
import pandas as pd
import numpy as np
import geopandas as gpd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pystac_client
import planetary_computer
import stackstac
# Import the database models we built earlier
from db_setup import VegetationStat, PermitBoundary, ClimateStat

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

def fetch_climate_data(session):
    """Fetches historical precipitation data and loads it into the database."""
    print("\n🌧️ Connecting to Open-Meteo Climate API...")
    
    # Silverbell Mine rough coordinates
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": 32.38,
        "longitude": -111.49,
        "start_date": "2020-01-01",
        "end_date": "2025-12-31",
        "daily": "precipitation_sum",
        "timezone": "America/Phoenix"
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    # Convert the daily API response into a Pandas DataFrame
    df = pd.DataFrame({
        "date": pd.to_datetime(data["daily"]["time"]),
        "precip_mm": data["daily"]["precipitation_sum"]
    })
    
    # Extract the year, and sum the daily rainfall into annual totals
    df['year'] = df['date'].dt.year
    annual_precip = df.groupby('year')['precip_mm'].sum().reset_index()
    
    # Load into the database
    for _, row in annual_precip.iterrows():
        year = int(row['year'])
        # Check if it already exists to prevent duplicates
        exists = session.query(ClimateStat).filter_by(year=year).first()
        if not exists:
            stat = ClimateStat(year=year, precip_mm=float(round(row['precip_mm'], 2)))
            session.add(stat)
            
    session.commit()
    print("✅ Annual precipitation data successfully loaded to PostGIS.")

def run_pipeline():
    session = Session()

    # 0. Fetch auxiliary climate data
    fetch_climate_data(session)

    # 1. Ensure our spatial boundary is in the database
    load_boundary_to_db(session, "../data/raw/silverbell_aoi.geojson", "Silverbell Mine")
    
    # --- PRODUCTION API FETCH STARTS HERE ---
    print("\n🌍 Connecting to Microsoft Planetary Computer STAC API...")
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    
    # Get the bounding box of our AOI to feed to the STAC search
    gdf = gpd.read_file("../data/raw/silverbell_aoi.geojson")
    bbox_wgs84 = tuple(gdf.total_bounds) # (minx, miny, maxx, maxy)

    # The Production Multi-Year Loop
    for year in range(2020, 2026):
        print(f"\n--- Processing Year: {year} ---")
        time_range = f"{year}-09-01/{year}-10-31" # Post-Monsoon Window
        
        # 1. Search the STAC API
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox_wgs84,
            datetime=time_range,
            query={"eo:cloud_cover": {"lt": 10}}
        )
        items = search.item_collection()
        print(f"Found {len(items)} satellite scenes. Building datacube...")
        
        if len(items) == 0:
            print(f"⚠️ Warning: No clear imagery found for {year}. Skipping.")
            continue
            
        # 2. Build the Stackstac Datacube (Only pulling Red and NIR to save RAM)
        cube = stackstac.stack(
            items,
            assets=["B04", "B08"], 
            bounds_latlon=bbox_wgs84,
            epsg=32612, 
            resolution=10
        )
        
        # 3. Compute Median Composite (Removes transient clouds/shadows)
        print("Downloading arrays and computing median composite... (This may take a minute)")
        median_cube = cube.median(dim="time", skipna=True).compute()
        
        # 4. Extract standard Numpy Arrays
        red_band = median_cube.sel(band="B04").values
        nir_band = median_cube.sel(band="B08").values
        
        # Create a valid pixel mask (ignores NoData areas around the tile edges)
        valid_mask = ~np.isnan(red_band) & ~np.isnan(nir_band)
        
        # 5. Calculate Indices & Load to Database
        ndvi_array, savi_array = calculate_indices(red_band, nir_band)
        
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

def export_for_tableau():
    """Queries the final database and exports a flat file for Tableau Public."""
    print("\nExtracting final warehouse data for Tableau Public...")
    
    query = """
        SELECT 
            v.year, 
            v.index_type, 
            v.classification, 
            v.area_hectares, 
            v.percentage,
            c.precip_mm
        FROM vegetation_stats v
        LEFT JOIN climate_stats c ON v.year = c.year
        ORDER BY v.year, v.index_type, v.classification;
    """
    
    df = pd.read_sql(query, engine)
    
    output_path = "../data/processed/v2_dashboard_export.csv"
    df.to_csv(output_path, index=False)
    print(f"✅ Tableau extract saved to: {output_path}")

if __name__ == "__main__":
    # 1. Run the main ETL process (extract, transform, load to PostGIS)
    run_pipeline()
    
    # 2. Extract the final CSV for Tableau Public
    export_for_tableau()