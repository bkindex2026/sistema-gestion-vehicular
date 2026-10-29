import os
import bcrypt
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
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- CONFIGURACIÓN DE CLOUDINARY ---
cloudinary.config(
    cloud_name="waeqxw9d",
    api_key="843623439288624",
    api_secret="449u-DZA3ZBkZW3jmWft4zqxe1I",
    secure=True
)

# Creación de tablas en la base de datos Neon.tech
models.Base.metadata.create_all(bind=engine)

# --- INICIALIZACIÓN DE FASTAPI Y CORS ---
app = FastAPI(title="Ponderosa Flota API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bkindex2026.github.io",
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ],
    allow_credentials=False,  # Desactivado para evitar bloqueos de cabecera en navegadores móviles y desktop
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ESQUEMA PYDANTIC PARA OPERACIONES DIARIAS ---
class OperacionSchema(BaseModel):
    id_vehiculo: int
    chofer: str
    fecha_operacion: str
    tipo_trabajo: Optional[str] = None
    ruta_origen_destino: Optional[str] = None
    toneladas_carga: Optional[float] = 0.0
    carga_toneladas: Optional[float] = None  # Soporte para ambos nombres de variable
    numero_viajes: Optional[int] = 1
    km_horometro_inicial: Optional[float] = 0.0
    km_horometro_final: Optional[float] = 0.0
    galones_combustible: Optional[float] = 0.0
    costo_combustible: Optional[float] = 0.0
    galones_urea: Optional[float] = 0.0
    costo_urea: Optional[float] = 0.0
    grifo_surtidor: Optional[str] = None
    observaciones: Optional[str] = None


def subir_a_cloudinary(archivo: UploadFile, carpeta: str) -> str:
    try:
        resultado = cloudinary.uploader.upload(
            archivo.file,
            folder=f"ponderosa_flota/{carpeta}",
            resource_type="auto"
        )
        return resultado.get("secure_url", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir archivo a Cloudinary: {str(e)}")


# --- ENDPOINT DE SALUD ---
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Servidor backend activo."}


# --- LOGIN CON VERIFICACIÓN BCRYPT Y SEGURIDAD ---
@app.post("/login/")
def login(data: dict, db: Session = Depends(get_db)):
    raw_email = data.get("email")
    password = data.get("password")
    
    if not raw_email or not password:
        raise HTTPException(status_code=400, detail="Debe ingresar correo y contraseña.")
    
    email_clean = str(raw_email).strip().lower()
    
    # 1. Búsqueda de usuario (insensible a mayúsculas)
    user = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == email_clean).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    # 2. Verificación nativa con bcrypt (sin pasar por passlib)
    es_valida = False
    stored_pw = user.password or ""
    
    try:
        if stored_pw.startswith("$2b$") or stored_pw.startswith("$2a$"):
            # Compara directamente con la librería bcrypt oficial
            es_valida = bcrypt.checkpw(password.encode('utf-8'), stored_pw.encode('utf-8'))
        else:
            es_valida = (stored_pw == password)
    except Exception:
        es_valida = False
        
    if not es_valida:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
        
    return {
        "access_token": user.email,
        "token_type": "bearer",
        "rol": user.rol,
        "nombre": getattr(user, 'nombre', user.email)
    }


# --- VEHÍCULOS ---
@app.get("/vehiculos/")
def listar_vehiculos(db: Session = Depends(get_db)):
    return db.query(models.Vehiculo).order_by(models.Vehiculo.id_vehiculo.asc()).all()


