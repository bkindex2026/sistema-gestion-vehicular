import os
import shutil
from typing import Optional

from database import Base, engine, get_db
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
import models
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

# Carpeta física donde se guardan las fotos y PDFs subidos
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Sistema de Gestión Vehicular - Ponderosa Flota")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Encriptación compatible tanto en Windows como en Render (Linux)
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto"
)


# ---------------------------------------------------------
# Funciones Auxiliares de Seguridad
# ---------------------------------------------------------
def encriptar_password(password: str) -> str:
  return pwd_context.hash(password)


def verificar_password(plain_password: str, hashed_password: str) -> bool:
  return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------
# MÓDULO 1: Autenticación y Gestión de Usuarios
# ---------------------------------------------------------
class UsuarioCreate(BaseModel):
  nombre: str
  email: str
  password: str
  rol: str = "Lectura"


@app.post("/usuarios/")
def crear_usuario(usuario: UsuarioCreate, db: Session = Depends(get_db)):
  if (
      db.query(models.Usuario)
      .filter(models.Usuario.email == usuario.email)
      .first()
  ):
    raise HTTPException(
        status_code=400, detail="El correo electrónico ya está registrado"
    )

  nuevo = models.Usuario(
      nombre=usuario.nombre,
      email=usuario.email,
      hashed_password=encriptar_password(usuario.password),
      rol=usuario.rol,
  )
  db.add(nuevo)
  db.commit()
  db.refresh(nuevo)
  return {"id": nuevo.id_usuario, "nombre": nuevo.nombre, "rol": nuevo.rol}


@app.post("/login/")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
  usuario = (
      db.query(models.Usuario)
      .filter(models.Usuario.email == form_data.username)
      .first()
  )
  if not usuario or not verificar_password(
      form_data.password, usuario.hashed_password
  ):
    raise HTTPException(
        status_code=401, detail="Correo o contraseña incorrectos"
    )

  return {
      "access_token": usuario.email,
      "token_type": "bearer",
      "rol": usuario.rol,
      "mensaje": f"Bienvenido {usuario.nombre}",
  }


