import os
from typing import List, Optional
from datetime import date
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

app = FastAPI(title="API Ponderosa Flota - Backend Integrado Cloudinary", version="1.0.5")

# Configuración explícita de CORS
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

class LoginSchema(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    username: Optional[str] = None

def subir_a_cloudinary(archivo: UploadFile, folder: str = "ponderosa_flota") -> str:
    try:
        resultado = cloudinary.uploader.upload(
            archivo.file,
            folder=folder,
            resource_type="auto",
            access_mode="public"
        )
        return resultado.get("secure_url")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir archivo a la nube: {str(e)}")

# --- MÓDULO 1: AUTENTICACIÓN Y USUARIOS ---
@app.post("/login/")
def login(payload: LoginSchema, db: Session = Depends(get_db)):
    try:
        raw_email = payload.email or payload.username or ""
        raw_password = payload.password or ""
        
        email_usuario = raw_email.strip().lower()
        clave_usuario = raw_password.strip()

        if not email_usuario or not clave_usuario:
            raise HTTPException(status_code=400, detail="Debe proporcionar correo electrónico y contraseña.")

        usuario = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == email_usuario).first()
        
        if not usuario:
            raise HTTPException(status_code=400, detail="El correo ingresado no está registrado en la base de datos.")
        
        clave_db = (usuario.hashed_password or "").strip()
        if clave_db != clave_usuario:
            raise HTTPException(status_code=400, detail="La contraseña ingresada es incorrecta.")

        return {
            "access_token": usuario.email,
            "token_type": "bearer",
            "rol": usuario.rol or "Lectura"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en servidor backend: {str(e)}")

@app.post("/usuarios/")
def crear_usuario(usuario: dict, db: Session = Depends(get_db)):
    nuevo = models.Usuario(
        nombre=usuario.get("nombre"),
        email=usuario.get("email"),
        hashed_password=usuario.get("password"),
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
    llantas = db.query(models.Llanta).filter(models.Llanta.id_vehiculo == id_vehiculo).all()
    
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
        "reparaciones": reparaciones,
        "llantas": llantas
    }

# --- MÓDULO 3: SEGUROS Y SOAT ---
@app.post("/seguros/")
async def crear_o_actualizar_seguro(
    id_vehiculo: int = Form(...),
    tipo_seguro: str = Form(...),
    compania_seguros: str = Form(...),
    broker: Optional[str] = Form("N/A"),
    costo_prima: Optional[float] = Form(0.0),
    numero_poliza: str = Form(...),
    fecha_inicio: date = Form(...),
    fecha_vencimiento: date = Form(...),
    archivo_adjunto: Optional[UploadFile] = File(None),
    reemplazar: Optional[bool] = Form(False),
    db: Session = Depends(get_db)
):
    seguro_existente = db.query(models.Seguro).filter(
        models.Seguro.id_vehiculo == id_vehiculo,
        models.Seguro.tipo_seguro == tipo_seguro
    ).first()

    if seguro_existente and not reemplazar:
        return {
            "requiere_confirmacion": True,
            "mensaje": f"Esta unidad ya cuenta con un {tipo_seguro} registrado (Póliza {seguro_existente.numero_poliza}). ¿Desea reemplazarlo con el nuevo certificado?"
        }

    url_adj = None
    if archivo_adjunto and archivo_adjunto.filename:
        url_adj = subir_a_cloudinary(archivo_adjunto, folder="seguros")

    if seguro_existente and reemplazar:
        seguro_existente.compania_seguros = compania_seguros
        seguro_existente.broker = broker
        seguro_existente.costo_prima = costo_prima
        seguro_existente.numero_poliza = numero_poliza
        seguro_existente.fecha_inicio = fecha_inicio
        seguro_existente.fecha_vencimiento = fecha_vencimiento
        if url_adj:
            seguro_existente.url_adjunto = url_adj
        db.commit()
        db.refresh(seguro_existente)
        return {"requiere_confirmacion": False, "mensaje": f"{tipo_seguro} actualizado exitosamente con la nueva póliza."}

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
    return {"requiere_confirmacion": False, "mensaje": f"{tipo_seguro} guardado exitosamente."}

@app.get("/seguros/vencimientos/")
def listar_seguros_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.Seguro).all()

