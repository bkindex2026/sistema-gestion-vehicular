import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. Enlace directo de respaldo a Neon.tech (Tus credenciales exactas)
NEON_URL = "postgresql+psycopg2://neondb_owner:npg_x7kQ1LZbXW9A@ep-rough-math-a54l5h48-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"

# 2. Lectura estricta: Si la variable de entorno no existe o está vacía (""), fuerza NEON_URL
env_value = os.getenv("DATABASE_URL", "").strip()

if env_value and ("postgres://" in env_value or "postgresql://" in env_value):
    DATABASE_URL = env_value
else:
    DATABASE_URL = NEON_URL

# 3. Corrección de protocolo para SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

print(f"--> Conectando a PostgreSQL Neon: {DATABASE_URL[:45]}...")

# 4. Inicialización del motor y sesión
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()