# ---------------------------------------------------------
# MÓDULO 2: Flota Vehicular y Hoja de Vida
# ---------------------------------------------------------
@app.post("/vehiculos/")
async def crear_vehiculo(
    placa: str = Form(...),
    sede_asignada: Optional[str] = Form("Sin Sede"),
    marca: Optional[str] = Form("N/A"),
    modelo: Optional[str] = Form("N/A"),
    anio: Optional[int] = Form(0),
    numero_vin: Optional[str] = Form("N/A"),
    descripcion: Optional[str] = Form(""),
    archivo_tive: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
  placa_upper = placa.strip().upper()
  if (
      db.query(models.Vehiculo)
      .filter(models.Vehiculo.placa == placa_upper)
      .first()
  ):
    raise HTTPException(
        status_code=400, detail="La placa ya se encuentra registrada"
    )

  url_tive = ""
  if archivo_tive and archivo_tive.filename:
    ext = os.path.splitext(archivo_tive.filename)[1]
    filename = f"TIVE_{placa_upper}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
      shutil.copyfileobj(archivo_tive.file, buffer)
    url_tive = f"/uploads/{filename}"

  nuevo = models.Vehiculo(
      placa=placa_upper,
      sede_asignada=sede_asignada,
      marca=marca,
      modelo=modelo,
      anio=anio,
      numero_vin=numero_vin,
      descripcion=descripcion,
      url_tive=url_tive,
      kilometraje_actual=0.0,
  )
  db.add(nuevo)
  db.commit()
  db.refresh(nuevo)
  return nuevo


@app.get("/vehiculos/")
def listar_vehiculos(db: Session = Depends(get_db)):
  return db.query(models.Vehiculo).all()


@app.get("/vehiculos/{id_vehiculo}/hoja_vida/")
def obtener_hoja_vida(id_vehiculo: int, db: Session = Depends(get_db)):
  vehiculo = (
      db.query(models.Vehiculo)
      .options(
          joinedload(models.Vehiculo.seguros),
          joinedload(models.Vehiculo.gps),
          joinedload(models.Vehiculo.documentos),
          joinedload(models.Vehiculo.reparaciones).joinedload(
              models.Reparacion.repuestos
          ),
      )
      .filter(models.Vehiculo.id_vehiculo == id_vehiculo)
      .first()
  )
  if not vehiculo:
    raise HTTPException(status_code=404, detail="Vehículo no encontrado")
  return vehiculo


# ---------------------------------------------------------
# MÓDULO 3: Seguros / SOAT
# ---------------------------------------------------------
@app.post("/seguros/")
async def registrar_seguro(
    id_vehiculo: int = Form(...),
    tipo_seguro: str = Form(...),
    compania_seguros: str = Form(...),
    broker: str = Form(...),
    costo_prima: float = Form(0.0),
    numero_poliza: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_vencimiento: str = Form(...),
    archivo_adjunto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
  url_adjunto = ""
  if archivo_adjunto and archivo_adjunto.filename:
    ext = os.path.splitext(archivo_adjunto.filename)[1]
    filename = f"SEGURO_{id_vehiculo}_{tipo_seguro.replace(' ', '_')}_{numero_poliza}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
      shutil.copyfileobj(archivo_adjunto.file, buffer)
    url_adjunto = f"/uploads/{filename}"

  nuevo = models.Seguro(
      id_vehiculo=id_vehiculo,
      tipo_seguro=tipo_seguro,
      compania_seguros=compania_seguros,
      broker=broker,
      costo_prima=costo_prima,
      numero_poliza=numero_poliza,
      fecha_inicio=fecha_inicio,
      fecha_vencimiento=fecha_vencimiento,
      url_adjunto=url_adjunto,
  )
  db.add(nuevo)
  db.commit()
  db.refresh(nuevo)
  return nuevo


@app.get("/seguros/vencimientos/")
def consultar_seguros(db: Session = Depends(get_db)):
  return db.query(models.Seguro).all()


# ---------------------------------------------------------
# MÓDULO 4: Documentación Legal (CITV / Revisiones Técnicas)
# ---------------------------------------------------------
@app.post("/documentos/")
async def registrar_documento(
    id_vehiculo: int = Form(...),
    tipo_documento: str = Form("Revision Tecnica"),
    entidad_emisora: str = Form(...),
    numero_documento: str = Form(...),
    fecha_emision: str = Form(...),
    fecha_vencimiento: str = Form(...),
    archivo_adjunto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
  url_adjunto = ""
  if archivo_adjunto and archivo_adjunto.filename:
    ext = os.path.splitext(archivo_adjunto.filename)[1]
    filename = f"CITV_{id_vehiculo}_{numero_documento.replace(' ', '_')}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
      shutil.copyfileobj(archivo_adjunto.file, buffer)
    url_adjunto = f"/uploads/{filename}"

  nuevo = models.Documento(
      id_vehiculo=id_vehiculo,
      tipo_documento=tipo_documento,
      entidad_emisora=entidad_emisora,
      numero_documento=numero_documento,
      fecha_emision=fecha_emision,
      fecha_vencimiento=fecha_vencimiento,
      url_adjunto=url_adjunto,
  )
  db.add(nuevo)
  db.commit()
  db.refresh(nuevo)
  return nuevo


@app.get("/documentos/vencimientos/")
def consultar_documentos(db: Session = Depends(get_db)):
  return db.query(models.Documento).all()


# ---------------------------------------------------------
# MÓDULO 5: Rastreo GPS
# ---------------------------------------------------------
@app.post("/gps/")
def registrar_gps(
    id_vehiculo: int = Form(...),
    empresa_gps: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_vencimiento: str = Form(...),
    db: Session = Depends(get_db),
):
  nuevo = models.ServicioGPS(
      id_vehiculo=id_vehiculo,
      empresa_gps=empresa_gps,
      fecha_inicio=fecha_inicio,
      fecha_vencimiento=fecha_vencimiento,
  )
  db.add(nuevo)
  db.commit()
  db.refresh(nuevo)
  return nuevo


@app.get("/gps/vencimientos/")
def consultar_gps(db: Session = Depends(get_db)):
  return db.query(models.ServicioGPS).all()


# ---------------------------------------------------------
# MÓDULO 6: Reparaciones y Mantenimiento
# ---------------------------------------------------------
@app.post("/reparaciones/")
def registrar_reparacion(
    id_vehiculo: int = Form(...),
    tipo_mantenimiento: str = Form(...),
    taller_servicio: str = Form(...),
    responsable_reparacion: str = Form(...),
    fecha_ingreso: str = Form(...),
    descripcion_falla: str = Form(...),
    db: Session = Depends(get_db),
):
  nueva = models.Reparacion(
      id_vehiculo=id_vehiculo,
      tipo_mantenimiento=tipo_mantenimiento,
      taller_servicio=taller_servicio,
      responsable_reparacion=responsable_reparacion,
      fecha_ingreso=fecha_ingreso,
      descripcion_falla=descripcion_falla,
  )
  db.add(nueva)
  db.commit()
  db.refresh(nueva)
  return nueva


# ---------------------------------------------------------
# MÓDULO 7: Inicializador Automático de Tablas y Roles (Neon.tech)
# ---------------------------------------------------------
@app.get("/init-db")
def inicializar_base_de_datos():
  # 1. Crear la estructura de tablas en PostgreSQL
  models.Base.metadata.create_all(bind=engine)

  db = next(get_db())
  try:
    # 2. Comprobar si ya existe el Administrador principal
    admin_exist = (
        db.query(models.Usuario)
        .filter(models.Usuario.email == "vtiburcioaliaga@gmail.com")
        .first()
    )

    if not admin_exist:
      # Usuario 1: ADMINISTRADOR (Control Total)
      usuario_admin = models.Usuario(
          nombre="Victor Tiburcio",
          email="vtiburcioaliaga@gmail.com",
          hashed_password=encriptar_password("Bkindex123$%&"),
          rol="Administrador",
      )

      # Usuario 2: EDICIÓN (Ingreso, modificación y borrado operativo)
      usuario_editor = models.Usuario(
          nombre="Operador Flota",
          email="operacion@ponderosa.com",
          hashed_password=encriptar_password("Operacion2026*"),
          rol="Edicion",
      )

      # Usuario 3: LECTURA (Solo consulta de datos y reportes)
      usuario_lector = models.Usuario(
          nombre="Usuario Consulta",
          email="consulta@ponderosa.com",
          hashed_password=encriptar_password("FlotaPonderosa2026"),
          rol="Lectura",
      )

      # Registrar los 3 usuarios en Neon.tech
      db.add(usuario_admin)
      db.add(usuario_editor)
      db.add(usuario_lector)
      db.commit()

      return {
          "status": "ok",
          "mensaje": (
              "Tablas y los 3 usuarios registrados exitosamente en Neon.tech"
          ),
          "roles": ["Administrador", "Edicion", "Lectura"],
      }

    return {
        "status": "ok",
        "mensaje": "La base de datos ya cuenta con la estructura y usuarios.",
    }

  except Exception as e:
    db.rollback()
    return {"status": "error", "detalle": str(e)}
  finally:
    db.close()
