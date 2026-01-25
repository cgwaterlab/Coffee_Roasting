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

# ✅ 실시간 타이머 라이브러리 체크
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("터미널에서 'pip install streamlit-autorefresh'를 실행해야 타이머가 작동합니다.")

# =========================================================
# 1. 설정 및 디자인
# =========================================================
st.set_page_config(page_title="Roasting QC Center", layout="wide", page_icon="☕")

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

# 타이머 작동 시 1초마다 자동 갱신 (에러 방지를 위해 running 일 때만 작동)
if st.session_state.timer_state == "running":
    st_autorefresh(interval=1000, key="timer_refresher")

# =========================================================
# 3. 핵심 함수 (에러 예외 처리 강화)
# =========================================================
def format_mmss(seconds):
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m}:{s:02d}"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    return any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e)

def estimate_agtron(uploaded_image):
    try:
        img = Image.open(uploaded_image).convert('L')
        stat = np.array(img)
        return int((np.mean(stat) / 255) * 120)
    except:
        return "N/A"

# =========================================================
# 4. 사이드바 (안전한 이미지 로딩)
# =========================================================
st.sidebar.markdown("## PERU COFFEE ORIGINS")
try:
    if os.path.exists(LOGO_PATH):
        st.sidebar.image(LOGO_PATH, use_container_width=True)
except:
    # 서버 에러 방지를 위해 이미지가 없거나 연결 오류 시 텍스트로 대체
    st.sidebar.info("☕ Professional Roasting Tool")

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

# =========================================================
# 5. 메인 로직
# =========================================================
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

if mode == "📊 데이터 분석":
    st.title("📊 Analysis Center")
    st.info("기존 로직대로 분석을 진행하세요.")
else:
    st.title("🔥 Professional Roasting")

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        bean_name = c1.text_input("원두 이름", "Geisha")
        roast_id = c2.text_input("ID", f"{bean_name}_{datetime.now().strftime('%m%d%H%M')}")
        initial_temp = c3.number_input("투입온도 (℃)", value=200)
        green_weight = c4.number_input("생두 무게(g)", value=250.0)

    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
        
        # 실시간 시간 계산
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
                    st.session_state.points = []
                    st.rerun()

        t_col2.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
        t_col3.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split))

        if st.session_state.timer_state == "running":
            with st.form("auto_form", clear_on_submit=True):
                f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
                curr_t = f1.number_input("온도", 0, 300, int(initial_temp))
                curr_g = f2.number_input("가스", 0.0, 15.0, step=0.1)
                curr_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "Drop"])
                if f4.form_submit_button("기록 (Enter)"):
                    now_ts = time.time()
                    rec_time = int(now_ts - st.session_state.start_time)
                    st.session_state.last_record_time = now_ts
                    st.session_state.points.append({"Time": rec_time, "Temp": curr_t, "Gas": curr_g, "Event": curr_e if curr_e != "기록" else None})
                    if curr_e == "Drop":
                        st.session_state.timer_state = "stopped"
                        st.session_state.stop_elapsed = rec_time
                    st.rerun()

# =========================================================
# 6. 그래프 시각화 (포인트가 있을 때만 로거가 보임)
# =========================================================
if st.session_state.points:
    df = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c = next((r['Time'] for _, r in df.iterrows() if check_is_crack(r['Event'])), None)

    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    # 1차 팝 전후 시각화
    pre_df = df[df['Time'] <= (t_1c if t_1c else 9999)]
    ax1.scatter(pre_df['Time'], pre_df['Temp'], color='#bdc3c7', s=50, label='Drying Phase')
    
    if t_1c:
        post_df = df[df['Time'] >= t_1c]
        ax1.plot(post_df['Time'], post_df['Temp'], color='#c0392b', lw=4, label='Development')
        row_1c = df[df['Time'] == t_1c].iloc[0]
        ax1.scatter(row_1c['Time'], row_1c['Temp'], marker='*', s=500, color='#f1c40f', zorder=10)

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)")
    ax1.grid(True, ls='--', alpha=0.3); ax1.legend()
    st.pyplot(fig)

# 품질 분석(QC) 및 저장 로직은 아래에 이어서 구성...

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
