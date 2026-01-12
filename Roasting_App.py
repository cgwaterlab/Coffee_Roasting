import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time  # 시간 계산용

# === 추가 import ===
import numpy as np
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# =========================================================
# 로고 설정 (✅ 프로젝트 폴더에 pco_logo.png 넣으면 적용)
# =========================================================
LOGO_PATH = "pco_logo.png"  # app.py와 같은 폴더에 두세요.

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Roasting Analysis Center", layout="wide", page_icon="☕")

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'
ASSET_DIR = "roast_assets"
os.makedirs(ASSET_DIR, exist_ok=True)

# --- 함수 모음 ---
def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"

def get_dtr_feedback(dtr):
    """DTR 수치에 따른 맛 평가 멘트"""
    if dtr < 10:
        return "⚠️ 언더 디벨롭 (Under Developed): 풋내나 떫은 맛이 날 수 있어요. 시간을 조금 더 늘려보세요."
    elif dtr <= 15:
        return "🍓 노르딕/라이트 (Light): 꽃향기와 화사한 산미, 차(Tea) 같은 깔끔함이 특징이에요."
    elif dtr <= 20:
        return "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 황금 비율이에요! (추천)"
    elif dtr <= 25:
        return "🍫 미디엄 다크 (Medium Dark): 산미는 줄고 바디감과 초콜릿 향이 살아나요."
    else:
        return "🔥 다크 (Dark): 묵직한 바디감, 스모키함, 쌉쌀한 맛이 강조돼요."

def format_mmss(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"

def load_and_standardize_csv(file, file_name_fallback):
    try:
        file.seek(0)
        raw = file.read()
        if isinstance(raw, str):
            content = raw
        else:
            try:
                content = raw.decode("utf-8-sig")
            except:
                content = raw.decode("cp949", errors="ignore")

        lines = content.splitlines()
        candidates = [",", "\t", ";"]
        header_row_idx = None
        delimiter = ","
        extracted_id = None

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            # 기존 로직 유지 (원두/bean 라인에서 id 추출 시도)
            if ("원두" in line) or ("bean" in line.lower()):
                parts = [p.strip() for p in re.split(r"[,\t;]", line)]
                if len(parts) > 1 and parts[1]:
                    extracted_id = parts[1]

            for d in candidates:
                cells = [c.strip().lower() for c in line.split(d)]
                if any(("time" in c) or ("시간" in c) for c in cells) and any(("temp" in c) or ("온도" in c) for c in cells):
                    header_row_idx = i
                    delimiter = d
                    break
            if header_row_idx is not None:
                break

        if header_row_idx is None:
            return None

        data_text = "\n".join(lines[header_row_idx:])
        rows = list(csv.reader(io.StringIO(data_text), delimiter=delimiter))
        if not rows:
            return None

        header = [str(c).strip() for c in rows[0]]
        while header and header[-1] == "":
            header.pop()
        expected = len(header)

        cleaned = []
        for r in rows[1:]:
            r = [str(c).strip() for c in r]
            if not any(r):
                continue
            if len(r) > expected:
                r = r[:expected]
            elif len(r) < expected:
                r = r + [""] * (expected - len(r))
            cleaned.append(r)

        df = pd.DataFrame(cleaned, columns=header)
        df.columns = [str(c).strip() for c in df.columns]

        col_map = {}
        for col in df.columns:
            c = col.lower()
            if ("time" in c) or ("시간" in c):
                col_map[col] = "Time"
            elif ("temp" in c) or ("온도" in c):
                col_map[col] = "Temp"
            elif ("gas" in c) or ("가스" in c):
                col_map[col] = "Gas"
            elif ("event" in c) or ("이벤트" in c):
                col_map[col] = "Event"

        df.rename(columns=col_map, inplace=True)

        if ("Time" not in df.columns) or ("Temp" not in df.columns):
            return None

        out = pd.DataFrame()
        out["Time"] = pd.to_numeric(df["Time"], errors="coerce")
        out["Temp"] = pd.to_numeric(df["Temp"], errors="coerce")
        out["Gas"] = pd.to_numeric(df["Gas"], errors="coerce").fillna(0) if "Gas" in df.columns else 0

        if "Event" in df.columns:
            out["Event"] = df["Event"].fillna("").astype(str)
            out.loc[out["Event"].str.lower() == "nan", "Event"] = ""
        else:
            out["Event"] = ""

        out = out.dropna(subset=["Time", "Temp"])
        out["Roast_ID"] = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        return out
    except:
        return None

def get_template_csv():
    return """파일 이름,Sample_01
날짜,2026-Jan-01
원두 이름,Geisha
로스터 이름,Sample Roaster
방식,드럼 (Drum)
결과무게,215
비고,템플릿

Time(sec),Temp(C),Gas,Event
0,200,0.0,Preheat
30,200,0.5,Charge
60,90,5.0,TP
300,150,4.0,Yellowing
540,192,2.0,1C Start
630,205,0,Drop
"""

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "first", "pop"]) and ("end" not in e) and ("2" not in e)
    is_2c = any(k in e for k in ["2c", "2nd", "second"])
    return is_1c, is_2c

def is_drop_event(e: str) -> bool:
    if not e:
        return False
    s = str(e).lower().strip()
    return ("drop" in s) or ("배출" in s)

# =========================================================
# ✅ (추가) 이미지/Agtron/리포트 유틸
# =========================================================
def pil_from_upload(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        img = Image.open(uploaded_file).convert("RGB")
        return img
    except:
        return None

def clamp_roi(x, y, w, h, W, H):
    x = int(max(0, min(x, W-1)))
    y = int(max(0, min(y, H-1)))
    w = int(max(1, min(w, W-x)))
    h = int(max(1, min(h, H-y)))
    return x, y, w, h

def srgb_to_linear(u):
    # u: 0..1
    return np.where(u <= 0.04045, u / 12.92, ((u + 0.055) / 1.055) ** 2.4)

def rgb_to_lab(rgb01):
    """
    rgb01: (...,3) float in 0..1 (sRGB)
    return Lab (...,3), L in 0..100
    """
    rgb_lin = srgb_to_linear(rgb01)

    # sRGB D65 -> XYZ
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ], dtype=np.float64)

    shape = rgb_lin.shape
    flat = rgb_lin.reshape(-1, 3)
    xyz = flat @ M.T

    # Reference white D65
    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
    x = xyz[:, 0] / Xn
    y = xyz[:, 1] / Yn
    z = xyz[:, 2] / Zn

    def f(t):
        eps = 216 / 24389  # ~0.008856
        kappa = 24389 / 27 # ~903.3
        return np.where(t > eps, np.cbrt(t), (kappa * t + 16) / 116)

    fx, fy, fz = f(x), f(y), f(z)
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)

    lab = np.stack([L, a, b], axis=1).reshape(*shape[:-1], 3)
    return lab

