import os
import io
import hashlib
import shutil
import logging
import base64
import time
from typing import Optional, Any
from datetime import datetime

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field
from PIL import Image

# Google GenAI SDK (SDK Oficial Vigente)
from google import genai
from google.genai import types

# ==============================================================================
# 1. CONFIGURACIÓN INICIAL Y ENTORNO SEGURO
# ==============================================================================
# Invariante del proyecto: Modelo oficial vigente gemini-3.8-flash
MODEL_NAME = "gemini-3.8-flash"

# Lectura de variable de entorno (Render o entorno local)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("⚠️ La variable de entorno GEMINI_API_KEY no esta configurada.")

client = genai.Client(api_key=GEMINI_API_KEY)

BASE_DIR = "comprobantes_whatsapp"
PROCESADOS_DIR = os.path.join(BASE_DIR, "procesados")
ERRORES_DIR = os.path.join(BASE_DIR, "errores")
LOG_FILE_PATH = os.path.join(ERRORES_DIR, "errores_procesamiento.log")

for directory in [BASE_DIR, PROCESADOS_DIR, ERRORES_DIR]:
    os.makedirs(directory, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AgentePonderosa")

app = FastAPI(
    title="Agente Ponderosa v2 - Plataforma Autónoma de Gastos",
    version="2.2.0",
)

try:
    import database
    HAS_DB = True
except ImportError:
    HAS_DB = False

try:
    from exportar_csv import agregar_o_actualizar_csv
    HAS_CSV_MODULE = True
except ImportError:
    HAS_CSV_MODULE = False

# ==============================================================================
# 2. ESQUEMA PYDANTIC PARA EXTRACCIÓN DE COMPROBANTES (Structured Output)
# ==============================================================================
class ComprobanteSchema(BaseModel):
    tipo_documento: str = Field(
        description="Tipo de comprobante: FACTURA, BOLETA, VALE_COMBUSTIBLE, LIQUIDACION, NOTA_CREDITO u OTRO"
    )
    serie_numero: Optional[str] = Field(default=None, description="Número de serie y correlativo")
    ruc_emisor: Optional[str] = Field(default=None, description="RUC de 11 dígitos del proveedor")
    razon_social: Optional[str] = Field(default=None, description="Nombre o razón social del proveedor")
    ruc_receptor: Optional[str] = Field(default="20601014193", description="RUC receptor (Ponderosa Minerals S.A.C.: 20601014193)")
    fecha_emision: Optional[str] = Field(default=None, description="Fecha de emisión en formato YYYY-MM-DD")
    hora: Optional[str] = Field(default=None, description="Hora de emisión HH:MM:SS")
    galones: Optional[float] = Field(default=0.0, description="Galones de combustible adquiridos si aplica")
    concepto: Optional[str] = Field(default=None, description="Descripción del bien, servicio o suministro")
    chofer: Optional[str] = Field(default=None, description="Nombre del chofer o responsable")
    moneda: str = Field(default="PEN", description="Moneda: PEN o USD")
    op_gravada: float = Field(default=0.0, description="Base imponible gravada")
    igv: float = Field(default=0.0, description="Monto del IGV (18%)")
    total: float = Field(default=0.0, description="Monto total del comprobante")
    placa: Optional[str] = Field(default=None, description="Número de placa del vehículo (ej. ABC-123)")

PROCESSED_HASHES = set()

# ==============================================================================
# 3. FUNCIONES AUXILIARES
# ==============================================================================
def calcular_sha256(file_bytes: bytes) -> str:
    hasher = hashlib.sha256()
    hasher.update(file_bytes)
    return hasher.hexdigest()

def convertir_tiff_a_png(file_bytes: bytes) -> bytes:
    image = Image.open(io.BytesIO(file_bytes))
    output_buffer = io.BytesIO()
    image.save(output_buffer, format="PNG")
    return output_buffer.getvalue()

def mover_a_fallidos(file_path: str, filename: str, motivo: str):
    dest_path = os.path.join(ERRORES_DIR, filename)
    if os.path.exists(file_path):
        shutil.move(file_path, dest_path)
    log_msg = f"Archivo '{filename}' movido a errores. Motivo: {motivo}"
    logger.warning(log_msg)
    print(f"⚠️ {log_msg}")

def actualizar_registro_csv(data: dict):
    if HAS_CSV_MODULE:
        try:
            agregar_o_actualizar_csv(data, csv_filename="comprobantes_ponderosa.csv")
            return
        except Exception as e:
            logger.error(f"Error con exportar_csv.py: {e}")
            
    csv_path = "comprobantes_ponderosa.csv"
    file_exists = os.path.exists(csv_path)
    fieldnames = list(ComprobanteSchema.model_fields.keys()) + ["sha256_hash", "fecha_registro"]
    
    import csv
    with open(csv_path, mode="a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        row = {k: data.get(k, "") for k in fieldnames}
        writer.writerow(row)

# ==============================================================================
# 4. MOTOR MULTIMODAL GEMINI OCR (Con Reintentos Automáticos)
# ==============================================================================
PROMPT_AUDITORIA = """
Actúa como un Auditor Contable Sénior especializado en la normativa tributaria peruana y operaciones mineras de Ponderosa Minerals S.A.C. (RUC: 20601014193).

Analiza el documento adjunto (imagen, ticket manuscrito o PDF).
Extrae los campos contables requeridos en el esquema JSON.
Si el comprobante es de combustible (manuscrito o impreso), identifica con precisión: galones, placa, chofer y total.
Si no se observa el RUC receptor pero es un gasto de operación legible, asigna ruc_receptor = 20601014193.
"""

def procesar_comprobante_con_gemini(file_bytes: bytes, mime_type: str) -> Optional[ComprobanteSchema]:
    max_retries = 3
    for intento in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    PROMPT_AUDITORIA
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ComprobanteSchema,
                    temperature=0.1
                )
            )
            return ComprobanteSchema.model_validate_json(response.text)
        except Exception as e:
            error_str = str(e)
            if ("503" in error_str or "UNAVAILABLE" in error_str or "429" in error_str) and intento < max_retries:
                espera = intento * 4
                print(f"⚠️ Servidor de Google saturado (503). Reintentando ({intento}/{max_retries}) en {espera}s...")
                time.sleep(espera)
            else:
                logger.error(f"Error procesando en Gemini API: {e}")
                print(f"⚠️ Error Gemini API: {e}")
                return None
    return None

