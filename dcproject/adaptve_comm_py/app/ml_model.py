# app/ml_model.py
import numpy as np
from math import erfc, sqrt
from sklearn.tree import DecisionTreeClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import pickle, os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

def ber_bpsk(ebn0_db): 
    ebn0 = 10**(ebn0_db/10.0); 
    return 0.5*erfc(sqrt(ebn0))

def ber_qpsk(ebn0_db): 
    return ber_bpsk(ebn0_db)

def ber_16qam(ebn0_db):
    ebn0 = 10**(ebn0_db/10.0)
    return (3/8.0)*erfc(sqrt(0.1*ebn0))

def gen(N=5000, seed=1):
    rng = np.random.default_rng(seed)
    X=[]; y=[]
    for _ in range(N):
        snr = rng.uniform(-2,18)
        delay = rng.uniform(5,60)
        jitter = rng.uniform(0.1,12)
        rb = ber_bpsk(snr); rq=ber_qpsk(snr); r16=ber_16qam(snr)
        recent = np.clip(0.6*rq + 0.02*rng.random(), 0, 1)
        if r16<1e-3: lab=2
        elif rq<1e-3: lab=1
        else: lab=0
        X.append([snr, delay, jitter, recent]); y.append(lab)
    return np.array(X,float), np.array(y,int)

def train_and_save():
    X,y = gen()
    Xtr,Xte,ytr,yte = train_test_split(X,y,test_size=0.25,random_state=42,stratify=y)
    pipe = Pipeline([('sc',StandardScaler()),('dt',DecisionTreeClassifier(max_depth=6,random_state=42))])
    pipe.fit(Xtr,ytr)
    with open(MODEL_PATH,'wb') as f: pickle.dump(pipe,f)

def load_model():
    if not os.path.exists(MODEL_PATH):
        train_and_save()
    with open(MODEL_PATH,'rb') as f:
        return pickle.load(f)

def select_modulation(model, snr_db, delay_ms, jitter_ms, recent_ber):
    X = np.array([[snr_db, delay_ms, jitter_ms, recent_ber]], float)
    idx = int(model.predict(X)[0])
    return ["BPSK","QPSK","16QAM"][idx]