def apply_white_balance(img01, white_roi, target=0.92):
    """
    img01: HxWx3 float 0..1
    white_roi: (x,y,w,h)
    """
    x, y, w, h = white_roi
    patch = img01[y:y+h, x:x+w, :]
    mean_rgb = patch.reshape(-1, 3).mean(axis=0) + 1e-6
    scale = target / mean_rgb
    out = img01 * scale
    return np.clip(out, 0, 1), mean_rgb, scale

def estimate_agtron_from_photo(pil_img, bean_roi, white_roi, gain=1.2, offset=5.0):
    """
    아주 러프한 '사진 기반' 추정(베타).
    - white_roi로 화이트밸런스 보정
    - bean_roi 평균 L* 계산
    - Agtron ≈ gain*L* + offset
    """
    img = np.asarray(pil_img).astype(np.float64) / 255.0
    H, W = img.shape[:2]
    bx, by, bw, bh = clamp_roi(*bean_roi, W, H)
    wx, wy, ww, wh = clamp_roi(*white_roi, W, H)

    balanced, white_mean, wb_scale = apply_white_balance(img, (wx, wy, ww, wh), target=0.92)
    bean_patch = balanced[by:by+bh, bx:bx+bw, :]
    lab = rgb_to_lab(bean_patch)
    L_mean = float(lab[..., 0].mean())
    agtron = float(np.clip(gain * L_mean + offset, 0, 100))
    return {
        "agtron_est": agtron,
        "L_mean": L_mean,
        "white_mean_rgb01": white_mean.tolist(),
        "wb_scale": wb_scale.tolist(),
        "bean_roi": (bx, by, bw, bh),
        "white_roi": (wx, wy, ww, wh),
    }

def save_image_bytes(pil_img, roast_id, kind="photo"):
    """
    로컬 파일 저장(배포 환경에 따라 영구 보장 X).
    """
    if pil_img is None:
        return None
    safe_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(roast_id))[:80]
    fn = f"{safe_id}_{kind}_{int(time.time())}.jpg"
    path = os.path.join(ASSET_DIR, fn)
    pil_img.save(path, format="JPEG", quality=92)
    return path

def avg_ror_in_window(ror_df, t0, t1):
    w = ror_df[(ror_df["t_mid"] >= t0) & (ror_df["t_mid"] <= t1)]
    if w.empty:
        return None
    return float(w["ror_c_per_min"].mean())

def build_ror_series(df_points):
    """
    df_points: Time(sec), Temp(C) 최소 2포인트
    return DataFrame[t_mid, ror_c_per_min]
    """
    df = df_points.sort_values("Time").reset_index(drop=True).copy()
    rows = []
    for i in range(1, len(df)):
        t0, t1 = float(df.loc[i-1, "Time"]), float(df.loc[i, "Time"])
        T0, T1 = float(df.loc[i-1, "Temp"]), float(df.loc[i, "Temp"])
        dt_min = (t1 - t0) / 60.0
        if dt_min <= 0:
            continue
        ror = (T1 - T0) / dt_min
        rows.append({"t_mid": (t0 + t1) / 2.0, "ror_c_per_min": ror, "dt_sec": (t1 - t0)})
    return pd.DataFrame(rows)

def compute_phase_times(df_points):
    """
    이벤트 기반으로 Drying/Maillard/Dev 구간 계산
    - Yellowing: 'Yellowing' 포함
    - 1C Start: check_is_crack 첫 1C
    - Drop: drop 이벤트 또는 마지막 time
    """
    df = df_points.sort_values("Time").reset_index(drop=True).copy()

    def find_time_by_pred(pred):
        for _, r in df.iterrows():
            e = str(r.get("Event", ""))
            if pred(e):
                return float(r["Time"])
        return None

    t_y = find_time_by_pred(lambda e: "yellow" in str(e).lower() or "옐로" in str(e))
    t_1c = None
    for _, r in df.iterrows():
        if check_is_crack(str(r.get("Event", "")))[0]:
            t_1c = float(r["Time"])
            break
    t_drop = None
    for _, r in df.iterrows():
        if is_drop_event(str(r.get("Event", ""))):
            t_drop = float(r["Time"])
    if t_drop is None and not df.empty:
        t_drop = float(df["Time"].max())

    t0 = 0.0 if df.empty else float(df["Time"].min())
    total = None if t_drop is None else (t_drop - t0)

    drying = maillard = dev = None
    if total is not None:
        if t_y is not None:
            drying = t_y - t0
        if (t_y is not None) and (t_1c is not None):
            maillard = t_1c - t_y
        if (t_1c is not None) and (t_drop is not None):
            dev = t_drop - t_1c

    return {
        "t_yellow": t_y,
        "t_1c": t_1c,
        "t_drop": t_drop,
        "total_sec": total,
        "drying_sec": drying,
        "maillard_sec": maillard,
        "dev_sec": dev,
    }

