"""
professor.py — Rotas do Professor
===================================
Compatível com schema Supabase (UUIDs, class_students, etc.)
Inclui: Gestão de turmas, chamadas, provas e cadastro manual de alunos.
"""

import io
import csv
import re
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
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

class CadastrarAlunoReq(BaseModel):
    name:       str
    enrollment: str
    birth_date: date
    class_id:   str       # UUID da turma


# ── Endpoints de Turmas e Alunos ──────────────────────────────────────────────

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
    """Lista alunos de uma turma específica."""
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
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


@router.post("/aluno/cadastrar")
def cadastrar_aluno_manual(dados: CadastrarAlunoReq, teacher=Depends(get_current_teacher)):
    """
    Cadastra um aluno, gera o PIN (DDMMAAAA) e vincula à turma.
    """
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        # 1. Validar se a turma pertence à escola
        cur.execute(
            "SELECT 1 FROM classes WHERE id = %s AND school_id = %s",
            (dados.class_id, teacher["school_id"])
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Acesso negado a esta turma.")

        # 2. Gerar Hash do PIN (Data de Nascimento sem traços)
        pin_plain = dados.birth_date.strftime("%d%m%Y")
        pin_hash = bcrypt.hashpw(pin_plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # 3. Inserir Aluno
        cur.execute(
            """
            INSERT INTO students (school_id, name, enrollment, birth_date, pin_hash, is_active)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            RETURNING id
            """,
            (teacher["school_id"], dados.name, dados.enrollment, dados.birth_date, pin_hash)
        )
        student_id = cur.fetchone()["id"]

        # 4. Vincular à Turma
        cur.execute(
            "INSERT INTO class_students (class_id, student_id) VALUES (%s, %s)",
            (dados.class_id, student_id)
        )

        conn.commit()
        return {"message": "Aluno cadastrado com sucesso!", "student_id": student_id}

    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower() and "enrollment" in str(e).lower():
            raise HTTPException(status_code=400, detail="Esta matrícula já existe.")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── Importação via CSV ────────────────────────────────────────────────────────

def _gerar_matricula(school_id: str, nome: str, ano: int, sequencia: int) -> str:
    """
    Gera matrícula no formato: ANO + 3 letras do nome + sequência com 4 dígitos.
    Ex: 2026JOA0001
    """
    iniciais = re.sub(r"[^A-Za-z]", "", nome).upper()[:3].ljust(3, "X")
    return f"{ano}{iniciais}{sequencia:04d}"


def _parse_data(valor: str) -> date:
    """
    Aceita os formatos mais comuns:
    DD/MM/AAAA, DD-MM-AAAA, AAAA-MM-DD
    """
    valor = valor.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: '{valor}'. Use DD/MM/AAAA.")


@router.post("/aluno/importar-csv")
async def importar_alunos_csv(
    class_id: str = Form(...),
    arquivo:  UploadFile = File(...),
    teacher=Depends(get_current_teacher),
):
    """
    Importa alunos em lote via CSV.

    Colunas esperadas (qualquer ordem, case-insensitive):
        nome_completo | data_nascimento | turma (ignorada — usa class_id do form)

    Regras:
    - Matrícula gerada automaticamente (ANO + 3 letras nome + sequência)
    - PIN = data de nascimento no formato DDMMAAAA
    - Alunos com matrícula duplicada são ignorados (não geram erro)
    - Retorna resumo: cadastrados, ignorados, erros por linha
    """

    # 1. Validar tipo do arquivo
    if not arquivo.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .csv")

    # 2. Validar turma
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute(
            "SELECT 1 FROM classes WHERE id = %s AND school_id = %s AND is_active = TRUE",
            (class_id, teacher["school_id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Turma não encontrada ou sem acesso.")

        # 3. Ler próxima sequência de matrícula da escola
        cur.execute(
            "SELECT COUNT(*) AS total FROM students WHERE school_id = %s",
            (teacher["school_id"],),
        )
        sequencia_base = (cur.fetchone()["total"] or 0) + 1
        ano_atual = datetime.now().year

        # 4. Ler e parsear CSV
        conteudo = await arquivo.read()
        try:
            texto = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            texto = conteudo.decode("latin-1")  # fallback para Excel BR

        reader = csv.DictReader(io.StringIO(texto))

        # Normaliza cabeçalhos — remove espaços e converte para minúsculo
        if reader.fieldnames is None:
            raise HTTPException(status_code=400, detail="CSV vazio ou sem cabeçalho.")

        campos = [f.strip().lower() for f in reader.fieldnames]

        # Detecta colunas de nome e data (aceita variações)
        col_nome = next((f for f in campos if "nome" in f), None)
        col_data = next((f for f in campos if "nasc" in f or "data" in f), None)

        if not col_nome or not col_data:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cabeçalho inválido. O CSV deve ter colunas com 'nome' e 'nascimento'. "
                    f"Encontrado: {campos}"
                ),
            )

        # 5. Processar linhas
        cadastrados = 0
        ignorados   = 0
        erros       = []

        for num_linha, row in enumerate(reader, start=2):
            # Normaliza keys do row
            row_norm = {k.strip().lower(): v.strip() for k, v in row.items() if k}

            nome = row_norm.get(col_nome, "").strip()
            data_str = row_norm.get(col_data, "").strip()

            if not nome or not data_str:
                erros.append({"linha": num_linha, "erro": "Nome ou data em branco."})
                continue

            try:
                birth_date = _parse_data(data_str)
            except ValueError as e:
                erros.append({"linha": num_linha, "erro": str(e)})
                continue

            # Gerar matrícula única
            matricula = _gerar_matricula(teacher["school_id"][:4], nome, ano_atual, sequencia_base)

            # Gerar PIN (DDMMAAAA) e hash
            pin_plain = birth_date.strftime("%d%m%Y")
            pin_hash  = bcrypt.hashpw(pin_plain.encode(), bcrypt.gensalt()).decode()

            try:
                # Inserir aluno
                cur.execute(
                    """
                    INSERT INTO students
                        (school_id, name, enrollment, birth_date, pin_hash, is_active)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (school_id, enrollment) DO NOTHING
                    RETURNING id
                    """,
                    (teacher["school_id"], nome, matricula, birth_date, pin_hash),
                )
                row_result = cur.fetchone()

                if row_result is None:
                    # ON CONFLICT — matrícula duplicada, tenta com sequência maior
                    sequencia_base += 1
                    matricula = _gerar_matricula(teacher["school_id"][:4], nome, ano_atual, sequencia_base)
                    cur.execute(
                        """
                        INSERT INTO students
                            (school_id, name, enrollment, birth_date, pin_hash, is_active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        RETURNING id
                        """,
                        (teacher["school_id"], nome, matricula, birth_date, pin_hash),
                    )
                    row_result = cur.fetchone()

                student_id = row_result["id"]

                # Vincular à turma (ignora se já vinculado)
                cur.execute(
                    """
                    INSERT INTO class_students (class_id, student_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (class_id, student_id),
                )

                cadastrados   += 1
                sequencia_base += 1

            except Exception as e:
                ignorados += 1
                erros.append({"linha": num_linha, "erro": str(e)})

        conn.commit()

        return {
            "message":    f"{cadastrados} aluno(s) cadastrado(s) com sucesso.",
            "cadastrados": cadastrados,
            "ignorados":   ignorados,
            "erros":       erros,
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── Endpoints de Chamada e Provas ─────────────────────────────────────────────

@router.post("/chamada")
def registrar_chamada(dados: RegistrarChamadaReq, teacher=Depends(get_current_teacher)):
    """Registra ou atualiza chamada (Idempotente)."""
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
                DO UPDATE SET status = EXCLUDED.status, note = EXCLUDED.note
                """,
                (teacher["school_id"], teacher["id"], aluno.student_id, dados.class_id, 
                 dados.subject, dados.lesson_date, aluno.status, aluno.note or "")
            )
        conn.commit()
        return {"message": "Chamada processada!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/provas")
def listar_provas(bimestre: Optional[int] = None, teacher=Depends(get_current_teacher)):
    """Lista gabaritos criados pelo professor."""
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        query = "SELECT * FROM answer_keys WHERE teacher_id = %s AND school_id = %s"
        params = [teacher["id"], teacher["school_id"]]
        if bimestre:
            query += " AND bimester = %s"
            params.append(bimestre)
        
        cur.execute(query + " ORDER BY created_at DESC", tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


@router.post("/prova/falta")
def registrar_falta_na_prova(dados: FaltaNaProvaReq, teacher=Depends(get_current_teacher)):
    """Regista nota 0 por ausência em dia de prova."""
    conn = get_conn()
    cur  = get_cursor(conn)
    try:
        cur.execute("SELECT name FROM students WHERE id = %s AND school_id = %s", 
                    (dados.student_id, teacher["school_id"]))
        student = cur.fetchone()
        if not student: raise HTTPException(status_code=404, detail="Aluno inexistente.")

        cur.execute(
            """
            INSERT INTO scan_results (
                school_id, teacher_id, answer_key_id, student_id, student_name,
                subject, class_name, score, bimester, confirmed, detections_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0.0, %s, TRUE, '{"status": "absent"}')
            ON CONFLICT DO NOTHING
            """,
            (teacher["school_id"], teacher["id"], dados.answer_key_id, dados.student_id, 
             student["name"], dados.subject, dados.class_name, dados.bimester)
        )
        conn.commit()
        return {"message": "Falta registada."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()