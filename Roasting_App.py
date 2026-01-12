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

# 한글 폰트 설정
try: plt.rcParams['font.family'] = 'Malgun Gothic' 
except: plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- 세션 상태 초기화 ---
if 'points' not in st.session_state: st.session_state.points = [] 
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'is_running' not in st.session_state: st.session_state.is_running = False

# --- 함수 모음 ---
def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"

def get_dtr_feedback(dtr):
    if dtr < 10: return "⚠️ 언더 디벨롭 (Under Developed): 풋내나 떫은 맛이 날 수 있어요. 시간을 조금 더 늘려보세요."
    elif dtr <= 15: return "🍓 노르딕/라이트 (Light): 꽃향기와 화사한 산미, 차(Tea) 같은 깔끔함이 특징이에요."
    elif dtr <= 20: return "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 황금 비율이에요! (추천)"
    elif dtr <= 25: return "🍫 미디엄 다크 (Medium Dark): 산미는 줄고 바디감과 초콜릿 향이 살아나요."
    else: return "🔥 다크 (Dark): 묵직한 바디감, 스모키함, 쌉쌀한 맛이 강조돼요."

def format_mmss(seconds):
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m}:{s:02d}"

# [핵심] 실시간 자바스크립트 타이머 컴포넌트
def show_realtime_timer_js(start_ts):
    clock_html = f"""
    <div id="timer_display" style="font-size: 3.5em; font-weight: 800; text-align: center; color: #c0392b; font-family: monospace; background: #fdf2f2; padding: 15px; border-radius: 12px; border: 2px solid #f5c6cb; margin-bottom: 20px;">00:00</div>
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
    components.html(clock_html, height=120)

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

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e) and not ("2" in e)
    is_2c = any(k in e for k in ["2c", "2nd", "second"])
    return is_1c, is_2c

# --- 사이드바 ---
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")
mode = st.sidebar.radio("모드 선택 (Mode)", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=0)

all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns: all_history.append(db_df)
    except: pass

uploaded_files = st.sidebar.file_uploader("기록 파일 업로드", accept_multiple_files=True)
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None: all_history.append(pdf)

full_df = pd.concat(all_history, ignore_index=True) if all_history else pd.DataFrame()

# --- 모드별 로직 분기 ---
is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_manual_mode = (mode == "🔥 로스팅 (Manual)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.sidebar.multiselect(f"비교할 그래프 선택 ({len(uids)}개)", uids)
    else: st.info("데이터가 없습니다. 파일을 업로드하세요.")

else:
    st.title(f"🔥 Coffee Roasting: {mode}")
    selected_ref = None
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_choice = st.sidebar.selectbox("📉 배경 레퍼런스 선택", ["(선택 안 함)"] + uids)
        if ref_choice != "(선택 안 함)": selected_ref = ref_choice

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3 = st.columns(3)
        bean_name = c1.text_input("원두 이름", value="Geisha")
        roast_id = c2.text_input("ID", value=f"{bean_name}_{get_intl_date_str()}")
        initial_temp = c3.number_input("투입온도 (℃)", 200)
        green_weight = c3.number_input("생두 무게(g)", 250.0)

    # 2. 로스팅 진행 영역
    if is_auto_mode:
        st.subheader("2. 실시간 로스팅 (Auto Timer)")
        t_col1, t_col2 = st.columns([1, 2])
        with t_col1:
            if not st.session_state.is_running:
                if st.button("▶️ START (로스팅 시작)", type="primary", use_container_width=True):
                    st.session_state.is_running = True
                    st.session_state.start_time = time.time()
                    # 투입 기록 자동 추가
                    st.session_state.points = [{"Time": 0, "Temp": initial_temp, "Gas": 0, "Event": "Charge", "Roast_ID": roast_id}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET (초기화)", use_container_width=True):
                    st.session_state.is_running = False
                    st.session_state.start_time = None
                    st.session_state.points = []
                    st.rerun()
        with t_col2:
            if st.session_state.is_running: show_realtime_timer_js(st.session_state.start_time)
            else: st.info("준비가 되면 시작 버튼을 누르세요.")

        if st.session_state.is_running:
            with st.form("auto_record_form", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
                curr_t = c1.number_input("현재 온도", 0, 300, initial_temp)
                curr_g = c2.number_input("가스압", 0.0, 15.0, step=0.1)
                curr_e = c3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"])
                if c4.form_submit_button("기록 (Enter)", use_container_width=True):
                    elapsed = int(time.time() - st.session_state.start_time)
                    st.session_state.points.append({"Time": elapsed, "Temp": curr_t, "Gas": curr_g, "Event": curr_e if curr_e != "기록" else "", "Roast_ID": roast_id})
                    if curr_e == "Drop": st.session_state.is_running = False
                    st.rerun()
    else:
        st.subheader("2. 수동 기록 (Manual Input)")
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2, 1])
        with c1: m = st.number_input("분", 0, 60, 0); s = st.number_input("초", 0, 59, 0); t_sec = m*60+s
        with c2: temp = st.number_input("온도", 0, 300, initial_temp)
        with c3: gas = st.number_input("가스", 0.0, 15.0, 0.0, step=0.1)
        with c4: evt = st.selectbox("이벤트", ["기록", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"])
        if c5.button("추가", type="primary", use_container_width=True):
            st.session_state.points.append({"Time": t_sec, "Temp": temp, "Gas": gas, "Event": evt if evt!="기록" else "", "Roast_ID": roast_id})

# --- 통합 그래프 시각화 (Matplotlib) ---
if (is_analysis_mode and 'selected_ids' in locals() and selected_ids) or st.session_state.points:
    st.write("---")
    fig, ax1 = plt.subplots(figsize=(12, 7))
    ax2 = ax1.twinx()
    ax_ror = ax1.twinx()
    ax_ror.set_ylim(0, 150); ax_ror.axis('off')

    def plot_roast_data(ax_temp, ax_gas, ax_ror_bar, df, color_temp, color_gas, label_prefix, is_main=False, show_ror=False):
        df = df.sort_values('Time')
        t_1c, idx_1c = None, None
        for i, row in df.iterrows():
            if check_is_crack(str(row['Event']))[0] and t_1c is None:
                t_1c = row['Time']; idx_1c = i

        # 온도선 그리기
        ax_temp.plot(df['Time'], df['Temp'], marker='o', markersize=4, label=label_prefix, color=color_temp, alpha=0.9, linewidth=2 if is_main else 1)
        
        # RoR 계산 및 신호등 바차트
        if show_ror and len(df) > 1:
            prev_ror = 0
            for i in range(1, len(df)):
                curr = df.iloc[i]; prev = df.iloc[i-1]
                dt = (curr['Time'] - prev['Time']) / 60.0
                if dt > 0:
                    ror = (curr['Temp'] - prev['Temp']) / dt
                    c = "#2ecc71" # Green
                    if ror < 5: c = "#3498db" # Blue
                    elif ror > prev_ror + 2: c = "#e74c3c" # Red
                    
                    bar_x = curr['Time'] - (curr['Time']-prev['Time'])/2
                    ax_ror_bar.bar(bar_x, ror, width=(curr['Time']-prev['Time']), color=c, alpha=0.4)
                    if ror > 2:
                        ax_ror_bar.text(bar_x, ror + 2, f"{ror:.1f}", ha='center', fontsize=8, color=c, fontweight='bold')
                    prev_ror = ror

        # 이벤트 어노테이션
        for i, row in df.iterrows():
            e = str(row['Event'])
            if e and e != "nan" and e != "":
                ax_temp.annotate(e, (row['Time'], row['Temp']), xytext=(0, 15), textcoords='offset points', ha='center', weight='bold', bbox=dict(boxstyle='round,pad=0.2', fc='white', ec=color_temp, alpha=0.7))

    # 데이터 플로팅 실행
    if is_analysis_mode:
        colors = plt.cm.tab10.colors
        for i, pid in enumerate(selected_ids):
            p_df = full_df[full_df['Roast_ID'] == pid]
            plot_roast_data(ax1, ax2, ax_ror, p_df, colors[i % 10], colors[i % 10], pid, is_main=True)
    else:
        if selected_ref:
            plot_roast_data(ax1, ax2, ax_ror, full_df[full_df['Roast_ID'] == selected_ref], "#bdc3c7", "#bdc3c7", f"Ref: {selected_ref}", is_main=False)
        if st.session_state.points:
            plot_roast_data(ax1, ax2, ax_ror, pd.DataFrame(st.session_state.points), "#c0392b", "#2980b9", roast_id, is_main=True, show_ror=True)

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)"); ax2.set_ylabel("Gas")
    ax1.grid(True, ls='--', alpha=0.5); ax1.legend(loc='upper left')
    st.pyplot(fig)

# --- 저장 및 분석 섹션 ---
if not is_analysis_mode and st.session_state.points:
    st.write("---")
    st.subheader("3. 로스팅 분석 및 저장 (Analysis & Save)")
    df = pd.DataFrame(st.session_state.points).sort_values('Time')
    
    c1, c2, c3 = st.columns([1, 2, 1])
    t_1c = next((r['Time'] for _, r in df.iterrows() if check_is_crack(r['Event'])[0]), None)
    
    with c1:
        rw = st.number_input("배출무게 (g)", 0.0)
        if rw > 0: st.metric("수율 (Yield)", f"{(rw/green_weight)*100:.1f}%")

    with c2:
        if t_1c:
            total_t = df.iloc[-1]['Time']
            dtr = ((total_t - t_1c) / total_t) * 100
            st.markdown(f"""<div style="background-color:#e8f6f3; padding:15px; border-radius:10px; border:1px solid #1abc9c;">
                <strong>📊 DTR: {dtr:.1f}%</strong><br>{get_dtr_feedback(dtr)}</div>""", unsafe_allow_html=True)
        else: st.warning("1차 팝이 기록되지 않았습니다.")

    with c3:
        note = st.text_input("메모", placeholder="맛, 특이사항")
        if st.button("💾 데이터베이스 저장 & 다운로드", type="primary", use_container_width=True):
            df['Roast_ID'] = roast_id
            m = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
            df.to_csv(DEFAULT_DATA_FILE, mode=m, header=(m=='w'), index=False, encoding='utf-8-sig')
            st.session_state.points = []; st.success("저장 완료!")
            st.rerun()