@app.delete("/seguros/{id_seguro}/")
def eliminar_seguro(id_seguro: int, db: Session = Depends(get_db)):
    seguro = db.query(models.Seguro).filter(models.Seguro.id_seguro == id_seguro).first()
    if not seguro:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    db.delete(seguro)
    db.commit()
    return {"mensaje": "Registro de seguro/SOAT eliminado con éxito"}

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

@app.delete("/documentos/{id_documento}/")
def eliminar_documento(id_documento: int, db: Session = Depends(get_db)):
    doc = db.query(models.Documento).filter(models.Documento.id_documento == id_documento).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    db.delete(doc)
    db.commit()
    return {"mensaje": "Documento eliminado con éxito"}

# --- MÓDULO 5: RASTREO GPS ---
@app.post("/gps/")
def crear_gps(
    id_vehiculo: int = Form(...),
    empresa_gps: str = Form(...),
    fecha_inicio: date = Form(...),
    fecha_vencimiento: date = Form(...),
    db: Session = Depends(get_db)
):
    nuevo_gps = models.ServicioGPS(
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
    return db.query(models.ServicioGPS).all()

# --- MÓDULO 6: TALLER Y REPUESTOS ---
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

@app.delete("/reparaciones/{id_reparacion}/")
def eliminar_reparacion(id_reparacion: int, db: Session = Depends(get_db)):
    rep = db.query(models.Reparacion).filter(models.Reparacion.id_reparacion == id_reparacion).first()
    if not rep:
        raise HTTPException(status_code=404, detail="Registro de taller no encontrado")
    db.delete(rep)
    db.commit()
    return {"mensaje": "Registro eliminado con éxito"}

# --- MÓDULO 7: CONTROL DE LLANTAS Y NEUMÁTICOS (INCLUYE CÓDIGO) ---
@app.post("/llantas/")
def crear_llanta(
    id_vehiculo: int = Form(...),
    codigo: str = Form(...),
    marca: str = Form(...),
    modelo: str = Form(...),
    posicion: str = Form(...),
    fecha_instalacion: date = Form(...),
    db: Session = Depends(get_db)
):
    nueva_llanta = models.Llanta(
        id_vehiculo=id_vehiculo,
        codigo=codigo,
        marca=marca,
        modelo=modelo,
        posicion=posicion,
        fecha_instalacion=fecha_instalacion
    )
    db.add(nueva_llanta)
    db.commit()
    db.refresh(nueva_llanta)
    return nueva_llanta

@app.get("/llantas/")
def listar_llantas(db: Session = Depends(get_db)):
    return db.query(models.Llanta).all()

@app.delete("/llantas/{id_llanta}/")
def eliminar_llanta(id_llanta: int, db: Session = Depends(get_db)):
    llanta = db.query(models.Llanta).filter(models.Llanta.id_llanta == id_llanta).first()
    if not llanta:
        raise HTTPException(status_code=404, detail="Neumático no encontrado")
    db.delete(llanta)
    db.commit()
    return {"mensaje": "Registro de neumático eliminado con éxito"}

# --- MÓDULO 8: INICIALIZADOR PROTEGIDO ---
@app.get("/init-db/")
def inicializar_base_de_datos(db: Session = Depends(get_db)):
    models.Base.metadata.create_all(bind=engine)
    admin_exist = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == "vtiburcioaliaga@gmail.com").first()
    if not admin_exist:
        admin = models.Usuario(
            nombre="Víctor Tiburcio",
            email="vtiburcioaliaga@gmail.com",
            hashed_password="Bkindex123$%&",
            rol="Administrador"
        )
        db.add(admin)
        db.commit()
        return {"mensaje": "Base de datos inicializada y usuario Administrador creado."}
    else:
        admin_exist.hashed_password = "Bkindex123$%&"
        db.commit()
        return {"mensaje": "Base de datos verificada y clave de Administrador sincronizada."}