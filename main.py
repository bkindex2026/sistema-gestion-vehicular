import os
import bcrypt
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
import cloudinary
import cloudinary.uploader
import models
from database import engine, get_db
import re
from fastapi import HTTPException

def sanitizar_placa(placa_raw: str) -> str:
    if not placa_raw:
        return ""
    placa = placa_raw.strip().upper().replace(" ", "")
    
    # Si viene de 6 caracteres sin guion (ej. ABC123), le inserta el guion
    if re.match(r"^[A-Z0-9]{6}$", placa):
        placa = f"{placa[:3]}-{placa[3:]}"
        
    # Valida el patrón estándar 3 caracteres - 3 caracteres
    if not re.match(r"^[A-Z0-9]{3}-[A-Z0-9]{3}$", placa):
        raise HTTPException(
            status_code=400, 
            detail="La placa ingresada no cumple el formato válido obligatorio (Ej. ABC-123)."
        )
    return placa

# --- CONFIGURACIÓN DE CLOUDINARY (ENTORNO CON RESPALDO) ---
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "waeqxw9d").strip(),
    api_key=os.getenv("CLOUDINARY_API_KEY", "843623439288624").strip(),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", "449u-DZA3ZBkZW3jmWft4zqxe1I").strip(),
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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- ESQUEMAS PYDANTIC ---
class OperacionSchema(BaseModel):
    id_vehiculo: int
    chofer: str
    fecha_operacion: str
    tipo_trabajo: Optional[str] = "Mina Baja -> Planta (Acarreo)"
    ruta_origen_destino: Optional[str] = None
    toneladas_carga: Optional[float] = 0.0
    carga_toneladas: Optional[float] = None
    numero_viajes: Optional[int] = 1
    km_horometro_inicial: Optional[float] = 0.0
    km_horometro_final: float
    kilometraje_manual: Optional[float] = None
    galones_combustible: Optional[float] = 0.0
    costo_combustible: Optional[float] = 0.0
    galones_urea: Optional[float] = 0.0
    costo_urea: Optional[float] = 0.0
    grifo_surtidor: Optional[str] = None
    observaciones: Optional[str] = None


class ChecklistSchema(BaseModel):
    id_vehiculo: int
    conductor: str
    fecha_inspeccion: str
    kilometraje: Optional[float] = 0.0
    estado_documentos: Optional[str] = "OK"
    estado_luces_exterior: Optional[str] = "OK"
    estado_neumaticos: Optional[str] = "OK"
    estado_niveles_motor: Optional[str] = "OK"
    estado_equipos_seguridad: Optional[str] = "OK"
    tiene_inconveniente: Optional[bool] = False
    detalle_inconveniente: Optional[str] = ""


class LlantaCreateSchema(BaseModel):
    id_vehiculo: int
    codigo: Optional[str] = "S/C"
    marca: str
    modelo: str
    posicion: str
    tipo_banda: Optional[str] = "Original"
    fecha_instalacion: str
    horometro_instalacion: Optional[float] = 0.0
    km_instalacion: Optional[float] = 0.0


class UsuarioCreateSchema(BaseModel):
    nombre: str
    email: str
    password: str
    rol: str


class GPSSchema(BaseModel):
    id_vehiculo: int
    empresa_gps: str
    fecha_inicio: str
    fecha_vencimiento: str


class TallerCreateSchema(BaseModel):
    id_vehiculo: int
    tipo_mantenimiento: str
    taller_servicio: str
    responsable_reparacion: str
    fecha_ingreso: str
    descripcion_falla: Optional[str] = ""


class RepuestoCreateSchema(BaseModel):
    id_vehiculo: int
    nombre_repuesto: str
    fecha_instalacion: str
    precio_total: Optional[float] = 0.0
    solicitante: str
    instalador: str


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


# --- USUARIOS ---
@app.get("/usuarios/")
def listar_usuarios(db: Session = Depends(get_db)):
    usuarios = db.query(models.Usuario).order_by(models.Usuario.id_usuario.asc()).all()
    return [
        {
            "id_usuario": u.id_usuario,
            "nombre": u.nombre,
            "email": u.email,
            "rol": u.rol
        }
        for u in usuarios
    ]


