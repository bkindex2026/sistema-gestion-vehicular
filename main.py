import os
from typing import List, Optional
from datetime import date
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session
import cloudinary
import cloudinary.uploader

import models
from database import engine, get_db

# Configuración de Cloudinary para almacenamiento permanente
cloudinary.config(
    cloud_name="waeqxw9d",
    api_key="843623439288624",
    api_secret="449u-DZA3ZBkZW3jmWft4zqxe1I",
    secure=True
)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="API Ponderosa Flota - Backend Integrado Cloudinary", version="1.0.4")

# Lista explícita de orígenes permitidos (Sin comodín '*' para evitar rechazo CORS con credenciales)
origins = [
    "https://bkindex2026.github.io",
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def subir_a_cloudinary(archivo: UploadFile, folder: str = "ponderosa_flota") -> str:
    try:
        resultado = cloudinary.uploader.upload(
            archivo.file,
            folder=folder,
            resource_type="auto"
        )
        return resultado.get("secure_url")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir archivo a la nube: {str(e)}")

# --- MÓDULO 1: AUTENTICACIÓN Y USUARIOS ---
@app.post("/login/")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email_usuario = form_data.username.strip().lower()
    clave_usuario = form_data.password.strip()

    usuario = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == email_usuario).first()
    
    if not usuario:
        raise HTTPException(status_code=400, detail="El correo ingresado no está registrado en la base de datos.")
    
    if usuario.password.strip() != clave_usuario:
        raise HTTPException(status_code=400, detail="La contraseña ingresada es incorrecta.")

    return {"access_token": usuario.email, "token_type": "bearer", "rol": usuario.rol}

@app.post("/usuarios/")
def crear_usuario(usuario: dict, db: Session = Depends(get_db)):
    nuevo = models.Usuario(
        nombre=usuario.get("nombre"),
        email=usuario.get("email"),
        password=usuario.get("password"),
        rol=usuario.get("rol", "Lectura")
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"mensaje": "Usuario creado exitosamente", "id_usuario": nuevo.id_usuario}

# --- MÓDULO 2: GESTIÓN DE VEHÍCULOS Y HOJA DE VIDA ---
@app.get("/vehiculos/")
def listar_vehiculos(db: Session = Depends(get_db)):
    return db.query(models.Vehiculo).all()

@app.post("/vehiculos/")
async def crear_vehiculo(
    placa: str = Form(...),
    sede_asignada: Optional[str] = Form("Por Asignar"),
    marca: Optional[str] = Form("Por Especificar"),
    modelo: Optional[str] = Form("Por Especificar"),
    anio: Optional[int] = Form(2024),
    numero_vin: Optional[str] = Form("S/N"),
    descripcion: Optional[str] = Form("Registrado por placa"),
    archivo_tive: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    url_tive_val = None
    if archivo_tive and archivo_tive.filename:
        url_tive_val = subir_a_cloudinary(archivo_tive, folder="tives")

    nuevo_v = models.Vehiculo(
        placa=placa,
        sede_asignada=sede_asignada,
        marca=marca,
        modelo=modelo,
        anio=anio,
        numero_vin=numero_vin,
        descripcion=descripcion,
        url_tive=url_tive_val
    )
    db.add(nuevo_v)
    db.commit()
    db.refresh(nuevo_v)
    return nuevo_v

@app.post("/vehiculos/{id_vehiculo}/tive/")
async def subir_tive_vehiculo(
    id_vehiculo: int,
    archivo_tive: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    vehiculo = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == id_vehiculo).first()
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    
    if archivo_tive and archivo_tive.filename:
        url_cloud = subir_a_cloudinary(archivo_tive, folder="tives")
        vehiculo.url_tive = url_cloud
        db.commit()
        db.refresh(vehiculo)
        return {"mensaje": "TIVE subida a Cloudinary exitosamente", "url_tive": vehiculo.url_tive}
    
    raise HTTPException(status_code=400, detail="Archivo no válido")

@app.get("/vehiculos/{id_vehiculo}/hoja_vida/")
def obtener_hoja_vida(id_vehiculo: int, db: Session = Depends(get_db)):
    v = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == id_vehiculo).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    
    seguros = db.query(models.Seguro).filter(models.Seguro.id_vehiculo == id_vehiculo).all()
    documentos = db.query(models.Documento).filter(models.Documento.id_vehiculo == id_vehiculo).all()
    reparaciones = db.query(models.Reparacion).filter(models.Reparacion.id_vehiculo == id_vehiculo).all()
    
    return {
        "id_vehiculo": v.id_vehiculo,
        "placa": v.placa,
        "sede_asignada": v.sede_asignada,
        "marca": v.marca,
        "modelo": v.modelo,
        "anio": v.anio,
        "numero_vin": v.numero_vin,
        "kilometraje_actual": v.kilometraje_actual,
        "url_tive": v.url_tive,
        "seguros": seguros,
        "documentos": documentos,
        "reparaciones": reparaciones
    }

