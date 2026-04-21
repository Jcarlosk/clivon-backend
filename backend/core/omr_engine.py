import cv2
import numpy as np
import base64
from dataclasses import dataclass
from typing import Optional

# ── Tesseract (OCR) ───────────────────────────────────────────────────────────
try:
    import pytesseract
    # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    _TESSERACT_OK = True
except ImportError:
    _TESSERACT_OK = False

OPTIONS = ["A", "B", "C", "D", "E"]


@dataclass
class BubbleDetection:
    question: int
    detected_answer: str
    confidence: float
    bubbles: list


@dataclass
class OMRResult:
    success: bool
    answers: list[str]
    detections: list[BubbleDetection]
    student_name_text: Optional[str] = None
    class_name_text: Optional[str] = None
    debug_image_b64: Optional[str] = None
    error: Optional[str] = None


# ── utils ─────────────────────────────────────────────────────────────────────

def decode_image(image_b64):
    data = base64.b64decode(image_b64)
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def encode_image(img):
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode()


def warp(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edged = cv2.Canny(gray, 50, 150)

    cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

    for c in cnts[:5]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        if len(approx) == 4:
            pts = approx.reshape(4, 2)
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]

            (tl, tr, br, bl) = rect
            width  = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))

            dst = np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            return cv2.warpPerspective(image, M, (width, height))

    return image


def group_circles_into_rows(circles, gap_factor=0.6):
    if len(circles) == 0:
        return []

    avg_r = float(np.mean([c[2] for c in circles]))
    threshold = avg_r * 2 * gap_factor
    sorted_circles = sorted(circles, key=lambda c: c[1])

    rows = []
    current_row = [sorted_circles[0]]
    row_y_sum = sorted_circles[0][1]

    for circle in sorted_circles[1:]:
        x, y, r = circle
        row_avg_y = row_y_sum / len(current_row)
        if abs(y - row_avg_y) <= threshold:
            current_row.append(circle)
            row_y_sum += y
        else:
            rows.append(current_row)
            current_row = [circle]
            row_y_sum = y

    if current_row:
        rows.append(current_row)

    return rows


def filter_valid_rows(rows, expected_options):
    return [row for row in rows if 2 <= len(row) <= expected_options + 1]


# ── OCR do cabeçalho ──────────────────────────────────────────────────────────

def _read_header(img, header_ratio=0.22):
    """
    Lê nome e turma do cabeçalho da folha OMR.

    Layout esperado (sua folha):
    ┌─────────────────────────────────┬────────┬──────────┐
    │ NOME DO ALUNO  joao carlos ...  │ TURMA  │  DATA    │
    └─────────────────────────────────┴────────┴──────────┘

    Estratégia:
      - Recorta os primeiros ~22% da imagem (cabeçalho)
      - Divide em faixa esquerda (nome) e faixa direita (turma)
      - Aplica OCR em cada faixa separadamente para maior precisão
    """
    if not _TESSERACT_OK:
        print("[OCR] pytesseract não disponível.")
        return "", ""

    H, W = img.shape[:2]
    header = img[0:int(H * header_ratio), 0:W]
    Hh, Wh = header.shape[:2]

    detected_name  = ""
    detected_class = ""

    def _ocr_region(region, psm=7):
        """Aplica pré-processamento + OCR numa região e retorna o texto."""
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        # Escala 3x para melhorar OCR em texto pequeno
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        config = f"--psm {psm} -l por"
        try:
            return pytesseract.image_to_string(thresh, config=config).strip()
        except Exception as e:
            print(f"[OCR WARNING] {e}")
            return ""

    # ── Estratégia 1: OCR em bloco no cabeçalho inteiro (psm=6) ──────────────
    full_text = _ocr_region(header, psm=6)
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        upper = line.upper()

        # "NOME DO ALUNO" aparece como label — o valor está na mesma linha ou na próxima
        if "NOME" in upper and "ALUNO" in upper:
            # Tenta pegar o conteúdo após "ALUNO" na mesma linha
            for kw in ["NOME DO ALUNO", "NOME DO ALUNO:", "ALUNO:", "ALUNO"]:
                if kw in line.upper():
                    idx = line.upper().find(kw) + len(kw)
                    candidate = line[idx:].strip(" :_-")
                    # Remove possível "TURMA xxx DATA xxx" que veio junto
                    for stopper in ["TURMA", "DATA", "DISCIPLINA"]:
                        if stopper in candidate.upper():
                            candidate = candidate[:candidate.upper().find(stopper)].strip()
                    if len(candidate) > 1:
                        detected_name = candidate
                        break
            # Se não achou na mesma linha, pega a próxima linha não-vazia
            if not detected_name and i + 1 < len(lines):
                candidate = lines[i + 1].strip(" :_-")
                for stopper in ["TURMA", "DATA", "DISCIPLINA"]:
                    if stopper in candidate.upper():
                        candidate = candidate[:candidate.upper().find(stopper)].strip()
                if len(candidate) > 1:
                    detected_name = candidate

        # "TURMA" — pega o valor logo após
        if not detected_class and "TURMA" in upper:
            for kw in ["TURMA:", "TURMA"]:
                if kw in upper:
                    idx = upper.find(kw) + len(kw)
                    candidate = line[idx:].strip(" :_-")
                    # Remove "DATA" e tudo depois
                    for stopper in ["DATA", "PROFESSOR", "\n"]:
                        if stopper in candidate.upper():
                            candidate = candidate[:candidate.upper().find(stopper)].strip()
                    # Turma costuma ser curta: "5A", "3B", "9º A"
                    candidate = candidate.split()[0] if candidate.split() else ""
                    if len(candidate) >= 1:
                        detected_class = candidate
                        break

    # ── Estratégia 2: OCR direto na faixa de nome (esq) e turma (dir) ────────
    # Faixa da linha do nome: ~15% a 30% da altura do cabeçalho
    name_row_top    = int(Hh * 0.15)
    name_row_bottom = int(Hh * 0.42)

    if not detected_name:
        # Faixa esquerda (~60% da largura) = campo do nome
        name_region = header[name_row_top:name_row_bottom, 0:int(Wh * 0.60)]
        raw = _ocr_region(name_region, psm=7)
        # Remove prefixos de label
        for kw in ["NOME DO ALUNO", "NOME DO ALUNO:", "ALUNO:", "ALUNO"]:
            raw = raw.replace(kw, "").replace(kw.lower(), "").replace(kw.title(), "")
        candidate = raw.strip(" :_-\n")
        if len(candidate) > 1:
            detected_name = candidate

    if not detected_class:
        # Faixa direita da mesma linha = campo da turma
        turma_region = header[name_row_top:name_row_bottom, int(Wh * 0.60):int(Wh * 0.78)]
        raw = _ocr_region(turma_region, psm=7)
        for kw in ["TURMA:", "TURMA"]:
            raw = raw.replace(kw, "").replace(kw.lower(), "").replace(kw.title(), "")
        candidate = raw.strip(" :_-\n").split()[0] if raw.strip() else ""
        if len(candidate) >= 1:
            detected_class = candidate

    return detected_name.strip(), detected_class.strip()


