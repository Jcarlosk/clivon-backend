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
    birth_date: str  # YYYY-MM-DD

class ImportStudentsPayload(BaseModel):
    class_id: str
    students: List[Dict[str, Any]]  # [{"name": "...", "birth_date": "YYYY-MM-DD"}]

class ClassCreatePayload(BaseModel):
    name: str
    year: int
    shift: str
    join_code: str


# ── Helpers internos ──────────────────────────────────────────────────────────

def _exec_commit(cur, conn, sql, params):
    """Executa SQL que retorna uma coluna 'result' (JSONB), faz commit e retorna o dict."""
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.commit()
    return row["result"]


# ── Dashboard ─────────────────────────────────────────────────────────────────

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro de base de dados: {e}")
    finally:
        cur.close()
        conn.close()


# ── Professores ───────────────────────────────────────────────────────────────

@router.get("/teachers")
def list_teachers(teacher: dict = Depends(require_admin)):
    """Lista todos os professores da escola logada."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, name, email, role, is_active, created_date
            FROM vw_admin_teachers_list
            WHERE school_id = %s
            ORDER BY name
        """, (teacher["school_id"],))
        return cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/teachers/{teacher_id}/deactivate")
def deactivate_teacher(teacher_id: str, teacher: dict = Depends(require_admin)):
    """Desativa um professor da escola."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        result = _exec_commit(
            cur, conn,
            "SELECT deactivate_teacher(%s, %s) AS result",
            (teacher["school_id"], teacher_id)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao desativar professor"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/teachers/{teacher_id}/activate")
def activate_teacher(teacher_id: str, teacher: dict = Depends(require_admin)):
    """Reativa um professor da escola."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        result = _exec_commit(
            cur, conn,
            "SELECT activate_teacher(%s, %s) AS result",
            (teacher["school_id"], teacher_id)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao reativar professor"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ── Turmas ────────────────────────────────────────────────────────────────────

@router.get("/classes")
def list_classes(teacher: dict = Depends(require_admin)):
    """Lista todas as turmas da escola logada, incluindo o total de alunos."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("""
            SELECT
                c.id, c.name, c.year, c.shift, c.join_code, c.is_active,
                (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id = c.id) AS students
            FROM classes c
            WHERE c.school_id = %s
            ORDER BY c.name
        """, (teacher["school_id"],))
        return cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/classes")
def create_class(payload: ClassCreatePayload, teacher: dict = Depends(require_admin)):
    """Cria uma nova turma na escola."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        result = _exec_commit(
            cur, conn,
            "SELECT create_class(%s, %s, %s, %s, %s) AS result",
            (teacher["school_id"], payload.name, payload.year, payload.shift, payload.join_code)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao criar turma"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/classes/{class_id}/deactivate")
def deactivate_class(class_id: str, teacher: dict = Depends(require_admin)):
    """Desativa uma turma da escola."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        result = _exec_commit(
            cur, conn,
            "SELECT deactivate_class(%s, %s) AS result",
            (teacher["school_id"], class_id)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao desativar turma"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ── Alunos ────────────────────────────────────────────────────────────────────

@router.get("/students")
def list_students(teacher: dict = Depends(require_admin)):
    """Lista todos os alunos da escola com dados da turma."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("""
            SELECT
                student_id  AS id,
                student_name AS name,
                enrollment,
                class_name,
                class_id,
                birth_date,
                is_active
            FROM vw_class_students
            WHERE school_id = %s
            ORDER BY student_name
        """, (teacher["school_id"],))
        return cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/students")
def create_student_route(payload: StudentCreatePayload, teacher: dict = Depends(require_admin)):
    """Cadastra um aluno individual usando a função SQL create_student()."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        result = _exec_commit(
            cur, conn,
            "SELECT create_student(%s, %s, %s, %s::date) AS result",
            (teacher["school_id"], payload.class_id, payload.name, payload.birth_date)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao cadastrar aluno"))
        return result
    except HTTPException:
        raise
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
        students_json = json.dumps(payload.students)
        result = _exec_commit(
            cur, conn,
            "SELECT import_students(%s, %s, %s::jsonb) AS result",
            (teacher["school_id"], payload.class_id, students_json)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro na importação"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/students/{student_id}/deactivate")
def deactivate_student(student_id: str, teacher: dict = Depends(require_admin)):
    """Desativa um aluno da escola."""
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        result = _exec_commit(
            cur, conn,
            "SELECT deactivate_student(%s, %s) AS result",
            (teacher["school_id"], student_id)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao desativar aluno"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()