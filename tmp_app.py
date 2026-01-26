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

# ✅ 실시간 갱신 라이브러리 체크
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("라이브러리 미설치: 터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 디자인
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
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c start", "1st pop", "1차 팝 시작", "1c s"])
    is_1c_end = any(k in e for k in ["1c end", "1차 팝 종료", "1c e"])
    is_2c = any(k in e for k in ["2c", "2차 팝", "second pop"])
    return is_1c, is_1c_end, is_2c

def get_intl_date_str():
    now = datetime.now()
    return f"{now.year}{now.month:02d}{now.day:02d}"

def is_drop_event(e: str) -> bool:
    if not e: return False
    s = str(e).lower().strip()
    return ("drop" in s) or ("배출" in s)

def get_dtr_feedback(dtr):
    leaf_green = "#228B22"
    if dtr < 10: msg = "⚠️ 언더 디벨롭: 풋내 주의. 시간을 더 늘려보세요."
    elif dtr <= 15: msg = "🍓 라이트 (Light): 산미와 화사한 향미 구간."
    elif dtr <= 20: msg = "⚖️ 미디엄 (Medium): 단맛과 산미의 황금 비율!"
    elif dtr <= 25: msg = "🍫 미디엄 다크 (Medium Dark): 묵직한 바디감 강조."
    else: msg = "🔥 다크 (Dark): 스모키하고 강렬한 맛."
    return f"<span style='color:{leaf_green}; font-weight:bold;'>{msg}</span>"

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
                if len(parts) > 1: extracted_id = parts[1]
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

# =========================================================
# 4. 사이드바 구성 및 변수 초기화 (에러 해결 포인트)
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

# ✅ 에러 방지를 위해 변수를 미리 선언합니다.
is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

# 히스토리 로드
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

# =========================================================
# 5. 그래프 엔진 (범례 및 교차 마커)
# =========================================================
def plot_professional_roast(df, ax, color, label, is_main=True, fill_marker=True):
    df = df.sort_values('Time').copy()
    t_1c = next((r['Time'] for _, r in df.iterrows() if check_is_crack(r.get('Event', ""))[0]), None)

    # 1차 팝 전: 점 / 후: 선
    pre_df = df[df['Time'] <= (t_1c if t_1c is not None else 99999)]
    for i, (_, row) in enumerate(pre_df.iterrows()):
        m_face = color if fill_marker else 'none'
        ax.scatter(row['Time'], row['Temp'], marker='o', edgecolors=color, facecolors=m_face, s=50, alpha=0.8)

    if t_1c is not None:
        post_df = df[df['Time'] >= t_1c]
        ax.plot(post_df['Time'], post_df['Temp'], color=color, lw=4 if is_main else 2, alpha=0.7, label=label)
        for i, (_, row) in enumerate(post_df.iterrows()):
            m_face = color if fill_marker else 'none'
            ax.scatter(row['Time'], row['Temp'], marker='o', edgecolors=color, facecolors=m_face, s=60, alpha=0.9)

    # 특수 마커 (별표 및 시간)
    for _, row in df.iterrows():
        e = str(row.get('Event', ""))
        if not e or e.lower() == "nan": continue
        t_lbl = format_mmss(row['Time'])
        is1s, is1e, is2s = check_is_crack(e)
        if is1s:
            ax.scatter(row['Time'], row['Temp'], marker='*', s=500, color='#f1c40f', edgecolors='black', zorder=10)
            ax.annotate(f"★ 1C Start ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color='#f39c12')
        elif is1e:
            ax.annotate(f"1C End ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, -25), textcoords='offset points', ha='center', color='#d35400', fontsize=9)
        elif is2s:
            ax.annotate(f"2C Start ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color='#8e44ad')
        elif is_drop_event(e):
            ax.annotate(f"DROP ({t_lbl})", (row['Time'], row['Temp']), xytext=(15, 0), textcoords='offset points', va='center', weight='bold', color='red')

# =========================================================
# 6. 모드별 실행
# =========================================================
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.multiselect("비교 분석할 Roast ID 선택", uids)
        if selected_ids:
            fig, ax = plt.subplots(figsize=(12, 7))
            colors = plt.cm.tab10.colors
            for i, rid in enumerate(selected_ids):
                plot_professional_roast(full_df[full_df['Roast_ID']==rid], ax, colors[i%10], rid, is_main=True, fill_marker=(i%2==0))
            ax.set_xlabel("Time (s)"); ax.set_ylabel("Temp (℃)"); ax.legend(title="파일 이름 (Legend)"); ax.grid(True, ls='--', alpha=0.3)
            st.pyplot(fig)
    else: st.info("업로드된 데이터가 없습니다.")

else:
    st.title("🔥 Professional Roasting Log")
    ref_id = st.sidebar.selectbox("📉 레퍼런스 선택", ["(없음)"] + list(full_df['Roast_ID'].unique())) if not full_df.empty else None

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        bean_name = c1.text_input("원두 이름", "Geisha")
        roast_id = c2.text_input("ID", f"{bean_name}_{get_intl_date_str()}")
        init_temp = c3.number_input("투입온도 (℃)", 200)
        green_weight = c4.number_input("생두 무게 (g)", 250.0)

    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        now_ts = time.time()
        elapsed_all = int(now_ts - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
        elapsed_split = int(now_ts - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

        t1, t2, t3 = st.columns([1, 2, 2])
        if st.session_state.timer_state == "idle":
            if t1.button("▶️ START", type="primary", use_container_width=True):
                st.session_state.start_time = now_ts; st.session_state.last_record_time = now_ts
                st.session_state.timer_state = "running"
                st.session_state.points = [{"Time": 0, "Temp": int(init_temp), "Gas": 0.0, "Event": "Charge"}]
                st.rerun()
        else:
            if t1.button("⏹️ RESET", use_container_width=True):
                st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()

        t2.metric("⏳ 전체 시간", format_mmss(elapsed_all))
        t3.metric("⏱️ 구간 시간", format_mmss(elapsed_split))

        with st.form("rec_form", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
            cur_t = f1.number_input("온도", 0, 300, int(init_temp))
            cur_g = f2.number_input("가스", 0.0, 15.0, step=0.1)
            cur_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"])
            if f4.form_submit_button("기록", use_container_width=True):
                st.session_state.last_record_time = time.time()
                rec_t = int(st.session_state.last_record_time - st.session_state.start_time)
                st.session_state.points.append({"Time": rec_t, "Temp": cur_t, "Gas": cur_g, "Event": cur_e if cur_e != "기록" else None})
                if is_drop_event(cur_e): st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
                st.rerun()

    if st.session_state.points:
        st.write("---")
        fig, ax = plt.subplots(figsize=(12, 7))
        if ref_id and ref_id != "(없음)":
            plot_professional_roast(full_df[full_df['Roast_ID']==ref_id], ax, "gray", f"Ref: {ref_id}", is_main=False, fill_marker=False)
        plot_professional_roast(pd.DataFrame(st.session_state.points), ax, "#c0392b", "Current", is_main=True, fill_marker=True)
        ax.set_xlabel("Time (s)"); ax.set_ylabel("Temp (℃)"); ax.grid(True, ls='--', alpha=0.3); st.pyplot(fig)

# =========================================================
# 7. 결과 분석 및 저장 (대표님 요청 QC 리포트)
# =========================================================
if not is_analysis_mode and st.session_state.points:
    st.subheader("3. 결과 분석 및 저장 (Result & QC)")
    df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c_f = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r.get('Event', ""))[0]), None)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        rw = st.number_input("배출 무게 (g)", 0.0)
        if rw > 0 and green_weight > 0:
            lw = green_weight - rw; last_t = df_f.iloc[-1]['Temp']
            q = (lw*2260 + rw*1.6*(last_t-25))/1000
            st.info(f"🔥 흡수 열량: {q:.1f} kJ")
            st.metric("수율 (Yield)", f"{(rw/green_weight)*100:.1f}%")

    with c2:
        if t_1c_f:
            total_t = df_f.iloc[-1]['Time']
            dtr = ((total_t - t_1c_f) / total_t) * 100
            st.markdown(f"<div style='background-color:#f9fdf9; padding:15px; border-radius:10px; border:2px solid #228B22;'><strong>📊 DTR: {dtr:.1f}%</strong><br>{get_dtr_feedback(dtr)}</div>", unsafe_allow_html=True)

    with c3:
        note = st.text_input("비고 (이용 열량 필수 기재)")
        if st.button("💾 최종 저장 및 데이터베이스 기록", type="primary", use_container_width=True):
            df_f['Roast_ID'] = roast_id
            df_f.to_csv(DEFAULT_DATA_FILE, mode='a', header=not os.path.exists(DEFAULT_DATA_FILE), index=False, encoding='utf-8-sig')
            st.success("저장 완료!"); st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()

    c1, c2 = st.sidebar.columns(2)
    with c1: st.link_button("🛍️ 스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
    with c2: st.link_button("📷 인스타", "https://instagram.com/perucoffee.origins", use_container_width=True)
