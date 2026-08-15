"""Statistical fallback classifier for need categories.

The lexicon in triage.py is precise and explainable but only recognizes phrases
it has seen. This model generalizes to new phrasing ("not responding", "deep
cut", "contaminated") using character and word n-grams, which also work across
English, Hindi and Tamil without language-specific tokenizers.

It is trained on data/triage_training.csv (the development set). The held-out
evaluation set is never used for training or model selection: the
regularization strength is chosen by cross-validation on the training data.

The model is only consulted when the lexicon finds no need at all, and any
request categorized this way is flagged for human review.
"""

from __future__ import annotations

import csv
import warnings
from functools import lru_cache
from pathlib import Path

TRAINING_FILE = Path(__file__).resolve().parent.parent / "data" / "triage_training.csv"
MIN_CONFIDENCE = 0.30


@lru_cache(maxsize=1)
def _model():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegressionCV
    from sklearn.pipeline import make_pipeline, make_union

    with open(TRAINING_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    texts = [r["text"] for r in rows]
    labels = [r["category"] for r in rows]
    features = make_union(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
        TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True),
    )
    clf = LogisticRegressionCV(Cs=[0.5, 1, 5, 20], cv=3, max_iter=3000)
    model = make_pipeline(features, clf)
    with warnings.catch_warnings():
        # Small training set + sklearn version-transition notices; neither affects results.
        warnings.simplefilter("ignore")
        model.fit(texts, labels)
    return model


def predict_category(text: str) -> tuple[str, float] | None:
    """Return (category, probability), or None if the model is unsure or unavailable."""
    try:
        model = _model()
    except Exception:
        return None
    probs = model.predict_proba([text])[0]
    best = probs.argmax()
    label, conf = model.classes_[best], float(probs[best])
    if label == "other" or conf < MIN_CONFIDENCE:
        return None
    return label, conf
