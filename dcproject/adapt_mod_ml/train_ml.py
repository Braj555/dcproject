"""
Train an ML model (Decision Tree) to select BPSK/QPSK/16QAM from features:
[SNR_dB, delay_ms, jitter_ms, recent_BER].
Synthetic dataset via AWGN-based heuristics keeps this self-contained.
"""

import numpy as np, pickle
from math import erfc, sqrt
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report

def ber_bpsk_theory(ebn0_db):
    ebn0 = 10**(ebn0_db/10.0)
    return 0.5*erfc(sqrt(ebn0))

def ber_qpsk_theory(ebn0_db):
    return ber_bpsk_theory(ebn0_db)

def ber_16qam_theory(ebn0_db):
    # crude but fine for labeling
    ebn0 = 10**(ebn0_db/10.0)
    return (3/8.0)*erfc(sqrt(0.1*ebn0))

def gen_data(N=6000, seed=1):
    np.random.seed(seed)
    X, y = [], []
    for _ in range(N):
        snr = np.random.uniform(-2, 18)  # dB
        delay = np.random.uniform(2, 40)
        jitter = np.random.uniform(0.2, 10.0)

        b_bpsk = ber_bpsk_theory(snr)
        b_qpsk = ber_qpsk_theory(snr)
        b_16q = ber_16qam_theory(snr)
        recent = np.clip(0.6*b_qpsk + 0.4*np.random.rand()*0.02, 0, 1)

        # choose highest order meeting BER<1e-3
        if b_16q < 1e-3: lab = 2
        elif b_qpsk < 1e-3: lab = 1
        else: lab = 0

        X.append([snr, delay, jitter, recent])
        y.append(lab)
    return np.array(X, float), np.array(y, int)

def main():
    X, y = gen_data()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    pipe = Pipeline([
        ('sc', StandardScaler()),
        ('dt', DecisionTreeClassifier(max_depth=6, random_state=42))
    ])
    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    print("Accuracy:", accuracy_score(yte, pred))
    print(classification_report(yte, pred, target_names=['BPSK','QPSK','16QAM']))
    with open('model.pkl', 'wb') as f:
        pickle.dump(pipe, f)
    print("Saved model.pkl")

if __name__ == "__main__":
    main()
