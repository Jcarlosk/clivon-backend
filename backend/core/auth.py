"""
auth.py — Clivon Edu Authentication
====================================
PROFESSOR → Supabase Auth (auth.users) + JWT próprio
ALUNO     → student_login_by_code() SQL + JWT próprio
            Recebe pin no formato DDMMYYYY e converte para DATE (YYYY-MM-DD)
"""

import os
import jwt
import httpx
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv

from .database import get_conn, get_cursor

load_dotenv()

# ── Configuração ──────────────────────────────────────────────────────────────

SECRET_KEY       = os.getenv("SECRET_KEY", "fallback_inseguro")
ALGORITHM        = "HS256"
SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON    = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE = os.getenv("SUPABASE_SERVICE_KEY", "")

router   = APIRouter(tags=["Auth"])
security = HTTPBearer()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TeacherLoginPayload(BaseModel):
    email:    EmailStr
    password: str

class StudentLoginPayload(BaseModel):
    join_code:  str   # ex: "ANO2A25"
    enrollment: str   # ex: "20260010007"
    pin:        str   # data de nascimento DDMMYYYY, ex: "20082005"

class RegisterPayload(BaseModel):
    name:      str
    email:     EmailStr
    password:  str
    school_id: str
    role:      Optional[str] = "teacher"


# ── Token helpers ─────────────────────────────────────────────────────────────

def _create_token(payload: dict, expires_hours: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    return jwt.encode({**payload, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")

def _pin_to_date(pin: str) -> str:
    """
    Converte PIN DDMMYYYY → YYYY-MM-DD para passar ao banco como DATE.
    Ex: "20082005" → "2005-08-20"
    Lança ValueError se o formato for inválido.
    """
    pin = pin.strip()
    if len(pin) != 8 or not pin.isdigit():
        raise ValueError(f"PIN inválido: '{pin}'. Esperado DDMMYYYY com 8 dígitos.")
    dd, mm, yyyy = pin[0:2], pin[2:4], pin[4:8]
    return f"{yyyy}-{mm}-{dd}"


# ── Guards (Dependencies) ─────────────────────────────────────────────────────

def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "teacher":
        raise HTTPException(status_code=403, detail="Acesso restrito a professores.")
    return {
        "id":        payload["sub"],
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
        "id":         payload["sub"],
        "name":       payload["name"],
        "enrollment": payload["enrollment"],
        "school_id":  payload["school_id"],
        "class_id":   payload.get("class_id"),
        "role":       "student",
    }

def require_coordinator(teacher: dict = Depends(get_current_teacher)) -> dict:
    if teacher["role"] not in ("coordinator", "admin"):
        raise HTTPException(status_code=403, detail="Apenas coordenadores podem aceder a este recurso.")
    return teacher


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
def teacher_login(payload: TeacherLoginPayload):
    """Login do professor via Supabase Auth."""
    if not SUPABASE_URL or not SUPABASE_ANON:
        raise HTTPException(status_code=500, detail="Configuração do Supabase ausente no servidor.")

    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            json={"email": payload.email, "password": payload.password},
            headers={"apikey": SUPABASE_ANON, "Content-Type": "application/json"},
            timeout=10,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Não foi possível conectar ao servidor de autenticação.")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    auth_uid = resp.json().get("user", {}).get("id")
    if not auth_uid:
        raise HTTPException(status_code=401, detail="Resposta inesperada do servidor de autenticação.")

    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            """
            SELECT t.id, t.name, t.school_id, t.role, t.is_active,
                   s.name AS school_name, s.code AS school_code
            FROM   teachers t
            JOIN   schools  s ON s.id = t.school_id
            WHERE  t.auth_id = %s
            """,
            (auth_uid,),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=403, detail="Utilizador autenticado mas sem perfil de professor. Contacte o suporte.")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Conta desativada. Entre em contacto com a escola.")

    token = _create_token(
        {
            "sub":       str(row["id"]),
            "name":      row["name"],
            "school_id": str(row["school_id"]),
            "role":      row["role"],
            "type":      "teacher",
        },
        expires_hours=24,
    )

    return {
        "access_token": token,
        "token_type":   "bearer",
        "name":         row["name"],
        "school_id":    str(row["school_id"]),
        "school_name":  row["school_name"],
        "school_code":  row["school_code"],
        "role":         row["role"],
    }


@router.post("/aluno/login")
def student_login(payload: StudentLoginPayload):
    """
    Login do aluno via student_login_by_code().
    Frontend envia pin no formato DDMMYYYY (ex: "20082005").
    Convertido internamente para DATE YYYY-MM-DD antes de ir ao banco.
    """
    # Converte DDMMYYYY → YYYY-MM-DD
    try:
        data_nascimento = _pin_to_date(payload.pin)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            "SELECT student_login_by_code(%s, %s, %s::date) AS result",
            (
                payload.join_code.strip().upper(),
                payload.enrollment.strip(),
                data_nascimento,
            ),
        )
        row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno no banco de dados: {e}")
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=500, detail="Erro interno ao autenticar aluno.")

    result = row["result"]

    if not result.get("ok"):
        friendly = {
            "Matrícula não encontrada":             "Matrícula não encontrada.",
            "PIN incorreto":                        "Data de nascimento incorreta.",
            "Aluno não está nesta turma":           "Código de turma não corresponde à sua matrícula.",
            "Código de turma inválido ou expirado": "Código de turma inválido ou expirado.",
        }
        error_msg = result.get("error", "Dados incorretos.")
        raise HTTPException(status_code=401, detail=friendly.get(error_msg, error_msg))

    token = _create_token(
        {
            "sub":        str(result["student_id"]),
            "name":       result["name"],
            "enrollment": result["enrollment"],
            "school_id":  "",
            "class_id":   str(result["class_id"]),
            "type":       "student",
        },
        expires_hours=12,
    )

    return {
        "access_token": token,
        "token_type":   "bearer",
        "name":         result["name"],
        "student_id":   str(result["student_id"]),
        "enrollment":   result["enrollment"],
        "class_id":     str(result["class_id"]),
        "class_name":   result.get("class_name", ""),
    }


@router.post("/register")
def register_teacher(
    payload:  RegisterPayload,
    _teacher: dict = Depends(require_coordinator),
):
    """Cria professor via create_teacher(). Apenas coordenadores e admins."""
    if _teacher["school_id"] != payload.school_id and _teacher["role"] != "admin":
        raise HTTPException(status_code=403, detail="Só podes registar professores na tua escola.")

    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            "SELECT create_teacher(%s, %s, %s, %s, %s::user_role) AS result",
            (payload.school_id, payload.name, payload.email, payload.password, payload.role),
        )
        row = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao registar professor: {e}")
    finally:
        cur.close()
        conn.close()

    result = row["result"]
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao registar professor."))

    return {
        "teacher_id": str(result["teacher_id"]),
        "message":    "Professor registado com sucesso.",
    }


@router.get("/me")
def get_me(teacher: dict = Depends(get_current_teacher)):
    return teachergit add backend/core/auth.py