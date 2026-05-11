"""
auth.py — Clivon Edu Authentication
====================================
Compatível com o schema Supabase real:

  PROFESSOR → autenticação via Supabase Auth (auth.users)
              A senha fica em auth.users.encrypted_password (crypt/bf)
              O token JWT é gerado pelo Supabase e validado aqui via SECRET_KEY

  ALUNO     → autenticação própria via função SQL student_login_by_code()
              Usa pin_hash (crypt/bf) na tabela students
              Recebe: join_code + enrollment + pin (DDMMYYYY)
              Token JWT gerado pela API (não pelo Supabase)

IDs → UUID em todo o banco (não INT)
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

SECRET_KEY      = os.getenv("SECRET_KEY", "fallback_inseguro")
ALGORITHM       = "HS256"

# URL + chave de serviço do Supabase (necessários para autenticar professor)
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")          # ex: https://xyzxyz.supabase.co
SUPABASE_ANON   = os.getenv("SUPABASE_ANON_KEY", "")     # chave anon pública
SUPABASE_SERVICE= os.getenv("SUPABASE_SERVICE_KEY", "")  # service_role (apenas no backend)

router   = APIRouter(tags=["Auth"])
security = HTTPBearer()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TeacherLoginPayload(BaseModel):
    email:    EmailStr
    password: str

class StudentLoginPayload(BaseModel):
    join_code:  str   # código da turma, ex: "MAT7B25"
    enrollment: str   # matrícula do aluno, ex: "2025001042"
    pin:        str   # data de nascimento DDMMYYYY, ex: "15042010"

class RegisterPayload(BaseModel):
    name:      str
    email:     EmailStr
    password:  str
    school_id: str        # UUID
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


# ── Guards (Dependencies) ─────────────────────────────────────────────────────

def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "teacher":
        raise HTTPException(status_code=403, detail="Acesso restrito a professores.")
    return {
        "id":        payload["sub"],          # UUID string
        "name":      payload["name"],
        "school_id": payload["school_id"],    # UUID string
        "role":      payload.get("role", "teacher"),
    }

def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "student":
        raise HTTPException(status_code=403, detail="Acesso restrito a alunos.")
    return {
        "id":         payload["sub"],         # UUID string
        "name":       payload["name"],
        "enrollment": payload["enrollment"],
        "school_id":  payload["school_id"],   # UUID string
        "class_id":   payload.get("class_id"),
        "role":       "student",
    }

def require_coordinator(teacher: dict = Depends(get_current_teacher)) -> dict:
    if teacher["role"] not in ("coordinator", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Apenas coordenadores podem aceder a este recurso."
        )
    return teacher


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
def teacher_login(payload: TeacherLoginPayload):
    """
    Login do professor via Supabase Auth.

    Fluxo:
      1. Chama a API de auth do Supabase (signInWithPassword)
      2. Supabase valida email + senha contra auth.users
      3. Busca dados complementares na tabela teachers (school_id, role, etc.)
      4. Gera nosso próprio JWT com os dados necessários para os guards
    """
    if not SUPABASE_URL or not SUPABASE_ANON:
        raise HTTPException(
            status_code=500,
            detail="Configuração do Supabase ausente no servidor."
        )

    # 1. Autentica no Supabase
    supabase_auth_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    try:
        resp = httpx.post(
            supabase_auth_url,
            json={"email": payload.email, "password": payload.password},
            headers={
                "apikey":        SUPABASE_ANON,
                "Content-Type":  "application/json",
            },
            timeout=10,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Não foi possível conectar ao servidor de autenticação.")

    if resp.status_code != 200:
        # Supabase retorna 400 para credenciais inválidas
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    auth_data  = resp.json()
    auth_user  = auth_data.get("user", {})
    auth_uid   = auth_user.get("id")

    if not auth_uid:
        raise HTTPException(status_code=401, detail="Resposta inesperada do servidor de autenticação.")

    # 2. Busca dados do professor na tabela teachers
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
        raise HTTPException(
            status_code=403,
            detail="Utilizador autenticado mas sem perfil de professor. Contacte o suporte."
        )

    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Conta desativada. Entre em contacto com a escola.")

    # 3. Gera nosso JWT para uso nos guards das outras rotas
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
    Login do aluno via função SQL student_login_by_code().

    Fluxo:
      1. Chama student_login_by_code(join_code, enrollment, pin) no Postgres
      2. A função SQL valida o pin_hash com crypt() e verifica vínculo com a turma
      3. Gera JWT próprio com os dados do aluno

    Campos recebidos do frontend:
      join_code  → código da turma (ex: MAT7B25)
      enrollment → matrícula (ex: 2025001042)
      pin        → data de nascimento DDMMYYYY (ex: 15042010)
    """
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        # Delega toda a validação para a função SQL segura
        cur.execute(
            "SELECT student_login_by_code(%s, %s, %s) AS result",
            (
                payload.join_code.strip().upper(),
                payload.enrollment.strip(),
                payload.pin.strip(),
            ),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=500, detail="Erro interno ao autenticar aluno.")

    result = row["result"]  # JSONB → dict pelo driver psycopg2

    # A função SQL retorna { ok: false, error: "..." } em caso de falha
    if not result.get("ok"):
        error_msg = result.get("error", "Dados incorretos.")

        # Mapeia erros internos para mensagens amigáveis
        friendly = {
            "Matrícula não encontrada":        "Matrícula não encontrada.",
            "PIN incorreto":                   "Data de nascimento incorreta.",
            "Aluno não está nesta turma":      "Código de turma não corresponde à sua matrícula.",
            "Código de turma inválido ou expirado": "Código de turma inválido ou expirado.",
        }
        raise HTTPException(
            status_code=401,
            detail=friendly.get(error_msg, "Matrícula ou dados incorretos.")
        )

    # Gera JWT do aluno
    token = _create_token(
        {
            "sub":        str(result["student_id"]),
            "name":       result["name"],
            "enrollment": result["enrollment"],
            "school_id":  "",           # student_login_by_code não retorna school_id
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
    """
    Cria professor via função SQL create_teacher() do Supabase.
    Apenas coordenadores e admins podem usar este endpoint.
    """
    if _teacher["school_id"] != payload.school_id and _teacher["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Só podes registar professores na tua escola."
        )

    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            "SELECT create_teacher(%s, %s, %s, %s, %s::user_role) AS result",
            (
                payload.school_id,
                payload.name,
                payload.email,
                payload.password,
                payload.role,
            ),
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
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Erro ao registar professor.")
        )

    return {
        "teacher_id": str(result["teacher_id"]),
        "message":    "Professor registado com sucesso.",
    }


@router.get("/me")
def get_me(teacher: dict = Depends(get_current_teacher)):
    return teacher