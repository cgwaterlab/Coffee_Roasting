import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time
# ✅ 실시간 갱신을 위해 필수 (터미널에서 pip install streamlit-autorefresh 실행)
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("라이브러리 미설치: 터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 스타일
# =========================================================
st.set_page_config(page_title="Roasting Analysis Center Pro", layout="wide", page_icon="☕")

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'
LOGO_PATH = "pco_logo.png"

# =========================================================
# 2. 세션 상태 초기화 (데이터 및 시계 관리)
# =========================================================
if 'points' not in st.session_state: st.session_state.points = []
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'last_record_time' not in st.session_state: st.session_state.last_record_time = None
if 'timer_state' not in st.session_state: st.session_state.timer_state = "idle" # idle, running, stopped
if 'stop_elapsed' not in st.session_state: st.session_state.stop_elapsed = 0

# ✅ 타이머 작동 시 1초마다 화면 강제 새로고침
if st.session_state.timer_state == "running":
    st_autorefresh(interval=1000, key="timer_refresher")

# =========================================================
# 3. 핵심 함수 모음
# =========================================================
def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"

def format_mmss(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"

def get_dtr_feedback(dtr):
    if dtr < 10: return "⚠️ 언더 디벨롭 (Under Developed): 풋내가 날 수 있어요."
    elif dtr <= 15: return "🍓 노르딕/라이트 (Light): 화사한 산미와 깔끔한 끝맛."
    elif dtr <= 20: return "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 비율!"
    elif dtr <= 25: return "🍫 미디엄 다크 (Medium Dark): 초콜릿 향과 묵직한 바디감."
    else: return "🔥 다크 (Dark): 스모키함과 쌉쌀함이 강조돼요."

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e)
    is_2c = any(k in e for k in ["2c", "2nd", "second"])
    return is_1c, is_2c

def is_drop_event(e: str) -> bool:
    if not e: return False
    s = str(e).lower().strip()
    return ("drop" in s) or ("배출" in s)

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
# 4. 사이드바 구성
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")

mode = st.sidebar.radio("모드 선택 (Mode)", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

# 레퍼런스 센터
all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    db_df = pd.read_csv(DEFAULT_DATA_FILE)
    if 'Roast_ID' in db_df.columns: all_history.append(db_df)

uploaded_files = st.sidebar.file_uploader("로스팅 기록 파일 업로드", accept_multiple_files=True)
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None: all_history.append(pdf)
full_df = pd.concat(all_history, ignore_index=True) if all_history else pd.DataFrame()

# =========================================================
# 5. 메인 로직 (모드별 분기)
# =========================================================
is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.sidebar.multiselect("비교할 그래프 선택", uids)
    else: st.info("기록된 데이터가 없습니다.")

else:
    st.title("🔥 Professional Roasting Log")
    reference_id = None
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_choice = st.sidebar.selectbox("📉 레퍼런스 선택", ["(선택 안 함)"] + uids)
        if ref_choice != "(선택 안 함)": reference_id = ref_choice

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        bean_name = c1.text_input("원두 이름", "Geisha")
        roast_id = c2.text_input("ID", f"{bean_name}_{get_intl_date_str()}")
        roaster_name = c3.text_input("로스터 이름", "")
        method = c4.selectbox("방식", ["드럼 (Drum)", "열풍 (Hot Air)", "하이브리드 (Hybrid)", "직화 (Direct Fire)"])
        initial_temp = st.number_input("투입온도 (℃)", value=200)
        green_weight = st.number_input("생두 무게 (g)", value=250.0)

    # --- 실시간 기록 (Auto-Timer) 핵심 영역 ---
    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        
        # 더블 타이머 표시
        t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
        elapsed_all = int(time.time() - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
        elapsed_split = int(time.time() - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

        with t_col1:
            if st.session_state.timer_state == "idle":
                if st.button("▶️ START", type="primary", use_container_width=True):
                    now = time.time()
                    st.session_state.start_time = now
                    st.session_state.last_record_time = now
                    st.session_state.timer_state = "running"
                    st.session_state.points = [{"Time": 0, "Temp": int(initial_temp), "Gas": 0.0, "Event": "Charge", "Roast_ID": roast_id}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET", use_container_width=True):
                    st.session_state.start_time = None
                    st.session_state.last_record_time = None
                    st.session_state.timer_state = "idle"
                    st.session_state.points = []
                    st.rerun()

        with t_col2: st.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
        with t_col3: st.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split), help="마지막 기록 시점부터 지난 시간입니다.")

        # 입력 폼
        can_rec = (st.session_state.timer_state == "running")
        c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 2, 1])
        with c1: st.text_input("현재 시간", value=format_mmss(elapsed_all), disabled=True)
        with c2: temp = st.number_input("온도", 0, 300, int(initial_temp), disabled=not can_rec, key="t_auto")
        with c3: gas = st.number_input("가스", 0.0, 15.0, 0.0, step=0.1, disabled=not can_rec, key="g_auto")
        with c4: evt = st.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"], disabled=not can_rec)
        with c5:
            st.write(""); st.write("")
            if st.button("기록 (Record)", type="primary", use_container_width=True, disabled=not can_rec):
                now_ts = time.time()
                rec_time = int(now_ts - st.session_state.start_time)
                st.session_state.last_record_time = now_ts # 구간 시계 리셋
                chosen_evt = evt if evt != "기록" else None
                st.session_state.points.append({"Time": rec_time, "Temp": temp, "Gas": gas, "Event": chosen_evt, "Roast_ID": roast_id})
                if is_drop_event(chosen_evt):
                    st.session_state.timer_state = "stopped"
                    st.session_state.stop_elapsed = rec_time
                st.rerun()
    else:
        # 수동 모드 로직 (기존 유지)
        st.subheader("2. 수동 기록 (Manual Input)")
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2, 1])
        with c1: m = st.number_input("분", 0, 60, 0); s = st.number_input("초", 0, 59, 0); t_sec = m*60+s
        with c2: temp = st.number_input("온도", 0, 300, int(initial_temp), key="t_man")
        with c3: gas = st.number_input("가스", 0.0, 15.0, 0.0, step=0.1, key="g_man")
        with c4: evt = st.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"], key="e_man")
        if c5.button("추가 (Add)", type="primary", use_container_width=True):
            st.session_state.points.append({"Time": t_sec, "Temp": temp, "Gas": gas, "Event": evt if evt != "기록" else None, "Roast_ID": roast_id})

    # 데이터 에디터
    if st.session_state.points:
        st.markdown("##### 📝 데이터 수정")
        edited = st.data_editor(pd.DataFrame(st.session_state.points), num_rows="dynamic", use_container_width=True)
        if not pd.DataFrame(st.session_state.points).equals(edited):
            st.session_state.points = edited.to_dict('records')

