"""
Training pipeline — SVM (hero) vs Random Forest (light baseline)
Intent classification untuk routing chat Customer Service Bahasa Indonesia.

Perubahan vs versi sebelumnya (sesuai feedback bimbingan skripsi):
  1. Preprocessing DISATUKAN jadi satu fungsi `preprocess_text` yang dipakai
     baik saat training maupun saat inference (classifier.py) -> konsisten.
  2. Ditambah Stratified K-Fold Cross Validation (5-fold) -> report mean +/- std.
  3. Ditambah ablation study (grid C, ngram_range, max_features) -> tabel.
  4. Random Forest sebagai LIGHT BASELINE (SVM tetap metode utama / hero).
  5. Confidence threshold + fallback intent ("other") untuk routing realistis di
     dunia nyata (pesan ngoceh / di luar 11 intent).

Dataset: Bitext Customer Support (diterjemahkan ke Bahasa Indonesia),
5.995 baris, 11 intent, balanced (~545/intent).
CATATAN METODOLOGI: dataset ini bersifat sintetis/terjemahan -> akurasi
99%+ adalah optimistic upper bound. Validasi ke chat CS ASLI (real) tetap
diperlukan dan harus didokumentasikan di bab metodologi.
"""

import re
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")  # headless / terminal safe
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

# ---------------------------------------------------------------------------
# 1. SHARED PREPROCESSING (dipakai train + inference -> konsisten)
# ---------------------------------------------------------------------------
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


def preprocess_text(text: str) -> str:
    """Normalisasi + stopword removal. SAMA PERSIS dengan app/services/classifier.py."""
    text = str(text).lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = [t for t in text.split() if t not in STOPWORDS]
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# 2. BUILD PIPELINES
# ---------------------------------------------------------------------------
def build_svm_pipeline(C: float = 1.0, ngram_range=(1, 2), max_features: int = 5000) -> Pipeline:
    return Pipeline(
        steps=[
            ("tfidf", TfidfVectorizer(max_features=max_features, ngram_range=ngram_range, sublinear_tf=True)),
            ("svm", LinearSVC(C=C, class_weight="balanced", random_state=42)),
        ]
    )


def build_rf_pipeline(ngram_range=(1, 2), max_features: int = 5000) -> Pipeline:
    return Pipeline(
        steps=[
            ("tfidf", TfidfVectorizer(max_features=max_features, ngram_range=ngram_range, sublinear_tf=True)),
            ("rf", RandomForestClassifier(n_estimators=200, max_depth=30, random_state=42, n_jobs=-1)),
        ]
    )


# ---------------------------------------------------------------------------
# 3. EVALUATION HELPERS
# ---------------------------------------------------------------------------
def stratified_cv(pipeline: Pipeline, X, y, cv: int = 5) -> tuple[float, float]:
    """Return (mean_acc, std_acc) via stratified k-fold CV."""
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)
    scores = cross_val_score(pipeline, X, y, cv=skf, scoring="accuracy", n_jobs=-1)
    return float(scores.mean()), float(scores.std())