@app.post("/vehiculos/")
def crear_vehiculo(
    placa: str = Form(...),
    sede_asignada: str = Form("Por Asignar"),
    marca: str = Form("Por Especificar"),
    modelo: str = Form("Por Especificar"),
    anio: int = Form(2024),
    numero_vin: str = Form("S/N"),
    descripcion: str = Form(""),
    archivo_tive: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    existente = db.query(models.Vehiculo).filter(models.Vehiculo.placa == placa.upper().strip()).first()
    if existente:
        raise HTTPException(status_code=400, detail="La placa ya está registrada")
    url_tive = ""
    if archivo_tive:
        url_tive = subir_a_cloudinary(archivo_tive, "tive")
    nuevo_v = models.Vehiculo(
        placa=placa.upper().strip(),
        sede_asignada=sede_asignada,
        marca=marca,
        modelo=modelo,
        anio=anio,
        numero_vin=numero_vin,
        descripcion=descripcion,
        url_tive=url_tive
    )
    db.add(nuevo_v)
    db.commit()
    db.refresh(nuevo_v)
    return nuevo_v


@app.post("/vehiculos/{id_vehiculo}/tive/")
def subir_tive_vehiculo(id_vehiculo: int, archivo_tive: UploadFile = File(...), db: Session = Depends(get_db)):
    v = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == id_vehiculo).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    
    url_cloud = subir_a_cloudinary(archivo_tive, "tive")
    v.url_tive = url_cloud
    db.commit()
    return {"mensaje": "Tarjeta TIVE subida a Cloudinary exitosamente", "url": url_cloud}


@app.get("/vehiculos/{id_vehiculo}/hoja_vida/")
def obtener_hoja_vida(id_vehiculo: int, db: Session = Depends(get_db)):
    vehiculo = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == id_vehiculo).first()
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    try: seguros = db.query(models.Seguro).filter(models.Seguro.id_vehiculo == id_vehiculo).all()
    except Exception: seguros = []
    try: documentos = db.query(models.Documento).filter(models.Documento.id_vehiculo == id_vehiculo).all()
    except Exception: documentos = []
    try: reparaciones = db.query(models.Reparacion).filter(models.Reparacion.id_vehiculo == id_vehiculo).all()
    except Exception: reparaciones = []
    try: gps = db.query(models.ServicioGPS).filter(models.ServicioGPS.id_vehiculo == id_vehiculo).all()
    except Exception: gps = []
    try: llantas = db.query(models.Llanta).filter(models.Llanta.id_vehiculo == id_vehiculo).all()
    except Exception: llantas = []
    try: operaciones = db.query(models.OperacionDiaria).filter(models.OperacionDiaria.id_vehiculo == id_vehiculo).all()
    except Exception: operaciones = []
    return {
        "id_vehiculo": vehiculo.id_vehiculo,
        "placa": vehiculo.placa,
        "sede_asignada": getattr(vehiculo, 'sede_asignada', 'Por Asignar'),
        "marca": getattr(vehiculo, 'marca', 'N/A'),
        "modelo": getattr(vehiculo, 'modelo', 'N/A'),
        "anio": getattr(vehiculo, 'anio', 2024),
        "numero_vin": getattr(vehiculo, 'numero_vin', 'S/N'),
        "kilometraje_actual": getattr(vehiculo, 'kilometraje_actual', 0.0),
        "seguros": seguros,
        "documentos": documentos,
        "reparaciones": reparaciones,
        "gps": gps,
        "llantas": llantas,
        "operaciones": operaciones
    }


# --- SEGUROS ---
@app.get("/seguros/vencimientos/")
def listar_seguros_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.Seguro).order_by(models.Seguro.fecha_vencimiento.asc()).all()


@app.post("/seguros/")
def registrar_seguro(
    id_vehiculo: int = Form(...),
    tipo_seguro: str = Form(...),
    compania_seguros: str = Form(...),
    broker: str = Form("N/A"),
    costo_prima: float = Form(0.0),
    numero_poliza: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_vencimiento: str = Form(...),
    reemplazar: str = Form("false"),
    archivo_adjunto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    if reemplazar != "true":
        existente = db.query(models.Seguro).filter(models.Seguro.id_vehiculo == id_vehiculo, models.Seguro.tipo_seguro == tipo_seguro).first()
        if existente:
            return {"requiere_confirmacion": True, "mensaje": f"Ya existe un {tipo_seguro} activo. ¿Desea reemplazarlo?"}
    if reemplazar == "true":
        db.query(models.Seguro).filter(models.Seguro.id_vehiculo == id_vehiculo, models.Seguro.tipo_seguro == tipo_seguro).delete()
    url_adjunto = ""
    if archivo_adjunto:
        url_adjunto = subir_a_cloudinary(archivo_adjunto, "seguros")
    nuevo_s = models.Seguro(
        id_vehiculo=id_vehiculo,
        tipo_seguro=tipo_seguro,
        compania_seguros=compania_seguros,
        broker=broker,
        costo_prima=costo_prima,
        numero_poliza=numero_poliza,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento,
        url_adjunto=url_adjunto
    )
    db.add(nuevo_s)
    db.commit()
    return {"mensaje": "Seguro registrado correctamente"}


@app.delete("/seguros/{id_seguro}/")
def eliminar_seguro(id_seguro: int, db: Session = Depends(get_db)):
    s = db.query(models.Seguro).filter(models.Seguro.id_seguro == id_seguro).first()
    if not s:
        raise HTTPException(status_code=404, detail="Seguro no encontrado")
    db.delete(s)
    db.commit()
    return {"mensaje": "Seguro eliminado"}


# --- DOCUMENTOS ---
@app.get("/documentos/vencimientos/")
def listar_documentos_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.Documento).order_by(models.Documento.fecha_vencimiento.asc()).all()


