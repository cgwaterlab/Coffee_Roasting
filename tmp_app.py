import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import time
import numpy as np
from PIL import Image

# ✅ 실시간 타이머를 위한 라이브러리 (터미널에서 pip install streamlit-autorefresh 필요)
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 디자인
# =========================================================
st.set_page_config(page_title="Roasting Analysis & QC Center", layout="wide", page_icon="☕")

try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'
LOGO_PATH = "pco_logo.png"

# =========================================================
# 2. 세션 상태 초기화
# =========================================================
if 'points' not in st.session_state: st.session_state.points = []
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'last_record_time' not in st.session_state: st.session_state.last_record_time = None
if 'timer_state' not in st.session_state: st.session_state.timer_state = "idle"
if 'stop_elapsed' not in st.session_state: st.session_state.stop_elapsed = 0

if st.session_state.timer_state == "running":
    st_autorefresh(interval=1000, key="timer_refresher")

# =========================================================
# 3. 핵심 유틸리티 함수
# =========================================================
def format_mmss(seconds):
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m}:{s:02d}"

def get_dtr_feedback(dtr):
    leaf_green = "#228B22"
    if dtr < 10: msg = "⚠️ 언더 디벨롭: 시간을 조금 더 늘려보세요."
    elif dtr <= 15: msg = "🍓 노르딕/라이트 (Light): 화사한 산미 구간."
    elif dtr <= 20: msg = "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미의 조화!"
    elif dtr <= 25: msg = "🍫 미디엄 다크 (Medium Dark): 묵직한 바디감."
    else: msg = "🔥 다크 (Dark): 스모키하고 진한 맛."
    return f"<span style='color:{leaf_green}; font-weight:bold; font-size:1.1em;'>{msg}</span>"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    return any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e)

def estimate_agtron(uploaded_image):
    try:
        img = Image.open(uploaded_image).convert('L')
        return int((np.mean(np.array(img)) / 255) * 120)
    except: return "N/A"

# CSV 로드 및 표준화 함수 (기존 기능 복구)
def load_and_standardize_csv(file, file_name_fallback):
    try:
        file.seek(0); raw = file.read()
        content = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        lines = content.splitlines()
        header_row_idx, delimiter, extracted_id = None, ",", None
        for i, line in enumerate(lines):
            if "원두" in line or "bean" in line.lower():
                parts = [p.strip() for p in re.split(r"[,\t;]", line)]
                if len(parts) > 1: extracted_id = parts[1]
            for d in [",", "\t", ";"]:
                cells = [c.strip().lower() for c in line.split(d)]
                if any("time" in c or "시간" in c for c in cells) and any("temp" in c or "온도" in c for c in cells):
                    header_row_idx, delimiter = i, d; break
            if header_row_idx is not None: break
        if header_row_idx is None: return None
        df = pd.read_csv(io.StringIO("\n".join(lines[header_row_idx:])), delimiter=delimiter)
        col_map = {col: ("Time" if "time" in col.lower() or "시간" in col else "Temp" if "temp" in col.lower() or "온도" in col else "Gas" if "gas" in col.lower() or "가스" in col else "Event" if "event" in col.lower() or "이벤트" in col else col) for col in df.columns}
        df.rename(columns=col_map, inplace=True); df["Roast_ID"] = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        return df
    except: return None

# =========================================================
# 4. 사이드바 (에러 방지 처리)
# =========================================================
st.sidebar.markdown("## PERU COFFEE ORIGINS")
try:
    if os.path.exists(LOGO_PATH):
        st.sidebar.image(LOGO_PATH, use_container_width=True)
except: pass # 서버 연결 에러 발생 시 이미지 출력을 건너뜀

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석 & 파일 로드", "⏱️ 로스팅 + 실시간 QC"], index=1)

# 데이터베이스 로드
all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if not db_df.empty: all_history.append(db_df)
    except: pass
full_db = pd.concat(all_history, ignore_index=True) if all_history else pd.DataFrame()

# =========================================================
# 5. [기능 1] 데이터 분석 및 파일 로드
# =========================================================
if mode == "📊 데이터 분석 & 파일 로드":
    st.title("📊 Analysis & History Center")
    
    uploaded_files = st.file_uploader("로스팅 로그 파일(CSV) 업로드", accept_multiple_files=True)
    temp_list = []
    if uploaded_files:
        for f in uploaded_files:
            tdf = load_and_standardize_csv(f, f.name)
            if tdf is not None: temp_list.append(tdf)
    
    combined_df = pd.concat([full_db] + temp_list, ignore_index=True) if not full_db.empty or temp_list else pd.DataFrame()
    
    if not combined_df.empty:
        uids = list(combined_df['Roast_ID'].unique())
        selected_ids = st.multiselect("비교 분석할 Roast ID 선택", uids)
        
        if selected_ids:
            fig, ax = plt.subplots(figsize=(12, 6))
            for rid in selected_ids:
                target = combined_df[combined_df['Roast_ID'] == rid].sort_values('Time')
                ax.plot(target['Time'], target['Temp'], label=rid, lw=2)
            ax.set_xlabel("Time (s)"); ax.set_ylabel("Temp (℃)")
            ax.legend(); ax.grid(True, alpha=0.3)
            st.pyplot(fig)
            st.dataframe(combined_df[combined_df['Roast_ID'].isin(selected_ids)])
    else:
        st.info("기록된 데이터가 없습니다. 파일을 업로드하거나 로스팅을 시작하세요.")

