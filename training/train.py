import re
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


STOPWORDS = {
    word.strip()
    for word in """
    dari, yang, di, ke, dan, ini, itu, saja, juga, dengan, pada, untuk, tidak, akan, dapat, telah,
    karena, tetapi, atau, adalah, mereka, kami, kita, saya, ada, sudah, bisa, mau, nya, pun, ya, deh,
    sih, kok, loh, dong, kah, punya, sedang, telah, belum, agar, supaya, sangat, paling, lebih, kurang,
    paling, semua, setiap, seorang, tersebut, sendiri, secara, antara, melalui, setelah, sebelum,
    sementara, seraya, sampai, sejak, mengenai, tentang, seperti, sebagai, selain, bagi, demi, oleh,
    dengan, tanpa, di, ke, dari, dalam, atas, bawah, luar, depan, belakang, dekat, jauh, sekitar, kira,
    antara, dalam, melalui, secara
    """.split(",")
    if word.strip()
}


def preprocess_text(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = [token for token in text.split() if token not in STOPWORDS]
    return " ".join(tokens)


def main() -> None:
    data_path = Path("dataset.csv")
    output_dir = Path("model")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        raise FileNotFoundError(f"Dataset not found: {data_path}")

    df = pd.read_csv(data_path)
    required_columns = {"intent", "text"}
    if not required_columns.issubset(df.columns):
        raise ValueError(
            f"dataset.csv must contain columns {required_columns}, found {set(df.columns)}"
        )

    df = df.dropna(subset=["intent", "text"]).copy()
    df["text_clean"] = df["text"].astype(str).apply(preprocess_text)

    X_train, X_test, y_train, y_test = train_test_split(
        df["text_clean"],
        df["intent"],
        test_size=0.2,
        stratify=df["intent"],
        random_state=42,
    )

    pipeline = Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=5000,
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                ),
            ),
            (
                "svm",
                LinearSVC(
                    C=1.0,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    print(f"Accuracy: {accuracy:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=4, zero_division=0))

    model_path = output_dir / "svm_intent_pipeline.joblib"
    joblib.dump(pipeline, model_path)
    print(f"\nSaved pipeline to: {model_path}")

    labels = sorted(df["intent"].unique())
    cm = confusion_matrix(y_test, y_pred, labels=labels)

    plt.figure(figsize=(12, 9))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=labels,
        yticklabels=labels,
    )
    plt.title("Confusion Matrix - SVM Intent Classifier")
    plt.xlabel("Predicted Label")
    plt.ylabel("True Label")
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()

    cm_path = output_dir / "confusion_matrix.png"
    plt.savefig(cm_path, dpi=300)
    plt.close()
    print(f"Saved confusion matrix to: {cm_path}")

    tfidf = pipeline.named_steps["tfidf"]
    svm = pipeline.named_steps["svm"]
    feature_names = tfidf.get_feature_names_out()
    coefficients = svm.coef_.toarray() if hasattr(svm.coef_, "toarray") else svm.coef_

    print("\nTop 10 TF-IDF tokens per intent:")
    for class_idx, intent in enumerate(svm.classes_):
        top_indices = coefficients[class_idx].argsort()[-10:][::-1]
        top_tokens = [feature_names[index] for index in top_indices]
        print(f"- {intent}: {', '.join(top_tokens)}")


if __name__ == "__main__":
    main()
