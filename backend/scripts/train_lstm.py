"""
TyphoonPath — LSTM Seq2Seq with Attention 훈련 스크립트
=========================================================
레퍼런스: sunyeongan/2022_SwCapstoneDesign_GNN (Seq2Seq + Attention 아이디어)
데이터:   IBTrACS WP (typhoons.json or typhoons_v2.json)

모델 구조
---------
Encoder : LSTM(8 features × past 4 steps → hidden)
Decoder : LSTM + Bahdanau Attention (auto-regressive, 40 steps)
Ensemble: hidden_size = [48, 64, 96] → 3개 모델 평균 예측

입력 피처 (8차원, 1스텝)
  dlat, dlng       : 이전 대비 위도·경도 변화 (이동 벡터)
  dpres            : 이전 대비 기압 변화
  lat_norm         : 정규화 위도 (0~1)
  lng_norm         : 정규화 경도 (0~1)
  pres_norm        : 정규화 기압 (0~1)
  sin_month        : 월 사인 인코딩
  cos_month        : 월 코사인 인코딩

훈련 방식
  - 슬라이딩 윈도우: 과거 4스텝(24h) → 미래 최대 40스텝(240h)
  - Teacher forcing: 훈련 시 정답 이전 스텝 입력
  - Loss: L1Loss (MAE)
  - Optimizer: Adam(lr=0.001), CosineAnnealingLR
  - Epoch: 80 / Batch: 256

출력
  backend/data/lstm_model_h{hidden}.pt  (3개)
  backend/data/lstm_meta.json
"""

import json, math, sys, os, time
from pathlib import Path

# ── 환경 확인 ──────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader, random_split
except ImportError:
    print("❌ PyTorch 미설치. 아래 명령어로 설치하세요:")
    print("   pip install torch --index-url https://download.pytorch.org/whl/cpu")
    sys.exit(1)

import numpy as np

DATA_DIR = Path(__file__).parent.parent / "data"
PAST_STEPS   = 4   # 24h 이력
FUTURE_STEPS = 40  # 240h 예측 (max)
HIDDEN_SIZES = [48, 64, 96]
EPOCHS       = 80
BATCH_SIZE   = 256
LR           = 0.001
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(f"디바이스: {DEVICE}")


# ── 정규화 범위 ──────────────────────────────────────────
LAT_MIN, LAT_MAX   =  0.0,  60.0
LNG_MIN, LNG_MAX   = 70.0, 210.0
PRES_MIN, PRES_MAX = 850.0, 1010.0

def norm_lat(v):  return (v - LAT_MIN)  / (LAT_MAX  - LAT_MIN)
def norm_lng(v):  return (v - LNG_MIN)  / (LNG_MAX  - LNG_MIN)
def norm_pres(v): return (v - PRES_MIN) / (PRES_MAX - PRES_MIN)


def make_features(lat, lng, pres, dlat, dlng, dpres, month):
    """8차원 피처 벡터 생성."""
    sin_m = math.sin(2 * math.pi * month / 12)
    cos_m = math.cos(2 * math.pi * month / 12)
    return [
        dlat, dlng, dpres,
        norm_lat(lat), norm_lng(lng), norm_pres(pres),
        sin_m, cos_m,
    ]


# ── 데이터셋 ──────────────────────────────────────────────
class TyphoonSeqDataset(Dataset):
    def __init__(self, sequences):
        self.data = sequences  # list of (src [4,8], tgt [N,3]) tensors

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx]


def load_data():
    for name in ["typhoons_v2.json", "typhoons.json"]:
        path = DATA_DIR / name
        if path.exists():
            print(f"데이터 로드: {name}")
            with open(path) as f:
                return json.load(f)["typhoons"]
    print("❌ 태풍 데이터 파일 없음"); sys.exit(1)


