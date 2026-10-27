import database
import models
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

print("1. Conectando a Neon.tech...")
db = next(database.get_db())

try:
    print("2. Registrando/Actualizando usuario de EDICIÓN (Admin)...")
    email_admin = "vtiburcioaliaga@gmail.com"
    pwd_admin = "Bkindex123$%&"
    user_admin = db.query(models.Usuario).filter(models.Usuario.email == email_admin).first()
    
    if not user_admin:
        user_admin = models.Usuario(
            nombre="Victor Tiburcio",
            email=email_admin,
            password=pwd_context.hash(pwd_admin),
            rol="Edicion"
        )
        db.add(user_admin)
    else:
        user_admin.password = pwd_context.hash(pwd_admin)
        user_admin.rol = "Edicion"

    print("3. Registrando/Actualizando usuario de LECTURA...")
    email_lector = "ponderosaminerals95@gmail.com"
    pwd_lector = "Lector123"
    user_lector = db.query(models.Usuario).filter(models.Usuario.email == email_lector).first()
    
    if not user_lector:
        user_lector = models.Usuario(
            nombre="Usuario Lectura",
            email=email_lector,
            password=pwd_context.hash(pwd_lector),
            rol="Lectura"
        )
        db.add(user_lector)
    else:
        user_lector.password = pwd_context.hash(pwd_lector)
        user_lector.rol = "Lectura"

    db.commit()
    print("\n¡ÉXITO TOTAL! Usuarios configurados correctamente en la base de datos.")

except Exception as e:
    db.rollback()
    print("\n-> Ocurrió un error al procesar usuarios:", e)
finally:
    db.close()
    