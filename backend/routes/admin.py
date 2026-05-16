"""
admin.py — Rotas exclusivas do Administrador Mestre
Comunica com o PostgreSQL chamando as funções SQL do Supabase.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json

from backend.core.database import get_conn, get_cursor
from backend.core.auth import require_admin

router = APIRouter(prefix="/admin", tags=["Admin Mestre"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TeacherCreatePayload(BaseModel):
    name: str
    email: str
    password: str
    role: str = "teacher"
    school_id: Optional[str] = None  # usa o do token se omitido


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


# ── Helper interno ────────────────────────────────────────────────────────────

def _exec_commit(cur, conn, sql, params):
    """Executa SQL que retorna coluna 'result' (JSONB), faz commit e retorna o dict."""
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.commit()
    return row["result"]


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_dashboard_stats(teacher: dict = Depends(require_admin)):
    """Puxa as contagens de professores, alunos e turmas."""
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
            SELECT *
            FROM vw_admin_teachers_list
            WHERE school_id = %s
            ORDER BY name
        """, (teacher["school_id"],))
        rows = cur.fetchall()

        def normalize(r):
            d = dict(r)
            return {
                "id":           d.get("id"),
                "name":         d.get("name")        or d.get("teacher_name") or d.get("full_name"),
                "email":        d.get("email")        or d.get("teacher_email"),
                "role":         d.get("role")         or d.get("teacher_role"),
                "is_active":    d.get("is_active"),
                "created_date": d.get("created_date") or d.get("created_at"),
            }

        return [normalize(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.post("/teachers")
def create_teacher_route(payload: TeacherCreatePayload, teacher: dict = Depends(require_admin)):
    """Cadastra um novo professor/admin usando create_teacher() no SQL."""
    VALID_ROLES = {"admin", "coordinator", "teacher"}
    if payload.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role inválido: '{payload.role}'. Use: admin, coordinator ou teacher"
        )

    conn = get_conn()
    cur = get_cursor(conn)
    school_id = payload.school_id or teacher["school_id"]
    try:
        cur.execute(
            "SELECT create_teacher(%s, %s, %s, %s, %s::text) AS result",
            (school_id, payload.name, payload.email, payload.password, payload.role)
        )
        row = cur.fetchone()
        conn.commit()
        result = row["result"]
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Erro ao cadastrar professor"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
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
        rows = cur.fetchall()

        def normalize(r):
            d = dict(r)
            return {
                "id":        d.get("id"),
                "name":      d.get("name")      or d.get("class_name"),
                "year":      d.get("year"),
                "shift":     d.get("shift"),
                "join_code": d.get("join_code") or d.get("joincode") or d.get("code"),
                "is_active": d.get("is_active"),
                "students":  d.get("students", 0),
            }

        return [normalize(r) for r in rows]
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
            SELECT *
            FROM vw_class_students
            WHERE school_id = %s
            ORDER BY student_name
        """, (teacher["school_id"],))
        rows = cur.fetchall()

        def normalize(r):
            d = dict(r)
            return {
                "id":         d.get("id")        or d.get("student_id"),
                "name":       d.get("name")       or d.get("student_name") or d.get("full_name"),
                "enrollment": d.get("enrollment") or d.get("matricula"),
                "class_name": d.get("class_name") or d.get("turma_name")   or d.get("turma"),
                "class_id":   d.get("class_id")   or d.get("turma_id"),
                "birth_date": d.get("birth_date") or d.get("data_nascimento"),
                "is_active":  d.get("is_active"),
            }

        return [normalize(r) for r in rows]
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


# ── Debug — remover após confirmar as views ───────────────────────────────────

@router.get("/debug/columns")
def debug_columns(teacher: dict = Depends(require_admin)):
    """Retorna os nomes reais das colunas das views. REMOVER EM PRODUÇÃO."""
    conn = get_conn()
    cur = get_cursor(conn)
    result = {}
    try:
        for view, label in [
            ("vw_admin_teachers_list", "teachers"),
            ("vw_class_students",      "students"),
            ("classes",                "classes"),
        ]:
            try:
                cur.execute(f"SELECT * FROM {view} LIMIT 1")
                row = cur.fetchone()
                result[label] = list(dict(row).keys()) if row else f"view '{view}' vazia"
            except Exception as ex:
                result[label] = f"ERRO: {str(ex)}"
        return result
    finally:
        cur.close()
        conn.close()