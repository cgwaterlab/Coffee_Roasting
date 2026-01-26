import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("라이브러리 미설치: 터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 스타일
# =========================================================
LOGO_PATH = "pco_logo.png" 
st.set_page_config(page_title="Roasting Analysis Center Pro", layout="wide", page_icon="☕")

try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

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
# 3. 핵심 함수 모음
# =========================================================
def format_mmss(seconds):
    if seconds is None or seconds < 0: return "00:00"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c start", "1st pop", "1차 팝 시작", "1c start"])
    is_1c_end = any(k in e for k in ["1c end", "1차 팝 종료"])
    is_2c = any(k in e for k in ["2c", "2차 팝", "second pop"])
    return is_1c, is_1c_end, is_2c

def get_intl_date_str():
    now = datetime.now()
    return f"{now.year}{now.month:02d}{now.day:02d}"

def is_drop_event(e: str) -> bool:
    if not e: return False
    s = str(e).lower().strip()
    return ("drop" in s) or ("배출" in s)

# =========================================================
# 4. 사이드바 및 메인 레이아웃 (기존 유지)
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("### PERU COFFEE ORIGINS")

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

# ... [파일 업로드 로직 등은 기존과 동일] ...

# =========================================================
# 5. 로스팅 로직
# =========================================================
st.title("🔥 Professional Roasting Log")

with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    bean_name = r1c1.text_input("원두 이름", value="Geisha")
    roast_id = r1c2.text_input("ID", value=f"{bean_name}_{get_intl_date_str()}")
    initial_temp = st.number_input("투입온도 (℃)", value=200)
    green_weight = st.number_input("생두 무게 (g)", value=250.0)

if is_auto_mode:
    st.subheader("2. 실시간 기록 (Double Timer)")
    now_ts = time.time()
    elapsed_all = int(now_ts - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
    elapsed_split = int(now_ts - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

    t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
    with t_col1:
        if st.session_state.timer_state == "idle":
            if st.button("▶️ START", type="primary", use_container_width=True):
                st.session_state.start_time = now_ts
                st.session_state.last_record_time = now_ts
                st.session_state.timer_state = "running"
                st.session_state.points = [{"Time": 0, "Temp": int(initial_temp), "Gas": 0.0, "Event": "Charge"}]
                st.rerun()
        else:
            if st.button("⏹️ RESET", use_container_width=True):
                st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()

    t_col2.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
    t_col3.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split))

    can_rec = (st.session_state.timer_state == "running")
    c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 2, 1])
    with c2: temp = st.number_input("온도", 0, 300, int(initial_temp), key="at_t")
    with c3: gas = st.number_input("가스", 0.0, 15.0, 0.0, step=0.1, key="at_g")
    EVT = ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"]
    with c4: evt = st.selectbox("이벤트", EVT, key="at_e")
    if c5.button("기록", type="primary", use_container_width=True, disabled=not can_rec):
        st.session_state.last_record_time = time.time()
        rec_t = int(st.session_state.last_record_time - st.session_state.start_time)
        st.session_state.points.append({"Time": rec_t, "Temp": temp, "Gas": gas, "Event": evt if evt != "기록" else None})
        if is_drop_event(evt):
            st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
        st.rerun()

# =========================================================
# 6. 전문가용 통합 그래프 시각화 (요청사항 반영)
# =========================================================
if st.session_state.points:
    st.write("---")
    df = pd.DataFrame(st.session_state.points).sort_values('Time')
    
    # 이벤트 위치 찾기
    t_1c, t_1c_end, t_2c = None, None, None
    for _, r in df.iterrows():
        is1s, is1e, is2s = check_is_crack(r['Event'])
        if is1s and t_1c is None: t_1c = r['Time']
        if is1e and t_1c_end is None: t_1c_end = r['Time']
        if is2s and t_2c is None: t_2c = r['Time']

    fig, ax1 = plt.subplots(figsize=(12, 7))
    
    # 1. 1차 팝 이전: 선 없이 점만 표시 (교차 스타일)
    pre_df = df[df['Time'] <= (t_1c if t_1c is not None else 9999)]
    for i, (idx, row) in enumerate(pre_df.iterrows()):
        m_style = 'o' if i % 2 == 0 else 'o'
        m_face = '#c0392b' if i % 2 == 0 else 'none' # 채워진 원 / 빈 원 교차
        ax1.scatter(row['Time'], row['Temp'], marker=m_style, edgecolors='#c0392b', facecolors=m_face, s=60, zorder=3)

    # 2. 1차 팝 이후: 실선으로 연결
    if t_1c is not None:
        post_df = df[df['Time'] >= t_1c]
        ax1.plot(post_df['Time'], post_df['Temp'], color='#c0392b', lw=4, alpha=0.8, zorder=2, label='Development')
        # 실선 위 점들도 교차 스타일 적용
        for i, (idx, row) in enumerate(post_df.iterrows()):
            m_face = '#c0392b' if i % 2 == 0 else 'none'
            ax1.scatter(row['Time'], row['Temp'], marker='o', edgecolors='#c0392b', facecolors=m_face, s=70, zorder=3)

    # 3. 특수 마커 및 텍스트 표시
    for _, row in df.iterrows():
        e = row['Event']
        if pd.isna(e) or e is None or e == "": continue
        
        is1s, is1e, is2s = check_is_crack(e)
        time_label = format_mmss(row['Time'])
        
        if is1s: # 1차 팝 시작 (별표)
            ax1.scatter(row['Time'], row['Temp'], marker='*', s=600, color='#f1c40f', edgecolors='black', zorder=10)
            ax1.annotate(f"★ 1C Start\n({time_label})", (row['Time'], row['Temp']), xytext=(0, 20), 
                         textcoords='offset points', ha='center', weight='bold', color='#f39c12')
        elif is1e: # 1차 팝 종료
            ax1.annotate(f"1C End\n({time_label})", (row['Time'], row['Temp']), xytext=(0, -30), 
                         textcoords='offset points', ha='center', color='#d35400')
        elif is2s: # 2차 팝 시작
            ax1.annotate(f"2C Start\n({time_label})", (row['Time'], row['Temp']), xytext=(0, 20), 
                         textcoords='offset points', ha='center', weight='bold', color='#8e44ad')
        elif is_drop_event(e): # 배출
            ax1.annotate(f"DROP\n({time_label})", (row['Time'], row['Temp']), xytext=(20, 0), 
                         textcoords='offset points', va='center', weight='bold', color='red')
        else: # 기타 이벤트 (TP, Yellowing 등)
            ax1.annotate(e, (row['Time'], row['Temp']), xytext=(0, 15), 
                         textcoords='offset points', ha='center', fontsize=9)

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (℃)")
    ax1.grid(True, ls='--', alpha=0.4); plt.tight_layout()
    st.pyplot(fig)

# =========================================================
# 7. 리포트 및 저장
# =========================================================
if st.session_state.timer_state == "stopped":
    st.subheader("3. 결과 분석 및 저장")
    df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c_f = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r['Event'])[0]), None)
    
    c1, c2 = st.columns(2)
    with c1:
        if t_1c_f:
            total_t = df_f.iloc[-1]['Time']
            dtr = ((total_t - t_1c_f) / total_t) * 100
            st.success(f"📊 DTR: {dtr:.1f}%")
        rw = st.number_input("배출 무게 (g)", 0.0)
        note = st.text_input("메모")
        if st.button("💾 최종 저장하기", type="primary"):
            st.success("데이터베이스에 저장되었습니다.")
            st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()