def build_sequences(typhoons):
    seqs = []
    skipped = 0
    for t in typhoons:
        track = t.get("track", [])
        if len(track) < PAST_STEPS + 4:
            continue
        try:
            month = int(track[0]["dt"][5:7])
        except Exception:
            continue

        # 전체 경로에 걸쳐 슬라이딩 윈도우
        for start in range(0, len(track) - PAST_STEPS - 2, 2):
            # ── 입력 (과거 4스텝) ──
            src_feats = []
            valid = True
            prev_lat = prev_lng = prev_pres = None

            for i in range(start, start + PAST_STEPS):
                p = track[i]
                try:
                    lat  = float(p["lat"])
                    lng  = float(p["lng"])
                    pres = float(p.get("pressure") or 985)
                except Exception:
                    valid = False; break

                if prev_lat is None:
                    dlat = dlng = dpres = 0.0
                else:
                    dlat  = lat  - prev_lat
                    dlng  = lng  - prev_lng
                    dpres = pres - prev_pres

                # 이상값 필터
                if abs(dlat) > 8 or abs(dlng) > 8:
                    valid = False; break

                src_feats.append(make_features(lat, lng, pres, dlat, dlng, dpres, month))
                prev_lat, prev_lng, prev_pres = lat, lng, pres

            if not valid or len(src_feats) < PAST_STEPS:
                skipped += 1; continue

            # ── 타겟 (미래 최대 FUTURE_STEPS) ──
            tgt_vecs = []
            p_lat = float(track[start + PAST_STEPS - 1]["lat"])
            p_lng = float(track[start + PAST_STEPS - 1]["lng"])
            p_pres = float(track[start + PAST_STEPS - 1].get("pressure") or 985)

            for j in range(start + PAST_STEPS, min(start + PAST_STEPS + FUTURE_STEPS, len(track))):
                nxt = track[j]
                try:
                    n_lat  = float(nxt["lat"])
                    n_lng  = float(nxt["lng"])
                    n_pres = float(nxt.get("pressure") or p_pres)
                except Exception:
                    break
                dl = n_lat  - p_lat
                dn = n_lng  - p_lng
                dp = n_pres - p_pres
                if abs(dl) > 8 or abs(dn) > 8:
                    break
                tgt_vecs.append([dl, dn, dp])
                p_lat, p_lng, p_pres = n_lat, n_lng, n_pres

            if len(tgt_vecs) < 4:
                skipped += 1; continue

            src_t = torch.tensor(src_feats, dtype=torch.float32)       # [4, 8]
            tgt_t = torch.tensor(tgt_vecs, dtype=torch.float32)        # [N, 3]
            seqs.append((src_t, tgt_t))

    print(f"  시퀀스: {len(seqs):,}개  건너뜀: {skipped:,}개")
    return seqs


def collate_fn(batch):
    """가변 길이 타겟을 min_len으로 트리밍하여 배치화."""
    srcs, tgts = zip(*batch)
    min_len = min(t.size(0) for t in tgts)
    min_len = max(min_len, 4)
    src_batch = torch.stack(srcs)                      # [B, 4, 8]
    tgt_batch = torch.stack([t[:min_len] for t in tgts])  # [B, L, 3]
    return src_batch, tgt_batch