@app.post("/documentos/")
def registrar_documento(
    id_vehiculo: int = Form(...),
    tipo_documento: str = Form(...),
    entidad_emisora: str = Form(...),
    numero_documento: str = Form(...),
    fecha_emision: str = Form(...),
    fecha_vencimiento: str = Form(...),
    archivo_adjunto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    url_adjunto = ""
    if archivo_adjunto:
        url_adjunto = subir_a_cloudinary(archivo_adjunto, "documentos")
    nuevo_d = models.Documento(
        id_vehiculo=id_vehiculo,
        tipo_documento=tipo_documento,
        entidad_emisora=entidad_emisora,
        numero_documento=numero_documento,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        url_adjunto=url_adjunto
    )
    db.add(nuevo_d)
    db.commit()
    return {"mensaje": "Documento registrado correctamente"}


@app.delete("/documentos/{id_documento}/")
def eliminar_documento(id_documento: int, db: Session = Depends(get_db)):
    d = db.query(models.Documento).filter(models.Documento.id_documento == id_documento).first()
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    db.delete(d)
    db.commit()
    return {"mensaje": "Documento eliminado"}


# --- GPS ---
@app.get("/gps/vencimientos/")
def listar_gps_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.ServicioGPS).order_by(models.ServicioGPS.fecha_vencimiento.asc()).all()


@app.post("/gps/")
def registrar_gps(
    id_vehiculo: int = Form(...),
    empresa_gps: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_vencimiento: str = Form(...),
    db: Session = Depends(get_db)
):
    v = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == id_vehiculo).first()
    if v:
        v.tiene_gps = True
        v.empresa_gps = empresa_gps
        v.vencimiento_gps = fecha_vencimiento
    nuevo_g = models.ServicioGPS(
        id_vehiculo=id_vehiculo,
        empresa_gps=empresa_gps,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento
    )
    db.add(nuevo_g)
    db.commit()
    return {"mensaje": "GPS registrado correctamente"}


# --- LLANTAS ---
@app.get("/llantas/")
def listar_llantas(db: Session = Depends(get_db)):
    return db.query(models.Llanta).order_by(models.Llanta.id_llanta.desc()).all()


@app.post("/llantas/")
def registrar_llanta(
    id_vehiculo: int = Form(...),
    codigo: str = Form("S/C"),
    marca: str = Form(...),
    modelo: str = Form(...),
    posicion: str = Form(...),
    fecha_instalacion: str = Form(...),
    db: Session = Depends(get_db)
):
    nueva_l = models.Llanta(
        id_vehiculo=id_vehiculo,
        codigo=codigo,
        marca=marca,
        modelo=modelo,
        posicion=posicion,
        fecha_instalacion=fecha_instalacion
    )
    db.add(nueva_l)
    db.commit()
    return {"mensaje": "Llanta registrada exitosamente"}


@app.delete("/llantas/{id_llanta}/")
def eliminar_llanta(id_llanta: int, db: Session = Depends(get_db)):
    l = db.query(models.Llanta).filter(models.Llanta.id_llanta == id_llanta).first()
    if not l:
        raise HTTPException(status_code=404, detail="Llanta no encontrada")
    db.delete(l)
    db.commit()
    return {"mensaje": "Llanta eliminada"}


