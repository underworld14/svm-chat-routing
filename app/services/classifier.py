from pathlib import Path
import re
from typing import Any

import joblib

from app.config import settings

# MUST match training/train.py::preprocess_text so inference == training.
STOPWORDS = {
    word.strip()
    for word in """
    dari, yang, di, ke, dan, ini, itu, saja, juga, dengan, pada, untuk, tidak, akan, dapat, telah,
    karena, tetapi, atau, adalah, mereka, kami, kita, saya, ada, sudah, bisa, mau, nya, pun, ya, deh,
    sih, kok, loh, dong, kah, punya, sedang, belum, agar, supaya, sangat, paling, lebih, kurang,
    semua, setiap, seorang, tersebut, sendiri, secara, antara, melalui, setelah, sebelum,
    sementara, seraya, sampai, sejak, mengenai, tentang, seperti, sebagai, selain, bagi, demi, oleh,
    tanpa, dalam, atas, bawah, luar, depan, belakang, dekat, jauh, sekitar, kira
    """.split(",")
    if word.strip()
}


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
        """Normalize + stopword removal. IDENTICAL to training/train.py."""
        text = str(text).lower()
        text = re.sub(r"[^a-z\s]", " ", text)
        tokens = [t for t in text.split() if t not in STOPWORDS]
        return " ".join(tokens)

    def predict(self, text: str) -> str:
        """Predict user intent from text."""
        model = self.load()
        if model is None:
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        preprocessed = self.preprocess(text)
        prediction = model.predict([preprocessed])
        return str(prediction[0])
