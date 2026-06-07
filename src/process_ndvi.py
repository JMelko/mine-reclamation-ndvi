import os
import numpy as np
import rasterio

def calculate_ndvi(red_path, nir_path, output_path):
    print("Loading Red and NIR arrays into memory...")
    
    # 1. Read the Red band and extract the spatial metadata (profile)
    with rasterio.open(red_path) as red_src:
        red_array = red_src.read(1).astype('float32')
        spatial_profile = red_src.profile

    # 2. Read the NIR band
    with rasterio.open(nir_path) as nir_src:
        nir_array = nir_src.read(1).astype('float32')

    print("Executing NDVI matrix calculation...")
    
    # 3. Defensive Math: Suppress warnings for division by zero
    np.seterr(divide='ignore', invalid='ignore')
    
    # Calculate the denominator first to identify zero-value pixels
    denominator = nir_array + red_array
    
    # Calculate NDVI. If denominator is 0, assign NaN. Otherwise, run the formula.
    ndvi_array = np.where(denominator == 0, np.nan, (nir_array - red_array) / denominator)

    # 4. Update the spatial profile for the new output file
    spatial_profile.update(
        dtype=rasterio.float32,
        count=1,
        nodata=np.nan,
        compress='lzw' # Compresses the file size without losing data
    )

    # 5. Write the output GeoTIFF to the processed folder
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"Exporting processed GeoTIFF to: {output_path}")
    with rasterio.open(output_path, 'w', **spatial_profile) as dst:
        dst.write(ndvi_array, 1)
        
    print("Pipeline execution complete.")

if __name__ == "__main__":
    # Define our input and output paths
    RED_INPUT = "../data/raw/silverbell_B04_red.tif"
    NIR_INPUT = "../data/raw/silverbell_B08_nir.tif"
    NDVI_OUTPUT = "../data/processed/silverbell_ndvi.tif"
    
    calculate_ndvi(RED_INPUT, NIR_INPUT, NDVI_OUTPUT)