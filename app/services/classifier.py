from pathlib import Path
import re
from typing import Any

import joblib

from app.config import settings


class IntentClassifier:
    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = Path(model_path or settings.MODEL_PATH)
        self.model: Any | None = None

    def load(self) -> Any | None:
        """Load the trained SVM pipeline if available."""
        if self.model is not None:
            return self.model

        if not self.model_path.exists():
            return None

        try:
            self.model = joblib.load(self.model_path)
        except FileNotFoundError:
            return None

        return self.model

    def preprocess(self, text: str) -> str:
        """Normalize text before classification."""
        normalized = str(text).lower()
        normalized = re.sub(r"[^a-z\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def predict(self, text: str) -> str:
        """Predict user intent from text."""
        model = self.load()
        if model is None:
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        preprocessed = self.preprocess(text)
        prediction = model.predict([preprocessed])
        return str(prediction[0])
