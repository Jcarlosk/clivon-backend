import cv2
import numpy as np


def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect


def process_scan(image_bytes):
    """
    Pipeline melhorado:
    1. Decode imagem
    2. Pré-processamento
    3. Detecção da folha
    4. Warp (corrigir perspectiva)
    5. Threshold adaptativo (robusto)
    """

    # ── 1. Decode ─────────────────────────────
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("Imagem inválida")

    # ── 2. Pré-processamento ──────────────────
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Melhor que Gaussian puro
    gray = cv2.bilateralFilter(gray, 11, 17, 17)

    # ── 3. Edge Detection ─────────────────────
    edged = cv2.Canny(gray, 50, 150)

    # ── 4. Contornos ──────────────────────────
    contours, _ = cv2.findContours(
        edged.copy(),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    paper_contour = None

    for c in contours[:10]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        if len(approx) == 4:
            paper_contour = approx
            break

    # ── Fallback inteligente ──────────────────
    if paper_contour is None:
        print("⚠️ Não encontrou folha — usando fallback")

        # usa adaptive threshold direto
        thresh = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            15,
            5
        )

        return thresh

    # ── 5. Warp (corrigir perspectiva) ────────
    pts = paper_contour.reshape(4, 2)
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = int(max(widthA, widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = int(max(heightA, heightB))

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(gray, M, (maxWidth, maxHeight))

    # ── 6. Melhorar contraste ─────────────────
    warped = cv2.equalizeHist(warped)

    # ── 7. Threshold (ESSENCIAL) ──────────────
    warped_binary = cv2.adaptiveThreshold(
        warped,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11,
        3
    )

    # ── 8. Remover ruído ──────────────────────
    kernel = np.ones((3, 3), np.uint8)
    warped_binary = cv2.morphologyEx(warped_binary, cv2.MORPH_CLOSE, kernel)

    return warped_binary