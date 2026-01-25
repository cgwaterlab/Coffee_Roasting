import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time
import numpy as np
from PIL import Image
# ✅ 필수 라이브러리: 터미널에서 pip install streamlit-autorefresh 실행 필요
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("라이브러리 미설치: 터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 디자인
# =========================================================
st.set_page_config(page_title="Roasting QC Center Pro", layout="wide", page_icon="☕")

# 한글 폰트 설정
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
if 'timer_state' not in st.session_state: st.session_state.timer_state = "idle" # idle, running, stopped
if 'stop_elapsed' not in st.session_state: st.session_state.stop_elapsed = 0

# 타이머 작동 시 1초마다 자동 갱신
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
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m}:{s:02d}"

def get_dtr_feedback(dtr):
    # 눈이 가장 편안하다는 나뭇잎 색 (#228B22 Forest Green) 적용
    leaf_green = "#228B22"
    if dtr < 10: msg = "⚠️ 언더 디벨롭 (Under Developed): 풋내가 날 수 있어요. 시간을 조금 더 늘려보세요."
    elif dtr <= 15: msg = "🍓 노르딕/라이트 (Light): 꽃향기와 화사한 산미, 차(Tea) 같은 깔끔함이 특징이에요."
    elif dtr <= 20: msg = "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 황금 비율이에요!"
    elif dtr <= 25: msg = "🍫 미디엄 다크 (Medium Dark): 산미는 줄고 바디감과 초콜릿 향이 살아나요."
    else: msg = "🔥 다크 (Dark): 묵직한 바디감, 스모키함, 쌉쌀한 맛이 강조돼요."
    return f"<span style='color:{leaf_green}; font-weight:bold; font-size:1.1em;'>{msg}</span>"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    return any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e)

def estimate_agtron(uploaded_image):
    img = Image.open(uploaded_image).convert('L')
    stat = np.array(img)
    mean_brightness = np.mean(stat)
    return int((mean_brightness / 255) * 120)

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
# 4. 사이드바 및 모드 설정
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")