# ==============================================================================
# 5. PIPELINE ASÍNCRONO DE PROCESAMIENTO
# ==============================================================================
def ejecutar_pipeline_comprobante(filename: str, original_bytes: bytes, mime_type: str):
    file_path = os.path.join(BASE_DIR, filename)
    bytes_a_procesar = original_bytes
    mime_final = mime_type

    if mime_type in ["image/tiff", "image/x-tiff"] or filename.lower().endswith((".tiff", ".tif")):
        try:
            bytes_a_procesar = convertir_tiff_a_png(original_bytes)
            mime_final = "image/png"
            filename = os.path.splitext(filename)[0] + ".png"
            file_path = os.path.join(BASE_DIR, filename)
        except Exception as e:
            mover_a_fallidos(file_path, filename, f"Fallo conversión TIFF: {e}")
            return

    with open(file_path, "wb") as f:
        f.write(bytes_a_procesar)

    file_hash = calcular_sha256(bytes_a_procesar)
    if file_hash in PROCESSED_HASHES:
        mover_a_fallidos(file_path, filename, f"Comprobante duplicado (Hash: {file_hash})")
        return

    print(f"🔍 Enviando {filename} a Gemini 3.8 Flash para OCR...")
    resultado_ocr = procesar_comprobante_con_gemini(bytes_a_procesar, mime_final)

    if not resultado_ocr:
        mover_a_fallidos(file_path, filename, "Fallo en la respuesta JSON de Gemini API")
        return

    es_invalido = (
        resultado_ocr.tipo_documento == "OTRO" and
        resultado_ocr.total <= 0.0 and resultado_ocr.op_gravada <= 0.0 and resultado_ocr.galones <= 0.0
    )

    if es_invalido:
        mover_a_fallidos(file_path, filename, f"Documento no contable (Tipo: {resultado_ocr.tipo_documento}, Total: {resultado_ocr.total})")
        return

    data_dict = resultado_ocr.model_dump()
    data_dict["sha256_hash"] = file_hash
    data_dict["fecha_registro"] = datetime.now().isoformat()

    if HAS_DB:
        try:
            database.insertar_comprobante(data_dict)
        except Exception as e:
            logger.error(f"Error PostgreSQL: {e}")

    actualizar_registro_csv(data_dict)
    print("📊 Registro exportado exitosamente a comprobantes_ponderosa.csv.")

    PROCESSED_HASHES.add(file_hash)
    dest_procesado = os.path.join(PROCESADOS_DIR, filename)
    shutil.move(file_path, dest_procesado)
    print(f"✅ Proceso completado. Archivo movido a: {dest_procesado}")

def extraer_base64_recursivo(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        if "base64" in data and isinstance(data["base64"], str) and len(data["base64"]) > 50:
            return data["base64"]
        for k, v in data.items():
            res = extraer_base64_recursivo(v)
            if res:
                return res
    return None

# ==============================================================================
# 6. ENDPOINT WEBHOOK
# ==============================================================================
@app.post("/webhook/whatsapp", status_code=status.HTTP_200_OK)
async def webhook_whatsapp(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON inválido")

    data = payload.get("data", {})
    message_data = data.get("message", {}) if isinstance(data, dict) else {}
    document_msg = message_data.get("documentMessage") or message_data.get("imageMessage") or message_data

    mime_type = "image/jpeg"
    filename = None

    if isinstance(document_msg, dict):
        mime_type = document_msg.get("mimetype", "image/jpeg").split(";")[0].strip()
        filename = document_msg.get("fileName")

    if not filename:
        filename = f"comprobante_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

    base64_str = extraer_base64_recursivo(payload)
    file_bytes = None

    if base64_str:
        try:
            file_bytes = base64.b64decode(base64_str)
        except Exception as e:
            return {"status": "error", "reason": f"Base64 corrupto: {e}"}
    else:
        file_bytes = await request.body()

    if not file_bytes or len(file_bytes) == 0:
        return {"status": "error", "reason": "Sin bytes válidos del adjunto."}

    background_tasks.add_task(
        ejecutar_pipeline_comprobante,
        filename=filename,
        original_bytes=file_bytes,
        mime_type=mime_type
    )

    return {"status": "queued", "filename": filename, "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando Agente Ponderosa v2...")
    uvicorn.run(app, host="0.0.0.0", port=8000)