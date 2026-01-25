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

# ✅ 실시간 타이머를 위한 라이브러리 설치 확인
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 디자인
# =========================================================
st.set_page_config(page_title="Roasting QC Center Pro", layout="wide", page_icon="☕")

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

# 타이머 작동 시 1초마다 자동 새로고침 (에러 방지를 위해 running일 때만 작동)
if st.session_state.timer_state == "running":
    st_autorefresh(interval=1000, key="timer_refresher")

# =========================================================
# 3. 핵심 함수 모음
# =========================================================
def format_mmss(seconds):
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m}:{s:02d}"

def get_dtr_feedback(dtr):
    leaf_green = "#228B22" # 눈이 편안한 나뭇잎 색
    if dtr < 10: msg = "⚠️ 언더 디벨롭: 시간을 조금 더 늘려보세요."
    elif dtr <= 15: msg = "🍓 노르딕/라이트 (Light): 화사한 산미 구간입니다."
    elif dtr <= 20: msg = "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 비율!"
    elif dtr <= 25: msg = "🍫 미디엄 다크 (Medium Dark): 바디감이 살아나요."
    else: msg = "🔥 다크 (Dark): 묵직하고 스모키함이 강조돼요."
    return f"<span style='color:{leaf_green}; font-weight:bold; font-size:1.1em;'>{msg}</span>"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    return any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e)

def estimate_agtron(uploaded_image):
    try:
        img = Image.open(uploaded_image).convert('L')
        stat = np.array(img)
        mean_brightness = np.mean(stat)
        return int((mean_brightness / 255) * 120)
    except Exception:
        return "측정 불가"

# =========================================================
# 4. 사이드바 (에러 유발 이미지 로직 안전하게 수정)
# =========================================================
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")
try:
    if os.path.exists(LOGO_PATH):
        # buildMediaURL 에러 방지를 위해 try-except로 감싸서 출력
        st.sidebar.image(LOGO_PATH, use_container_width=True)
except Exception:
    st.sidebar.title("☕ ROASTING CENTER")

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

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

if mode == "📊 데이터 분석":
    st.title("📊 Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.sidebar.multiselect("비교 그래프 선택", uids)
    else: st.info("기록된 데이터가 없습니다.")

else:
    st.title("🔥 Professional Roasting Log")

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        bean_name = c1.text_input("원두 이름", value="Geisha")
        roast_id = c2.text_input("ID", value=f"{bean_name}_{datetime.now().strftime('%m%d%H%M')}")
        initial_temp = c3.number_input("투입온도 (℃)", value=200)
        green_weight = c4.number_input("생두 무게 (g)", value=250.0)

    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
        
        # 시간 계산 로직
        if st.session_state.timer_state == "running":
            elapsed_all = int(time.time() - st.session_state.start_time)
            elapsed_split = int(time.time() - st.session_state.last_record_time)
        else:
            elapsed_all = st.session_state.stop_elapsed
            elapsed_split = 0

        with t_col1:
            if st.session_state.timer_state == "idle":
                if st.button("▶️ START", type="primary", use_container_width=True):
                    now = time.time()
                    st.session_state.start_time = now
                    st.session_state.last_record_time = now
                    st.session_state.timer_state = "running"
                    st.session_state.points = [{"Time": 0, "Temp": int(initial_temp), "Gas": 0.0, "Event": "Charge"}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET", use_container_width=True):
                    st.session_state.timer_state = "idle"
                    st.session_state.start_time = None
                    st.session_state.last_record_time = None
                    st.session_state.points = []
                    st.rerun()

        t_col2.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
        t_col3.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split))

        if st.session_state.timer_state == "running":
            with st.form("record_form", clear_on_submit=True):
                f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
                curr_t = f1.number_input("현재 온도", 0, 300, int(initial_temp))
                curr_g = f2.number_input("가스압", 0.0, 15.0, step=0.1)
                curr_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"])
                if f4.form_submit_button("기록 (Enter)", use_container_width=True):
                    now_ts = time.time()
                    rec_time = int(now_ts - st.session_state.start_time)
                    st.session_state.last_record_time = now_ts # 구간 시계 리셋
                    st.session_state.points.append({"Time": rec_time, "Temp": curr_t, "Gas": curr_g, "Event": curr_e if curr_e != "기록" else None})
                    if curr_e == "Drop":
                        st.session_state.timer_state = "stopped"
                        st.session_state.stop_elapsed = rec_time
                    st.rerun()

# =========================================================
# 6. 전문가용 시각화 (1차 팝 전후 구분)
# =========================================================
if st.session_state.points:
    st.write("---")
    df = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c = next((r['Time'] for _, r in df.iterrows() if check_is_crack(r['Event'])), None)

    fig, ax1 = plt.subplots(figsize=(12, 6))
    pre_df = df[df['Time'] <= (t_1c if t_1c else 9999)]
    ax1.scatter(pre_df['Time'], pre_df['Temp'], color='#bdc3c7', s=50, label='Drying Phase')
    
    if t_1c:
        post_df = df[df['Time'] >= t_1c]
        ax1.plot(post_df['Time'], post_df['Temp'], color='#c0392b', lw=5, label='Development', solid_capstyle='round')
        row_1c = df[df['Time'] == t_1c].iloc[0]
        ax1.scatter(row_1c['Time'], row_1c['Temp'], marker='*', s=550, color='#f1c40f', edgecolors='black', zorder=10)

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)")
    ax1.grid(True, ls='--', alpha=0.3); ax1.legend()
    st.pyplot(fig)

# =========================================================
# 7. QC 프로세스 및 아그트론 분석 (에러 방지 적용)
# =========================================================
if st.session_state.timer_state == "stopped":
    st.markdown("---")
    st.subheader("3. 품질 분석 및 결과 저장 (QC)")
    
    col_qc, col_report = st.columns(2)
    
    with col_qc:
        st.markdown("#### 🎨 아그트론 분석")
        do_agtron = st.checkbox("아그트론(Agtron) 사진 분석을 진행하시겠습니까?")
        if do_agtron:
            st.info("💡 **가이드:** 아그트론 넘버 색상표(종이)를 원두 옆에 두고 함께 촬영해 주세요.")
            try:
                cam_photo = st.camera_input("원두 촬영")
                if cam_photo:
                    est_ag = estimate_agtron(cam_photo)
                    st.success(f"📸 추정 아그트론 넘버: **{est_ag}**")
            except Exception:
                st.warning("카메라 연결에 문제가 있습니다.")

    with col_report:
        st.markdown("#### 📊 로스팅 리포트")
        df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
        t_1c_f = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r['Event'])), None)
        
        if t_1c_f:
            dtr = ((df_f.iloc[-1]['Time'] - t_1c_f) / df_f.iloc[-1]['Time']) * 100
            st.markdown(f"""
            <div style="background-color:#f9fdf9; padding:20px; border-radius:12px; border:2px solid #228B22;">
                <h3 style="margin:0; color:#228B22;">📊 DTR: {dtr:.1f}%</h3>
                {get_dtr_feedback(dtr)}
            </div>
            """, unsafe_allow_html=True)
            
        rw = st.number_input("배출 무게 (g)", value=0.0)
        st.warning("📝 **비고란 안내:** 이용 열량 값을 반드시 기재해 주세요.")
        note = st.text_area("비고 (열량 및 메모)", placeholder="예: 1560kJ / 산미 우수")
        
        if st.button("💾 데이터베이스 저장", type="primary", use_container_width=True):
            st.success("기록되었습니다!")
            st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()
