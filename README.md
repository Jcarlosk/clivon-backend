# Clivon Backend

API do Clivon Edu construída em FastAPI. Responsável pelo processamento de imagem (OpenCV), reconhecimento de texto (Tesseract OCR) e integração com a base de dados.

## Sobre o Projeto

Plataforma web para correção automática de provas com suporte a múltiplas escolas, visão computacional e painel para professores e alunos.

Este sistema automatiza a correção de provas, permitindo que professores economizem tempo e acompanhem o desempenho dos alunos.

A aplicação utiliza OCR (reconhecimento de texto) para leitura de respostas a partir de imagens, além de oferecer autenticação, relatórios e organização por escolas.

## Funcionalidades

- Correção automática de provas via imagem (OCR)
- Leitura direta da câmera
- Suporte a múltiplas escolas (multi-tenant)
- Painel do professor
- Painel do aluno
- Exportação de resultados em Excel
- Geração de relatórios em PDF
- Autenticação segura (JWT + hash de senha)

## Tecnologias Utilizadas

**Backend**
- FastAPI
- Uvicorn

**Visão Computacional**
- OpenCV
- Tesseract OCR

**Banco de Dados e Segurança**
- Supabase (PostgreSQL)
- Psycopg2
- Python-JOSE (JWT)
- Passlib + Bcrypt

**Arquivos**
- OpenPyXL (Excel)
- ReportLab (PDF)

**Outros**
- NumPy
- Python-dotenv
- Python-multipart

## Dependências

```txt
fastapi==0.111.0
uvicorn==0.29.0
opencv-python-headless==4.9.0.80
numpy==1.26.4
python-multipart==0.0.9
python-jose==3.3.0
passlib==1.7.4
bcrypt==4.1.2
openpyxl==3.1.2
reportlab==4.1.0
pytesseract==0.3.10
supabase==2.4.3
psycopg2-binary==2.9.9
python-dotenv==1.0.1
```

## Como rodar o projeto

### Rodar o servidor

```bash
uvicorn main:app --reload
```

A API estará disponível em:

```
http://localhost:8000
```

Documentação automática:

```
http://localhost:8000/docs
```

## Licença

MIT

## Autor

Desenvolvido por Weko Studio
