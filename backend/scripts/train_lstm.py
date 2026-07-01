"""
TyphoonPath — LSTM Seq2Seq with Attention 훈련 스크립트 v2
===========================================================

[v2 개선사항 — 연구 기반]
1. Scheduled Sampling (Bengio et al., NeurIPS 2015)
   - 훈련 시 점점 더 모델 자신의 출력을 입력으로 사용
   - Exposure Bias(훈련-추론 불일치) 해소 → 장기 예측 안정화
   - 전략: linear decay  tf_ratio = max(0.0, 1.0 - epoch/EPOCHS)
     (초반엔 ground truth 많이, 후반엔 모델 자신의 출력 많이)

2. FUTURE_STEPS 40 → 60 (240h → 360h)
   - 추론 max_steps=80(480h)에 더 가깝게 훈련 커버리지 확장
   - 외삽 구간 480-360=120h로 단축 (기존 480-240=240h 대비 절반)

3. Physics-informed Auxiliary Loss
   - 논문: "Phase-based physics-informed Seq2Seq for typhoon prediction" (2025)
   - 베타 드리프트 제약: 저위도(lat<20) 태풍은 서북진해야 함
   - 기압 물리 제약: 일정 위도 이상에서는 기압이 오르는 방향(약화)이어야 함
   - 물리 제약 위반 시 penalty를 loss에 추가 (weight=0.1)

4. 다중 스텝 오차 가중 손실 (Multi-step Weighted Loss)
   - 초반 스텝(6h~48h)에 더 높은 가중치
   - 장기 예측보다 단기 예측 정확도를 우선 확보

모델 구조 (변경 없음)
---------------------
Encoder : LSTM(8 features × past 4 steps → hidden)
Decoder : LSTM + Bahdanau Attention (auto-regressive)
Ensemble: hidden_size = [48, 64, 96] → 3개 모델 평균 예측

입력 피처 (8차원)
  dlat, dlng, dpres  : 이동 벡터 + 기압 변화
  lat_norm, lng_norm, pres_norm : 정규화 위치/기압
  sin_month, cos_month : 계절 인코딩

레퍼런스
  - Bengio et al. (2015) "Scheduled Sampling for Sequence Prediction"
  - Kim et al. (2025) "Phase-based physics-informed Seq2Seq" ScienceDirect
  - IBTrACS WP 1951-2024 typhoons.json
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

# ── 하이퍼파라미터 ─────────────────────────────────────
PAST_STEPS    = 4    # 24h 이력 (고정)
FUTURE_STEPS  = 60   # v2: 360h → 추론 480h와의 갭 축소 (기존 40→240h)
HIDDEN_SIZES  = [48, 64, 96]
EPOCHS        = 100  # v2: 80→100 (Scheduled Sampling이 후반 에폭을 더 활용)
BATCH_SIZE    = 256
LR            = 0.001
PHYS_WEIGHT   = 0.1  # Physics-informed loss 가중치
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(f"디바이스: {DEVICE}")
print(f"설정: FUTURE_STEPS={FUTURE_STEPS}, EPOCHS={EPOCHS}, PHYS_WEIGHT={PHYS_WEIGHT}")


# ── 정규화 ─────────────────────────────────────────────
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
        self.data = sequences

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

                if abs(dlat) > 8 or abs(dlng) > 8:
                    valid = False; break

                src_feats.append(make_features(lat, lng, pres, dlat, dlng, dpres, month))
                prev_lat, prev_lng, prev_pres = lat, lng, pres

            if not valid or len(src_feats) < PAST_STEPS:
                skipped += 1; continue

            # ── 타겟 (미래 최대 FUTURE_STEPS) ──
            tgt_vecs = []
            p_lat  = float(track[start + PAST_STEPS - 1]["lat"])
            p_lng  = float(track[start + PAST_STEPS - 1]["lng"])
            p_pres = float(track[start + PAST_STEPS - 1].get("pressure") or 985)

            for j in range(start + PAST_STEPS,
                           min(start + PAST_STEPS + FUTURE_STEPS, len(track))):
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

            # 시작 위도 저장 (Physics Loss에 사용)
            start_lat = float(track[start + PAST_STEPS - 1]["lat"])

            src_t = torch.tensor(src_feats, dtype=torch.float32)    # [4, 8]
            tgt_t = torch.tensor(tgt_vecs, dtype=torch.float32)     # [N, 3]
            seqs.append((src_t, tgt_t, start_lat))

    print(f"  시퀀스: {len(seqs):,}개  건너뜀: {skipped:,}개")
    return seqs


def collate_fn(batch):
    """가변 길이 타겟을 min_len으로 트리밍하여 배치화."""
    srcs, tgts, lats = zip(*batch)
    min_len = min(t.size(0) for t in tgts)
    min_len = max(min_len, 4)
    src_batch = torch.stack(srcs)
    tgt_batch = torch.stack([t[:min_len] for t in tgts])
    lat_batch = torch.tensor(lats, dtype=torch.float32)
    return src_batch, tgt_batch, lat_batch


# ── 모델 ──────────────────────────────────────────────────
class BahdanauAttention(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.W1 = nn.Linear(hidden_size, hidden_size)
        self.W2 = nn.Linear(hidden_size, hidden_size)
        self.v  = nn.Linear(hidden_size, 1, bias=False)

    def forward(self, dec_hidden, enc_outputs):
        dec_exp = dec_hidden.unsqueeze(1).expand_as(enc_outputs)
        energy  = torch.tanh(self.W1(enc_outputs) + self.W2(dec_exp))
        scores  = self.v(energy).squeeze(-1)
        weights = torch.softmax(scores, dim=1)
        context = (weights.unsqueeze(-1) * enc_outputs).sum(dim=1)
        return context, weights


class TyphoonSeq2Seq(nn.Module):
    INPUT_SIZE = 8
    DEC_INPUT  = 3

    def __init__(self, hidden_size: int, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers  = num_layers

        self.encoder = nn.LSTM(
            self.INPUT_SIZE, hidden_size, num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.decoder = nn.LSTM(
            self.DEC_INPUT + hidden_size,
            hidden_size, num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.attention = BahdanauAttention(hidden_size)
        self.out_track = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 3),
        )

    def encode(self, src):
        enc_out, (h, c) = self.encoder(src)
        return enc_out, h, c

    def decode_step(self, dec_inp, h, c, enc_out):
        last_h = h[-1]
        context, _ = self.attention(last_h, enc_out)
        dec_in = torch.cat([dec_inp, context], dim=1).unsqueeze(1)
        out, (h, c) = self.decoder(dec_in, (h, c))
        out = out.squeeze(1)
        pred = self.out_track(torch.cat([out, context], dim=1))
        return pred, h, c

    def forward(self, src, tgt=None, teacher_forcing_ratio=0.5):
        """
        [v2] Scheduled Sampling 적용
        teacher_forcing_ratio: 각 스텝에서 ground truth를 쓸 확률
          - 훈련 초반: 높음 (1.0 → ground truth 위주)
          - 훈련 후반: 낮음 (0.0 → 자신의 예측 위주)
          → 추론 환경(ground truth 없음)에 점진적으로 적응
        """
        B = src.size(0)
        enc_out, h, c = self.encode(src)
        dec_inp = src[:, -1, :3]
        tgt_len = tgt.size(1) if tgt is not None else FUTURE_STEPS
        preds = []

        for t in range(tgt_len):
            pred, h, c = self.decode_step(dec_inp, h, c, enc_out)
            preds.append(pred.unsqueeze(1))

            # [핵심] Scheduled Sampling:
            # 배치의 각 샘플마다 독립적으로 ground truth vs 예측값 선택
            if tgt is not None and teacher_forcing_ratio > 0.0:
                use_gt = torch.rand(B, device=src.device) < teacher_forcing_ratio
                gt = tgt[:, t, :]                           # [B, 3]
                pred_d = pred.detach()                      # [B, 3]
                dec_inp = torch.where(use_gt.unsqueeze(1), gt, pred_d)
            else:
                dec_inp = pred.detach()

        return torch.cat(preds, dim=1)   # [B, tgt_len, 3]


# ── Physics-informed Loss ─────────────────────────────────
def physics_penalty(pred_seq, start_lats):
    """
    물리 제약 위반 시 패널티 반환.

    제약 1 (베타 드리프트): 저위도(lat<20°N) 태풍은 서진(dlng<0)해야 함
                            → dlng > +0.5 이면 패널티
    제약 2 (기압 약화): 위도>30°N에서는 기압이 올라야 함(dpres>0)
                       → dpres < -0.5 이면 패널티 (이상 강화)

    pred_seq: [B, T, 3]  (dlat, dlng, dpres)
    start_lats: [B]      (시작 위도)
    """
    penalty = torch.tensor(0.0, device=pred_seq.device)
    B = pred_seq.size(0)

    for b in range(B):
        lat = start_lats[b].item()

        # 제약 1: 저위도 서진
        if lat < 20.0:
            dlng = pred_seq[b, :8, 1]               # 첫 48h (8스텝)
            east_violation = torch.relu(dlng - 0.5) # 0.5° 이상 동진
            penalty = penalty + east_violation.mean()

        # 제약 2: 고위도 약화
        if lat > 30.0:
            dpres = pred_seq[b, :12, 2]             # 첫 72h (12스텝)
            intens_violation = torch.relu(-dpres - 0.5)  # 이상 강화
            penalty = penalty + intens_violation.mean()

    return penalty / max(B, 1)


# ── 다중 스텝 가중 손실 ────────────────────────────────────
def weighted_step_loss(criterion, pred, tgt):
    """
    단기 스텝에 더 높은 가중치를 부여하는 MAE Loss.
    가중치: step 0~3 → 2.0, step 4~11 → 1.5, step 12~ → 1.0
    """
    T = pred.size(1)
    weights = []
    for t in range(T):
        if t < 4:
            weights.append(2.0)
        elif t < 12:
            weights.append(1.5)
        else:
            weights.append(1.0)
    w = torch.tensor(weights, device=pred.device).unsqueeze(0).unsqueeze(-1)  # [1, T, 1]
    loss = (torch.abs(pred - tgt) * w).mean()
    return loss


# ── 훈련 루프 ──────────────────────────────────────────────
def train_model(hidden_size: int, train_loader, val_loader):
    model = TyphoonSeq2Seq(hidden_size).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    criterion = nn.L1Loss()

    best_val_loss = float("inf")
    best_state    = None
    patience      = 15   # v2: 12→15 (에폭 늘었으므로)
    no_improve    = 0

    for epoch in range(1, EPOCHS + 1):
        # [v2] Scheduled Sampling: 선형 감소
        # epoch 1 → tf=1.0 (ground truth만)
        # epoch 50 → tf=0.5
        # epoch 100 → tf=0.0 (모델 자신의 출력만)
        tf_ratio = max(0.0, 1.0 - (epoch - 1) / (EPOCHS - 1))

        # Train
        model.train()
        train_loss = 0.0
        for src, tgt, start_lats in train_loader:
            src, tgt = src.to(DEVICE), tgt.to(DEVICE)
            start_lats = start_lats.to(DEVICE)

            pred = model(src, tgt, teacher_forcing_ratio=tf_ratio)

            # 기본 MAE (다중 스텝 가중)
            main_loss = weighted_step_loss(criterion, pred, tgt)

            # Physics-informed penalty
            phys_loss = physics_penalty(pred, start_lats)

            loss = main_loss + PHYS_WEIGHT * phys_loss

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += main_loss.item()   # 비교용으로 main_loss만 기록

        train_loss /= len(train_loader)

        # Validate (teacher forcing 없이 — 실제 추론 환경 시뮬레이션)
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for src, tgt, _ in val_loader:
                src, tgt = src.to(DEVICE), tgt.to(DEVICE)
                pred = model(src, tgt, teacher_forcing_ratio=0.0)  # 추론 모드
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
                  f"tf={tf_ratio:.2f}  train={train_loss:.4f}  "
                  f"val={val_loss:.4f}  best={best_val_loss:.4f}")

        if no_improve >= patience:
            print(f"  조기 종료 (epoch {epoch}, patience={patience})")
            break

    model.load_state_dict(best_state)
    return model, best_val_loss


# ── 검증: km 오차 계산 ─────────────────────────────────────
def eval_km_error(models_list, val_loader):
    """앙상블 모델의 평균 위치 오차(km)를 계산 — 6h / 24h / 72h 각각."""
    errors_6h, errors_24h, errors_72h = [], [], []

    for src, tgt, _ in val_loader:
        src, tgt = src.to(DEVICE), tgt.to(DEVICE)
        preds = []
        for m in models_list:
            m.eval()
            with torch.no_grad():
                preds.append(m(src, teacher_forcing_ratio=0.0))
        ensemble = torch.stack(preds).mean(0)   # [B, L, 3]

        for b in range(src.size(0)):
            start_lat = (src[b, -1, 3] * (LAT_MAX - LAT_MIN) + LAT_MIN).item()
            start_lng = (src[b, -1, 4] * (LNG_MAX - LNG_MIN) + LNG_MIN).item()

            pred_lats = [start_lat]; pred_lngs = [start_lng]
            true_lats = [start_lat]; true_lngs = [start_lng]

            for t in range(tgt.size(1)):
                pred_lats.append(pred_lats[-1] + ensemble[b, t, 0].item())
                pred_lngs.append(pred_lngs[-1] + ensemble[b, t, 1].item())
                true_lats.append(true_lats[-1] + tgt[b, t, 0].item())
                true_lngs.append(true_lngs[-1] + tgt[b, t, 1].item())

            def km_err(step):
                if step >= len(pred_lats): return None
                dlat = (pred_lats[step] - true_lats[step]) * 111.0
                dlng = (pred_lngs[step] - true_lngs[step]) * 111.0 * math.cos(math.radians(start_lat))
                return math.sqrt(dlat**2 + dlng**2)

            e6  = km_err(1)
            e24 = km_err(4)
            e72 = km_err(12)
            if e6  is not None: errors_6h.append(e6)
            if e24 is not None: errors_24h.append(e24)
            if e72 is not None: errors_72h.append(e72)

        if len(errors_6h) > 2000:
            break

    return (
        float(np.mean(errors_6h))  if errors_6h  else 0.0,
        float(np.mean(errors_24h)) if errors_24h else 0.0,
        float(np.mean(errors_72h)) if errors_72h else 0.0,
    )


# ── 메인 ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("TyphoonPath LSTM Seq2Seq 훈련 v2")
    print("  개선: Scheduled Sampling + Physics Loss + 60스텝")
    print("=" * 60)

    typhoons = load_data()
    print(f"태풍 수: {len(typhoons):,}")

    print("[1] 시퀀스 생성...")
    seqs = build_sequences(typhoons)

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
        print(f"  완료 — val_loss={best_val:.4f}  ({elapsed:.0f}s / {elapsed/60:.1f}min)")

        save_path = DATA_DIR / f"lstm_model_h{hs}.pt"
        torch.save(model.state_dict(), save_path)
        print(f"  저장: {save_path.name}")
        trained_models.append(model)

    print("\n[3] 앙상블 위치 오차 계산 (6h / 24h / 72h)...")
    km6, km24, km72 = eval_km_error(trained_models, val_loader)
    print(f"  6h  오차: {km6:.1f} km  (목표: <15 km)")
    print(f"  24h 오차: {km24:.1f} km  (목표: <60 km)")
    print(f"  72h 오차: {km72:.1f} km  (목표: <180 km)")

    meta = {
        "hidden_sizes":  HIDDEN_SIZES,
        "past_steps":    PAST_STEPS,
        "future_steps":  FUTURE_STEPS,
        "km_error_6h":   round(km6,  1),
        "km_error_24h":  round(km24, 1),
        "km_error_72h":  round(km72, 1),
        "val_size":      n_val,
        "train_size":    n_train,
        "improvements":  ["scheduled_sampling", "physics_loss", "weighted_step_loss",
                          "future_steps_60", "epochs_100"],
    }
    with open(DATA_DIR / "lstm_meta.json", "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"  메타 저장: lstm_meta.json")

    print("\n" + "=" * 60)
    print("✅ LSTM 훈련 v2 완료!")
    print(f"   모델: lstm_model_h48.pt / h64.pt / h96.pt")
    print(f"   6h: {km6:.1f} km  24h: {km24:.1f} km  72h: {km72:.1f} km")
    print("=" * 60)


if __name__ == "__main__":
    main()