# =========================================================
# 6. 통합 Matplotlib 그래프 (전문가용)
# =========================================================
if (is_analysis_mode and 'selected_ids' in locals() and selected_ids) or st.session_state.points:
    st.write("---")
    fig, ax1 = plt.subplots(figsize=(12, 7))
    ax2 = ax1.twinx()
    ax_ror = ax1.twinx()
    ax_ror.set_ylim(0, 150); ax_ror.axis('off')

    def plot_data(df, color_t, label, is_main=False, show_ror=False):
        df = df.sort_values('Time')
        # RoR 계산
        df['RoR'] = 0.0
        for i in range(1, len(df)):
            dt = (df.iloc[i]['Time'] - df.iloc[i-1]['Time']) / 60.0
            if dt > 0: df.iloc[i, df.columns.get_loc('RoR')] = (df.iloc[i]['Temp'] - df.iloc[i-1]['Temp']) / dt
        
        ax1.plot(df['Time'], df['Temp'], marker='o', ls='-' if is_main else '--', color=color_t, label=label, lw=2 if is_main else 1, alpha=0.9 if is_main else 0.4)
        
        if is_main and show_ror:
            prev_r = 0
            for i in range(1, len(df)):
                r = df.iloc[i]['RoR']
                c = "#2ecc71" # Green
                if r > prev_r + 2 or r > 15: c = "#e74c3c" # Red
                elif r < 5: c = "#3498db" # Blue
                ax_ror.bar(df.iloc[i]['Time'], r, width=10, color=c, alpha=0.3)
                if r > 3: ax_ror.text(df.iloc[i]['Time'], r+2, f"{r:.1f}", ha='center', fontsize=8, color=c, weight='bold')
                prev_r = r
            for _, row in df.iterrows():
                if row['Event'] and str(row['Event']) != 'nan':
                    ax1.annotate(row['Event'], (row['Time'], row['Temp']), xytext=(0,15), textcoords='offset points', ha='center', weight='bold', bbox=dict(boxstyle='round,pad=0.2', fc='white', ec=color_t, alpha=0.7))

    if is_analysis_mode:
        colors = plt.cm.tab10.colors
        for i, pid in enumerate(selected_ids): plot_data(full_df[full_df['Roast_ID']==pid], colors[i%10], pid, is_main=True)
    else:
        if reference_id: plot_data(full_df[full_df['Roast_ID']==reference_id], "#bdc3c7", f"Ref: {reference_id}")
        if st.session_state.points: plot_data(pd.DataFrame(st.session_state.points), "#c0392b", f"Current: {roast_id}", is_main=True, show_ror=True)

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)"); ax2.set_ylabel("Gas")
    ax1.grid(True, ls='--', alpha=0.5); ax1.legend(loc='upper left')
    st.pyplot(fig)

