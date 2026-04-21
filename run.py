"""
Ponto de entrada único do servidor Clivon Edu.
Execute: python run.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ["PYTHONPATH"] = ROOT
sys.path.insert(0, ROOT)

import uvicorn

if __name__ == "__main__":
    print("\n🎓  Clivon Edu — servidor iniciando em http://127.0.0.1:8000\n")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)