# --- MÓDULO 3: SEGUROS Y SOAT ---
@app.post("/seguros/")
async def crear_seguro(
    id_vehiculo: int = Form(...),
    tipo_seguro: str = Form(...),
    compania_seguros: str = Form(...),
    broker: Optional[str] = Form("N/A"),
    costo_prima: Optional[float] = Form(0.0),
    numero_poliza: str = Form(...),
    fecha_inicio: date = Form(...),
    fecha_vencimiento: date = Form(...),
    archivo_adjunto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    url_adj = None
    if archivo_adjunto and archivo_adjunto.filename:
        url_adj = subir_a_cloudinary(archivo_adjunto, folder="seguros")

    nuevo_s = models.Seguro(
        id_vehiculo=id_vehiculo,
        tipo_seguro=tipo_seguro,
        compania_seguros=compania_seguros,
        broker=broker,
        costo_prima=costo_prima,
        numero_poliza=numero_poliza,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento,
        url_adjunto=url_adj
    )
    db.add(nuevo_s)
    db.commit()
    db.refresh(nuevo_s)
    return nuevo_s

@app.get("/seguros/vencimientos/")
def listar_seguros_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.Seguro).all()

# --- MÓDULO 4: REVISIONES TÉCNICAS (CITV) ---
@app.post("/documentos/")
async def crear_documento(
    id_vehiculo: int = Form(...),
    tipo_documento: str = Form(...),
    entidad_emisora: str = Form(...),
    numero_documento: str = Form(...),
    fecha_emision: date = Form(...),
    fecha_vencimiento: date = Form(...),
    archivo_adjunto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    url_adj = None
    if archivo_adjunto and archivo_adjunto.filename:
        url_adj = subir_a_cloudinary(archivo_adjunto, folder="citv")

    nuevo_doc = models.Documento(
        id_vehiculo=id_vehiculo,
        tipo_documento=tipo_documento,
        entidad_emisora=entidad_emisora,
        numero_documento=numero_documento,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        url_adjunto=url_adj
    )
    db.add(nuevo_doc)
    db.commit()
    db.refresh(nuevo_doc)
    return nuevo_doc

@app.get("/documentos/vencimientos/")
def listar_documentos_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.Documento).all()

# --- MÓDULO 5: RASTREO GPS ---
@app.post("/gps/")
def crear_gps(
    id_vehiculo: int = Form(...),
    empresa_gps: str = Form(...),
    fecha_inicio: date = Form(...),
    fecha_vencimiento: date = Form(...),
    db: Session = Depends(get_db)
):
    nuevo_gps = models.GPS(
        id_vehiculo=id_vehiculo,
        empresa_gps=empresa_gps,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento
    )
    db.add(nuevo_gps)
    db.commit()
    db.refresh(nuevo_gps)
    return nuevo_gps

@app.get("/gps/vencimientos/")
def listar_gps_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.GPS).all()

# --- MÓDULO 6: TALLER, MANTENIMIENTO Y REPUESTOS ---
@app.post("/reparaciones/")
async def crear_reparacion(
    id_vehiculo: int = Form(...),
    tipo_mantenimiento: str = Form(...),
    taller_servicio: str = Form(...),
    responsable_reparacion: str = Form(...),
    fecha_ingreso: date = Form(...),
    descripcion_falla: Optional[str] = Form(""),
    archivo_adjunto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    url_adj = None
    if archivo_adjunto and archivo_adjunto.filename:
        url_adj = subir_a_cloudinary(archivo_adjunto, folder="taller")

    nueva_rep = models.Reparacion(
        id_vehiculo=id_vehiculo,
        tipo_mantenimiento=tipo_mantenimiento,
        taller_servicio=taller_servicio,
        responsable_reparacion=responsable_reparacion,
        fecha_ingreso=fecha_ingreso,
        descripcion_falla=descripcion_falla,
        url_adjunto=url_adj
    )
    db.add(nueva_rep)
    db.commit()
    db.refresh(nueva_rep)
    return nueva_rep

# --- MÓDULO 7: INICIALIZADOR PROTEGIDO Y SINCRONIZADOR DE CLAVE ---
@app.get("/init-db/")
def inicializar_base_de_datos(db: Session = Depends(get_db)):
    models.Base.metadata.create_all(bind=engine)
    admin_exist = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == "vtiburcioaliaga@gmail.com").first()
    if not admin_exist:
        admin = models.Usuario(
            nombre="Víctor Tiburcio",
            email="vtiburcioaliaga@gmail.com",
            password="Bkindex123$%&",
            rol="Administrador"
        )
        db.add(admin)
        db.commit()
        return {"mensaje": "Base de datos inicializada y usuario Administrador creado."}
    else:
        admin_exist.password = "Bkindex123$%&"
        db.commit()
        return {"mensaje": "Base de datos verificada y clave de Administrador sincronizada."}