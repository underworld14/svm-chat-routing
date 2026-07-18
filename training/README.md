# Training SVM — Intent Classification

Training script untuk model SVM (LinearSVC + TF-IDF) yang mengklasifikasikan intent pesan chat dalam Bahasa Indonesia.

## Dataset

**File:** `dataset.csv` (5.995 baris, 11 intent, balanced 545/sample)

**Intent:**
| Intent | Contoh |
|---|---|
| `account_data` | cara menghapus riwayat pencarian min |
| `cancellation_request` | pembatalan tiket event bisa ga nih |
| `complaint` | saya minta kompensasi atas ketidaknyamanan ini sob |
| `operating_hours_location` | ada toko yg buka sampai jam 10 malam deh |
| `order_status` | driver udah otw belum ya |
| `payment_inquiry` | tagihan beda sama harga di keranjang kenapa deh |
| `product_service_info` | selimut cocok buat lama ga sih |
| `promotions_discounts` | ada diskon di toko offline juga ga sih |
| `refund_request` | proses refund item berapa lama sob |
| `shipping_information` | JNE ke Palembang berapa hari reguler |
| `technical_support` | app grab error pas buka checkout |

## Cara Pakai

```bash
# 1. Buat venv dengan uv (Python 3.13+)
uv venv --python 3.13 && source .venv/bin/activate

# 2. Install dependencies
uv pip install scikit-learn pandas numpy matplotlib seaborn joblib

# 3. Jalankan training
python train.py
```

Output:
- `model/svm_intent_pipeline.joblib` — pipeline TF-IDF + LinearSVC
- `model/confusion_matrix.png` — confusion matrix heatmap

## Test Prediction

```bash
source .venv/bin/activate
python3 -c "
import joblib
pipeline = joblib.load('model/svm_intent_pipeline.joblib')
text = 'pesanan saya belum sampai'
intent = pipeline.predict([text])[0]
print(f'Intent: {intent}')
"
```

## Hasil

| Metrik | Nilai |
|---|---|
| Accuracy | 99.92% |
| Test samples | 1.199 |
| Pipeline | TF-IDF (max_features=5000, ngram 1-2) → LinearSVC (C=1.0) |

## Dependencies

- Python 3
- scikit-learn
- pandas
- numpy
- matplotlib
- seaborn
- joblib

Sudah terinstall di `.venv/`.
