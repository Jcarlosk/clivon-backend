from fastapi import APIRouter, Depends
from ..core.database import get_conn, get_cursor
from ..core.auth import get_current_student

router = APIRouter(prefix="/aluno", tags=["Painel do Aluno"])

@router.get("/dashboard")
def get_student_dashboard(student=Depends(get_current_student)):
    conn = get_conn()
    cur = get_cursor(conn)
    
    try:
        cur.execute("SELECT * FROM student_grades_summary WHERE student_id = %s", (student["id"],))
        grades = [dict(r) for r in cur.fetchall()]
        
        cur.execute("SELECT * FROM student_absence_summary WHERE student_id = %s", (student["id"],))
        absences = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT s.*, t.name as teacher_name 
            FROM schedules s
            LEFT JOIN teachers t ON s.teacher_id = t.id
            WHERE s.class_id = %s AND s.school_id = %s
            ORDER BY s.weekday, s.start_time
        """, (student["class_id"], student["school_id"]))
        horario = [dict(r) for r in cur.fetchall()]
        
        # Converter start_time e end_time para string (timedelta não é serializável)
        for aula in horario:
            if hasattr(aula.get("start_time"), "seconds"):
                total = aula["start_time"].seconds
                aula["start_time"] = f"{total//3600:02d}:{(total%3600)//60:02d}:00"
            if hasattr(aula.get("end_time"), "seconds"):
                total = aula["end_time"].seconds
                aula["end_time"] = f"{total//3600:02d}:{(total%3600)//60:02d}:00"

        return {
            "aluno": student["name"],
            "notas": grades,
            "faltas": absences,
            "horario": horario
        }
    finally:
        cur.close()
        conn.close()