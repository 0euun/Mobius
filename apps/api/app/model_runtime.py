# 로컬에 저장된 Mobius 분류 모델의 지연 로딩 추론 런타임

from __future__ import annotations

from pathlib import Path
from typing import Literal
import os

MODEL_DIR = Path(os.getenv("MOBIUS_MODEL_DIR", str(Path.cwd() / "artifacts" / "text-classifier-full" / "best")))


class TextClassifier:
    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._torch = None
        self.error: str | None = None

    @property
    def status(self) -> Literal["ready", "unavailable", "not_loaded"]:
        if self._model is not None:
            return "ready"
        if self.error is not None or not MODEL_DIR.exists():
            return "unavailable"
        return "not_loaded"

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if not MODEL_DIR.exists():
            self.error = f"모델 파일이 없습니다: {MODEL_DIR}"
            return False
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
            self._model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
            self._model.eval()
            return True
        except Exception as error:  # Docker fallback을 위해 API 자체는 계속 동작시킨다.
            self.error = str(error)
            return False

    def harmful_probabilities(self, texts: list[str]) -> list[float] | None:
        if not texts or not self._load():
            return None
        assert self._torch is not None and self._tokenizer is not None and self._model is not None
        with self._torch.no_grad():
            batch = self._tokenizer(texts, padding=True, truncation=True, max_length=160, return_tensors="pt")
            logits = self._model(**batch).logits
            return self._torch.softmax(logits, dim=-1)[:, 1].tolist()


classifier = TextClassifier()
