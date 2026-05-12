"""
aluno.py — Painel do Aluno
===========================
Compatível com schema Supabase (UUIDs, class_students, views).
"""

from fastapi import APIRouter, Depends
from ..core.database import get_conn, get_cursor
from ..core.auth import get_current_student

router = APIRouter(prefix="/aluno", tags=["Painel do Aluno"])


def _timedelta_to_str(td) -> str:
    """Converte timedelta (retornado pelo psycopg2 para TIME) para string HH:MM:SS."""
    if td is None:
        return None
    if hasattr(td, "seconds"):
        total = td.seconds
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:00"
    return str(td)


@router.get("/dashboard")
def get_student_dashboard(student=Depends(get_current_student)):
    conn = get_conn()
    cur  = get_cursor(conn)

    try:
      # Notas — ajustado para o nome real da view no Supabase
        cur.execute(
            "SELECT * FROM v_student_grades_summary WHERE student_id = %s",
            (student["id"],),
        )
        grades = [dict(r) for r in cur.fetchall()]

        # Faltas — ajustado para attendance
        cur.execute(
            "SELECT * FROM v_student_attendance_summary WHERE student_id = %s",
            (student["id"],),
        )
        absences = [dict(r) for r in cur.fetchall()]

        # Horário — usa class_id do token JWT
        cur.execute(
            """
            SELECT
                s.id,
                s.weekday,
                s.start_time,
                s.end_time,
                s.subject,
                t.name AS teacher_name
            FROM   schedules s
            LEFT JOIN teachers t ON t.id = s.teacher_id
            WHERE  s.class_id = %s
            ORDER  BY s.weekday, s.start_time
            """,
            (student["class_id"],),
        )
        horario = []
        for row in cur.fetchall():
            aula = dict(row)
            aula["start_time"] = _timedelta_to_str(aula.get("start_time"))
            aula["end_time"]   = _timedelta_to_str(aula.get("end_time"))
            horario.append(aula)

        return {
            "aluno":   student["name"],
            "notas":   grades,
            "faltas":  absences,
            "horario": horario,
        }

    finally:
        cur.close()
        conn.close()