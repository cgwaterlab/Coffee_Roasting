import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os
from datetime import datetime
import io
import re
import csv
import time
import numpy as np
from PIL import Image

# ✅ 실시간 갱신 라이브러리 체크
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 디자인
# =========================================================
LOGO_PATH = "pco_logo.png" 
st.set_page_config(page_title="Roasting Analysis Center Pro", layout="wide", page_icon="☕")

# 한글 폰트 설정
def set_korean_font():
    font_names = [f.name for f in fm.fontManager.ttflist]
    if 'Malgun Gothic' in font_names: plt.rcParams['font.family'] = 'Malgun Gothic'
    elif 'AppleGothic' in font_names: plt.rcParams['font.family'] = 'AppleGothic'
    elif 'NanumGothic' in font_names: plt.rcParams['font.family'] = 'NanumGothic'
    else: pass 
    plt.rcParams['axes.unicode_minus'] = False

set_korean_font()
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

def get_intl_date_str():
    now = datetime.now()
    return f"{now.year}{now.month:02d}{now.day:02d}"

# ✅ [수정] 이벤트 감지 로직 강화 (다양한 표현 수용)
def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    # 1차 팝: 1c, 1st, pop, first 등의 단어가 포함되면 인정
    is_1c = any(k in e for k in ["1c", "1st", "pop", "first", "1차"]) and not ("end" in e or "종료" in e)
    is_1c_end = any(k in e for k in ["1c end", "1차 팝 종료", "end", "휴지기"])
    is_2c = any(k in e for k in ["2c", "2차", "second"])
    return is_1c, is_1c_end, is_2c

def is_drop_event(e: str) -> bool:
    if not e: return False
    s = str(e).lower().strip()
    return ("drop" in s) or ("배출" in s)

def get_dtr_feedback(dtr):
    leaf_green = "#228B22" 
    if dtr < 10: msg = "⚠️ 언더 디벨롭 (Under Developed)"
    elif dtr <= 15: msg = "🍓 노르딕/라이트 (Light)"
    elif dtr <= 20: msg = "⚖️ 미디엄/밸런스 (Medium)"
    elif dtr <= 25: msg = "🍫 미디엄 다크 (Medium Dark)"
    else: msg = "🔥 다크 (Dark)"
    return f"<span style='color:{leaf_green}; font-weight:bold; font-size:1.1em;'>{msg}</span>"

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
        col_map = {c: ("Time" if "time" in c.lower() else "Temp" if "temp" in c.lower() else "Gas" if "gas" in c.lower() else "Event" if "event" in c.lower() else c) for c in df.columns}
        df.rename(columns=col_map, inplace=True)
        clean_name = file_name_fallback.replace(".csv", "")
        df["Roast_ID"] = f"{extracted_id}({clean_name})" if extracted_id else clean_name
        return df
    except: return None

def get_template_csv():
    return """파일 이름,Sample_01\n날짜,2026-Jan-01\n원두 이름,Geisha\n로스터 이름,Sample Roaster\n방식,드럼\n결과무게,215\n비고,템플릿\n\nTime(sec),Temp(C),Gas,Event\n0,200,0.0,Preheat\n30,200,0.5,Charge\n60,90,5.0,TP\n300,150,4.0,Yellowing\n540,192,2.0,1C Start\n630,205,0,Drop\n"""

# =========================================================
# 4. 사이드바
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("### PERU COFFEE ORIGINS")
st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**")

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

