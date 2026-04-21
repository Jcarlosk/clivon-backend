from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from ..core.database import get_conn, get_cursor
from ..core.auth import get_current_teacher

router = APIRouter(prefix="/professor", tags=["Professor"])

class ChamadaAluno(BaseModel):
    student_id: int
    status: str
    note: Optional[str] = ""

class RegistrarChamadaReq(BaseModel):
    class_id: int
    subject: str
    lesson_date: date
    alunos: List[ChamadaAluno]

class FaltaNaProvaReq(BaseModel):
    student_id: int
    answer_key_id: int
    subject: str
    bimester: int
    class_name: str

@router.get("/turmas")
def listar_turmas(teacher=Depends(get_current_teacher)):
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, name, year, shift
            FROM classes
            WHERE school_id = %s
            ORDER BY name
        """, (teacher["school_id"],))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

@router.get("/turmas/{class_id}/alunos")
def listar_alunos_turma(class_id: int, teacher=Depends(get_current_teacher)):
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, name, enrollment 
            FROM students 
            WHERE class_id = %s AND school_id = %s AND is_active = True 
            ORDER BY name
        """, (class_id, teacher["school_id"]))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

@router.post("/chamada")
def registrar_chamada(dados: RegistrarChamadaReq, teacher=Depends(get_current_teacher)):
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        for aluno in dados.alunos:
            cur.execute("""
                INSERT INTO attendance (school_id, teacher_id, student_id, class_id, subject, lesson_date, status, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (student_id, subject, lesson_date) 
                DO UPDATE SET status = EXCLUDED.status, note = EXCLUDED.note
            """, (teacher["school_id"], teacher["id"], aluno.student_id, dados.class_id, 
                  dados.subject, dados.lesson_date, aluno.status, aluno.note))
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
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        query = "SELECT * FROM answer_keys WHERE teacher_id = %s AND school_id = %s"
        params = [teacher["id"], teacher["school_id"]]
        if bimestre:
            query += " AND bimester = %s"
            params.append(bimestre)
        query += " ORDER BY created_at DESC"
        
        cur.execute(query, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

@router.post("/prova/falta")
def registrar_falta_na_prova(dados: FaltaNaProvaReq, teacher=Depends(get_current_teacher)):
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT name FROM students WHERE id = %s", (dados.student_id,))
        student = cur.fetchone()
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        cur.execute("""
            INSERT INTO scan_results 
            (school_id, teacher_id, answer_key_id, student_id, student_name, subject, class_name, answers_read, correct, wrong, score, bimester, confirmed, detections_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, '{}', 0, 0, 0.0, %s, True, '{"status": "absent_from_exam"}')
        """, (teacher["school_id"], teacher["id"], dados.answer_key_id, dados.student_id, student["name"], 
              dados.subject, dados.class_name, dados.bimester))
        
        conn.commit()
        return {"message": f"Falta na prova registrada para {student['name']}."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()