mode = st.sidebar.radio("모드 선택 (Mode)", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

# 히스토리 로드
all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns: all_history.append(db_df)
    except: pass
full_df = pd.concat(all_history, ignore_index=True) if all_history else pd.DataFrame()

# =========================================================
# 5. 메인 로직
# =========================================================
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

if mode == "📊 데이터 분석 (Analysis)":
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.sidebar.multiselect("비교할 그래프 선택", uids)
        # 분석 그래프 로직 추가 가능
    else: st.info("기록된 데이터가 없습니다.")

else:
    st.title("🔥 Professional Roasting Log")
    reference_id = None
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_choice = st.sidebar.selectbox("📉 레퍼런스(배경) 선택", ["(선택 안 함)"] + uids)
        if ref_choice != "(선택 안 함)": reference_id = ref_choice

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        bean_name = c1.text_input("원두 이름", "Geisha")
        roast_id = c2.text_input("ID", f"{bean_name}_{get_intl_date_str()}")
        roaster_name = c3.text_input("로스터 이름", "")
        method = c4.selectbox("방식", ["드럼 (Drum)", "열풍 (Hot Air)", "하이브리드 (Hybrid)", "직화 (Direct Fire)"])
        initial_temp = st.number_input("투입온도 (℃)", value=200)
        green_weight = st.number_input("생두 무게 (g)", value=250.0)

    # --- 2. 로스팅 진행 (Double Timer) ---
    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
        elapsed_all = int(time.time() - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
        elapsed_split = int(time.time() - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

        with t_col1:
            if st.session_state.timer_state == "idle":
                if st.button("▶️ START (로스팅 시작)", type="primary", use_container_width=True):
                    now = time.time()
                    st.session_state.start_time = now
                    st.session_state.last_record_time = now
                    st.session_state.timer_state = "running"
                    st.session_state.points = [{"Time": 0, "Temp": int(initial_temp), "Gas": 0.0, "Event": "Charge", "Roast_ID": roast_id}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET (초기화)", use_container_width=True):
                    st.session_state.timer_state = "idle"
                    st.session_state.start_time = None
                    st.session_state.last_record_time = None
                    st.session_state.points = []
                    st.rerun()

        t_col2.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
        t_col3.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split), help="마지막 기록 시점부터 지난 시간입니다.")

        # 입력 폼
        can_rec = (st.session_state.timer_state == "running")
        with st.form("record_form", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
            curr_t = f1.number_input("현재 온도", 0, 300, int(initial_temp))
            curr_g = f2.number_input("가스압", 0.0, 15.0, 0.0, step=0.1)
            curr_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"])
            if f4.form_submit_button("기록 (Enter)", use_container_width=True):
                now_ts = time.time()
                rec_time = int(now_ts - st.session_state.start_time)
                st.session_state.last_record_time = now_ts # 구간 시계 리셋
                chosen_evt = curr_e if curr_e != "기록" else None
                st.session_state.points.append({"Time": rec_time, "Temp": curr_t, "Gas": curr_g, "Event": chosen_evt, "Roast_ID": roast_id})
                if chosen_evt == "Drop" or "배출" in str(chosen_evt):
                    st.session_state.timer_state = "stopped"
                    st.session_state.stop_elapsed = rec_time
                st.rerun()
    else:
        st.subheader("2. 수동 기록 (Manual Input)")
        # 수동 로직 생략(기존과 동일)

# =========================================================
# 6. 전문가용 시각화 (1차 팝 전후 구분)
# =========================================================
if st.session_state.points:
    st.write("---")
    df = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c = next((r['Time'] for _, r in df.iterrows() if check_is_crack(r['Event'])), None)

    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    # 1차 팝 이전: 점(Scatter) / 이후: 굵은 선(Line)
    pre_df = df[df['Time'] <= (t_1c if t_1c else 9999)]
    ax1.scatter(pre_df['Time'], pre_df['Temp'], color='#bdc3c7', s=50, label='Maillard Phase (Dots)')
    
    if t_1c:
        post_df = df[df['Time'] >= t_1c]
        ax1.plot(post_df['Time'], post_df['Temp'], color='#c0392b', lw=5, label='Development (Bold Line)', solid_capstyle='round')
        ax1.scatter(post_df['Time'], post_df['Temp'], color='#c0392b', s=70)
        # 1차 팝 별표
        row_1c = df[df['Time'] == t_1c].iloc[0]
        ax1.scatter(row_1c['Time'], row_1c['Temp'], marker='*', s=550, color='#f1c40f', edgecolors='black', zorder=10, label='1st Pop Start')

    # 이벤트 표시
    for _, row in df.iterrows():
        if row['Event']:
            ax1.annotate(row['Event'], (row['Time'], row['Temp']), xytext=(0,15), textcoords='offset points', ha='center', weight='bold', bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='#c0392b', alpha=0.7))

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)")
    ax1.grid(True, ls='--', alpha=0.4); ax1.legend(loc='upper left')
    st.pyplot(fig)

# =========================================================
# 7. QC 프로세스 및 결과 저장
# =========================================================
if st.session_state.timer_state == "stopped":
    st.markdown("---")
    st.subheader("3. 품질 분석 및 결과 저장 (QC Report)")
    
    col_qc, col_save = st.columns(2)
    
    with col_qc:
        st.markdown("#### 🎨 아그트론 색도 분석")
        do_agtron = st.radio("아그트론(Agtron) 분석을 진행하시겠습니까?", ["아니오", "네"], index=0)
        
        if do_agtron == "네":
            st.info("💡 **촬영 가이드:** 정확한 측정을 위해 **아그트론 넘버 색상표(종이)**를 원두 옆에 두고 함께 촬영해 주세요.")
            cam_photo = st.camera_input("원두 사진 촬영 (QC용)")
            if cam_photo:
                est_no = estimate_agtron(cam_photo)
                st.success(f"📸 추정 아그트론 넘버: **{est_no}**")
        else:
            st.write("색도 분석 QC를 건너뜁니다.")

    with col_save:
        st.markdown("#### 📊 로스팅 리포트")
        df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
        t_1c_f = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r['Event'])), None)
        
        if t_1c_f:
            total_t = df_f.iloc[-1]['Time']
            dtr = ((total_t - t_1c_f) / total_t) * 100
            # 나뭇잎 색 피드백 박스
            st.markdown(f"""
            <div style="background-color:#f8fff8; padding:20px; border-radius:12px; border:2px solid #228B22; margin-bottom:15px;">
                <h3 style="margin-top:0; color:#228B22;">📊 DTR: {dtr:.1f}%</h3>
                {get_dtr_feedback(dtr)}
            </div>
            """, unsafe_allow_html=True)

        rw = st.number_input("배출 무게 (Output Weight, g)", value=0.0)
        
        # 이용 열량 가이드 및 비고란
        st.warning("📝 **안내:** 정확한 QC 기록을 위해 아래 '비고'란에 **[이용 열량 값]**을 반드시 기재해 주세요.")
        note = st.text_area("비고 (이용 열량 및 품질 메모)", placeholder="예: 1580kJ / 산미 발현 우수, 클린컵 좋음")
        
        if st.button("💾 최종 결과 저장", type="primary", use_container_width=True):
            # CSV 저장 로직
            df_f['Roast_ID'] = roast_id
            m = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
            df_f.to_csv(DEFAULT_DATA_FILE, mode=m, header=(m=='w'), index=False, encoding='utf-8-sig')
            st.success("QC 데이터베이스에 성공적으로 기록되었습니다!")
            st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()
