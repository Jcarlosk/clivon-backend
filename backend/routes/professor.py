"""
professor.py — Rotas do Professor
===================================
Compatível com schema Supabase (UUIDs, class_students, etc.)
Corrige: fetchall() sem dict() que quebrava a serialização JSON.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from ..core.database import get_conn, get_cursor
from ..core.auth import get_current_teacher

router = APIRouter(prefix="/professor", tags=["Professor"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChamadaAluno(BaseModel):
    student_id: str          # UUID
    status:     str          # "present" | "absent" | "late"
    note:       Optional[str] = ""

class RegistrarChamadaReq(BaseModel):
    class_id:    str         # UUID
    subject:     str
    lesson_date: date
    alunos:      List[ChamadaAluno]

class FaltaNaProvaReq(BaseModel):
    student_id:    str       # UUID
    answer_key_id: str       # UUID
    subject:       str
    bimester:      int
    class_name:    str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/turmas")
def listar_turmas(teacher=Depends(get_current_teacher)):
    """Lista todas as turmas da escola do professor."""
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            """
            SELECT id, name, year, shift, join_code
            FROM   classes
            WHERE  school_id = %s AND is_active = TRUE
            ORDER  BY name
            """,
            (teacher["school_id"],),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


@router.get("/turmas/{class_id}/alunos")
def listar_alunos_turma(class_id: str, teacher=Depends(get_current_teacher)):
    """
    Lista alunos de uma turma.
    Usa a view vw_class_students para incluir enrollment e birth_date.
    Valida que a turma pertence à escola do professor.
    """
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        # Verifica que a turma pertence à escola do professor
        cur.execute(
            "SELECT 1 FROM classes WHERE id = %s AND school_id = %s AND is_active = TRUE",
            (class_id, teacher["school_id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Turma não encontrada.")

        cur.execute(
            """
            SELECT student_id AS id, student_name AS name, enrollment, is_active
            FROM   vw_class_students
            WHERE  class_id = %s AND is_active = TRUE
            ORDER  BY student_name
            """,
            (class_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


@router.post("/chamada")
def registrar_chamada(dados: RegistrarChamadaReq, teacher=Depends(get_current_teacher)):
    """Registra ou atualiza chamada para uma aula. Usa UPSERT para idempotência."""
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        for aluno in dados.alunos:
            cur.execute(
                """
                INSERT INTO attendance
                    (school_id, teacher_id, student_id, class_id, subject, lesson_date, status, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (student_id, subject, lesson_date)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    note   = EXCLUDED.note
                """,
                (
                    teacher["school_id"],
                    teacher["id"],
                    aluno.student_id,
                    dados.class_id,
                    dados.subject,
                    dados.lesson_date,
                    aluno.status,
                    aluno.note or "",
                ),
            )
        conn.commit()
        return {"message": "Chamada registrada com sucesso!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/provas")
def listar_provas(bimestre: Optional[int] = None, teacher=Depends(get_current_teacher)):
    """
    Lista provas/gabaritos criados pelo professor.
    Corrigido: fetchall() agora retorna dict() para serialização JSON correta.
    """
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        query  = "SELECT * FROM answer_keys WHERE teacher_id = %s AND school_id = %s"
        params = [teacher["id"], teacher["school_id"]]

        if bimestre:
            query += " AND bimester = %s"
            params.append(bimestre)

        query += " ORDER BY created_at DESC"
        cur.execute(query, tuple(params))

        # ✅ Corrigido: dict() necessário para serialização JSON
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


@router.post("/prova/falta")
def registrar_falta_na_prova(dados: FaltaNaProvaReq, teacher=Depends(get_current_teacher)):
    """Registra ausência de aluno em prova com score 0 e status 'absent_from_exam'."""
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            "SELECT name FROM students WHERE id = %s AND school_id = %s",
            (dados.student_id, teacher["school_id"]),
        )
        student = cur.fetchone()
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado.")

        cur.execute(
            """
            INSERT INTO scan_results (
                school_id, teacher_id, answer_key_id, student_id, student_name,
                subject, class_name, answers_read, correct, wrong, score,
                bimester, confirmed, detections_json
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, '{}'::jsonb, 0, 0, 0.0,
                %s, TRUE, '{"status": "absent_from_exam"}'::jsonb
            )
            ON CONFLICT DO NOTHING
            """,
            (
                teacher["school_id"],
                teacher["id"],
                dados.answer_key_id,
                dados.student_id,
                student["name"],
                dados.subject,
                dados.class_name,
                dados.bimester,
            ),
        )
        conn.commit()
        return {"message": f"Falta na prova registrada para {student['name']}."}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()