# --- REPARACIONES Y TALLER ---
@app.post("/operaciones/")
def registrar_operacion(payload: OperacionSchema, db: Session = Depends(get_db)):
    toneladas = payload.toneladas_carga if payload.toneladas_carga is not None and payload.toneladas_carga > 0 else (payload.carga_toneladas or 0.0)
    
    nueva_op = models.OperacionDiaria(
        id_vehiculo=payload.id_vehiculo,
        chofer=payload.chofer,
        fecha_operacion=payload.fecha_operacion,
        tipo_trabajo=payload.tipo_trabajo or "",
        ruta_origen_destino=payload.ruta_origen_destino or "",
        carga_toneladas=toneladas,
        numero_viajes=payload.numero_viajes or 1,
        km_horometro_inicial=payload.km_horometro_inicial or 0.0,
        km_horometro_final=payload.km_horometro_final or 0.0,
        galones_combustible=payload.galones_combustible or 0.0,
        costo_combustible=payload.costo_combustible or 0.0,
        galones_urea=payload.galones_urea or 0.0,   # <--- AGREGAR ESTA LÍNEA
        costo_urea=payload.costo_urea or 0.0,       # <--- AGREGAR ESTA LÍNEA
        grifo_surtidor=payload.grifo_surtidor or "",
        observaciones=payload.observaciones or ""
    )
    db.add(nueva_op)
    
    vehiculo = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == payload.id_vehiculo).first()
    if vehiculo and payload.km_horometro_final and payload.km_horometro_final > 0:
        vehiculo.kilometraje_actual = payload.km_horometro_final
        
    db.commit()
    db.refresh(nueva_op)
    return {"mensaje": "Parte diario registrado exitosamente", "id_operacion": nueva_op.id_operacion}


@app.delete("/reparaciones/{id_reparacion}/")
def eliminar_reparacion(id_reparacion: int, db: Session = Depends(get_db)):
    r = db.query(models.Reparacion).filter(models.Reparacion.id_reparacion == id_reparacion).first()
    if not r:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    db.delete(r)
    db.commit()
    return {"mensaje": "Registro de taller eliminado"}


# --- OPERACIONES Y CARGA DIARIA (RECEPCIÓ N JSON COMPATIBLE) ---
@app.get("/operaciones/")
def listar_operaciones(db: Session = Depends(get_db)):
    return db.query(models.OperacionDiaria).order_by(models.OperacionDiaria.fecha_operacion.desc()).all()


@app.post("/operaciones/")
def registrar_operacion(payload: OperacionSchema, db: Session = Depends(get_db)):
    # Determinación del tonelaje (soporta tanto toneladas_carga como carga_toneladas)
    toneladas = payload.toneladas_carga if payload.toneladas_carga is not None and payload.toneladas_carga > 0 else (payload.carga_toneladas or 0.0)
    
    nueva_op = models.OperacionDiaria(
        id_vehiculo=payload.id_vehiculo,
        chofer=payload.chofer,
        fecha_operacion=payload.fecha_operacion,
        tipo_trabajo=payload.tipo_trabajo or "",
        ruta_origen_destino=payload.ruta_origen_destino or "",
        carga_toneladas=toneladas,
        numero_viajes=payload.numero_viajes or 1,
        km_horometro_inicial=payload.km_horometro_inicial or 0.0,
        km_horometro_final=payload.km_horometro_final or 0.0,
        galones_combustible=payload.galones_combustible or 0.0,
        costo_combustible=payload.costo_combustible or 0.0,
        grifo_surtidor=payload.grifo_surtidor or "",
        observaciones=payload.observaciones or ""
    )
    db.add(nueva_op)
    
    # Actualización automática de kilometraje en la ficha del vehículo
    vehiculo = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == payload.id_vehiculo).first()
    if vehiculo and payload.km_horometro_final and payload.km_horometro_final > 0:
        vehiculo.kilometraje_actual = payload.km_horometro_final
        
    db.commit()
    db.refresh(nueva_op)
    return {"mensaje": "Parte diario registrado exitosamente", "id_operacion": nueva_op.id_operacion}


@app.delete("/operaciones/{id_operacion}/")
def eliminar_operacion(id_operacion: int, db: Session = Depends(get_db)):
    op = db.query(models.OperacionDiaria).filter(models.OperacionDiaria.id_operacion == id_operacion).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operación no encontrada")
    db.delete(op)
    db.commit()
    return {"mensaje": "Operación eliminada"}