def compute_qc_summary(df_points, green_weight_g=None, output_weight_g=None, dtr_pct=None):
    """
    내부 디벨롭 힌트:
    - color spread(whole vs ground)은 UI에서 입력받아 계산
    - 여기서는 RoR 크래시/플릭/정체 등 간단 휴리스틱
    - weight loss(%) 계산
    """
    df = df_points.sort_values("Time").reset_index(drop=True).copy()
    phases = compute_phase_times(df)
    ror_df = build_ror_series(df) if len(df) >= 2 else pd.DataFrame()

    wl_pct = None
    if green_weight_g and output_weight_g and green_weight_g > 0:
        wl_pct = float((green_weight_g - output_weight_g) / green_weight_g * 100.0)

    # RoR crash around 1C (간단 버전)
    crash_flag = None
    flick_flag = None
    stall_flag = None
    crash_ratio = None
    ror_before = ror_after = None

    t_1c = phases.get("t_1c", None)
    t_drop = phases.get("t_drop", None)

    if (t_1c is not None) and (not ror_df.empty):
        ror_before = avg_ror_in_window(ror_df, max(0, t_1c - 90), max(0, t_1c - 20))
        ror_after  = avg_ror_in_window(ror_df, t_1c + 10, t_1c + 90)

        if (ror_before is not None) and (ror_after is not None) and (ror_before > 0):
            crash_ratio = ror_after / ror_before
            crash_flag = crash_ratio < 0.55  # 경험적 임계값(조정 가능)

        # stall: 1C 이후 RoR이 매우 낮은 구간이 길면
        if t_drop is not None:
            w = ror_df[(ror_df["t_mid"] >= t_1c + 10) & (ror_df["t_mid"] <= t_drop)]
            if not w.empty:
                low = w[w["ror_c_per_min"] < 1.0]
                stall_flag = (low["dt_sec"].sum() >= 45.0)  # 누적 45초 이상 매우 낮은 RoR

    # flick: 종료 직전 RoR이 급상승
    if (not ror_df.empty) and len(ror_df) >= 3:
        last = float(ror_df.iloc[-1]["ror_c_per_min"])
        prev = float(ror_df.iloc[-2]["ror_c_per_min"])
        flick_flag = (last > prev + 3.0)

    return {
        "phases": phases,
        "wl_pct": wl_pct,
        "dtr_pct": dtr_pct,
        "ror_before_1c": ror_before,
        "ror_after_1c": ror_after,
        "crash_ratio": crash_ratio,
        "crash_flag": crash_flag,
        "flick_flag": flick_flag,
        "stall_flag": stall_flag,
    }

