from typing import List, Dict, Any

ANSWER_KEY: List[str] = ["A", "B", "C", "D", "E", "A", "B", "C", "D", "E"]


def grade(answers: List[str], answer_key: List[str] = ANSWER_KEY) -> Dict[str, Any]:
    """
    Compare student answers against the answer key.
    BLANK and INVALID are always wrong.
    Returns score, total, and per-question breakdown.
    """
    total = len(answer_key)
    score = 0
    breakdown = []

    for i, (given, correct) in enumerate(zip(answers, answer_key)):
        is_correct = given == correct
        if is_correct:
            score += 1
        breakdown.append({
            "question": i + 1,
            "given": given,
            "correct": correct,
            "result": "correct" if is_correct else "wrong",
        })

    return {
        "answers": answers,
        "score": score,
        "total": total,
        "breakdown": breakdown,
    }
