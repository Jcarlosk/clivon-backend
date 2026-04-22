<div align="center">

<img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat&logo=fastapi&logoColor=white"/>
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=flat&logo=supabase&logoColor=white"/>
<img src="https://img.shields.io/badge/OpenCV-4.9-5C3EE8?style=flat&logo=opencv&logoColor=white"/>
<img src="https://img.shields.io/badge/Tesseract-OCR-blue?style=flat"/>
<img src="https://img.shields.io/badge/License-MIT-green?style=flat"/>
<img src="https://img.shields.io/badge/Status-Live-brightgreen?style=flat"/>

# Clivon Edu — Backend

**API REST para correção automática de provas com visão computacional, OCR e painel para professores e alunos.**

[🚀 API em Produção](https://clivon-api.onrender.com) · [📖 Documentação Interativa](https://clivon-api.onrender.com/docs) · [🐛 Reportar Bug](https://github.com/weko-studio/clivon-backend/issues)

</div>

---

## Sobre o Projeto

O **Clivon Edu** é uma plataforma web que automatiza a correção de provas escolares. O professor fotografa a folha de respostas do aluno, e o sistema usa visão computacional (OpenCV) e reconhecimento de texto (Tesseract OCR) para identificar as respostas automaticamente, comparar com o gabarito e salvar o resultado no banco de dados em segundos.

A arquitetura suporta múltiplas escolas (multi-tenant), com autenticação separada para professores e alunos, exportação de resultados e geração de relatórios.

---

## Funcionalidades

- ✅ Correção automática de provas via imagem (câmera ou upload)
- ✅ OCR com Tesseract para leitura das respostas
- ✅ Processamento de imagem com OpenCV
- ✅ Suporte a múltiplas escolas (multi-tenant)
- ✅ Painel do professor com histórico e estatísticas
- ✅ Painel do aluno com notas, faltas e horários
- ✅ Exportação de resultados em Excel (.xlsx)
- ✅ Geração de relatórios em PDF
- ✅ Autenticação segura com JWT + hash de senha (bcrypt)

---

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Framework | FastAPI + Uvicorn |
| Visão Computacional | OpenCV, Tesseract OCR, NumPy |
| Banco de Dados | Supabase (PostgreSQL) + Psycopg2 |
| Autenticação | Python-JOSE (JWT) + Passlib + Bcrypt |
| Arquivos | OpenPyXL (Excel) + ReportLab (PDF) |
| Configuração | Python-dotenv, Python-multipart |

---

## Estrutura do Projeto

```
📦 clivon-backend
 ┣ 📂 backend
 ┃ ┣ 📜 main.py              # Ponto de entrada da aplicação
 ┃ ┣ 📂 routes               # Endpoints da API (professor, aluno, OCR)
 ┃ ┣ 📂 services             # Lógica de negócio e processamento de imagem
 ┃ ┣ 📂 models               # Schemas Pydantic e modelos de dados
 ┃ ┗ 📂 core                 # Configurações, JWT, segurança
 ┣ 📂 frontend
 ┃ ┣ 📜 index.html
 ┃ ┣ 📂 assets
 ┃ ┗ 📂 scripts
 ┣ 📂 uploads                # Imagens temporárias enviadas pelos professores
 ┣ 📜 requirements.txt
 ┗ 📜 README.md
```

---

## Como Rodar Localmente

### Pré-requisitos

- Python 3.11+
- Tesseract OCR instalado na máquina
- Conta no [Supabase](https://supabase.com) com projeto criado

### 1. Clonar o repositório

```bash
git clone https://github.com/weko-studio/clivon-backend.git
cd clivon-backend
```

### 2. Criar e ativar o ambiente virtual

```bash
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Instalar o Tesseract OCR

**Linux:**
```bash
sudo apt install tesseract-ocr
```

**Windows:** Baixe o instalador em [github.com/UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) e adicione ao PATH do sistema.

### 5. Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
SUPABASE_URL=https://xxxx.supabase.co       # URL do seu projeto no Supabase
SUPABASE_KEY=eyJ...                          # Chave anon ou service role do Supabase
SECRET_KEY=sua-chave-secreta-aqui            # Chave para assinar os tokens JWT
DATABASE_URL=postgresql://user:pass@host/db  # String de conexão direta ao PostgreSQL
```

> ⚠️ Nunca suba o arquivo `.env` para o repositório. Ele já está no `.gitignore`.

### 6. Rodar a API

```bash
uvicorn main:app --reload
```

A API estará disponível em `http://127.0.0.1:8000`.
A documentação interativa (Swagger) em `http://127.0.0.1:8000/docs`.

---

## API em Produção

| Ambiente | URL |
|---|---|
| Produção | https://clivon-api.onrender.com |
| Documentação Swagger | https://clivon-api.onrender.com/docs |

> ℹ️ O servidor usa o plano gratuito do Render, que entra em modo sleep após inatividade. A primeira requisição pode levar até 60 segundos para "acordar" a API.

---

## Como Funciona

```
Professor tira foto da prova
        ↓
OpenCV processa e normaliza a imagem
        ↓
Tesseract OCR extrai as respostas marcadas
        ↓
API compara com o gabarito salvo
        ↓
Resultado é salvo no Supabase e exibido no painel
```

---

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

---

## Roadmap

- [x] Correção automática via OCR
- [x] Autenticação JWT para professores e alunos
- [x] Multi-tenant (suporte a múltiplas escolas)
- [x] Exportação Excel e PDF
- [ ] Reconhecimento de bolhas estilo ENEM (visão computacional avançada)
- [ ] Dashboard com gráficos de desempenho
- [ ] Correção com IA (modelos de linguagem)
- [ ] Upload em lote de provas
- [ ] Aplicativo mobile
- [ ] Sistema SaaS com planos e assinaturas

---

## Contribuição

Contribuições são bem-vindas!

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas alterações (`git commit -m 'feat: adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

---

## Licença

Distribuído sob a licença MIT. Veja o arquivo `LICENSE` para mais informações.

---

<div align="center">
  Desenvolvido com dedicação por <strong>Weko Studio</strong>
</div>