def build_pdf_report(
    roast_id,
    meta_dict,
    roast_curve_png_bytes,
    roast_photo_pil=None,
):
    """
    A4 한 장 PDF 생성
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # 타이틀
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, H - 40, f"Roast Report: {roast_id}")

    # 메타 텍스트
    c.setFont("Helvetica", 10)
    y = H - 65
    for k, v in meta_dict.items():
        c.drawString(36, y, f"{k}: {v}")
        y -= 14
        if y < 360:
            break

    # 그래프 이미지
    if roast_curve_png_bytes:
        img_reader = ImageReader(io.BytesIO(roast_curve_png_bytes))
        c.drawImage(img_reader, 36, 165, width=W-72, height=180, preserveAspectRatio=True, anchor='c')

    # 사진(선택)
    if roast_photo_pil is not None:
        photo_buf = io.BytesIO()
        roast_photo_pil.save(photo_buf, format="JPEG", quality=92)
        photo_reader = ImageReader(io.BytesIO(photo_buf.getvalue()))
        c.drawImage(photo_reader, 36, 36, width=220, height=110, preserveAspectRatio=True, anchor='c')
        c.setFont("Helvetica", 9)
        c.drawString(36, 150, "Roasted coffee photo")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# =========================================================
# 사이드바
# =========================================================
# ✅ 페루 국기 대신 로고 이미지 표시
if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, use_container_width=True)
    st.sidebar.markdown("### PERU COFFEE ORIGINS")
else:
    st.sidebar.markdown("## PERU COFFEE ORIGINS")
    st.sidebar.caption("로고를 표시하려면 프로젝트 폴더에 pco_logo.png를 추가하세요.")

st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**\n\n지속 가능한 커피 문화를 위해 최고의 농장과 함께합니다.")

mode = st.sidebar.radio(
    "모드 선택 (Mode)",
    ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"],
    index=0
)

c1, c2 = st.sidebar.columns(2)
with c1:
    st.link_button("🛍️ 스마트\n스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with c2:
    st.link_button("📷 Instagram", "https://instagram.com/perucoffee.origins", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("🛠️ 유틸리티")
c3, c4 = st.sidebar.columns(2)
with c3:
    st.download_button("📥 파일\n템플릿", get_template_csv().encode('utf-8-sig'), "template.csv", "text/csv", use_container_width=True)
with c4:
    st.link_button("⚡ Web\nRoasting\nLogger", "https://roastinglog.netlify.app/", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("📂 레퍼런스 센터")

all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns:
            all_history.append(db_df)
    except:
        pass

uploaded_files = st.sidebar.file_uploader("로스팅 기록 파일 업로드", accept_multiple_files=True, type=['csv'])
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None:
            all_history.append(pdf)

full_df = pd.DataFrame()
if all_history:
    full_df = pd.concat(all_history, ignore_index=True)

selected_ids_analysis = []
reference_id_roasting = None
is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_manual_mode = (mode == "🔥 로스팅 (Manual)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

# =========================================================
# ✅ 세션 상태 (추가: Agtron/사진/QC)
# =========================================================
if 'points' not in st.session_state:
    st.session_state.points = []
if 'start_time' not in st.session_state:
    st.session_state.start_time = None
if 'timer_state' not in st.session_state:
    st.session_state.timer_state = "idle"  # idle / running / stopped
if 'stop_elapsed' not in st.session_state:
    st.session_state.stop_elapsed = None

# 추가 상태
if 'agtron_whole' not in st.session_state:
    st.session_state.agtron_whole = None
if 'agtron_ground' not in st.session_state:
    st.session_state.agtron_ground = None
if 'agtron_est' not in st.session_state:
    st.session_state.agtron_est = None
if 'roast_photo_path' not in st.session_state:
    st.session_state.roast_photo_path = None
if 'roast_photo_pil' not in st.session_state:
    st.session_state.roast_photo_pil = None
if 'qc_summary' not in st.session_state:
    st.session_state.qc_summary = None

# =========================================================
# 3. 모드별 로직
# =========================================================
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids_analysis = st.sidebar.multiselect(f"비교할 그래프 선택 ({len(uids)}개)", uids)
    else:
        st.info("데이터가 없습니다. CSV 파일을 업로드하세요.")

else:
    st.title("🔥 Coffee Roasting Log V1.0")

    # 레퍼런스 선택
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_options = ["(선택 안 함)"] + uids
        selected_ref = st.sidebar.selectbox("📉 배경 레퍼런스 선택 (Single Reference)", ref_options)
        if selected_ref != "(선택 안 함)":
            reference_id_roasting = selected_ref

    # ✅ 셋업에 로스터/방식 추가
    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        intl_date = get_intl_date_str()

        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1:
            bean_name = st.text_input("원두 이름 (Bean Name)", value="Geisha")
        with r1c2:
            roast_id = st.text_input("ID", value=f"{bean_name}_{intl_date}")
        with r1c3:
            roaster_name = st.text_input("로스터 이름 (Roaster Name)", value="")
        with r1c4:
            method = st.selectbox(
                "방식 (Method)",
                ["드럼 (Drum)", "열풍 (Hot Air)", "하이브리드 (Hybrid)", "직화 (Direct Fire)", "기타 (Other)"],
                index=0
            )

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            initial_temp = st.number_input("투입온도 (Charge Temp, ℃)", min_value=0, max_value=300, value=200, step=10)
        with r2c2:
            green_weight = st.number_input("생두 무게 (Green Weight, g)", 250.0)

    EVT = ["예열(Preheat)", "Charge", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"]

    # -----------------------------------------------------
    # Auto Timer
    # -----------------------------------------------------
    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")

        t_col1, t_col2, t_col3 = st.columns([1, 3, 1])
        with t_col1:
            if st.session_state.timer_state == "idle":
                if st.button("▶️ START (시작)", type="primary"):
                    st.session_state.start_time = time.time()
                    st.session_state.timer_state = "running"
                    st.session_state.stop_elapsed = None

                    # ✅ 시작과 동시에 예열(Preheat) 자동 기록 (Time=0)
                    st.session_state.points = [{
                        "Time": 0,
                        "Temp": int(initial_temp),
                        "Gas": 0.0,
                        "Event": "예열(Preheat)",
                        "Roast_ID": roast_id
                    }]

                    # ✅ Agtron/QC 초기화
                    st.session_state.agtron_whole = None
                    st.session_state.agtron_ground = None
                    st.session_state.agtron_est = None
                    st.session_state.roast_photo_path = None
                    st.session_state.roast_photo_pil = None
                    st.session_state.qc_summary = None

                    st.rerun()

            else:
                if st.button("⏹️ RESET (초기화)"):
                    st.session_state.start_time = None
                    st.session_state.timer_state = "idle"
                    st.session_state.stop_elapsed = None
                    st.session_state.points = []

                    # ✅ Agtron/QC 초기화
                    st.session_state.agtron_whole = None
                    st.session_state.agtron_ground = None
                    st.session_state.agtron_est = None
                    st.session_state.roast_photo_path = None
                    st.session_state.roast_photo_pil = None
                    st.session_state.qc_summary = None

                    st.rerun()

        def get_elapsed_now():
            if st.session_state.timer_state == "stopped" and st.session_state.stop_elapsed is not None:
                return int(st.session_state.stop_elapsed)
            if st.session_state.timer_state == "running" and st.session_state.start_time is not None:
                return int(time.time() - st.session_state.start_time)
            return 0

        elapsed = get_elapsed_now()
        with t_col2:
            st.metric("경과 시간", format_mmss(elapsed))

        with t_col3:
            # 화면 표시 업데이트용 (누르면 rerun)
            if st.session_state.timer_state == "running":
                if st.button("↻ 갱신"):
                    st.rerun()

        if st.session_state.timer_state == "stopped":
            st.info("✅ Drop이 기록되어 타이머가 정지되었습니다. (다시 시작하려면 RESET)")

        can_record = (st.session_state.timer_state == "running")

        c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 2, 1])
        with c1:
            st.text_input("현재 시간(표시) (Now)", value=format_mmss(elapsed), disabled=True)

        with c2:
            default_temp = int(st.session_state.points[-1]["Temp"]) if st.session_state.points else int(initial_temp)
            temp = st.number_input("온도 (Temp)", 0, 300, default_temp, disabled=not can_record, key="auto_temp")

        with c3:
            last_gas = float(st.session_state.points[-1]["Gas"]) if st.session_state.points else 0.0
            gas = st.number_input("가스 (Gas)", 0.0, 15.0, last_gas, step=0.1, disabled=not can_record, key="auto_gas")

        with c4:
            evt = st.selectbox("이벤트 (Event)", ["기록"] + EVT, disabled=not can_record, key="auto_evt")

        with c5:
            st.write("")
            st.write("")
            if st.button("기록 (Record)", type="primary", use_container_width=True, disabled=not can_record):
                rec_time = int(time.time() - st.session_state.start_time)
                chosen_evt = evt if evt != "기록" else None

                st.session_state.points.append({
                    "Time": rec_time,
                    "Temp": temp,
                    "Gas": gas,
                    "Event": chosen_evt,
                    "Roast_ID": roast_id
                })

                # ✅ Drop 기록 시 타이머 정지
                if is_drop_event(chosen_evt):
                    st.session_state.timer_state = "stopped"
                    st.session_state.stop_elapsed = rec_time

                st.rerun()

        # ✅ 단계별 기록(고정) 타임라인 표시
        if st.session_state.points:
            dfp = pd.DataFrame(st.session_state.points).sort_values("Time").reset_index(drop=True)
            ev = dfp[dfp["Event"].notna() & (dfp["Event"].astype(str).str.strip() != "")]
            if not ev.empty:
                timeline = ev[["Event", "Time"]].copy()
                timeline["Time(mm:ss)"] = timeline["Time"].apply(format_mmss)
                timeline["Δprev(sec)"] = timeline["Time"].diff().fillna(0).astype(int)
                st.markdown("##### ⏱️ 단계 타임라인 (Timeline)")
                st.dataframe(timeline[["Event", "Time(mm:ss)", "Time", "Δprev(sec)"]], use_container_width=True)

    # -----------------------------------------------------
    # Manual
    # -----------------------------------------------------
    else:
        st.subheader("2. 실시간 기록 (Manual Input)")
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2, 1])
        with c1:
            m = st.number_input("분 (Min)", 0, 60, 0)
            s = st.number_input("초 (Sec)", 0, 59, 0)
            t_sec = m * 60 + s
        with c2:
            temp = st.number_input("온도 (Temp)", 0, 300, int(initial_temp))
        with c3:
            gas = st.number_input("가스 (Gas)", 0.0, 15.0, 0.0, step=0.1)
        with c4:
            evt = st.selectbox("이벤트 (Event)", ["기록"] + EVT)
        with c5:
            st.write("")
            st.write("")
            if st.button("추가 (Add)", type="primary", use_container_width=True):
                st.session_state.points.append({
                    "Time": t_sec, "Temp": temp, "Gas": gas,
                    "Event": evt if evt != "기록" else None, "Roast_ID": roast_id
                })

    # 공통 데이터 에디터
    if st.session_state.points:
        st.markdown("##### 📝 데이터 수정 (Edit)")
        edited = st.data_editor(
            pd.DataFrame(st.session_state.points),
            num_rows="dynamic",
            use_container_width=True,
            key="editor",
            column_config={"Event": st.column_config.SelectboxColumn("이벤트 (Event)", options=EVT)}
        )
        if not pd.DataFrame(st.session_state.points).equals(edited):
            st.session_state.points = edited.to_dict('records')

            # Drop이 에디터에서 추가되면 타이머도 정지 상태로 맞춤
            df_tmp = pd.DataFrame(st.session_state.points).sort_values("Time")
            drop_rows = df_tmp[df_tmp["Event"].astype(str).apply(is_drop_event)]
            if not drop_rows.empty and st.session_state.timer_state != "idle":
                st.session_state.timer_state = "stopped"
                st.session_state.stop_elapsed = int(drop_rows["Time"].max())
            st.rerun()

# =========================================================
# 4. 통합 그래프
# =========================================================
st.write("---")
fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx()
ax_ror = ax1.twinx()
ax_ror.set_ylim(0, 150)
ax_ror.axis('off')

def plot_roast_data(ax_temp, ax_gas, ax_ror_bar, df, color_temp, color_gas, label_prefix, is_main=False, show_ror=False):
    t_1c, t_2c, idx_1c = None, None, None
    for i, row in df.iterrows():
        e = str(row['Event']).lower()
        if not e or e == "nan":
            continue
        is_1c_evt, is_2c_evt = check_is_crack(e)
        if is_1c_evt and t_1c is None:
            t_1c = row['Time']
            idx_1c = i
        if is_2c_evt and t_2c is None:
            t_2c = row['Time']

    final_c_temp = color_temp if (is_main or is_analysis_mode) else "#bdc3c7"
    final_c_gas = color_gas if (is_main or is_analysis_mode) else "#bdc3c7"
    line_style = '-' if (is_main or is_analysis_mode) else '--'
    alpha_val = 0.9 if is_main else 0.7

    if idx_1c is not None and (is_main or is_analysis_mode):
        ax_temp.plot(df.iloc[:idx_1c+1]['Time'], df.iloc[:idx_1c+1]['Temp'], marker='o', markersize=6,
                     color=final_c_temp, linewidth=2, label=label_prefix)
        ax_temp.plot(df.iloc[idx_1c:]['Time'], df.iloc[idx_1c:]['Temp'], marker='o', markersize=6,
                     color=final_c_temp, linewidth=8, alpha=alpha_val)
    else:
        marker = 'o' if (is_main or is_analysis_mode) else None
        ax_temp.plot(df['Time'], df['Temp'], marker=marker, markersize=5, linestyle=line_style,
                     color=final_c_temp, linewidth=2, label=label_prefix, alpha=alpha_val)

    if (is_main or is_analysis_mode) and 'Gas' in df.columns and df['Gas'].sum() > 0:
        ax_gas.plot(df['Time'], df['Gas'], drawstyle='steps-post', marker='x', markersize=5, linestyle=':',
                    color=final_c_gas, alpha=0.5, label='Gas' if is_main else None)

    if show_ror and len(df) > 1:
        prev_ror = 0
        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            dt = (curr['Time'] - prev['Time']) / 60.0
            dtemp = curr['Temp'] - prev['Temp']
            if dt > 0:
                ror = dtemp / dt
                c = "#2ecc71"
                if ror < 5:
                    c = "#3498db"
                elif ror > prev_ror + 2:
                    c = "#e74c3c"
                bar_x = curr['Time'] - (curr['Time'] - prev['Time']) / 2
                ax_ror_bar.bar(bar_x, ror, width=(curr['Time'] - prev['Time']), color=c, alpha=0.6)
                if ror > 3:
                    ax_ror_bar.text(bar_x, ror + 2, f"{ror:.1f}", ha='center', va='bottom', fontsize=8,
                                    color=c, fontweight='bold')
                prev_ror = ror

    if is_main or is_analysis_mode:
        event_points = []
        for _, row in df.iterrows():
            e = str(row['Event'])
            if e and e != "nan" and e != "None":
                event_points.append(row)

        for i, row in enumerate(event_points):
            e = str(row['Event'])
            label_text = e
            is_drop = is_drop_event(e)

            if is_drop:
                if t_2c:
                    label_text = f"Drop (+2C {format_mmss(row['Time']-t_2c)})"
                elif t_1c:
                    label_text = f"Drop (+1C {format_mmss(row['Time']-t_1c)})"

            is_1c_evt, is_2c_evt = check_is_crack(e)
            y_offset = 25 if i % 2 == 0 else -30
            va_align = 'bottom' if i % 2 == 0 else 'top'

            if is_1c_evt or is_2c_evt:
                box_props = dict(boxstyle="round,pad=0.4", fc="gold", ec="black", alpha=1.0)
                ax_temp.scatter(row['Time'], row['Temp'], marker='*', s=400, facecolors=final_c_temp,
                                edgecolors='black', linewidths=1.5, zorder=10)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, 20),
                                 textcoords='offset points', ha='center', weight='bold', color='black',
                                 fontsize=11, bbox=box_props)
            elif is_drop:
                box_props = dict(boxstyle="round,pad=0.4", fc="#9b59b6", ec="black", alpha=1.0)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, 35),
                                 textcoords='offset points', ha='center', weight='bold', color='white',
                                 fontsize=11, bbox=box_props, arrowprops=dict(arrowstyle="-", color='purple'))
            else:
                box_props = dict(boxstyle="round,pad=0.3", fc="white", ec=final_c_temp, alpha=0.9)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, y_offset),
                                 textcoords='offset points', ha='center', va=va_align, color='black',
                                 fontsize=10, bbox=box_props, arrowprops=dict(arrowstyle="-", color=final_c_temp))

# 그래프 실행
if is_analysis_mode:
    if selected_ids_analysis and not full_df.empty:
        colors = plt.cm.tab10.colors
        for i, pid in enumerate(selected_ids_analysis):
            p = full_df[full_df['Roast_ID'] == pid].sort_values('Time').reset_index(drop=True)
            if not p.empty:
                c = colors[i % len(colors)]
                plot_roast_data(ax1, ax2, ax_ror, p, c, c, f'{pid}', is_main=True, show_ror=False)
else:
    if reference_id_roasting and not full_df.empty:
        ref_data = full_df[full_df['Roast_ID'] == reference_id_roasting].sort_values('Time').reset_index(drop=True)
        if not ref_data.empty:
            plot_roast_data(ax1, ax2, ax_ror, ref_data, '#bdc3c7', '#bdc3c7',
                            f'Ref: {reference_id_roasting}', is_main=False, show_ror=False)

    if st.session_state.get("points"):
        curr_df = pd.DataFrame(st.session_state.points).sort_values('Time').reset_index(drop=True)
        plot_roast_data(ax1, ax2, ax_ror, curr_df, '#c0392b', '#2980b9', f'Current: {roast_id}', is_main=True, show_ror=True)

ax1.set_xlabel("Time (sec)")
ax1.set_ylabel("Temp (C)", color='#c0392b')
ax2.set_ylabel("Gas", color='#2980b9')
ax2.set_ylim(0, 10)
ax1.grid(True, ls='--', alpha=0.5)
ax1.legend(loc='upper left')
st.pyplot(fig)

# =========================================================
# ✅ (추가) 로스팅 종료 후: Agtron + 사진 + 내부디벨롭 힌트(QC)
# =========================================================
if not is_analysis_mode:
    roast_finished = False
    if st.session_state.points:
        df_finish = pd.DataFrame(st.session_state.points).sort_values("Time")
        if (df_finish["Event"].astype(str).apply(is_drop_event)).any():
            roast_finished = True
        elif is_auto_mode and st.session_state.timer_state == "stopped":
            roast_finished = True

    if roast_finished and st.session_state.points:
        with st.expander("4. ✅ 로스팅 종료 QC (Agtron / 내부디벨롭 / 사진 리포트)", expanded=True):
            st.markdown(
                "- **권장 흐름:** (1) Agtron(Whole/Ground) 입력 또는 사진 기반 추정 → "
                "(2) Color spread로 내부디벨롭 힌트 확인 → (3) PDF 리포트 다운로드/출력"
            )

            # ---- 아그트론 입력 ----
            a1, a2, a3 = st.columns([1, 1, 1.2])
            with a1:
                ag_w = st.number_input("Agtron (Whole, 겉)", min_value=0.0, max_value=150.0, value=float(st.session_state.agtron_whole or 0.0), step=0.1)
            with a2:
                ag_g = st.number_input("Agtron (Ground, 속)", min_value=0.0, max_value=150.0, value=float(st.session_state.agtron_ground or 0.0), step=0.1)
            with a3:
                st.caption("💡 SCA 커핑 기준(샘플 로스팅)은 Ground 기준 Agtron Gourmet 63±1 등으로 관리합니다.")
            st.session_state.agtron_whole = ag_w if ag_w > 0 else None
            st.session_state.agtron_ground = ag_g if ag_g > 0 else None

            # ---- Color spread (내부디벨롭 힌트) ----
            if st.session_state.agtron_whole and st.session_state.agtron_ground:
                spread = float(st.session_state.agtron_ground - st.session_state.agtron_whole)
                st.info(f"📌 Color spread (Ground - Whole) = **{spread:.1f}**  (겉/속 차이 힌트)")
                if spread >= 15:
                    st.warning("⚠️ 스프레드가 큰 편입니다 → 겉은 진행됐지만 속이 상대적으로 덜 진행(불균일) 가능성. (프로파일/열전달 재점검 추천)")
                elif spread >= 8:
                    st.warning("🟡 스프레드가 약간 큽니다 → 배치/원두에 따라 허용 범위지만, 내부 디벨롭 관찰 필요.")
                else:
                    st.success("✅ 스프레드가 과도하지 않습니다 → 비교적 균일하게 진행됐을 가능성이 큽니다.")

            # ---- 사진 업로드/촬영 ----
            st.markdown("##### 📷 볶은 커피 + (가능하면) 흰 종이(화이트 레퍼런스) 같이 촬영")
            p1, p2 = st.columns([1, 1])
            photo_file = None
            with p1:
                cam = st.camera_input("카메라로 촬영 (가능하면 흰 종이를 함께 프레임에 넣어주세요)")
                if cam is not None:
                    photo_file = cam
            with p2:
                up = st.file_uploader("또는 사진 업로드 (jpg/png)", type=["jpg", "jpeg", "png"])
                if up is not None:
                    photo_file = up

            roast_photo_pil = pil_from_upload(photo_file) if photo_file else None
            if roast_photo_pil is not None:
                st.image(roast_photo_pil, caption="업로드된 사진", use_container_width=True)

                # 저장(선택)
                if st.button("🗂️ 사진 저장(로컬)", use_container_width=True):
                    path = save_image_bytes(roast_photo_pil, roast_id, kind="roast_photo")
                    st.session_state.roast_photo_path = path
                    st.session_state.roast_photo_pil = roast_photo_pil
                    st.success(f"저장됨: {path}")

                # ---- 사진 기반 Agtron 추정(베타) ----
                st.markdown("##### 🧪 사진 기반 Agtron 추정 (베타 / 조명 영향 큼)")
                H, W = roast_photo_pil.size[1], roast_photo_pil.size[0]

                st.caption("ROI(영역) 두 개를 잡습니다: (1) 흰 종이/하이라이트(화이트밸런스), (2) 원두 영역(색 측정)")
                c_roi1, c_roi2, c_roi3 = st.columns([1, 1, 1])

                # 기본값(대충)
                default_white = (int(W*0.05), int(H*0.05), int(W*0.25), int(H*0.2))
                default_beans = (int(W*0.35), int(H*0.45), int(W*0.3), int(H*0.3))

                with c_roi1:
                    wx = st.number_input("White ROI x", 0, W-1, default_white[0])
                    wy = st.number_input("White ROI y", 0, H-1, default_white[1])
                with c_roi2:
                    ww = st.number_input("White ROI w", 1, W, default_white[2])
                    wh = st.number_input("White ROI h", 1, H, default_white[3])
                with c_roi3:
                    bx = st.number_input("Bean ROI x", 0, W-1, default_beans[0])
                    by = st.number_input("Bean ROI y", 0, H-1, default_beans[1])
                    bw = st.number_input("Bean ROI w", 1, W, default_beans[2])
                    bh = st.number_input("Bean ROI h", 1, H, default_beans[3])

                gain = st.slider("Agtron gain", 0.5, 2.0, 1.2, 0.05)
                offset = st.slider("Agtron offset", -20.0, 40.0, 5.0, 0.5)

                if st.button("🧮 사진으로 Agtron 추정", type="primary"):
                    res = estimate_agtron_from_photo(
                        roast_photo_pil,
                        bean_roi=(bx, by, bw, bh),
                        white_roi=(wx, wy, ww, wh),
                        gain=gain,
                        offset=offset
                    )
                    st.session_state.agtron_est = res["agtron_est"]
                    st.session_state.roast_photo_pil = roast_photo_pil

                    st.success(f"추정 Agtron(대략): **{res['agtron_est']:.1f}**  (L* 평균: {res['L_mean']:.1f})")
                    st.caption("※ 정확한 Agtron은 NIR/전용 계측기를 권장합니다. 사진 추정은 조명/카메라에 따라 변동됩니다.")

            # ---- QC 요약 (RoR/Weight loss/Phase) ----
            st.markdown("##### 📊 내부 디벨롭/베이크 리스크 힌트(QC)")
            df_pts = pd.DataFrame(st.session_state.points).sort_values("Time")
            qc = compute_qc_summary(df_pts, green_weight_g=float(green_weight), output_weight_g=None, dtr_pct=None)
            st.session_state.qc_summary = qc

            phases = qc["phases"]
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Total", format_mmss(phases["total_sec"] or 0))
            with m2:
                st.metric("Drying", format_mmss(phases["drying_sec"] or 0))
            with m3:
                st.metric("Maillard", format_mmss(phases["maillard_sec"] or 0))
            with m4:
                st.metric("Dev", format_mmss(phases["dev_sec"] or 0))

            # RoR flags
            ftxt = []
            if qc["crash_flag"] is True:
                ftxt.append("⚠️ RoR crash 의심(1C 근처)")
            if qc["stall_flag"] is True:
                ftxt.append("⚠️ 1C 이후 RoR 정체(베이크/플랫 리스크)")
            if qc["flick_flag"] is True:
                ftxt.append("⚠️ 마지막 구간 RoR flick 의심")
            if not ftxt:
                st.success("✅ RoR 기반 큰 위험 신호는 크지 않습니다(간단 휴리스틱 기준).")
            else:
                st.warning(" / ".join(ftxt))

            if qc["ror_before_1c"] is not None and qc["ror_after_1c"] is not None:
                st.caption(f"RoR(1C 전)≈{qc['ror_before_1c']:.1f} ℃/min, RoR(1C 후)≈{qc['ror_after_1c']:.1f} ℃/min, ratio={qc['crash_ratio']:.2f}" if qc["crash_ratio"] is not None else "")

# =========================================================
# 저장 섹션 & DTR 평가 + PDF 리포트
# =========================================================
if not is_analysis_mode:
    st.subheader("3. 저장 (Save)")
    c1, c2, c3 = st.columns([1, 2, 1])
    calc_E = None

    current_dtr = 0
    dtr_feedback = ""
    df = None

    if st.session_state.points:
        df = pd.DataFrame(st.session_state.points).sort_values('Time')
        t_1c = None
        for _, r in df.iterrows():
            if check_is_crack(str(r['Event']))[0]:
                t_1c = r['Time']
                break

        if t_1c and df.iloc[-1]['Time'] > t_1c:
            total_time = df.iloc[-1]['Time']
            dev_time = total_time - t_1c
            current_dtr = (dev_time / total_time) * 100
            dtr_feedback = get_dtr_feedback(current_dtr)

    with c1:
        rw = st.number_input("배출무게 (Output Weight, g)", 0.0)
        wl_pct = None
        if rw > 0 and green_weight > 0:
            wl_pct = float((green_weight - rw) / green_weight * 100)
            st.info(f"📉 웨이트 로스(Weight loss): **{wl_pct:.1f}%**")

            lw = green_weight - rw
            last_t = st.session_state.points[-1]['Temp'] if st.session_state.points else initial_temp
            q = (lw * 2260 + rw * 1.6 * (last_t - 25)) / 1000
            calc_E = f"{q:.1f} kJ"
            st.info(f"🔥 열량 (Energy): {calc_E}")

    with c2:
        note = st.text_input("메모 (Note)", placeholder="맛, 날씨, 특이사항")
        intl_date = get_intl_date_str()
        save_name = st.text_input("파일 이름 (File Name)", value=f"Roasting_{intl_date}_{bean_name}")

    with c3:
        st.write("")
        st.write("")
        if st.session_state.points:
            if dtr_feedback:
                st.markdown(f"""
                <div style="background-color:#e8f6f3; padding:10px; border-radius:5px; border:1px solid #1abc9c; font-size:0.9em; margin-bottom:10px;">
                    <strong>📊 DTR: {current_dtr:.1f}%</strong><br>{dtr_feedback}
                </div>
                """, unsafe_allow_html=True)

            sdf = pd.DataFrame(st.session_state.points)

            # QC 요약 갱신(저장용)
            qc2 = compute_qc_summary(
                sdf.sort_values("Time"),
                green_weight_g=float(green_weight),
                output_weight_g=float(rw) if rw > 0 else None,
                dtr_pct=float(current_dtr) if current_dtr else None
            )
            st.session_state.qc_summary = qc2

            phases = qc2["phases"]

            # CSV 다운로드용(메타 포함)
            buf = io.StringIO()
            buf.write(
                f"파일 이름,{save_name}\n"
                f"날짜,{get_intl_date_str()}\n"
                f"원두 이름,{bean_name}\n"
                f"로스터 이름,{roaster_name}\n"
                f"방식,{method}\n"
                f"결과무게,{rw}\n"
                f"웨이트로스(%),{(qc2['wl_pct'] if qc2['wl_pct'] is not None else '')}\n"
                f"DTR(%),{(qc2['dtr_pct'] if qc2['dtr_pct'] is not None else '')}\n"
                f"Drying(sec),{(phases['drying_sec'] if phases['drying_sec'] is not None else '')}\n"
                f"Maillard(sec),{(phases['maillard_sec'] if phases['maillard_sec'] is not None else '')}\n"
                f"Development(sec),{(phases['dev_sec'] if phases['dev_sec'] is not None else '')}\n"
                f"Agtron_Whole,{(st.session_state.agtron_whole if st.session_state.agtron_whole else '')}\n"
                f"Agtron_Ground,{(st.session_state.agtron_ground if st.session_state.agtron_ground else '')}\n"
                f"Agtron_Est(photo),{(st.session_state.agtron_est if st.session_state.agtron_est else '')}\n"
                f"흡수열량,{calc_E}\n"
                f"비고,{note}\n\n"
            )
            sdf[['Time', 'Temp', 'Gas', 'Event']].rename(columns={'Time': 'Time(sec)', 'Temp': 'Temp(C)'}).to_csv(buf, index=False)
            csv_d = buf.getvalue().encode('utf-8-sig')

            def save():
                # DB 저장용에는 메타를 각 row에 컬럼으로 넣어둠(분석에 유리)
                to_save = sdf.copy()
                to_save['Roast_ID'] = roast_id
                to_save['Bean_Name'] = bean_name
                to_save['Roaster_Name'] = roaster_name
                to_save['Method'] = method
                to_save['Output_Weight_g'] = rw
                to_save['WeightLoss_pct'] = qc2['wl_pct']
                to_save['DTR_pct'] = qc2['dtr_pct']
                to_save['Drying_sec'] = phases['drying_sec']
                to_save['Maillard_sec'] = phases['maillard_sec']
                to_save['Dev_sec'] = phases['dev_sec']
                to_save['Agtron_Whole'] = st.session_state.agtron_whole
                to_save['Agtron_Ground'] = st.session_state.agtron_ground
                to_save['Agtron_Est_photo'] = st.session_state.agtron_est
                to_save['RoastPhotoPath'] = st.session_state.roast_photo_path

                m = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
                h = not os.path.exists(DEFAULT_DATA_FILE)
                to_save.to_csv(DEFAULT_DATA_FILE, mode=m, header=h, index=False, encoding='utf-8-sig')

                # 상태 초기화
                st.session_state.points = []
                st.session_state.timer_state = "idle"
                st.session_state.start_time = None
                st.session_state.stop_elapsed = None

                # Agtron/QC 초기화
                st.session_state.agtron_whole = None
                st.session_state.agtron_ground = None
                st.session_state.agtron_est = None
                st.session_state.roast_photo_path = None
                st.session_state.roast_photo_pil = None
                st.session_state.qc_summary = None

                st.success("저장 완료!")

            st.download_button(
                "💾 CSV 저장 및 다운로드",
                csv_d,
                f"{save_name}.csv",
                "text/csv",
                type="primary",
                on_click=save,
                use_container_width=True
            )

            # ✅ PDF 리포트 생성/다운로드 (출력용)
            st.write("")
            st.markdown("##### 🖨️ 출력용 1페이지 리포트(PDF)")
            # 그래프를 PNG로 저장
            curve_buf = io.BytesIO()
            fig.savefig(curve_buf, format="png", dpi=160, bbox_inches="tight")
            curve_png = curve_buf.getvalue()

            meta = {
                "Date": get_intl_date_str(),
                "Bean": bean_name,
                "Roaster": roaster_name,
                "Method": method,
                "Green(g)": f"{green_weight}",
                "Output(g)": f"{rw}",
                "WeightLoss(%)": f"{qc2['wl_pct']:.1f}" if qc2['wl_pct'] is not None else "",
                "DTR(%)": f"{current_dtr:.1f}" if current_dtr else "",
                "Agtron Whole": f"{st.session_state.agtron_whole}" if st.session_state.agtron_whole else "",
                "Agtron Ground": f"{st.session_state.agtron_ground}" if st.session_state.agtron_ground else "",
                "Agtron Est(photo)": f"{st.session_state.agtron_est:.1f}" if st.session_state.agtron_est else "",
                "Note": note,
            }

            pdf_bytes = build_pdf_report(
                roast_id=roast_id,
                meta_dict=meta,
                roast_curve_png_bytes=curve_png,
                roast_photo_pil=st.session_state.roast_photo_pil
            )

            st.download_button(
                "📄 PDF 리포트 다운로드(출력)",
                data=pdf_bytes,
                file_name=f"{save_name}_report.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        else:
            st.button("💾 CSV 저장", disabled=True, use_container_width=True)
