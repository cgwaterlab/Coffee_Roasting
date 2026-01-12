import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time
import streamlit.components.v1 as components

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Roasting Analysis Center Pro", layout="wide", page_icon="☕")

# 한글 폰트 설정 (환경에 따라 선택)
try: plt.rcParams['font.family'] = 'Malgun Gothic' 
except: plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- 세션 상태 초기화 (데이터 보존용) ---
if 'points' not in st.session_state: st.session_state.points = [] 
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'is_running' not in st.session_state: st.session_state.is_running = False

# --- 유틸리티 함수 ---
def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"

def get_dtr_feedback(dtr):
    if dtr < 10: return "⚠️ 언더 디벨롭 (Under Developed): 시간을 조금 더 늘려보세요."
    elif dtr <= 15: return "🍓 노르딕/라이트 (Light): 화사한 산미와 꽃향기가 특징이에요."
    elif dtr <= 20: return "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미의 황금 비율! (추천)"
    elif dtr <= 25: return "🍫 미디엄 다크 (Medium Dark): 초콜릿 향과 묵직한 바디감."
    else: return "🔥 다크 (Dark): 스모키하고 중후한 맛."

def format_mmss(seconds):
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m}:{s:02d}"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e)
    is_2c = any(k in e for k in ["2c", "2nd", "second"])
    return is_1c, is_2c

# [핵심] 실시간 자바스크립트 타이머 표시 함수
def show_realtime_clock(start_ts):
    clock_html = f"""
    <div id="timer_display" style="font-size: 4em; font-weight: 800; text-align: center; color: #2d3436; font-family: monospace; background: #f8f9fa; padding: 15px; border-radius: 15px; border: 2px solid #dee2e6; margin-bottom: 20px;">00:00</div>
    <script>
    function update() {{
        const start = {start_ts} * 1000;
        const now = new Date().getTime();
        const diff = Math.floor((now - start) / 1000);
        if (diff < 0) return;
        const m = Math.floor(diff / 60).toString().padStart(2, '0');
        const s = (diff % 60).toString().padStart(2, '0');
        document.getElementById('timer_display').innerText = m + ':' + s;
    }}
    setInterval(update, 1000); update();
    </script>
    """
    components.html(clock_html, height=130)

# --- CSV 로딩 및 표준화 ---
def load_and_standardize_csv(file, file_name_fallback):
    try:
        file.seek(0); raw = file.read()
        content = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        lines = content.splitlines()
        header_row_idx, delimiter, extracted_id = None, ",", None
        for i, line in enumerate(lines):
            if "원두" in line or "bean" in line.lower():
                parts = [p.strip() for p in re.split(r"[,\t;]", line)]
                if len(parts) > 1 and parts[1]: extracted_id = parts[1]
            for d in [",", "\t", ";"]:
                cells = [c.strip().lower() for c in line.split(d)]
                if any("time" in c or "시간" in c for c in cells) and any("temp" in c or "온도" in c for c in cells):
                    header_row_idx, delimiter = i, d; break
            if header_row_idx is not None: break
        if header_row_idx is None: return None
        df = pd.read_csv(io.StringIO("\n".join(lines[header_row_idx:])), delimiter=delimiter)
        # 컬럼명 통일
        col_map = {}
        for col in df.columns:
            c = str(col).lower()
            if "time" in c or "시간" in c: col_map[col] = "Time"
            elif "temp" in c or "온도" in c: col_map[col] = "Temp"
            elif "gas" in c or "가스" in c: col_map[col] = "Gas"
            elif "event" in c or "이벤트" in c: col_map[col] = "Event"
        df.rename(columns=col_map, inplace=True)
        df["Roast_ID"] = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        return df
    except: return None

# --- 사이드바 및 히스토리 관리 ---
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")
mode = st.sidebar.radio("모드 선택 (Mode)", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto)"], index=0)

all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try: db_df = pd.read_csv(DEFAULT_DATA_FILE); all_history.append(db_df)
    except: pass

uploaded_files = st.sidebar.file_uploader("로스팅 기록 파일 업로드", accept_multiple_files=True)
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None: all_history.append(pdf)

full_df = pd.concat(all_history, ignore_index=True) if all_history else pd.DataFrame()

# --- 메인 로직 ---
if mode == "📊 데이터 분석 (Analysis)":
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.sidebar.multiselect("비교 그래프 선택", uids)
    else: st.info("업로드된 데이터가 없습니다.")