# =========================================================
# 6. [기능 2] 로스팅 + 실시간 QC (핵심 요청 사항)
# =========================================================
else:
    st.title("🔥 Professional Roasting & QC")
    
    # 레퍼런스(배경) 선택 기능
    reference_df = pd.DataFrame()
    if not full_db.empty:
        ref_id = st.sidebar.selectbox("📉 레퍼런스 로드 (배경 그래프)", ["(선택 안 함)"] + list(full_db['Roast_ID'].unique()))
        if ref_id != "(선택 안 함)":
            reference_df = full_db[full_db['Roast_ID'] == ref_id].sort_values('Time')

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        bean_name = c1.text_input("원두 이름", "Geisha")
        roast_id = c2.text_input("Roast ID", f"{bean_name}_{datetime.now().strftime('%m%d%H%M')}")
        init_temp = c3.number_input("투입온도 (℃)", value=200)
        weight = c4.number_input("생두 무게 (g)", value=250.0)

    # 더블 타이머 영역
    st.subheader("2. 실시간 로스팅 로거")
    t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
    
    elapsed_all = int(time.time() - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
    elapsed_split = int(time.time() - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

    with t_col1:
        if st.session_state.timer_state == "idle":
            if st.button("▶️ START", type="primary", use_container_width=True):
                now = time.time()
                st.session_state.start_time = now; st.session_state.last_record_time = now
                st.session_state.timer_state = "running"
                st.session_state.points = [{"Time": 0, "Temp": int(init_temp), "Gas": 0.0, "Event": "Charge", "Roast_ID": roast_id}]
                st.rerun()
        else:
            if st.button("⏹️ RESET", use_container_width=True):
                st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()

    t_col2.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
    t_col3.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split))

    # 데이터 입력 폼
    if st.session_state.timer_state == "running":
        with st.form("auto_record_form", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
            c_temp = f1.number_input("온도", 0, 300, int(init_temp))
            c_gas = f2.number_input("가스", 0.0, 15.0, step=0.1)
            c_evt = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "Drop"])
            if f4.form_submit_button("기록 (Enter)"):
                now_ts = time.time()
                rec_t = int(now_ts - st.session_state.start_time)
                st.session_state.last_record_time = now_ts
                st.session_state.points.append({"Time": rec_t, "Temp": c_temp, "Gas": c_gas, "Event": c_evt if c_evt != "기록" else None, "Roast_ID": roast_id})
                if c_evt == "Drop":
                    st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
                st.rerun()

    # 실시간 그래프 시각화 (레퍼런스 비교 포함)
    if st.session_state.points:
        curr_df = pd.DataFrame(st.session_state.points).sort_values('Time')
        t_1c = next((r['Time'] for _, r in curr_df.iterrows() if check_is_crack(r['Event'])), None)
        
        fig, ax1 = plt.subplots(figsize=(12, 6))
        
        # 레퍼런스 배경 출력
        if not reference_df.empty:
            ax1.plot(reference_df['Time'], reference_df['Temp'], color='#ecf0f1', lw=2, label=f"Ref: {ref_id}", zorder=1)

        # 현재 로스팅 출력 (1차 팝 전후 구분)
        pre_df = curr_df[curr_df['Time'] <= (t_1c if t_1c else 9999)]
        ax1.scatter(pre_df['Time'], pre_df['Temp'], color='#bdc3c7', s=40, label='Drying Phase', zorder=3)
        
        if t_1c:
            post_df = curr_df[curr_df['Time'] >= t_1c]
            ax1.plot(post_df['Time'], post_df['Temp'], color='#c0392b', lw=5, label='Development Phase', zorder=4)
            row_1c = curr_df[curr_df['Time'] == t_1c].iloc[0]
            ax1.scatter(row_1c['Time'], row_1c['Temp'], marker='*', s=500, color='#f1c40f', edgecolors='black', zorder=10)

        ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)")
        ax1.legend(); ax1.grid(True, ls='--', alpha=0.3)
        st.pyplot(fig)

    # 7. QC 섹션 (로스팅 종료 시 노출)
    if st.session_state.timer_state == "stopped":
        st.markdown("---")
        st.subheader("3. 품질 분석 및 데이터 저장 (QC)")
        qc1, qc2 = st.columns(2)
        
        with qc1:
            st.markdown("#### 🎨 아그트론 분석")
            do_ag = st.checkbox("아그트론(Agtron) 사진 분석 진행")
            if do_ag:
                st.info("💡 **가이드:** 아그트론 색상표(종이)와 원두를 함께 촬영하세요.")
                cam = st.camera_input("QC 촬영")
                if cam: st.success(f"📸 추정 아그트론 넘버: **{estimate_agtron(cam)}**")
        
        with qc2:
            st.markdown("#### 📊 리포트 요약")
            df_final = pd.DataFrame(st.session_state.points).sort_values('Time')
            t_1c_f = next((r['Time'] for _, r in df_final.iterrows() if check_is_crack(r['Event'])), None)
            if t_1c_f:
                dtr = ((df_final.iloc[-1]['Time'] - t_1c_f) / df_final.iloc[-1]['Time']) * 100
                st.markdown(f"<div style='background-color:#f9fdf9; padding:15px; border-radius:10px; border:2px solid #228B22;'><b>DTR: {dtr:.1f}%</b><br>{get_dtr_feedback(dtr)}</div>", unsafe_allow_html=True)
            
            st.warning("📝 **안내:** 비고란에 [이용 열량 값]을 꼭 적어주세요.")
            note = st.text_area("비고 (열량 및 메모)", placeholder="예: 1540kJ 기록")
            
            if st.button("💾 최종 저장 및 종료", type="primary", use_container_width=True):
                df_final.to_csv(DEFAULT_DATA_FILE, mode='a', header=not os.path.exists(DEFAULT_DATA_FILE), index=False, encoding='utf-8-sig')
                st.success("데이터베이스에 저장되었습니다.")
                st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()
