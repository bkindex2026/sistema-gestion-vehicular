from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id_usuario = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    rol = Column(String(50), nullable=False)


class Vehiculo(Base):
    __tablename__ = "vehiculos"

    id_vehiculo = Column(Integer, primary_key=True, index=True)
    placa = Column(String(20), unique=True, nullable=False)
    sede_asignada = Column(String(100), default="Por Asignar")
    marca = Column(String(100), default="Por Especificar")
    modelo = Column(String(100), default="Por Especificar")
    anio = Column(Integer, default=2024)
    numero_vin = Column(String(100), default="S/N")
    descripcion = Column(String(255), default="")
    kilometraje_actual = Column(Float, default=0.0)
    tiene_gps = Column(Boolean, default=False)
    empresa_gps = Column(String(100), default="")
    vencimiento_gps = Column(String(10), default="")
    url_tive = Column(String(255), default="")
    url_registrada = Column(String(255), default="")


class Seguro(Base):
    __tablename__ = "seguros"

    id_seguro = Column(Integer, primary_key=True, index=True)
    id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"), nullable=False)
    tipo_seguro = Column(String(100), nullable=False)
    compania_seguros = Column(String(100), nullable=False)
    broker = Column(String(100), default="N/A")
    costo_prima = Column(Float, default=0.0)
    numero_poliza = Column(String(100), nullable=False)
    fecha_inicio = Column(String(10), nullable=False)
    fecha_vencimiento = Column(String(10), nullable=False)
    url_adjunto = Column(String(255), default="")


class Documento(Base):
    __tablename__ = "documentos"

    id_documento = Column(Integer, primary_key=True, index=True)
    id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"), nullable=False)
    tipo_documento = Column(String(100), nullable=False)
    entidad_emisora = Column(String(100), nullable=False)
    numero_documento = Column(String(100), nullable=False)
    fecha_emision = Column(String(10), nullable=False)
    fecha_vencimiento = Column(String(10), nullable=False)
    url_adjunto = Column(String(255), default="")


class ServicioGPS(Base):
    __tablename__ = "servicios_gps"

    id_gps = Column(Integer, primary_key=True, index=True)
    id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"), nullable=False)
    empresa_gps = Column(String(100), nullable=False)
    fecha_inicio = Column(String(10), nullable=False)
    fecha_vencimiento = Column(String(10), nullable=False)


class Llanta(Base):
    __tablename__ = "llantas"

    id_llanta = Column(Integer, primary_key=True, index=True)
    id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"), nullable=False)
    codigo = Column(String(100), default="S/C")
    marca = Column(String(100), nullable=False)
    modelo = Column(String(100), nullable=False)
    posicion = Column(String(100), nullable=False)
    fecha_instalacion = Column(String(10), nullable=False)


class Reparacion(Base):
    __tablename__ = "reparaciones"

    id_reparacion = Column(Integer, primary_key=True, index=True)
    id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"), nullable=False)
    tipo_mantenimiento = Column(String(100), nullable=False)
    taller_servicio = Column(String(100), nullable=False)
    responsable_reparacion = Column(String(100), nullable=False)
    fecha_ingreso = Column(String(10), nullable=False)
    descripcion_falla = Column(String(255), default="")


class OperacionDiaria(Base):
    __tablename__ = "operaciones_diarias"

    id_operacion = Column(Integer, primary_key=True, index=True)
    id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"), nullable=False)
    chofer = Column(String(150), nullable=False)
    fecha_operacion = Column(String(10), nullable=False)
    tipo_trabajo = Column(String(150), nullable=False)
    ruta_origen_destino = Column(String(200), default="")
    carga_toneladas = Column(Float, default=0.0)
    numero_viajes = Column(Integer, default=0)
    km_horometro_inicial = Column(Float, default=0.0)
    km_horometro_final = Column(Float, default=0.0)
    galones_combustible = Column(Float, default=0.0)
    costo_combustible = Column(Float, default=0.0)
    grifo_surtidor = Column(String(100), default="")
    observaciones = Column(String(255), default="")
    galones_urea = Column(Float, default=0.0)
    costo_urea = Column(Float, default=0.0)