@app.post("/usuarios/")
def crear_usuario(payload: UsuarioCreateSchema, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    password_clean = payload.password.strip()
    nombre_clean = payload.nombre.strip()
    rol_clean = payload.rol.strip()

    if not nombre_clean or not email_clean or not password_clean:
        raise HTTPException(status_code=400, detail="Nombre, correo y contraseña son obligatorios.")

    existente = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == email_clean).first()
    if existente:
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")

    password_hash = bcrypt.hashpw(password_clean.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    nuevo_u = models.Usuario(
        nombre=nombre_clean,
        email=email_clean,
        password=password_hash,
        rol=rol_clean or "Lectura"
    )
    db.add(nuevo_u)
    db.commit()
    db.refresh(nuevo_u)
    return {
        "mensaje": "Usuario creado exitosamente",
        "id_usuario": nuevo_u.id_usuario,
        "nombre": nuevo_u.nombre,
        "email": nuevo_u.email,
        "rol": nuevo_u.rol
    }


# --- GPS ---
@app.get("/gps/vencimientos/")
def listar_gps_vencimientos(db: Session = Depends(get_db)):
    return db.query(models.ServicioGPS).order_by(models.ServicioGPS.fecha_vencimiento.asc()).all()


@app.post("/gps/")
def registrar_gps(payload: GPSSchema, db: Session = Depends(get_db)):
    v = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == payload.id_vehiculo).first()
    if v:
        v.tiene_gps = True
        v.empresa_gps = payload.empresa_gps.strip()
        v.vencimiento_gps = payload.fecha_vencimiento.strip()

    nuevo_g = models.ServicioGPS(
        id_vehiculo=payload.id_vehiculo,
        empresa_gps=payload.empresa_gps.strip(),
        fecha_inicio=payload.fecha_inicio.strip(),
        fecha_vencimiento=payload.fecha_vencimiento.strip()
    )
    db.add(nuevo_g)
    db.commit()
    return {"mensaje": "GPS registrado correctamente"}


# --- TALLER Y REPUESTOS ---
@app.post("/taller/")
def registrar_taller(payload: TallerCreateSchema, db: Session = Depends(get_db)):
    nueva_rep = models.Reparacion(
        id_vehiculo=payload.id_vehiculo,
        tipo_mantenimiento=payload.tipo_mantenimiento.strip(),
        taller_servicio=payload.taller_servicio.strip(),
        responsable_reparacion=payload.responsable_reparacion.strip(),
        fecha_ingreso=payload.fecha_ingreso.strip(),
        descripcion_falla=(payload.descripcion_falla or "").strip()
    )
    db.add(nueva_rep)
    db.commit()
    db.refresh(nueva_rep)
    return {"mensaje": "Mantenimiento registrado correctamente", "id_reparacion": nueva_rep.id_reparacion}


@app.post("/repuestos/")
def registrar_repuesto(payload: RepuestoCreateSchema, db: Session = Depends(get_db)):
    nuevo_rep = models.Repuesto(
        id_vehiculo=payload.id_vehiculo,
        nombre_repuesto=payload.nombre_repuesto.strip(),
        fecha_instalacion=payload.fecha_instalacion.strip(),
        precio_total=payload.precio_total or 0.0,
        solicitante=payload.solicitante.strip(),
        instalador=payload.instalador.strip()
    )
    db.add(nuevo_rep)
    db.commit()
    db.refresh(nuevo_rep)
    return {"mensaje": "Repuesto registrado correctamente", "id_repuesto": nuevo_rep.id_repuesto}


# --- LOGIN CON VERIFICACIÓN BCRYPT ---
@app.post("/login/")
def login(data: dict, db: Session = Depends(get_db)):
    raw_email = data.get("email")
    password = data.get("password")

    if not raw_email or not password:
        raise HTTPException(status_code=400, detail="Debe ingresar correo y contraseña.")

    email_clean = str(raw_email).strip().lower()
    user = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == email_clean).first()

    if not user:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    es_valida = False
    stored_pw = user.password or ""

    try:
        if stored_pw.startswith("$2b$") or stored_pw.startswith("$2a$"):
            es_valida = bcrypt.checkpw(password.encode("utf-8"), stored_pw.encode("utf-8"))
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
        "nombre": getattr(user, "nombre", user.email)
    }


