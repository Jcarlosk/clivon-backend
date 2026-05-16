import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.grade import router as grade_router
from backend.core.auth import router as auth_router
from backend.routes.aluno import router as aluno_router
from backend.routes.professor import router as professor_router
from backend.routes.admin import router as admin_router # NOVO

app = FastAPI(
    title="Clivon Edu API",
    description="Sistema Inteligente de Gestão e Correção de Provas",
    version="2.0.0",
)

# ── CORS ──────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "https://clivon-edu.vercel.app",
    "https://clivon-frontend.vercel.app",
    "https://clivonedu.netlify.app",       # (a antiga, se ainda quiser manter)
    "http://localhost:5500",               # (para quando testar no PC)
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Rotas ─────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(grade_router)
app.include_router(aluno_router)
app.include_router(professor_router)
app.include_router(admin_router) # Adicionado aqui!

@app.get("/")
def root():
    return {
        "status": "online",
        "brand":  "Clivon Edu",
        "version": "2.0.0",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)