# =========================================================
# 7. 저장 섹션 & 분석 리포트
# =========================================================
if not is_analysis_mode and st.session_state.points:
    st.subheader("3. 결과 분석 및 저장 (Save)")
    c1, c2, c3 = st.columns([1, 2, 1])
    df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r['Event'])[0]), None)

    with c1:
        rw = st.number_input("배출 무게 (g)", 0.0)
        if rw > 0 and green_weight > 0:
            lw = green_weight - rw; last_t = df_f.iloc[-1]['Temp']
            q = (lw*2260 + rw*1.6*(last_t-25))/1000
            st.info(f"🔥 흡수 열량: {q:.1f} kJ")

    with c2:
        if t_1c:
            total_t = df_f.iloc[-1]['Time']
            dtr = ((total_t - t_1c) / total_t) * 100
            st.markdown(f"""<div style="background-color:#e8f6f3; padding:15px; border-radius:10px; border:1px solid #1abc9c;">
                <strong>📊 DTR: {dtr:.1f}%</strong><br>{get_dtr_feedback(dtr)}</div>""", unsafe_allow_html=True)

    with c3:
        note = st.text_input("메모", placeholder="맛, 특이사항")
        buf = io.StringIO()
        buf.write(f"파일 이름,{roast_id}\n원두,{bean_name}\n로스터,{roaster_name}\n방식,{method}\n결과무게,{rw}\n비고,{note}\n\n")
        df_f[['Time','Temp','Gas','Event']].rename(columns={'Time':'Time(sec)','Temp':'Temp(C)'}).to_csv(buf, index=False)
        
        def on_save():
            df_save = df_f.copy(); df_save['Roast_ID'] = roast_id
            m = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
            df_save.to_csv(DEFAULT_DATA_FILE, mode=m, header=(m=='w'), index=False, encoding='utf-8-sig')
            st.session_state.points = []; st.session_state.timer_state = "idle"; st.success("저장 완료!")

        st.download_button("💾 CSV 저장 및 다운로드", buf.getvalue().encode('utf-8-sig'), f"{roast_id}.csv", "text/csv", type="primary", on_click=on_save, use_container_width=True)
