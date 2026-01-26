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

# 한글 폰트 설정 (깨짐 방지 강화)
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

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "pop", "1차"]) and not ("end" in e or "종료" in e)
    is_1c_end = any(k in e for k in ["1c end", "1차 팝 종료", "end"])
    is_2c = any(k in e for k in ["2c", "2차", "second"])
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
            if "원두" in line or "bean" in line.lower():
                parts = [p.strip() for p in re.split(r"[,\t;]", line)]
                if len(parts) > 1: extracted_id = parts[1]
            for d in [",", "\t", ";"]:
                cells = [c.strip().lower() for c in line.split(d)]
                if any("time" in c for c in cells) and any("temp" in c for c in cells):
                    header_row_idx, delimiter = i, d; break
            if header_row_idx is not None: break
        if header_row_idx is None: return None
        df = pd.read_csv(io.StringIO("\n".join(lines[header_row_idx:])), delimiter=delimiter)
        col_map = {c: ("Time" if "time" in c.lower() else "Temp" if "temp" in c.lower() else "Gas" if "gas" in c.lower() else "Event" if "event" in c.lower() else c) for c in df.columns}
        df.rename(columns=col_map, inplace=True)
        # ID 중복 방지를 위해 파일명 결합
        clean_name = file_name_fallback.replace(".csv", "")
        df["Roast_ID"] = f"{extracted_id}({clean_name})" if extracted_id else clean_name
        return df
    except: return None

def get_template_csv():
    return """파일 이름,Sample_01\n날짜,2026-Jan-01\n원두 이름,Geisha\n로스터 이름,Sample Roaster\n방식,드럼\n결과무게,215\n비고,템플릿\n\nTime(sec),Temp(C),Gas,Event\n0,200,0.0,Preheat\n30,200,0.5,Charge\n60,90,5.0,TP\n300,150,4.0,Yellowing\n540,192,2.0,1C Start\n630,205,0,Drop\n"""

# =========================================================
# 4. 사이드바 구성
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("### PERU COFFEE ORIGINS")
st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**")

