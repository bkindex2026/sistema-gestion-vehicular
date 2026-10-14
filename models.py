from database import Base
from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship


# 1. TABLA USUARIOS (Control de Acceso y Roles)
class Usuario(Base):
  __tablename__ = "usuarios"

  id_usuario = Column(Integer, primary_key=True, index=True)
  nombre = Column(String(100), nullable=False)
  email = Column(String(100), unique=True, index=True, nullable=False)
  hashed_password = Column(String(255), nullable=False)
  rol = Column(String(20), default="Lectura")
  estado = Column(String(20), default="Activo")


# 2. TABLA VEHÍCULOS (Placa obligatoria, resto opcional + Sede + TIVE)
class Vehiculo(Base):
  __tablename__ = "vehiculos"

  id_vehiculo = Column(Integer, primary_key=True, index=True)
  placa = Column(String(10), unique=True, index=True, nullable=False)
  marca = Column(String(50), nullable=True)
  modelo = Column(String(50), nullable=True)
  anio = Column(Integer, nullable=True)
  numero_vin = Column(String(50), nullable=True)
  kilometraje_actual = Column(Float, default=0.0)
  estado = Column(String(20), default="Activo")
  descripcion = Column(Text, nullable=True)
  sede_asignada = Column(String(100), nullable=True)
  url_tive = Column(String(255), nullable=True)

  reparaciones = relationship("Reparacion", back_populates="vehiculo")
  seguros = relationship("Seguro", back_populates="vehiculo")
  gps = relationship("ServicioGPS", back_populates="vehiculo")
  documentos = relationship("Documento", back_populates="vehiculo")


# 3. TABLA SEGUROS (SOAT / Seguro Vehicular con Broker, Prima y Adjunto)
class Seguro(Base):
  __tablename__ = "seguros"

  id_seguro = Column(Integer, primary_key=True, index=True)
  id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"))
  tipo_seguro = Column(String(50), nullable=False)
  compania_seguros = Column(String(100), nullable=False)
  broker = Column(String(100), nullable=True)
  numero_poliza = Column(String(50), nullable=True)
  costo_prima = Column(Float, default=0.0)
  fecha_inicio = Column(Date, nullable=False)
  fecha_vencimiento = Column(Date, nullable=False)
  url_adjunto = Column(String(255), nullable=True)
  estado_poliza = Column(String(20), default="Vigente")

  vehiculo = relationship("Vehiculo", back_populates="seguros")


# 4. TABLA SERVICIO GPS
class ServicioGPS(Base):
  __tablename__ = "servicios_gps"

  id_gps = Column(Integer, primary_key=True, index=True)
  id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"))
  empresa_gps = Column(String(100), nullable=False)
  fecha_inicio = Column(Date, nullable=False)
  fecha_vencimiento = Column(Date, nullable=False)
  estado_servicio = Column(String(20), default="Activo")

  vehiculo = relationship("Vehiculo", back_populates="gps")


# 5. TABLA DOCUMENTOS (REVISIÓN TÉCNICA - CITV)
class Documento(Base):
  __tablename__ = "documentos"

  id_documento = Column(Integer, primary_key=True, index=True)
  id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"))
  tipo_documento = Column(String(50))
  numero_documento = Column(String(50))
  entidad_emisora = Column(String(100))
  fecha_emision = Column(Date)
  fecha_vencimiento = Column(Date)
  url_adjunto = Column(String(255), nullable=True)

  vehiculo = relationship("Vehiculo", back_populates="documentos")


# 6. TABLA REPARACIONES (Con Responsable de Reparación)
class Reparacion(Base):
  __tablename__ = "reparaciones"

  id_reparacion = Column(Integer, primary_key=True, index=True)
  id_vehiculo = Column(Integer, ForeignKey("vehiculos.id_vehiculo"))
  tipo_mantenimiento = Column(String(50))
  fecha_ingreso = Column(Date)
  taller_servicio = Column(String(100))
  descripcion_falla = Column(Text)
  responsable_reparacion = Column(String(100), nullable=False)
  estado_reparacion = Column(String(20), default="En proceso")

  vehiculo = relationship("Vehiculo", back_populates="reparaciones")
  repuestos = relationship("RepuestoReparacion", back_populates="reparacion")


# 7. TABLA REPUESTOS (Con Responsable de Compra)
class RepuestoReparacion(Base):
  __tablename__ = "repuestos_reparacion"

  id_repuesto_rep = Column(Integer, primary_key=True, index=True)
  id_reparacion = Column(Integer, ForeignKey("reparaciones.id_reparacion"))
  nombre_repuesto = Column(String(100), nullable=False)
  cantidad = Column(Integer, default=1)
  costo_unitario = Column(Float, default=0.0)
  responsable_compra = Column(String(100), nullable=False)

  reparacion = relationship("Reparacion", back_populates="repuestos")