def ablation_table(X, y, cv: int = 5) -> pd.DataFrame:
    """Grid search ringan: C, ngram_range, max_features -> SVM CV mean/std."""
    rows = []
    for ngram in [(1, 1), (1, 2)]:
        for mf in [3000, 5000]:
            for C in [0.5, 1.0, 2.0]:
                pipe = build_svm_pipeline(C=C, ngram_range=ngram, max_features=mf)
                mean, std = stratified_cv(pipe, X, y, cv=cv)
                rows.append({"ngram_range": str(ngram), "max_features": mf, "C": C,
                             "cv_mean": round(mean, 4), "cv_std": round(std, 4)})
    return pd.DataFrame(rows).sort_values("cv_mean", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    base = Path(__file__).resolve().parent
    data_path = base / "dataset.csv"
    output_dir = base / "model"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        raise FileNotFoundError(f"Dataset not found: {data_path}")

    df = pd.read_csv(data_path)
    if not {"intent", "text"}.issubset(df.columns):
        raise ValueError(f"dataset.csv must contain {{intent, text}}, found {set(df.columns)}")

    df = df.dropna(subset=["intent", "text"]).copy()
    df["text_clean"] = df["text"].astype(str).apply(preprocess_text)

    X = df["text_clean"].values
    y = df["intent"].values

    # Hold-out split (stratified) untuk classification report + confusion matrix
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    print("=" * 70)
    print("DATASET")
    print(f"  Total rows : {len(df)}")
    print(f"  Intents    : {df['intent'].nunique()}")
    print(f"  Train/Test : {len(X_train)} / {len(X_test)}")
    print("=" * 70)

    # ---- Stratified K-Fold CV (5-fold) ----
    print("\n[1] STRATIFIED K-FOLD CROSS VALIDATION (5-fold, mean +/- std)")
    svm_cv_mean, svm_cv_std = stratified_cv(build_svm_pipeline(), X, y)
    rf_cv_mean, rf_cv_std = stratified_cv(build_rf_pipeline(), X, y)
    print(f"  SVM (LinearSVC, C=1.0) : {svm_cv_mean:.4f} (+/- {svm_cv_std:.4f})")
    print(f"  RF  (200 trees)         : {rf_cv_mean:.4f} (+/- {rf_cv_std:.4f})")

    # ---- Ablation study ----
    print("\n[2] ABLATION STUDY (SVM hyperparameter grid, by CV mean)")
    abl = ablation_table(X, y)
    print(abl.to_string(index=False))

    # ---- Final models on hold-out ----
    print("\n[3] HOLD-OUT EVALUATION (test_size=0.2, stratified)")
    svm = build_svm_pipeline()
    svm.fit(X_train, y_train)
    svm_pred = svm.predict(X_test)
    svm_acc = accuracy_score(y_test, svm_pred)
    print(f"  SVM Accuracy: {svm_acc:.4f}")
    print(classification_report(y_test, svm_pred, digits=4, zero_division=0))

    rf = build_rf_pipeline()
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)
    rf_acc = accuracy_score(y_test, rf_pred)
    print(f"  RF  Accuracy: {rf_acc:.4f}")
    print(classification_report(y_test, rf_pred, digits=4, zero_division=0))

    # ---- Save hero model (SVM) ----
    model_path = output_dir / "svm_intent_pipeline.joblib"
    joblib.dump(svm, model_path)
    print(f"\nSaved HERO model (SVM) -> {model_path}")

    # ---- Confusion matrix (SVM) ----
    labels = sorted(df["intent"].unique())
    cm = confusion_matrix(y_test, svm_pred, labels=labels)
    plt.figure(figsize=(12, 9))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=labels, yticklabels=labels)
    plt.title("Confusion Matrix - SVM Intent Classifier")
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    cm_path = output_dir / "confusion_matrix.png"
    plt.savefig(cm_path, dpi=300)
    plt.close()
    print(f"Saved confusion matrix -> {cm_path}")

    # ---- Top-10 tokens per intent (interpretability) ----
    tfidf = svm.named_steps["tfidf"]
    svm_clf = svm.named_steps["svm"]
    feat_names = tfidf.get_feature_names_out()
    coef = svm_clf.coef_
    print("\n[4] TOP-10 TF-IDF TOKENS PER INTENT (interpretability)")
    for idx, intent in enumerate(svm_clf.classes_):
        top = [feat_names[i] for i in coef[idx].argsort()[-10:][::-1]]
        print(f"  - {intent}: {', '.join(top)}")

    # ---- Confidence threshold / fallback demo ----
    # LinearSVC tidak punya predict_proba; pakai decision_function (margin).
    # Untuk routing realistis: jika margin maks < THRESHOLD -> intent 'other'.
    print("\n[5] FALLBACK / CONFIDENCE THRESHOLD (routing ke 'other' jika ragu)")
    margins = svm.decision_function(X_test)
    confidence = margins.max(axis=1)
    THRESHOLD = 0.2  # tune di bab 4
    fallback_rate = (confidence < THRESHOLD).mean()
    print(f"  Threshold={THRESHOLD} -> {(fallback_rate*100):.2f}% test msgs routed to 'other'")
    print("  (Implementasi di classifier.py: bandingkan decision_function max vs threshold)")

    print("\nDONE.")


if __name__ == "__main__":
    main()