# ── MAIN ──────────────────────────────────────────────────────────────────────

def process_omr(image_b64, total_questions, answer_key):

    img = decode_image(image_b64)
    if img is None:
        return OMRResult(False, [], [], error="Imagem inválida")

    img = warp(img)
    H, W = img.shape[:2]

    # 1. Lê nome e turma do cabeçalho
    detected_name, detected_class = _read_header(img)
    print(f"[OCR] Nome: '{detected_name}' | Turma: '{detected_class}'")

    # 2. Prepara imagem para bolhas
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)

    # 3. Detecta círculos
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=18,
        param1=50, param2=28,
        minRadius=8, maxRadius=30,
    )

    if circles is None:
        return OMRResult(False, [], [], error="Nenhum círculo detectado")

    circles = np.round(circles[0, :]).astype("int").tolist()

    # 4. Agrupa e filtra linhas
    rows = group_circles_into_rows(circles, gap_factor=0.6)
    num_options = len(answer_key[0]) if answer_key and isinstance(answer_key[0], list) else len(OPTIONS)
    rows = filter_valid_rows(rows, num_options)
    rows = sorted(rows, key=lambda row: np.mean([c[1] for c in row]))

    if len(rows) < total_questions:
        print(f"[OMR WARNING] Esperado {total_questions} linhas, detectado {len(rows)}")

    # 5. Threshold para preenchimento
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11, 3,
    )

    answers = []
    detections = []
    debug = img.copy()

    for i, row in enumerate(rows[:total_questions]):
        row_sorted = sorted(row, key=lambda c: c[0])
        fill_scores = []
        bubbles = []

        for j, (x, y, r) in enumerate(row_sorted):
            mask = np.zeros(thresh.shape, dtype="uint8")
            cv2.circle(mask, (x, y), r, 255, -1)
            total_px  = cv2.countNonZero(mask)
            filled_px = cv2.countNonZero(cv2.bitwise_and(thresh, thresh, mask=mask))
            ratio = filled_px / float(total_px) if total_px > 0 else 0
            fill_scores.append(ratio)
            bubbles.append({
                "option": OPTIONS[j] if j < len(OPTIONS) else "?",
                "ratio": round(ratio, 3),
                "filled": False,
                "cx": round(x / W, 4),
                "cy": round(y / H, 4),
                "r":  round(r / max(W, H), 4),
            })

        idx = int(np.argmax(fill_scores))

        if fill_scores[idx] > 0.35 and idx < len(OPTIONS):
            detected = OPTIONS[idx]
            bubbles[idx]["filled"] = True
        else:
            detected = "?"

        correct    = answer_key[i] if i < len(answer_key) else "?"
        is_correct = detected == correct

        for j, (x, y, r) in enumerate(row_sorted):
            color = (160, 160, 160)
            if j == idx and detected != "?":
                color = (0, 200, 80) if is_correct else (0, 60, 220)
            cv2.circle(debug, (x, y), r, color, 2)
            if j == 0:
                cv2.putText(debug, str(i + 1), (x - r - 22, y + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 80), 1)

        detections.append(BubbleDetection(
            question=i + 1,
            detected_answer=detected,
            confidence=round(fill_scores[idx], 2),
            bubbles=bubbles,
        ))
        answers.append(detected)

    return OMRResult(
        success=True,
        answers=answers,
        detections=detections,
        student_name_text=detected_name or None,
        class_name_text=detected_class or None,
        debug_image_b64=encode_image(debug),
    )