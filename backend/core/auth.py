import os
import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv

from .database import get_conn, get_cursor

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback_inseguro")
ALGORITHM  = "HS256"

router   = APIRouter(tags=["Auth"])
security = HTTPBearer()


# ── Schemas ───────────────────────────────────────────────────

class TeacherLoginPayload(BaseModel):
    email:    str
    password: str

class StudentLoginPayload(BaseModel):
    enrollment:  str         # matrícula do aluno
    password:    str
    school_code: str         # código da escola ex: "ESC001"

class RegisterPayload(BaseModel):
    name:       str
    email:      str
    password:   str
    school_id:  int
    role:       Optional[str] = "teacher"


# ── Helpers de Segurança & Token ──────────────────────────────

def verify_password(plain_password: str, db_hash) -> bool:
    """
    Verificação blindada: lida com strings, bytes ou memoryviews
    devolvidos pelo driver do banco de dados para evitar o TypeError.
    """
    try:
        password_bytes = plain_password.encode("utf-8")
        
        if isinstance(db_hash, str):
            hash_bytes = db_hash.encode("utf-8")
        elif isinstance(db_hash, memoryview):
            hash_bytes = bytes(db_hash)
        elif isinstance(db_hash, bytes):
            hash_bytes = db_hash
        else:
            hash_bytes = str(db_hash).encode("utf-8")
            
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception as e:
        print(f"[Erro de Autenticação] Falha na verificação bcrypt: {e}")
        return False

def create_teacher_token(user_id: int, name: str, school_id: int, role: str) -> str:
    expire  = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "sub":       str(user_id),
        "name":      name,
        "school_id": school_id,
        "role":      role,
        "type":      "teacher",
        "exp":       expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_student_token(student_id: int, name: str, school_id: int, class_id: Optional[int]) -> str:
    expire  = datetime.now(timezone.utc) + timedelta(hours=12)
    payload = {
        "sub":       str(student_id),
        "name":      name,
        "school_id": school_id,
        "class_id":  class_id,
        "role":      "student",
        "type":      "student",
        "exp":       expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")


# ── Guards (Dependencies) ─────────────────────────────────────

def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "teacher":
        raise HTTPException(status_code=403, detail="Acesso restrito a professores.")
    return {
        "id":        int(payload["sub"]),
        "name":      payload["name"],
        "school_id": payload["school_id"],
        "role":      payload.get("role", "teacher"),
    }

def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "student":
        raise HTTPException(status_code=403, detail="Acesso restrito a alunos.")
    return {
        "id":        int(payload["sub"]),
        "name":      payload["name"],
        "school_id": payload["school_id"],
        "class_id":  payload.get("class_id"),
        "role":      "student",
    }

def require_coordinator(teacher: dict = Depends(get_current_teacher)) -> dict:
    if teacher["role"] not in ("coordinator", "admin"):
        raise HTTPException(status_code=403, detail="Apenas coordenadores podem aceder a este recurso.")
    return teacher


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/login")
def teacher_login(payload: TeacherLoginPayload):
    conn = get_conn()
    cur  = get_cursor(conn)

    try:
        cur.execute(
            """
            SELECT t.id, t.name, t.password_hash, t.school_id, t.role, t.is_active,
                   s.name AS school_name, s.code AS school_code
            FROM   teachers t
            JOIN   schools  s ON s.id = t.school_id
            WHERE  t.email = %s
            """,
            (payload.email,),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Conta desativada. Entre em contacto com a escola.")

    token = create_teacher_token(row["id"], row["name"], row["school_id"], row["role"])

    return {
        "access_token": token,
        "token_type":   "bearer",
        "name":         row["name"],
        "school_id":    row["school_id"],
        "school_name":  row["school_name"],
        "school_code":  row["school_code"],
        "role":         row["role"],
    }


@router.post("/aluno/login")
def student_login(payload: StudentLoginPayload):
    conn = get_conn()
    cur  = get_cursor(conn)

    try:
        cur.execute(
            """
            SELECT st.id, st.name, st.password_hash, st.school_id, st.class_id, st.is_active,
                   s.name AS school_name
            FROM   students st
            JOIN   schools  s  ON s.id  = st.school_id
            WHERE  st.enrollment = %s
              AND  s.code        = %s
            """,
            (payload.enrollment, payload.school_code),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Matrícula, código da escola ou senha inválidos.")
    
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Conta desativada.")

    token = create_student_token(row["id"], row["name"], row["school_id"], row["class_id"])

    return {
        "access_token": token,
        "token_type":   "bearer",
        "name":         row["name"],
        "school_id":    row["school_id"],
        "school_name":  row["school_name"],
        "class_id":     row["class_id"],
    }


@router.post("/register")
def register_teacher(
    payload:  RegisterPayload,
    _teacher: dict = Depends(require_coordinator),
):
    if _teacher["school_id"] != payload.school_id and _teacher["role"] != "admin":
        raise HTTPException(status_code=403, detail="Só podes registar professores na tua escola.")

    password_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            """
            INSERT INTO teachers (school_id, name, email, password_hash, role)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (payload.school_id, payload.name, payload.email, password_hash, payload.role),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Erro ao registar: E-mail já existe ou dados inválidos.")
    finally:
        cur.close()
        conn.close()

    return {"id": new_id, "message": "Professor registado com sucesso."}


@router.get("/me")
def get_me(teacher: dict = Depends(get_current_teacher)):
    return teacher