import os
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask

def extract_zonal_stats(ndvi_path, geojson_path, output_csv):
    print("Loading AOI boundary for clipping...")
    # 1. Load the AOI
    aoi = gpd.read_file(geojson_path)
    
    # 2. Open the NDVI raster
    with rasterio.open(ndvi_path) as src:
        # Reproject AOI to match raster CRS just in case
        aoi = aoi.to_crs(src.crs)
        
        print("Masking raster to exact polygon boundary...")
        # Mask the raster with the polygon (crops out the corners of the bounding box)
        out_image, out_transform = mask(src, aoi.geometry, crop=True)
        
        # Extract the actual 2D data array
        ndvi_array = out_image[0]
        
        # Filter out NaN values (pixels outside our polygon)
        valid_pixels = ndvi_array[~np.isnan(ndvi_array)]
        
        # Sentinel-2 resolution is 10m x 10m = 100 square meters per pixel
        pixel_area_m2 = 100 
        
        print("Calculating zonal statistics...")
        
        # 3. Categorize pixels based on our custom Sonoran Desert thresholds
        barren = valid_pixels[valid_pixels < 0.05]
        sparse = valid_pixels[(valid_pixels >= 0.05) & (valid_pixels < 0.15)]
        canopy = valid_pixels[valid_pixels >= 0.15]
        
        total_valid = len(valid_pixels)
        
        # 4. Compile the statistics into a dictionary
        stats = {
            "Classification": ["Barren/Disturbed (<0.05)", "Sparse Scrub (0.05-0.15)", "Established Canopy (>0.15)"],
            "Pixel_Count": [len(barren), len(sparse), len(canopy)],
            "Area_Hectares": [(len(barren) * pixel_area_m2) / 10000, 
                              (len(sparse) * pixel_area_m2) / 10000, 
                              (len(canopy) * pixel_area_m2) / 10000],
            "Percentage": [(len(barren) / total_valid) * 100, 
                           (len(sparse) / total_valid) * 100, 
                           (len(canopy) / total_valid) * 100]
        }
        
        df = pd.DataFrame(stats)
        
        # Clean up the formatting for the dashboard
        df["Area_Hectares"] = df["Area_Hectares"].round(2)
        df["Percentage"] = df["Percentage"].round(2)
        
        # 5. Export to CSV
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)
        df.to_csv(output_csv, index=False)
        
        print(f"Success! Statistics exported to {output_csv}")
        print("\nPreview of extracted data:")
        print(df.to_string())

if __name__ == "__main__":
    NDVI_INPUT = "../data/processed/silverbell_ndvi.tif"
    GEOJSON_INPUT = "../data/raw/silverbell_aoi.geojson"
    CSV_OUTPUT = "../data/processed/silverbell_ndvi_stats.csv"
    
    extract_zonal_stats(NDVI_INPUT, GEOJSON_INPUT, CSV_OUTPUT)