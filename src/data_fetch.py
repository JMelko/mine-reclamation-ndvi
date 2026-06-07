import os
import sys

# --- DEFENSIVE IMPORT BLOCK ---
try:
    import geopandas as gpd
    from shapely.geometry import shape
    from pystac_client import Client
    import planetary_computer as pc
    import stackstac
    import rioxarray
except ImportError as e:
    print(f"\n[CRITICAL ERROR] Missing Dependency: {e.name}")
    print("Your script cannot run because a required geospatial library is not installed.")
    print("Please ensure your virtual environment '(.venv)' is active and run:")
    print("    pip install -r ../requirements.txt\n")
    sys.exit(1)
# ------------------------------

def fetch_sentinel_data(geojson_path, output_dir, start_date, end_date):
    print(f"Loading boundary from: {geojson_path}")
    
    # 1. Load the Silverbell AOI in WGS84 (Degrees) for the API Search
    aoi_wgs84 = gpd.read_file(geojson_path)
    aoi_wgs84 = aoi_wgs84.to_crs("EPSG:4326")
    search_bbox = tuple(aoi_wgs84.total_bounds)

    print(f"Searching STAC API for dates {start_date} to {end_date}...")
    
    # 2. Connect to the Planetary Computer STAC catalog
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=pc.sign_inplace
    )

    # 3. Search using the WGS84 Bounding Box
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=search_bbox,
        datetime=f"{start_date}/{end_date}",
        query={"eo:cloud_cover": {"lt": 10}}
    )
    
    items = search.item_collection()
    if len(items) == 0:
        print("No cloud-free imagery found for this time period and location.")
        return

    # 4. Grab the absolute least cloudy item
 # 4. Filter for tiles that cover the true center of the AOI
    # Calculate the bullseye (centroid) of the Silverbell boundary
    aoi_centroid = aoi_wgs84.geometry.iloc[0].centroid
    
    # Check every returned tile: Does its footprint contain our bullseye?
    valid_items = [
        item for item in items 
        if shape(item.geometry).contains(aoi_centroid)
    ]
    
    if len(valid_items) == 0:
        print("No single tile covers the center of the AOI.")
        return

    # Grab the least cloudy item from our VALIDATED list
    best_item = min(valid_items, key=lambda i: i.properties["eo:cloud_cover"])
    print(f"Selected Image Date: {best_item.datetime}")
    print(f"Cloud Cover: {best_item.properties['eo:cloud_cover']}%")

    # --- THE FIX: Reproject the AOI to UTM (Meters) for Cropping ---
    item_epsg = best_item.properties.get("proj:epsg", 32612) 
    aoi_utm = aoi_wgs84.to_crs(f"EPSG:{item_epsg}")
    crop_bbox = tuple(aoi_utm.total_bounds) # This bbox is now in meters!

    # 5. Load the arrays, cropped with the UTM Bounding Box
    print(f"Streaming and cropping Band 4 (Red) and Band 8 (NIR) from the cloud (EPSG:{item_epsg})...")
    ds = stackstac.stack(
        best_item,
        assets=["B04", "B08"],
        bounds=crop_bbox, 
        resolution=10, 
        epsg=item_epsg 
    )

    # 6. Save the data locally
    os.makedirs(output_dir, exist_ok=True)
    
    # Isolate the bands and safely scrub non-spatial metadata prior to export
    red_band = ds.isel(band=0).squeeze().drop_vars(["band", "time"], errors="ignore")
    nir_band = ds.isel(band=1).squeeze().drop_vars(["band", "time"], errors="ignore")

    red_out = os.path.join(output_dir, "silverbell_B04_red.tif")
    nir_out = os.path.join(output_dir, "silverbell_B08_nir.tif")

    red_band.rio.to_raster(red_out)
    nir_band.rio.to_raster(nir_out)
    
    print(f"Success! Data saved to {output_dir}")

if __name__ == "__main__":
    # Define our local paths and parameters
    GEOJSON = "../data/raw/silverbell_aoi.geojson"
    OUTPUT = "../data/raw/"
    
    # Post-monsoon window
    START = "2025-09-15"
    END = "2025-10-15"
    
    fetch_sentinel_data(GEOJSON, OUTPUT, START, END)