c1, c2 = st.sidebar.columns(2)
with c1: st.link_button("🛍️ 스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with c2: st.link_button("📷 인스타", "https://instagram.com/perucoffee.origins", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("🛠️ 유틸리티")
u1, u2 = st.sidebar.columns(2)
with u1: st.download_button("📥 템플릿", get_template_csv().encode('utf-8-sig'), "template.csv", "text/csv", use_container_width=True)
with u2: st.link_button("⚡ Web Log", "https://roastinglog.netlify.app/", use_container_width=True)

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
# 5. [전문가용] 분석 엔진 (그래프 그리기 로직 개선)
# =========================================================
def plot_advanced_analysis(selected_ids, full_db):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True, height_ratios=[3, 1])
    plt.subplots_adjust(hspace=0.05)
    
    ax1_gas = ax1.twinx()
    ax2_energy = ax2.twinx()
    
    colors = plt.cm.tab10.colors
    phase_data = [] 

    for i, rid in enumerate(selected_ids):
        df = full_db[full_db['Roast_ID'] == rid].sort_values('Time').reset_index(drop=True)
        if df.empty: continue
        
        color = colors[i % 10]
        fill_style = (i % 2 == 0)

        # --- 1. 상단: 온도 프로파일 ---
        t_1c = None
        t_yellow = None
        t_drop = df.iloc[-1]['Time']
        
        for _, r in df.iterrows():
            evt = str(r.get('Event', "")).lower()
            if check_is_crack(evt)[0] and t_1c is None: t_1c = r['Time']
            if "yellow" in evt and t_yellow is None: t_yellow = r['Time']

        # ✅ [수정] 1차 팝이 감지되지 않아도 그래프가 끊기지 않도록 처리
        if t_1c is None:
            # 1차 팝이 없으면 전체를 하나의 실선으로 그림
            ax1.plot(df['Time'], df['Temp'], color=color, lw=2, alpha=0.7, label=rid)
            # 점은 교차 스타일로
            m_face = color if fill_style else 'none'
            ax1.scatter(df['Time'], df['Temp'], marker='o', edgecolors=color, facecolors=m_face, s=40, alpha=0.6)
        else:
            # 1차 팝이 있으면: 전반부(점) + 후반부(굵은 선)
            pre_df = df[df['Time'] <= t_1c]
            post_df = df[df['Time'] >= t_1c]
            
            # 전반부 (점)
            m_face = color if fill_style else 'none'
            ax1.scatter(pre_df['Time'], pre_df['Temp'], marker='o', edgecolors=color, facecolors=m_face, s=40, alpha=0.7)
            
            # 후반부 (선 + 별표)
            ax1.plot(post_df['Time'], post_df['Temp'], color=color, lw=3, label=rid)
            r_1c = df[df['Time'] == t_1c].iloc[0]
            ax1.scatter(r_1c['Time'], r_1c['Temp'], marker='*', s=350, color=color, edgecolors='black', zorder=10)

        # 가스 압력 (계단식)
        if 'Gas' in df.columns:
            ax1_gas.plot(df['Time'], df['Gas'], color=color, linestyle=':', alpha=0.5, lw=1.5, drawstyle='steps-post')

        # 이벤트 텍스트
        for _, row in df.iterrows():
            e = str(row.get('Event', ""))
            if not e or e.lower() in ["nan", "none", "", "null"]: continue
            is1s, is1e, is2s = check_is_crack(e)
            t_lbl = format_mmss(row['Time'])
            if is1s: 
                ax1.annotate(f"★ 1C ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color=color)
            elif is_drop_event(e): 
                ax1.annotate(f"DROP", (row['Time'], row['Temp']), xytext=(10, 0), textcoords='offset points', va='center', weight='bold', color='red')
            else: 
                ax1.annotate(e, (row['Time'], row['Temp']), xytext=(0, 10), textcoords='offset points', ha='center', fontsize=8, alpha=0.8, color='black')

        # --- 2. 하단: RoR 곡선 ---
        df['dt'] = df['Time'].diff()
        df['dTemp'] = df['Temp'].diff()
        df['RoR'] = (df['dTemp'] / df['dt']) * 60
        df['RoR_Smooth'] = df['RoR'].rolling(window=3, center=True).mean()
        ax2.plot(df['Time'], df['RoR_Smooth'], color=color, lw=1.5, alpha=0.8)
        
        # 에너지 그래프 (속 빈 삼각형)
        mass_series = np.linspace(250, 215, len(df)) # 간이 질량 모델
        energy_series = (mass_series * 1.6 * (df['Temp'] - 25)) / 1000
        ax2_energy.scatter(df['Time'][::15], energy_series[::15], marker='^', color='none', edgecolors=color, s=30, alpha=0.6, label='Energy')

        # --- 3. 구간 분석 ---
        p_row = {"ID": rid, "Drying": "-", "Maillard": "-", "Development": "-", "Total Time": format_mmss(t_drop)}
        if t_yellow and t_1c:
            drying_t = t_yellow; maillard_t = t_1c - t_yellow; dev_t = t_drop - t_1c
            p_row["Drying"] = f"{format_mmss(drying_t)} ({drying_t/t_drop*100:.1f}%)"
            p_row["Maillard"] = f"{format_mmss(maillard_t)} ({maillard_t/t_drop*100:.1f}%)"
            p_row["Development"] = f"{format_mmss(dev_t)} ({dev_t/t_drop*100:.1f}%)"
        elif not t_yellow: p_row["Drying"] = "Yellowing 없음"
        elif not t_1c: p_row["Development"] = "1C Start 없음"
        phase_data.append(p_row)

    ax1.set_ylabel("Temp (℃)"); ax1.legend(loc='lower right', title="Roast Profiles"); ax1.grid(True, ls='--', alpha=0.3)
    ax1_gas.set_ylabel("Gas (kPa)"); ax1_gas.set_ylim(0, 15)
    ax2.set_ylabel("RoR (℃/min)"); ax2.set_xlabel("Time (seconds)"); ax2.set_ylim(0, 30); ax2.grid(True, ls='--', alpha=0.3)
    ax2_energy.set_ylabel("Energy (kJ)"); 
    st.pyplot(fig)
    
    if phase_data:
        st.markdown("##### 📊 구간별 분석 (Phase Breakdown)")
        st.table(pd.DataFrame(phase_data).set_index("ID"))

# =========================================================
# 6. 실시간 로스팅 그래프
# =========================================================
def plot_realtime_roast(df, ax, color, label, is_main=True):
    df = df.sort_values('Time')
    t_1c = None
    for _, r in df.iterrows():
        if check_is_crack(r.get('Event', ""))[0]: t_1c = r['Time']; break
    
    pre = df[df['Time'] <= (t_1c if t_1c else 9999)]
    ax.scatter(pre['Time'], pre['Temp'], c=color, s=50, alpha=0.7)
    
    if t_1c:
        post = df[df['Time'] >= t_1c]
        ax.plot(post['Time'], post['Temp'], c=color, lw=4, label=label)
        r1c = df[df['Time']==t_1c].iloc[0]
        ax.scatter(r1c['Time'], r1c['Temp'], marker='*', s=500, c='gold', edgecolors='black', zorder=10)
    
    if is_main and len(df) > 1:
        ax_gas = ax.twinx(); ax_gas.set_ylim(0, 15); ax_gas.set_ylabel("Gas", color='blue')
        ax_gas.plot(df['Time'], df['Gas'], color='blue', linestyle=':', label='Gas', alpha=0.6, drawstyle='steps-post')
        for _, row in df.iterrows():
            e = str(row.get('Event', ""))
            if e and e.lower() not in ["nan", "none", "", "기록"]:
                ax.annotate(e, (row['Time'], row['Temp']), xytext=(0, 15), textcoords='offset points', ha='center')

# =========================================================
# 7. 메인 실행 로직
# =========================================================
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.multiselect("비교 분석할 Roast ID 선택", uids)
        if selected_ids:
            plot_advanced_analysis(selected_ids, full_df)
    else: st.info("데이터가 없습니다.")

else:
    st.title("🔥 Professional Roasting Log")
    ref_id = None
    if not full_df.empty:
        ref_id = st.sidebar.selectbox("📉 배경 레퍼런스", ["(없음)"] + list(full_df['Roast_ID'].unique()))

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        intl_date = get_intl_date_str()
        r1, r2, r3, r4 = st.columns(4)
        bean_name = r1.text_input("원두명", "Geisha")
        roast_id = r2.text_input("ID", f"{bean_name}_{intl_date}")
        roaster_name = r3.text_input("로스터", "")
        method_opts = ["Drum (드럼)", "Hot Air (열풍)", "Hybrid (하이브리드)", "Direct Fire (직화)", "Handy Roaster (핸디)", "Mesh (수망)", "Other"]
        method = r4.selectbox("방식", method_opts)
        c1, c2 = st.columns(2)
        init_temp = c1.number_input("투입온도(℃)", 200)
        green_weight = c2.number_input("생두무게(g)", min_value=0.0, value=250.0, step=0.1, format="%.1f")

    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Double Timer)")
        now = time.time()
        el_all = int(now - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
        el_spl = int(now - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0
        
        b1, b2, b3 = st.columns([1, 2, 2])
        if st.session_state.timer_state == "idle":
            if b1.button("▶️ START", type="primary"):
                st.session_state.start_time = now; st.session_state.last_record_time = now
                st.session_state.timer_state = "running"
                st.session_state.points = [{"Time": 0, "Temp": int(init_temp), "Gas": 0.0, "Event": "Charge"}]
                st.rerun()
        else:
            if b1.button("⏹️ RESET"):
                st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()
        
        b2.metric("⏳ 전체 시간", format_mmss(el_all))
        b3.metric("⏱️ 구간 시간", format_mmss(el_spl))

        st.write("---")
        can_rec = (st.session_state.timer_state == "running")
        f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
        cur_t = f1.number_input("온도", 0, 300, int(init_temp), disabled=not can_rec, label_visibility="collapsed", placeholder="온도")
        cur_g = f2.number_input("가스", 0.0, 15.0, step=0.1, disabled=not can_rec, label_visibility="collapsed", placeholder="가스")
        cur_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"], disabled=not can_rec, label_visibility="collapsed")
        
        if f4.button("🔴 기록", type="primary", use_container_width=True, disabled=not can_rec):
            st.session_state.last_record_time = time.time()
            rec_t = int(st.session_state.last_record_time - st.session_state.start_time)
            st.session_state.points.append({"Time": rec_t, "Temp": cur_t, "Gas": cur_g, "Event": cur_e if cur_e != "기록" else None})
            if is_drop_event(cur_e):
                st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
            st.rerun()
    else:
        st.subheader("2. 수동 기록")
        m1, m2, m3, m4, m5 = st.columns([1, 1, 2, 2, 1])
        t_sec = m1.number_input("분", 0) * 60 + m1.number_input("초", 0)
        temp = m2.number_input("온도", 0, 300, int(init_temp))
        gas = m3.number_input("가스", 0.0, 15.0, step=0.1)
        evt = m4.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"])
        if m5.button("➕ 추가", type="primary", use_container_width=True):
            st.session_state.points.append({"Time": t_sec, "Temp": temp, "Gas": gas, "Event": evt if evt != "기록" else None})

    if st.session_state.points:
        st.write("---")
        fig, ax = plt.subplots(figsize=(12, 7))
        if ref_id and ref_id != "(없음)":
            plot_realtime_roast(full_df[full_df['Roast_ID']==ref_id], ax, "gray", "Ref", False)
        plot_realtime_roast(pd.DataFrame(st.session_state.points), ax, "#c0392b", "Current", True)
        ax.set_xlabel("Time (s)"); ax.set_ylabel("Temp (℃)"); ax.grid(True, ls='--', alpha=0.3)
        st.pyplot(fig)

# =========================================================
# 8. QC 결과 저장
# =========================================================
if not is_analysis_mode and st.session_state.points:
    st.markdown("---")
    st.subheader("3. 결과 분석 및 저장")
    df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c_f = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r.get('Event', ""))[0]), None)

    c1, c2, c3 = st.columns([1, 2, 1])
    # 미리 계산 (비고란 자동완성용)
    q_val = 0.0; yield_val = 0.0; rw = 0.0
    
    with c1:
        rw = st.number_input("배출 무게 (g)", min_value=0.0, value=0.0, step=0.1, format="%.1f")
        if rw > 0 and green_weight > 0:
            q_val = ((green_weight-rw)*2260 + rw*1.6*(df_f.iloc[-1]['Temp']-25))/1000
            yield_val = (rw/green_weight)*100
            st.info(f"🔥 흡수 열량: {q_val:.1f} kJ")
            st.metric("수율", f"{yield_val:.1f}%")

    with c2:
        if t_1c_f:
            dtr = ((df_f.iloc[-1]['Time'] - t_1c_f) / df_f.iloc[-1]['Time']) * 100
            st.markdown(f"<div style='background-color:#f9fdf9; padding:10px; border:2px solid #228B22;'><strong>📊 DTR: {dtr:.1f}%</strong><br>{get_dtr_feedback(dtr)}</div>", unsafe_allow_html=True)
    
    with c3:
        if st.checkbox("아그트론 분석"):
            st.info("촬영 가이드: 색상표 포함"); st.camera_input("촬영")
        
        auto_note = ""
        if rw > 0: auto_note = f"[시스템 기록] 수율: {yield_val:.1f}% | 열량: {q_val:.1f}kJ | 수분감소: {100-yield_val:.1f}%"
        note = st.text_area("비고 (자동계산 + 메모)", value=auto_note, height=100)
        
        if st.button("💾 저장", type="primary"):
            df_f['Roast_ID'] = roast_id
            df_f['Note'] = note
            df_f.to_csv(DEFAULT_DATA_FILE, mode='a', header=not os.path.exists(DEFAULT_DATA_FILE), index=False, encoding='utf-8-sig')
            st.success("완료!"); st.session_state.points=[]; st.session_state.timer_state="idle"; st.rerun()