else:
    st.title(f"🔥 Coffee Roasting: {mode}")
    
    # 레퍼런스 선택
    selected_ref = None
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_choice = st.sidebar.selectbox("📉 배경 레퍼런스 선택", ["(선택 안 함)"] + uids)
        if ref_choice != "(선택 안 함)": selected_ref = ref_choice

    # 1. Setup
    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3 = st.columns(3)
        bean_name = c1.text_input("원두 이름", "Geisha")
        roast_id = c2.text_input("ID (파일이름)", f"{bean_name}_{get_intl_date_str()}")
        initial_temp = c3.number_input("투입온도 (℃)", 200)
        green_weight = c3.number_input("생두 무게(g)", 250)

    # 2. Process (실시간/수동 입력)
    if mode == "⏱️ 로스팅 + 시계 (Auto)":
        st.subheader("2. 실시간 로스팅 (Auto Timer)")
        col_t1, col_t2 = st.columns([1, 2])
        with col_t1:
            if not st.session_state.is_running:
                if st.button("▶️ START (로스팅 시작)", type="primary", use_container_width=True):
                    st.session_state.is_running = True
                    st.session_state.start_time = time.time()
                    st.session_state.points = [{"Time": 0, "Temp": initial_temp, "Gas": 0, "Event": "Charge", "Roast_ID": roast_id}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET (초기화)", use_container_width=True):
                    st.session_state.is_running = False
                    st.session_state.start_time = None
                    st.session_state.points = []
                    st.rerun()
        with col_t2:
            if st.session_state.is_running: show_realtime_clock(st.session_state.start_time)
            else: st.info("준비가 되면 시작 버튼을 누르세요.")

        if st.session_state.is_running:
            with st.form("auto_entry", clear_on_submit=True):
                f1, f2, f3, f4 = st.columns([1,1,2,1])
                curr_t = f1.number_input("현재 온도", 0, 300, initial_temp)
                curr_g = f2.number_input("가스압", 0.0, 10.0, step=0.1)
                curr_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"])
                if f4.form_submit_button("기록 (Enter)", use_container_width=True):
                    elapsed = int(time.time() - st.session_state.start_time)
                    st.session_state.points.append({"Time": elapsed, "Temp": curr_t, "Gas": curr_g, "Event": curr_e if curr_e != "기록" else "", "Roast_ID": roast_id})
                    if curr_e == "Drop": st.session_state.is_running = False
                    st.rerun()
    else:
        # Manual Mode 생략 (필요시 추가)
        pass

# --- 그래프 렌더링 (Matplotlib) ---
if (mode == "📊 데이터 분석 (Analysis)" and 'selected_ids' in locals() and selected_ids) or st.session_state.points:
    st.write("---")
    fig, ax1 = plt.subplots(figsize=(12, 7))
    ax2 = ax1.twinx() # Gas Axis
    ax_ror = ax1.twinx() # RoR Axis (hidden)
    ax_ror.set_ylim(0, 150); ax_ror.axis('off')

    def plot_data(df, is_main=True, label=""):
        df = df.sort_values('Time')
        # RoR 계산
        df['RoR'] = 0.0
        for i in range(1, len(df)):
            dt = (df.iloc[i]['Time'] - df.iloc[i-1]['Time']) / 60.0
            if dt > 0: df.iloc[i, df.columns.get_loc('RoR')] = (df.iloc[i]['Temp'] - df.iloc[i-1]['Temp']) / dt
        
        color = '#c0392b' if is_main else '#bdc3c7'
        ax1.plot(df['Time'], df['Temp'], marker='o', ls='-' if is_main else '--', color=color, label=label, lw=2 if is_main else 1)
        
        if is_main:
            # RoR Bar (사용자 요청: 2배 크기 및 신호등)
            prev_ror = 0
            for i in range(1, len(df)):
                r = df.iloc[i]['RoR']
                c = '#2ecc71' # Green
                if r > prev_ror + 2 or r > 15: c = '#e74c3c' # Red
                elif r < 5: c = '#3498db' # Blue
                ax_ror.bar(df.iloc[i]['Time'], r, width=10, color=c, alpha=0.4)
                if r > 2: ax_ror.text(df.iloc[i]['Time'], r+2, f"{r:.1f}", ha='center', fontsize=8, color=c, weight='bold')
                prev_ror = r
            
            # 이벤트 어노테이션
            for _, row in df.iterrows():
                if row['Event'] and str(row['Event']) != 'nan':
                    ax1.annotate(row['Event'], (row['Time'], row['Temp']), xytext=(0,15), textcoords='offset points', ha='center', weight='bold', bbox=dict(boxstyle='round,pad=0.3', fc='white', ec=color, alpha=0.8))

    # 레퍼런스 그리기
    if mode != "📊 데이터 분석 (Analysis)" and selected_ref:
        ref_df = full_df[full_df['Roast_ID'] == selected_ref]
        plot_data(ref_df, is_main=False, label=f"Ref: {selected_ref}")

    # 메인 데이터 그리기
    if mode == "📊 데이터 분석 (Analysis)":
        for i, pid in enumerate(selected_ids):
            plot_data(full_df[full_df['Roast_ID'] == pid], label=pid)
    elif st.session_state.points:
        plot_data(pd.DataFrame(st.session_state.points), label=f"Current: {roast_id}")

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)"); ax2.set_ylabel("Gas")
    ax1.grid(True, ls='--', alpha=0.5); ax1.legend()
    st.pyplot(fig)

# --- 저장 및 DTR 평가 ---
if mode != "📊 데이터 분석 (Analysis)" and st.session_state.points:
    st.write("---")
    st.subheader("3. 로스팅 결과 및 저장 (Save)")
    
    # DTR 계산
    df = pd.DataFrame(st.session_state.points)
    t_1c = None
    for _, r in df.iterrows():
        if check_is_crack(r['Event'])[0]: t_1c = r['Time']; break
    
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        rw = st.number_input("배출 무게 (g)", 0)
        if rw > 0:
            yield_val = (rw / green_weight) * 100
            st.metric("수율 (Yield)", f"{yield_val:.1f}%")
    
    with col_s2:
        if t_1c:
            total_t = df.iloc[-1]['Time']
            dtr = ((total_t - t_1c) / total_t) * 100
            st.info(f"📊 **DTR: {dtr:.1f}%**\n{get_dtr_feedback(dtr)}")
        else: st.warning("1차 팝이 기록되지 않았습니다.")

    with col_s3:
        note = st.text_input("메모", placeholder="특이사항 입력")
        if st.button("💾 데이터베이스 저장 및 CSV 다운로드", type="primary", use_container_width=True):
            # DB 저장 로직 (기본 뼈대 유지)
            df['Roast_ID'] = roast_id
            m = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
            df.to_csv(DEFAULT_DATA_FILE, mode=m, header=(m=='w'), index=False, encoding='utf-8-sig')
            st.success("저장 완료!")
