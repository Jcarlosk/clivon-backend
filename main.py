import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. Importando as rotas separadamente (Dando nomes diferentes para não conflitar)
from backend.routes.grade import router as grade_router
from backend.core.auth import router as auth_router            # Login do Professor
from backend.routes.aluno import router as aluno_router        # Rotas do Painel do Aluno
from backend.routes.professor import router as professor_router  # Gestão de faltas e notas (Multi-escola)

app = FastAPI(
    title="Clivon Edu API",
    description="Sistema Inteligente de Gestão e Correção de Provas",
    version="2.0.0",
)

# CORS — em produção substitua "*" pelo seu domínio real
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Conectando as rotas no aplicativo
app.include_router(auth_router)       # Cadastro do login do professor
app.include_router(grade_router)      # Correção e gabaritos
app.include_router(aluno_router)      # Acesso e dashboard do aluno
app.include_router(professor_router)  # Lançamento de chamadas e faltas em provas

@app.get("/")
def root():
    return {
        "status": "online",
        "brand": "Clivon Edu",
        "version": "2.0.0",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)