# ── 모델 ──────────────────────────────────────────────────
class BahdanauAttention(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.W1 = nn.Linear(hidden_size, hidden_size)
        self.W2 = nn.Linear(hidden_size, hidden_size)
        self.v  = nn.Linear(hidden_size, 1, bias=False)

    def forward(self, dec_hidden, enc_outputs):
        # dec_hidden: [B, H]  enc_outputs: [B, T, H]
        dec_exp = dec_hidden.unsqueeze(1).expand_as(enc_outputs)  # [B, T, H]
        energy  = torch.tanh(self.W1(enc_outputs) + self.W2(dec_exp))
        scores  = self.v(energy).squeeze(-1)          # [B, T]
        weights = torch.softmax(scores, dim=1)        # [B, T]
        context = (weights.unsqueeze(-1) * enc_outputs).sum(dim=1)  # [B, H]
        return context, weights


class TyphoonSeq2Seq(nn.Module):
    INPUT_SIZE = 8   # encoder input features
    DEC_INPUT  = 3   # decoder input: dlat, dlng, dpres

    def __init__(self, hidden_size: int, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers  = num_layers

        self.encoder = nn.LSTM(
            self.INPUT_SIZE, hidden_size, num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.decoder = nn.LSTM(
            self.DEC_INPUT + hidden_size,  # 입력 + context concat
            hidden_size, num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.attention  = BahdanauAttention(hidden_size)
        self.out_track  = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 3),  # dlat, dlng, dpres
        )

    def encode(self, src):
        enc_out, (h, c) = self.encoder(src)  # [B, T, H], [L, B, H]
        return enc_out, h, c

    def decode_step(self, dec_inp, h, c, enc_out):
        # dec_inp: [B, 3]
        last_h = h[-1]                                   # [B, H]
        context, _ = self.attention(last_h, enc_out)     # [B, H]
        dec_in = torch.cat([dec_inp, context], dim=1).unsqueeze(1)  # [B, 1, 3+H]
        out, (h, c) = self.decoder(dec_in, (h, c))
        out = out.squeeze(1)                             # [B, H]
        pred = self.out_track(torch.cat([out, context], dim=1))  # [B, 3]
        return pred, h, c

    def forward(self, src, tgt=None, teacher_forcing_ratio=0.5):
        B = src.size(0)
        enc_out, h, c = self.encode(src)

        # 첫 디코더 입력: 마지막 인코더 입력의 dlat,dlng,dpres
        dec_inp = src[:, -1, :3]   # [B, 3]

        tgt_len = tgt.size(1) if tgt is not None else FUTURE_STEPS
        preds = []

        for t in range(tgt_len):
            pred, h, c = self.decode_step(dec_inp, h, c, enc_out)
            preds.append(pred.unsqueeze(1))
            # Teacher forcing
            if tgt is not None and torch.rand(1).item() < teacher_forcing_ratio:
                dec_inp = tgt[:, t, :]
            else:
                dec_inp = pred.detach()

        return torch.cat(preds, dim=1)   # [B, tgt_len, 3]


# ── 훈련 루프 ──────────────────────────────────────────────
def train_model(hidden_size: int, train_loader, val_loader):
    model = TyphoonSeq2Seq(hidden_size).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    criterion = nn.L1Loss()

    best_val_loss = float("inf")
    best_state    = None
    patience = 12
    no_improve = 0

    for epoch in range(1, EPOCHS + 1):
        # Train
        model.train()
        train_loss = 0.0
        for src, tgt in train_loader:
            src, tgt = src.to(DEVICE), tgt.to(DEVICE)
            tf_ratio = max(0.0, 0.8 - epoch / EPOCHS)   # teacher forcing 점감
            pred = model(src, tgt, teacher_forcing_ratio=tf_ratio)
            loss = criterion(pred, tgt)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item()
        train_loss /= len(train_loader)

        # Validate
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for src, tgt in val_loader:
                src, tgt = src.to(DEVICE), tgt.to(DEVICE)
                pred = model(src, tgt, teacher_forcing_ratio=0.0)
                val_loss += criterion(pred, tgt).item()
        val_loss /= len(val_loader)
        scheduler.step()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state    = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve    = 0
        else:
            no_improve += 1

        if epoch % 10 == 0 or epoch <= 3:
            print(f"  [h={hidden_size}] epoch {epoch:>3}/{EPOCHS}  "
                  f"train={train_loss:.4f}  val={val_loss:.4f}  "
                  f"best={best_val_loss:.4f}")

        if no_improve >= patience:
            print(f"  조기 종료 (epoch {epoch})")
            break

    model.load_state_dict(best_state)
    return model, best_val_loss


# ── 검증: km 오차 계산 ─────────────────────────────────────
def eval_km_error(models_list, val_loader):
    """앙상블 모델의 평균 위치 오차(km)를 계산."""
    errors = []
    for src, tgt in val_loader:
        src, tgt = src.to(DEVICE), tgt.to(DEVICE)
        preds = []
        for m in models_list:
            m.eval()
            with torch.no_grad():
                preds.append(m(src))   # tgt=None → FUTURE_STEPS 자동 사용
        ensemble = torch.stack(preds).mean(0)   # [B, L, 3]

        # dlat, dlng → 누적 위치
        for b in range(src.size(0)):
            start_lat = (src[b, -1, 3] * (LAT_MAX - LAT_MIN) + LAT_MIN).item()
            start_lng = (src[b, -1, 4] * (LNG_MAX - LNG_MIN) + LNG_MIN).item()

            pred_lats = [start_lat]
            pred_lngs = [start_lng]
            true_lats = [start_lat]
            true_lngs = [start_lng]

            for t in range(tgt.size(1)):
                pred_lats.append(pred_lats[-1] + ensemble[b, t, 0].item())
                pred_lngs.append(pred_lngs[-1] + ensemble[b, t, 1].item())
                true_lats.append(true_lats[-1] + tgt[b, t, 0].item())
                true_lngs.append(true_lngs[-1] + tgt[b, t, 1].item())

            # 6h(1스텝) 위치 오차만 사용 (1st step error)
            dlat = (pred_lats[1] - true_lats[1]) * 111.0
            dlng = (pred_lngs[1] - true_lngs[1]) * 111.0 * math.cos(math.radians(start_lat))
            errors.append(math.sqrt(dlat**2 + dlng**2))

        if len(errors) > 2000:
            break

    return float(np.mean(errors))


# ── 메인 ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("TyphoonPath LSTM Seq2Seq 훈련")
    print("=" * 60)

    typhoons = load_data()
    print(f"태풍 수: {len(typhoons):,}")

    print("[1] 시퀀스 생성...")
    seqs = build_sequences(typhoons)

    # 8:2 분할
    n_val = max(200, int(len(seqs) * 0.2))
    n_train = len(seqs) - n_val
    train_ds, val_ds = random_split(
        TyphoonSeqDataset(seqs), [n_train, n_val],
        generator=torch.Generator().manual_seed(42),
    )
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                              collate_fn=collate_fn, num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False,
                              collate_fn=collate_fn, num_workers=0)
    print(f"  훈련: {n_train:,}개  검증: {n_val:,}개")

    print(f"\n[2] 앙상블 훈련 ({len(HIDDEN_SIZES)}개 모델)...")
    trained_models = []
    for hs in HIDDEN_SIZES:
        print(f"\n  hidden_size={hs}")
        t0 = time.time()
        model, best_val = train_model(hs, train_loader, val_loader)
        elapsed = time.time() - t0
        print(f"  완료 — val_loss={best_val:.4f}  ({elapsed:.0f}s)")

        save_path = DATA_DIR / f"lstm_model_h{hs}.pt"
        torch.save(model.state_dict(), save_path)
        print(f"  저장: {save_path.name}")
        trained_models.append(model)

    print("\n[3] 앙상블 위치 오차 계산...")
    km_err = eval_km_error(trained_models, val_loader)
    print(f"  평균 6h 위치 오차: {km_err:.1f} km")

    meta = {
        "hidden_sizes": HIDDEN_SIZES,
        "past_steps":   PAST_STEPS,
        "future_steps": FUTURE_STEPS,
        "km_error_6h":  round(km_err, 1),
        "val_size":     n_val,
        "train_size":   n_train,
    }
    with open(DATA_DIR / "lstm_meta.json", "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"  메타 저장: lstm_meta.json")

    print("\n" + "=" * 60)
    print("✅ LSTM 훈련 완료!")
    print(f"   모델: lstm_model_h48.pt / h64.pt / h96.pt")
    print(f"   6h 오차: {km_err:.1f} km")
    print("=" * 60)


if __name__ == "__main__":
    main()