# --- VEHÍCULOS ---
@app.get("/vehiculos/")
def listar_vehiculos(db: Session = Depends(get_db)):
    return db.query(models.Vehiculo).order_by(models.Vehiculo.id_vehiculo.asc()).all()


@app.post("/vehiculos/")
def crear_vehiculo(
    placa: str = Form(...),
    sede: Optional[str] = Form(None),
    marca: Optional[str] = Form(None),
    modelo: Optional[str] = Form(None),
    anio: Optional[int] = Form(None),
    vin: Optional[str] = Form(None),
    descripcion: Optional[str] = Form(None),
    archivo_tive: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    placa_normalizada = sanitizar_placa(placa)

    existe = db.query(models.Vehiculo).filter(models.Vehiculo.placa == placa_normalizada).first()
    if existe:
        raise HTTPException(status_code=400, detail=f"La placa {placa_normalizada} ya se encuentra registrada.")

    url_tive = ""
    if archivo_tive:
        url_tive = subir_a_cloudinary(archivo_tive, "tives_vehiculos")

    nuevo_vehiculo = models.Vehiculo(
        placa=placa_normalizada,
        sede_asignada=sede or "Por Asignar",
        marca=marca or "Por Especificar",
        modelo=modelo or "Por Especificar",
        anio=anio or 2024,
        numero_vin=vin or "S/N",
        descripcion=descripcion or "",
        url_tive=url_tive
    )
    db.add(nuevo_vehiculo)
    db.commit()
    db.refresh(nuevo_vehiculo)
    
    return {"mensaje": "Vehículo registrado correctamente", "id_vehiculo": nuevo_vehiculo.id_vehiculo}


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
    try:
        seguros = db.query(models.Seguro).filter(models.Seguro.id_vehiculo == id_vehiculo).all()
    except Exception:
        seguros = []
    try:
        documentos = db.query(models.Documento).filter(models.Documento.id_vehiculo == id_vehiculo).all()
    except Exception:
        documentos = []
    try:
        reparaciones = db.query(models.Reparacion).filter(models.Reparacion.id_vehiculo == id_vehiculo).all()
    except Exception:
        reparaciones = []
    try:
        gps = db.query(models.ServicioGPS).filter(models.ServicioGPS.id_vehiculo == id_vehiculo).all()
    except Exception:
        gps = []
    try:
        llantas = db.query(models.Llanta).filter(models.Llanta.id_vehiculo == id_vehiculo).all()
    except Exception:
        llantas = []
    try:
        operaciones = db.query(models.OperacionDiaria).filter(models.OperacionDiaria.id_vehiculo == id_vehiculo).all()
    except Exception:
        operaciones = []

    return {
        "id_vehiculo": vehiculo.id_vehiculo,
        "placa": vehiculo.placa,
        "sede_asignada": getattr(vehiculo, "sede_asignada", "Por Asignar"),
        "marca": getattr(vehiculo, "marca", "N/A"),
        "modelo": getattr(vehiculo, "modelo", "N/A"),
        "anio": getattr(vehiculo, "anio", 2024),
        "numero_vin": getattr(vehiculo, "numero_vin", "S/N"),
        "kilometraje_actual": getattr(vehiculo, "kilometraje_actual", 0.0),
        "url_tive": getattr(vehiculo, "url_tive", ""),
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
        existente = db.query(models.Seguro).filter(
            models.Seguro.id_vehiculo == id_vehiculo,
            models.Seguro.tipo_seguro == tipo_seguro
        ).first()
        if existente:
            return {"requiere_confirmacion": True, "mensaje": f"Ya existe un {tipo_seguro} activo. ¿Desea reemplazarlo?"}
    if reemplazar == "true":
        db.query(models.Seguro).filter(
            models.Seguro.id_vehiculo == id_vehiculo,
            models.Seguro.tipo_seguro == tipo_seguro
        ).delete()

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


# --- LLANTAS ---
@app.get("/llantas/")
def listar_llantas(db: Session = Depends(get_db)):
    return db.query(models.Llanta).order_by(models.Llanta.id_llanta.desc()).all()


@app.post("/llantas/")
def registrar_llanta(payload: LlantaCreateSchema, db: Session = Depends(get_db)):
    nueva_l = models.Llanta(
        id_vehiculo=payload.id_vehiculo,
        codigo=(payload.codigo or "S/C").strip(),
        marca=payload.marca.strip(),
        modelo=payload.modelo.strip(),
        posicion=payload.posicion.strip(),
        tipo_banda=(payload.tipo_banda or "Original").strip(),
        fecha_instalacion=payload.fecha_instalacion,
        horometro_instalacion=payload.horometro_instalacion or 0.0,
        km_instalacion=payload.km_instalacion or 0.0,
        estado_llanta="INSTALADA"
    )
    db.add(nueva_l)
    db.commit()
    db.refresh(nueva_l)
    return {"mensaje": "Llanta registrada exitosamente", "id_llanta": nueva_l.id_llanta}


@app.delete("/llantas/{id_llanta}/")
def eliminar_llanta(id_llanta: int, db: Session = Depends(get_db)):
    l = db.query(models.Llanta).filter(models.Llanta.id_llanta == id_llanta).first()
    if not l:
        raise HTTPException(status_code=404, detail="Llanta no encontrada")
    db.delete(l)
    db.commit()
    return {"mensaje": "Llanta eliminada"}


@app.post("/llantas/rotar/")
def rotar_llanta(
    id_llanta: int = Form(...),
    id_vehiculo_destino: int = Form(...),
    posicion_destino: str = Form(...),
    fecha_movimiento: str = Form(...),
    km_evento: float = Form(0.0),
    horometro_evento: float = Form(0.0),
    motivo_cambio: str = Form("Rotación preventiva"),
    db: Session = Depends(get_db)
):
    llanta = db.query(models.Llanta).filter(models.Llanta.id_llanta == id_llanta).first()
    if not llanta:
        raise HTTPException(status_code=404, detail="Llanta no encontrada")

    movimiento = models.MovimientoLlanta(
        id_llanta=id_llanta,
        id_vehiculo_origen=llanta.id_vehiculo,
        posicion_origen=llanta.posicion,
        id_vehiculo_destino=id_vehiculo_destino,
        posicion_destino=posicion_destino,
        fecha_movimiento=fecha_movimiento,
        km_evento=km_evento,
        horometro_evento=horometro_evento,
        motivo_cambio=motivo_cambio
    )
    db.add(movimiento)

    llanta.id_vehiculo = id_vehiculo_destino
    llanta.posicion = posicion_destino
    db.commit()
    return {"mensaje": "Rotación de llanta efectuada correctamente"}


@app.post("/llantas/reparaciones/")
def registrar_reparacion_llanta(
    id_llanta: int = Form(...),
    tipo_actividad: str = Form(...),
    taller_proveedor: str = Form(...),
    costo_reparacion: float = Form(0.0),
    fecha_actividad: str = Form(...),
    km_evento: float = Form(0.0),
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    reparacion = models.ReparacionLlanta(
        id_llanta=id_llanta,
        tipo_actividad=tipo_actividad,
        taller_proveedor=taller_proveedor,
        costo_reparacion=costo_reparacion,
        fecha_actividad=fecha_actividad,
        km_evento=km_evento,
        observaciones=observaciones
    )
    db.add(reparacion)
    db.commit()
    return {"mensaje": "Mantenimiento de llanta registrado exitosamente"}


@app.get("/llantas/{id_llanta}/historial/")
def historial_llanta(id_llanta: int, db: Session = Depends(get_db)):
    llanta = db.query(models.Llanta).filter(models.Llanta.id_llanta == id_llanta).first()
    if not llanta:
        raise HTTPException(status_code=404, detail="Llanta no encontrada")

    movimientos = db.query(models.MovimientoLlanta).filter(
        models.MovimientoLlanta.id_llanta == id_llanta
    ).order_by(models.MovimientoLlanta.id_movimiento.desc()).all()
    reparaciones = db.query(models.ReparacionLlanta).filter(
        models.ReparacionLlanta.id_llanta == id_llanta
    ).order_by(models.ReparacionLlanta.id_reparacion_llanta.desc()).all()

    return {
        "llanta": llanta,
        "movimientos": movimientos,
        "reparaciones": reparaciones
    }


# --- REPARACIONES ---
@app.delete("/reparaciones/{id_reparacion}/")
def eliminar_reparacion(id_reparacion: int, db: Session = Depends(get_db)):
    r = db.query(models.Reparacion).filter(models.Reparacion.id_reparacion == id_reparacion).first()
    if not r:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    db.delete(r)
    db.commit()
    return {"mensaje": "Registro de taller eliminado"}


# --- OPERACIONES Y CARGA DIARIA (ÚNICO ENDPOINT POST UNIFICADO) ---
@app.get("/operaciones/")
def listar_operaciones(db: Session = Depends(get_db)):
    return db.query(models.OperacionDiaria).order_by(models.OperacionDiaria.fecha_operacion.desc()).all()


@app.post("/operaciones/")
def registrar_operacion(payload: OperacionSchema, db: Session = Depends(get_db)):
    toneladas = (
        payload.toneladas_carga
        if payload.toneladas_carga is not None and payload.toneladas_carga > 0
        else (payload.carga_toneladas or 0.0)
    )

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
        kilometraje_manual=payload.kilometraje_manual,
        galones_combustible=payload.galones_combustible or 0.0,
        costo_combustible=payload.costo_combustible or 0.0,
        galones_urea=payload.galones_urea or 0.0,
        costo_urea=payload.costo_urea or 0.0,
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


@app.delete("/operaciones/{id_operacion}/")
def eliminar_operacion(id_operacion: int, db: Session = Depends(get_db)):
    op = db.query(models.OperacionDiaria).filter(models.OperacionDiaria.id_operacion == id_operacion).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operación no encontrada")
    db.delete(op)
    db.commit()
    return {"mensaje": "Operación eliminada"}


# --- MÓDULO CHECKLIST VEHICULAR PRE-OPERATIVO ---
@app.post("/checklists/")
def registrar_checklist(payload: ChecklistSchema, db: Session = Depends(get_db)):
    nuevo_chk = models.ChecklistVehicular(
        id_vehiculo=payload.id_vehiculo,
        conductor=payload.conductor,
        fecha_inspeccion=payload.fecha_inspeccion,
        kilometraje=payload.kilometraje or 0.0,
        estado_documentos=payload.estado_documentos or "OK",
        estado_luces_exterior=payload.estado_luces_exterior or "OK",
        estado_neumaticos=payload.estado_neumaticos or "OK",
        estado_niveles_motor=payload.estado_niveles_motor or "OK",
        estado_equipos_seguridad=payload.estado_equipos_seguridad or "OK",
        tiene_inconveniente=payload.tiene_inconveniente or False,
        detalle_inconveniente=payload.detalle_inconveniente or ""
    )
    db.add(nuevo_chk)

    vehiculo = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == payload.id_vehiculo).first()
    if vehiculo and payload.kilometraje and payload.kilometraje > 0:
        vehiculo.kilometraje_actual = payload.kilometraje

    if payload.tiene_inconveniente and payload.detalle_inconveniente:
        nueva_reparacion = models.Reparacion(
            id_vehiculo=payload.id_vehiculo,
            tipo_mantenimiento="CORRECTIVO (Checklist)",
            taller_servicio="Taller Interno / Alerta Checklist",
            responsable_reparacion=payload.conductor,
            fecha_ingreso=payload.fecha_inspeccion,
            descripcion_falla=f"[ALERTA CHECKLIST PRE-OPERATIVO]: {payload.detalle_inconveniente}"
        )
        db.add(nueva_reparacion)

    db.commit()
    db.refresh(nuevo_chk)
    return {"mensaje": "Checklist registrado correctamente", "id_checklist": nuevo_chk.id_checklist}


@app.get("/checklists/")
def listar_checklists(db: Session = Depends(get_db)):
    return db.query(models.ChecklistVehicular).order_by(models.ChecklistVehicular.id_checklist.desc()).all()


@app.get("/checklists/vehiculo/{id_vehiculo}")
def listar_checklists_por_vehiculo(id_vehiculo: int, db: Session = Depends(get_db)):
    return db.query(models.ChecklistVehicular).filter(
        models.ChecklistVehicular.id_vehiculo == id_vehiculo
    ).order_by(models.ChecklistVehicular.id_checklist.desc()).all()


# --- ENDPOINT ESPECIALIZADO PARA ROL CHOFER ---
@app.post("/operaciones/chofer/")
def registrar_operacion_chofer(
    id_vehiculo: int = Form(...),
    chofer: str = Form(...),
    fecha_operacion: str = Form(...),
    tipo_trabajo: str = Form("Mina Baja -> Planta (Acarreo)"),
    horometro_final: float = Form(...),
    kilometraje_manual: Optional[float] = Form(None),
    galones_combustible: Optional[float] = Form(0.0),
    galones_urea: Optional[float] = Form(0.0),
    foto_tablero: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    url_foto = ""
    lectura_ocr_texto = "No procesado"

    if foto_tablero:
        contenido_bytes = foto_tablero.file.read()
        foto_tablero.file.seek(0)
        
        # 1. Subida del archivo a Cloudinary
        url_foto = subir_a_cloudinary(foto_tablero, "tableros_horometro")

        # 2. Procesamiento de OCR Multimodal mediante Gemini API (Modelo validado 3.8-flash)
        api_key_gemini = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key_gemini and contenido_bytes:
            try:
                client = genai.Client(api_key=api_key_gemini)
                prompt_ocr = "Analiza esta imagen de un tablero de vehículo o maquinaria. Extrae únicamente la lectura numérica del horómetro u odómetro principal. Responde strictly con el número o un resumen corto del valor leído."
                
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=[
                        types.Part.from_bytes(data=contenido_bytes, mime_type=foto_tablero.content_type or "image/jpeg"),
                        prompt_ocr
                    ]
                )
                if response.text:
                    lectura_ocr_texto = response.text.strip()
            except Exception as e:
                lectura_ocr_texto = f"Error OCR: {str(e)}"

    obs_final = f"Foto Tablero: {url_foto} | OCR Lectura: {lectura_ocr_texto}" if url_foto else "Sin Foto"

    nueva_op = models.OperacionDiaria(
        id_vehiculo=id_vehiculo,
        chofer=chofer,
        fecha_operacion=fecha_operacion,
        tipo_trabajo=tipo_trabajo,
        km_horometro_final=horometro_final,
        kilometraje_manual=kilometraje_manual,
        galones_combustible=galones_combustible or 0.0,
        costo_combustible=0.0,
        galones_urea=galones_urea or 0.0,
        costo_urea=0.0,
        observaciones=obs_final
    )
    db.add(nueva_op)

    vehiculo = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == id_vehiculo).first()
    if vehiculo and horometro_final > 0:
        vehiculo.kilometraje_actual = horometro_final

    db.commit()
    db.refresh(nueva_op)
    return {
        "mensaje": "Parte diario registrado correctamente por Chofer",
        "id_operacion": nueva_op.id_operacion,
        "url_foto": url_foto,
        "horometro_ocr": lectura_ocr_texto
    }

@app.put("/vehiculos/{id_vehiculo}/tive")
def actualizar_tive_vehiculo(
    id_vehiculo: int,
    tarjeta_tive: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    vehiculo = db.query(models.Vehiculo).filter(models.Vehiculo.id_vehiculo == id_vehiculo).first()
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    url_tive = subir_a_cloudinary(tarjeta_tive, "tives_vehiculos")
    vehiculo.url_tive = url_tive

    db.commit()
    db.refresh(vehiculo)

    return {"mensaje": "TIVE actualizada correctamente", "url_tive": url_tive}