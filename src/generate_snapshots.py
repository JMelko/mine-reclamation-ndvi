import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import pystac_client
import planetary_computer
import stackstac

def generate_snapshots():
    print("🌍 Connecting to STAC API for visual extraction...")
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    gdf = gpd.read_file("../data/raw/silverbell_aoi.geojson")
    bbox_wgs84 = tuple(gdf.total_bounds)

    # We want to compare the 2020 Peak to the 2023 Trough
    years_to_compare = [2020, 2023]
    
    # Create a custom desert-themed colormap (Tan -> Light Green -> Dark Green)
    savi_cmap = LinearSegmentedColormap.from_list(
        "desert_savi", ["#d2b48c", "#90ee90", "#006400"] 
    )

    for year in years_to_compare:
        print(f"\n📸 Fetching imagery for {year}...")
        time_range = f"{year}-09-01/{year}-10-31"
        
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox_wgs84,
            datetime=time_range,
            query={"eo:cloud_cover": {"lt": 10}}
        )
        items = search.item_collection()
        
        if len(items) == 0:
            print(f"⚠️ No imagery found for {year}.")
            continue
            
        # Build Datacube (RGB + NIR)
        cube = stackstac.stack(
            items,
            assets=["B04", "B03", "B02", "B08"], 
            bounds_latlon=bbox_wgs84,
            epsg=32612,
            resolution=10
        )
        
        median_cube = cube.median(dim="time", skipna=True).compute()
        
        # Extract individual bands using double quotes for the pointers
        red = median_cube.sel(band="B04").values
        green = median_cube.sel(band="B03").values
        blue = median_cube.sel(band="B02").values
        nir = median_cube.sel(band="B08").values
        
        # --- 1. Generate True Color Image ---
        # Sentinel-2 optical data is scaled by 10000. We divide to get standard 0-1 decimals.
        # We also clip the maximum to 0.3 to artificially brighten the image so the terrain pops.
        rgb = np.dstack((red, green, blue)) / 10000.0
        rgb = np.clip(rgb / 0.3, 0, 1) 
        
        plt.figure(figsize=(10, 10))
        plt.imshow(rgb)
        plt.axis("off")
        plt.title(f"Silverbell Mine True Color ({year})", fontsize=16)
        plt.tight_layout()
        
        true_color_path = f"../data/processed/true_color_{year}.png"
        plt.savefig(true_color_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        print(f"✅ Saved: {true_color_path}")
        
        # --- 2. Generate SAVI Heatmap ---
        np.seterr(divide="ignore", invalid="ignore")
        L = 0.5
        savi = ((nir - red) / (nir + red + L)) * (1.0 + L)
        
        plt.figure(figsize=(10, 10))
        # We strictly lock the color scale (vmin to vmax) so the colors mean the exact 
        # same thing across both years. Otherwise, Matplotlib auto-stretches them.
        plt.imshow(savi, cmap=savi_cmap, vmin=0.0, vmax=0.3) 
        plt.axis("off")
        plt.title(f"Silverbell Mine SAVI Heatmap ({year})", fontsize=16)
        plt.colorbar(shrink=0.7, label="SAVI Value")
        plt.tight_layout()
        
        heatmap_path = f"../data/processed/savi_heatmap_{year}.png"
        plt.savefig(heatmap_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        print(f"✅ Saved: {heatmap_path}")

if __name__ == "__main__":
    generate_snapshots()