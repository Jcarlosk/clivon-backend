"""
admin.py — Rotas exclusivas do Administrador Mestre
Comunica com o PostgreSQL chamando as funções SQL do Supabase.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any
import json

from backend.core.database import get_conn, get_cursor
from backend.core.auth import require_admin

router = APIRouter(prefix="/admin", tags=["Admin Mestre"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class StudentCreatePayload(BaseModel):
    class_id: str
    name: str
    birth_date: str # YYYY-MM-DD

class ImportStudentsPayload(BaseModel):
    class_id: str
    students: List[Dict[str, Any]] # Lista de {"name": "...", "birth_date": "YYYY-MM-DD"}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_dashboard_stats(teacher: dict = Depends(require_admin)):
    """Puxa as contagens de professores, alunos e turmas (get_admin_stats)."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT get_admin_stats(%s) AS result", (teacher["school_id"],))
        row = cur.fetchone()
        
        result = row["result"]
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao gerar estatísticas"))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro de base de dados: {e}")
    finally:
        cur.close()
        conn.close()


@router.post("/students")
def create_student_route(payload: StudentCreatePayload, teacher: dict = Depends(require_admin)):
    """Cadastra um aluno individual usando a função SQL create_student()."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute(
            "SELECT create_student(%s, %s, %s, %s::date) AS result",
            (teacher["school_id"], payload.class_id, payload.name, payload.birth_date)
        )
        row = cur.fetchone()
        conn.commit()
        
        result = row["result"]
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao cadastrar aluno"))
            
        return result
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/students/import")
def import_students_route(payload: ImportStudentsPayload, teacher: dict = Depends(require_admin)):
    """Importa alunos em lote (CSV) chamando import_students() no SQL."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        # Transforma o array Python em JSON String para o PostgreSQL (jsonb)
        students_json = json.dumps(payload.students)
        
        cur.execute(
            "SELECT import_students(%s, %s, %s::jsonb) AS result",
            (teacher["school_id"], payload.class_id, students_json)
        )
        row = cur.fetchone()
        conn.commit()
        
        result = row["result"]
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro na importação"))
            
        return result
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()