mode = st.sidebar.radio("모드 선택", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

# 변수 선언 (에러 방지)
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
# 5. 핵심 그래프 엔진 (버그 수정 완료)
# =========================================================
def plot_professional_roast(df, ax, color, label, is_main=True, fill_style=True):
    # 데이터 정렬 및 초기화
    df = df.sort_values('Time').reset_index(drop=True)
    
    # 1차 팝 시점 찾기
    t_1c = None
    for _, r in df.iterrows():
        # check_is_crack 함수 결과의 첫번째 값(is_1c)이 True인 경우
        if check_is_crack(str(r.get('Event', "")))[0]:
            t_1c = r['Time']
            break

    # [수정] 1차 팝 전/후 데이터 분리 로직 강화
    if t_1c is not None:
        pre_df = df[df['Time'] <= t_1c]
        post_df = df[df['Time'] >= t_1c]
    else:
        pre_df = df # 1차 팝이 없으면 전체가 전반부
        post_df = pd.DataFrame() # 빈 데이터프레임

    # 1. 1차 팝 이전: 점만 표시 (교차 스타일 적용)
    for i, (_, row) in enumerate(pre_df.iterrows()):
        # 교차 스타일: fill_style이 True면 채움, False면 비움
        m_face = color if fill_style else 'none'
        ax.scatter(row['Time'], row['Temp'], marker='o', edgecolors=color, 
                   facecolors=m_face, s=50, alpha=0.8, zorder=3)

    # 2. 1차 팝 이후: 굵은 실선으로 연결 + 교차 점
    if not post_df.empty:
        # 선 그리기 (범례 표시를 위해 label은 여기서만 사용)
        ax.plot(post_df['Time'], post_df['Temp'], color=color, lw=4 if is_main else 2, alpha=0.8, label=label, zorder=2)
        # 선 위의 점 그리기
        for i, (_, row) in enumerate(post_df.iterrows()):
            m_face = color if fill_style else 'none'
            ax.scatter(row['Time'], row['Temp'], marker='o', edgecolors=color, 
                       facecolors=m_face, s=60, alpha=0.9, zorder=3)
    else:
        # 1차 팝이 없어도 범례(Legend)가 나오도록 투명 선 추가
        ax.plot(df['Time'], df['Temp'], color=color, lw=0, label=label)

    # 3. 특수 이벤트 강조
    for _, row in df.iterrows():
        e = str(row.get('Event', ""))
        if not e or e.lower() in ["nan", "none", ""]: continue
        
        is1s, is1e, is2s = check_is_crack(e)
        t_lbl = format_mmss(row['Time'])
        
        if is1s: 
            ax.scatter(row['Time'], row['Temp'], marker='*', s=500, color='#f1c40f', edgecolors='black', zorder=10)
            ax.annotate(f"★ 1C ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color='#f39c12')
        elif is1e: 
            ax.annotate(f"1C End ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, -25), textcoords='offset points', ha='center', color='#d35400', fontsize=9)
        elif is2s: 
            ax.annotate(f"2C ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color='#8e44ad')
        elif is_drop_event(e): 
            ax.annotate(f"DROP ({t_lbl})", (row['Time'], row['Temp']), xytext=(15, 0), textcoords='offset points', va='center', weight='bold', color='red')
        elif is_main: 
            ax.annotate(e, (row['Time'], row['Temp']), xytext=(0, 15), textcoords='offset points', ha='center', fontsize=8, alpha=0.7)

# =========================================================
# 6. 모드별 실행 로직
# =========================================================
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.multiselect(f"비교 분석할 그래프 선택 ({len(uids)}개)", uids)
        if selected_ids:
            fig, ax1 = plt.subplots(figsize=(12, 7))
            colors = plt.cm.tab10.colors
            
            for i, rid in enumerate(selected_ids):
                target_df = full_df[full_df['Roast_ID'] == rid]
                # ✅ 마커 교차 스타일: i가 짝수면 채움(True), 홀수면 비움(False)
                fill = (i % 2 == 0)
                plot_professional_roast(target_df, ax1, colors[i%10], rid, is_main=True, fill_style=fill)
            
            ax1.set_xlabel("Time (s)"); ax1.set_ylabel("Temp (℃)")
            ax1.grid(True, ls='--', alpha=0.3)
            # ✅ 범례 위치: 오른쪽 아래 (lower right)
            ax1.legend(loc='lower right', title="Roast Profiles")
            st.pyplot(fig)
    else: st.info("데이터가 없습니다. CSV 파일을 업로드하세요.")

else:
    st.title("🔥 Professional Roasting Log")
    ref_id = None
    if not full_df.empty:
        ref_id = st.sidebar.selectbox("📉 배경 레퍼런스", ["(선택 안 함)"] + list(full_df['Roast_ID'].unique()))

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        intl_date = get_intl_date_str()
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        bean_name = r1c1.text_input("원두 이름", "Geisha")
        roast_id = r1c2.text_input("ID", f"{bean_name}_{intl_date}")
        roaster_name = r1c3.text_input("로스터", "")
        method = r1c4.selectbox("방식", ["드럼", "열풍", "하이브리드", "직화"])
        r2c1, r2c2 = st.columns(2)
        initial_temp = r2c1.number_input("투입온도 (℃)", value=200)
        # ✅ 생두 무게 0.1g 단위 적용
        green_weight = r2c2.number_input("생두 무게 (g)", value=250.0, step=0.1, format="%.1f")

    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Double Timer)")
        now_ts = time.time()
        elapsed_all = int(now_ts - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
        elapsed_split = int(now_ts - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

        t1, t2, t3 = st.columns([1, 2, 2])
        if st.session_state.timer_state == "idle":
            if t1.button("▶️ START", type="primary", use_container_width=True):
                st.session_state.start_time = now_ts; st.session_state.last_record_time = now_ts
                st.session_state.timer_state = "running"
                st.session_state.points = [{"Time": 0, "Temp": int(initial_temp), "Gas": 0.0, "Event": "Charge"}]
                st.rerun()
        else:
            if t1.button("⏹️ RESET", use_container_width=True):
                st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()

        t2.metric("⏳ 전체 시간", format_mmss(elapsed_all))
        t3.metric("⏱️ 구간 시간", format_mmss(elapsed_split))

        with st.form("rec", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
            cur_t = f1.number_input("온도", 0, 300, int(initial_temp), disabled=(st.session_state.timer_state!="running"))
            cur_g = f2.number_input("가스", 0.0, 15.0, step=0.1, disabled=(st.session_state.timer_state!="running"))
            cur_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"], disabled=(st.session_state.timer_state!="running"))
            if f4.form_submit_button("기록", use_container_width=True):
                st.session_state.last_record_time = time.time()
                rec_t = int(st.session_state.last_record_time - st.session_state.start_time)
                st.session_state.points.append({"Time": rec_t, "Temp": cur_t, "Gas": cur_g, "Event": cur_e if cur_e != "기록" else None})
                if is_drop_event(cur_e):
                    st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
                st.rerun()
    else:
        st.subheader("2. 수동 기록 (Manual)")
        # (수동 로직 기존 유지)
        m1, m2, m3, m4, m5 = st.columns([1, 1, 1, 2, 1])
        t_sec = m1.number_input("분", 0) * 60 + m1.number_input("초", 0)
        temp = m2.number_input("온도", 0, 300, int(initial_temp))
        gas = m3.number_input("가스", 0.0, 15.0, step=0.1)
        evt = m4.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"])
        if m5.button("추가", type="primary"):
            st.session_state.points.append({"Time": t_sec, "Temp": temp, "Gas": gas, "Event": evt if evt != "기록" else None})

    # 그래프
    if st.session_state.points:
        st.write("---")
        fig, ax = plt.subplots(figsize=(12, 7))
        if ref_id and ref_id != "(선택 안 함)":
            plot_professional_roast(full_df[full_df['Roast_ID']==ref_id], ax, "gray", f"Ref: {ref_id}", is_main=False, fill_style=False)
        plot_professional_roast(pd.DataFrame(st.session_state.points), ax, "#c0392b", "Current", is_main=True, fill_style=True)
        ax.set_xlabel("Time (s)"); ax.set_ylabel("Temp (℃)"); ax.grid(True, ls='--', alpha=0.3); ax.legend(loc='lower right')
        st.pyplot(fig)

# =========================================================
# 7. QC 결과 분석 및 저장
# =========================================================
if not is_analysis_mode and st.session_state.points:
    st.markdown("---")
    st.subheader("3. 품질 분석 및 결과 저장")
    df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c_f = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r.get('Event', ""))[0]), None)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        rw = st.number_input("배출 무게 (g)", 0.0, step=0.1, format="%.1f")
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
        if st.checkbox("아그트론 사진 분석"):
            st.info("색상표와 함께 촬영"); st.camera_input("촬영")
        note = st.text_input("비고 (이용 열량 필수)")
        if st.button("💾 최종 저장", type="primary", use_container_width=True):
            df_f['Roast_ID'] = roast_id
            df_f.to_csv(DEFAULT_DATA_FILE, mode='a', header=not os.path.exists(DEFAULT_DATA_FILE), index=False, encoding='utf-8-sig')
            st.success("저장 완료!"); st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()
