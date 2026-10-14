from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configuración de la conexión a PostgreSQL
# IMPORTANTE: Reemplaza 'TU_CONTRASEÑA' con la clave que creaste para postgres en la instalación
DATABASE_URL = "postgresql://postgres:Bkindex123$%&@localhost:5432/gestion_vehicular"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()