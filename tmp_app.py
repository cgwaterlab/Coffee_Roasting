import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time

# ✅ 실시간 갱신 필수 라이브러리
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("라이브러리 미설치: 터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 디자인
# =========================================================
LOGO_PATH = "pco_logo.png" 
st.set_page_config(page_title="Roasting Analysis Center Pro", layout="wide", page_icon="☕")

# 한글 폰트 설정
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
    is_1c = any(k in e for k in ["1c start", "1st pop", "1차 팝 시작", "1c s"])
    is_1c_end = any(k in e for k in ["1c end", "1차 팝 종료", "1c e"])
    is_2c = any(k in e for k in ["2c", "2차 팝", "second pop"])
    return is_1c, is_1c_end, is_2c

def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"

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
            if not line.strip(): continue
            if ("원두" in line) or ("bean" in line.lower()):
                parts = [p.strip() for p in re.split(r"[,\t;]", line)]
                if len(parts) > 1 and parts[1]: extracted_id = parts[1]
            for d in [",", "\t", ";"]:
                cells = [c.strip().lower() for c in line.split(d)]
                if any(("time" in c) or ("시간" in c) for c in cells) and any(("temp" in c) or ("온도" in c) for c in cells):
                    header_row_idx, delimiter = i, d; break
            if header_row_idx is not None: break
        if header_row_idx is None: return None
        df = pd.read_csv(io.StringIO("\n".join(lines[header_row_idx:])), delimiter=delimiter)
        col_map = {col: ("Time" if "time" in col.lower() or "시간" in col else "Temp" if "temp" in col.lower() or "온도" in col else "Gas" if "gas" in col.lower() or "가스" in col else "Event" if "event" in col.lower() or "이벤트" in col else col) for col in df.columns}
        df.rename(columns=col_map, inplace=True); df["Roast_ID"] = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        return df
    except: return None

def get_template_csv():
    return """파일 이름,Sample_01\n날짜,2026-Jan-01\n원두 이름,Geisha\n로스터 이름,Sample Roaster\n방식,드럼 (Drum)\n결과무게,215\n비고,템플릿\n\nTime(sec),Temp(C),Gas,Event\n0,200,0.0,Preheat\n30,200,0.5,Charge\n60,90,5.0,TP\n300,150,4.0,Yellowing\n540,192,2.0,1C Start\n630,205,0,Drop\n"""

# =========================================================
# 4. 사이드바 구성 (링크 및 레퍼런스 유지)
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("### PERU COFFEE ORIGINS")
st.sidebar.info("**페루의 Micro/Nano Lot 최상급 커피를 소개합니다.**")

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

c1, c2 = st.sidebar.columns(2)
with c1: st.link_button("🛍️ 스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with c2: st.link_button("📷 인스타", "https://instagram.com/perucoffee.origins", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("🛠️ 유틸리티")
u1, u2 = st.sidebar.columns(2)
with u1: st.download_button("📥 템플릿", get_template_csv().encode('utf-8-sig'), "template.csv", "text/csv", use_container_width=True)
with u2: st.link_button("⚡ Web Log", "https://roastinglog.netlify.app/", use_container_width=True)

# 레퍼런스 센터 데이터 로드
all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns: all_history.append(db_df)
    except: pass
uploaded_files = st.sidebar.file_uploader("기록 파일 업로드", accept_multiple_files=True, type=['csv'])
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None: all_history.append(pdf)
full_df = pd.concat(all_history, ignore_index=True) if all_history else pd.DataFrame()

# =========================================================
# 5. 핵심 그래프 시각화 엔진 (데이터 분석/실시간 공용)
# =========================================================
def plot_professional_roast(df, ax, color, label, is_main=True):
    df = df.sort_values('Time').copy()
    # 이벤트 위치 찾기
    t_1c = None
    for _, r in df.iterrows():
        if check_is_crack(r.get('Event', ""))[0] and t_1c is None:
            t_1c = r['Time']; break

    # 1. 1차 팝 이전: 점(Scatter)으로만 표시 (교차 마커)
    pre_df = df[df['Time'] <= (t_1c if t_1c is not None else 99999)]
    for i, (idx, row) in enumerate(pre_df.iterrows()):
        m_face = color if i % 2 == 0 else 'none'
        ax.scatter(row['Time'], row['Temp'], marker='o', edgecolors=color, facecolors=m_face, s=50, alpha=0.8, zorder=3)

    # 2. 1차 팝 이후: 실선으로 연결 및 교차 점 표시
    if t_1c is not None:
        post_df = df[df['Time'] >= t_1c]
        ax.plot(post_df['Time'], post_df['Temp'], color=color, lw=4 if is_main else 2, alpha=0.7, label=label, zorder=2)
        for i, (idx, row) in enumerate(post_df.iterrows()):
            m_face = color if i % 2 == 0 else 'none'
            ax.scatter(row['Time'], row['Temp'], marker='o', edgecolors=color, facecolors=m_face, s=60, alpha=0.9, zorder=3)

    # 3. 이벤트 강조 (텍스트 및 별표)
    for _, row in df.iterrows():
        e = row.get('Event', "")
        if pd.isna(e) or e == "" or e == "nan": continue
        
        is1s, is1e, is2s = check_is_crack(e)
        t_lbl = format_mmss(row['Time'])
        
        if is1s: # 1차 팝 시작 (별표)
            ax.scatter(row['Time'], row['Temp'], marker='*', s=500, color='#f1c40f', edgecolors='black', zorder=10)
            ax.annotate(f"★ 1C Start\n({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color='#f39c12')
        elif is1e: # 1차 팝 종료
            ax.annotate(f"1C End\n({t_lbl})", (row['Time'], row['Temp']), xytext=(0, -25), textcoords='offset points', ha='center', color='#d35400', fontsize=9)
        elif is2s: # 2차 팝 시작
            ax.annotate(f"2C Start\n({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color='#8e44ad')
        elif is_drop_event(e): # 배출
            ax.annotate(f"DROP ({t_lbl})", (row['Time'], row['Temp']), xytext=(15, 0), textcoords='offset points', va='center', weight='bold', color='red')
        else: # 기타 (TP, Yellow 등)
            ax.annotate(e, (row['Time'], row['Temp']), xytext=(0, 15), textcoords='offset points', ha='center', fontsize=8, alpha=0.7)

# =========================================================
# 6. 모드별 로직
# =========================================================
if mode == "📊 데이터 분석 (Analysis)":
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.multiselect(f"비교 분석할 그래프 선택 ({len(uids)}개)", uids)
        if selected_ids:
            fig, ax1 = plt.subplots(figsize=(12, 7))
            colors = plt.cm.tab10.colors
            for i, rid in enumerate(selected_ids):
                target_df = full_df[full_df['Roast_ID'] == rid]
                plot_professional_roast(target_df, ax1, colors[i%10], rid, is_main=True)
            ax1.set_xlabel("Time (s)"); ax1.set_ylabel("Temp (℃)"); ax1.grid(True, ls='--', alpha=0.4)
            st.pyplot(fig)
    else: st.info("데이터가 없습니다. CSV 파일을 업로드하세요.")

else:
    st.title("🔥 Professional Roasting Log")
    ref_id = None
    if not full_df.empty:
        ref_id = st.sidebar.selectbox("📉 레퍼런스(배경) 선택", ["(선택 안 함)"] + list(full_df['Roast_ID'].unique()))

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        bean_name = r1c1.text_input("원두 이름", value="Geisha")
        roast_id = r1c2.text_input("ID", value=f"{bean_name}_{get_intl_date_str()}")
        init_temp = r1c3.number_input("투입온도 (℃)", value=200)
        green_weight = r1c4.number_input("생두 무게 (g)", value=250.0)

    if mode == "⏱️ 로스팅 + 시계 (Auto-Timer)":
        st.subheader("2. 실시간 기록 (Double Timer)")
        now_ts = time.time()
        elapsed_all = int(now_ts - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
        elapsed_split = int(now_ts - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

        t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
        with t_col1:
            if st.session_state.timer_state == "idle":
                if st.button("▶️ START", type="primary", use_container_width=True):
                    st.session_state.start_time = now_ts; st.session_state.last_record_time = now_ts
                    st.session_state.timer_state = "running"
                    st.session_state.points = [{"Time": 0, "Temp": int(init_temp), "Gas": 0.0, "Event": "Charge"}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET", use_container_width=True):
                    st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()

        t_col2.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
        t_col3.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split))

        with st.form("record_form", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
            cur_t = f1.number_input("온도", 0, 300, int(init_temp))
            cur_g = f2.number_input("가스", 0.0, 15.0, step=0.1)
            cur_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"])
            if f4.form_submit_button("기록 (Enter)", use_container_width=True):
                st.session_state.last_record_time = time.time()
                rec_t = int(st.session_state.last_record_time - st.session_state.start_time)
                st.session_state.points.append({"Time": rec_t, "Temp": cur_t, "Gas": cur_g, "Event": cur_e if cur_e != "기록" else None})
                if is_drop_event(cur_e):
                    st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
                st.rerun()

    # 그래프 출력 (레퍼런스 포함)
    if st.session_state.points:
        st.write("---")
        fig, ax = plt.subplots(figsize=(12, 7))
        if ref_id and ref_id != "(선택 안 함)":
            plot_professional_roast(full_df[full_df['Roast_ID']==ref_id], ax, "gray", f"Ref: {ref_id}", is_main=False)
        plot_professional_roast(pd.DataFrame(st.session_state.points), ax, "#c0392b", "Current", is_main=True)
        ax.set_xlabel("Time (s)"); ax.set_ylabel("Temp (℃)"); ax.grid(True, ls='--', alpha=0.3)
        st.pyplot(fig)

# =========================================================
# 7. 저장 섹션
# =========================================================
if st.session_state.timer_state == "stopped" and st.session_state.points:
    st.subheader("3. 결과 분석 및 저장")
    df_final = pd.DataFrame(st.session_state.points).sort_values('Time')
    # DTR 계산 등 기존 저장 로직 수행
    rw = st.number_input("배출 무게 (g)", 0.0)
    if st.button("💾 최종 저장하기", type="primary"):
        df_final['Roast_ID'] = roast_id
        df_final.to_csv(DEFAULT_DATA_FILE, mode='a', header=not os.path.exists(DEFAULT_DATA_FILE), index=False, encoding='utf-8-sig')
        st.success("저장 완료!"); st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()
