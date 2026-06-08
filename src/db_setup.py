from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geometry

# This Base class acts as the blueprint for our tables
Base = declarative_base()

# 1. The Time-Series Metrics Table
class VegetationStat(Base):
    __tablename__ = 'vegetation_stats'
    
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    index_type = Column(String(10), nullable=False)       # 'NDVI' or 'SAVI'
    classification = Column(String(50), nullable=False)   # 'Established Canopy', etc.
    pixel_count = Column(Integer)
    area_hectares = Column(Float)
    percentage = Column(Float)

# 2. The Spatial Vector Table
class PermitBoundary(Base):
    __tablename__ = 'permit_boundaries'
    
    id = Column(Integer, primary_key=True)
    site_name = Column(String(100), nullable=False)
    # GeoAlchemy2 automatically handles the PostGIS geometry typing
    geom = Column(Geometry('POLYGON', srid=4326)) 

def init_db():
    DB_URL = "postgresql://postgres:postgres_admin_password@localhost:5432/silverbell"
    engine = create_engine(DB_URL)
    
    print("Translating Python models into PostGIS tables...")
    # This command checks the database and builds any tables that don't exist yet
    Base.metadata.create_all(engine)
    print("✅ Tables successfully created!")

if __name__ == "__main__":
    init_db()