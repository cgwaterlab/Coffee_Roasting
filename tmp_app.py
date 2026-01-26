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

# ✅ 실시간 갱신 필수 라이브러리
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("라이브러리 미설치: 터미널에서 'pip install streamlit-autorefresh'를 실행해 주세요.")

# =========================================================
# 1. 설정 및 디자인 스타일
# =========================================================
LOGO_PATH = "pco_logo.png" 
st.set_page_config(page_title="Roasting Analysis Center", layout="wide", page_icon="☕")

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# =========================================================
# 2. 세션 상태 초기화 (시계 및 데이터 관리)
# =========================================================
if 'points' not in st.session_state: st.session_state.points = []
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'last_record_time' not in st.session_state: st.session_state.last_record_time = None
if 'timer_state' not in st.session_state: st.session_state.timer_state = "idle" 
if 'stop_elapsed' not in st.session_state: st.session_state.stop_elapsed = 0

# 타이머 작동 시 1초마다 자동 새로고침
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
    if seconds is None or seconds < 0: return "0:00"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"

def check_is_crack(event_str):
    e = str(event_str).lower().strip()
    is_1c = any(k in e for k in ["1c start", "1st pop", "1차 팝 시작", "1c s"])
    is_1c_end = any(k in e for k in ["1c end", "1차 팝 종료", "1c e"])
    is_2c = any(k in e for k in ["2c", "2차 팝", "second pop", "2c s"])
    return is_1c, is_1c_end, is_2c

def get_dtr_feedback(dtr):
    leaf_green = "#228B22" 
    if dtr < 10: msg = "⚠️ 언더 디벨롭 (Under Developed): 풋내나 떫은 맛이 날 수 있어요. 시간을 조금 더 늘려보세요."
    elif dtr <= 15: msg = "🍓 노르딕/라이트 (Light): 꽃향기와 화사한 산미, 차(Tea) 같은 깔끔함이 특징이에요."
    elif dtr <= 20: msg = "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 황금 비율이에요! (추천)"
    elif dtr <= 25: msg = "🍫 미디엄 다크 (Medium Dark): 산미는 줄고 바디감과 초콜릿 향이 살아나요."
    else: msg = "🔥 다크 (Dark): 묵직한 바디감, 스모키함, 쌉쌀한 맛이 강조돼요."
    return f"<span style='color:{leaf_green}; font-weight:bold; font-size:1.1em;'>{msg}</span>"

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
# 4. 핵심 그래프 시각화 엔진 (요청하신 디테일 반영)
# =========================================================
def plot_professional_roast(df, ax, color, label, is_main=True, fill_style=True):
    df = df.sort_values('Time').copy()
    t_1c = None
    for _, r in df.iterrows():
        if check_is_crack(r.get('Event', ""))[0] and t_1c is None:
            t_1c = r['Time']; break

    # 1. 1차 팝 전: 선 없이 점만 표시 (교차 스타일)
    pre_df = df[df['Time'] <= (t_1c if t_1c is not None else 99999)]
    ax.scatter(pre_df['Time'], pre_df['Temp'], marker='o', edgecolors=color, 
               facecolors=color if fill_style else 'none', s=50, alpha=0.8, zorder=3)

    # 2. 1차 팝 후: 굵은 실선으로 연결 + 교차 점
    if t_1c is not None:
        post_df = df[df['Time'] >= t_1c]
        ax.plot(post_df['Time'], post_df['Temp'], color=color, lw=5 if is_main else 2, alpha=0.7, label=label, zorder=2)
        ax.scatter(post_df['Time'], post_df['Temp'], marker='o', edgecolors=color, 
                   facecolors=color if fill_style else 'none', s=60, alpha=0.9, zorder=3)

    # 3. 특수 이벤트 강조 및 텍스트 (NaN 제거)
    for _, row in df.iterrows():
        e = str(row.get('Event', ""))
        if not e or e.lower() in ["nan", "none", ""]: continue
        
        is1s, is1e, is2s = check_is_crack(e)
        t_lbl = format_mmss(row['Time'])
        
        if is1s: # 1차 팝 시작 (황금 별표)
            ax.scatter(row['Time'], row['Temp'], marker='*', s=600, color='#f1c40f', edgecolors='black', zorder=10)
            ax.annotate(f"★ 1C Start ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 25), 
                         textcoords='offset points', ha='center', weight='bold', color='#f39c12')
        elif is1e: # 1차 팝 종료
            ax.annotate(f"1C End ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, -30), 
                         textcoords='offset points', ha='center', color='#d35400', fontsize=9)
        elif is2s: # 2차 팝 시작
            ax.annotate(f"2C Start ({t_lbl})", (row['Time'], row['Temp']), xytext=(0, 20), 
                         textcoords='offset points', ha='center', weight='bold', color='#8e44ad')
        elif is_drop_event(e): # 배출
            ax.annotate(f"DROP ({t_lbl})", (row['Time'], row['Temp']), xytext=(20, 0), 
                         textcoords='offset points', va='center', weight='bold', color='red')
        else: # 일반 이벤트 (TP, Yellow)
            if is_main: ax.annotate(e, (row['Time'], row['Temp']), xytext=(0, 15), 
                                     textcoords='offset points', ha='center', fontsize=8, alpha=0.7)

# =========================================================
# 5. 사이드바 구성 (기존 링크 복구)
# =========================================================
if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, use_container_width=True)
    st.sidebar.markdown("### PERU COFFEE ORIGINS")
else:
    st.sidebar.markdown("## PERU COFFEE ORIGINS")

st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**")

mode = st.sidebar.radio("모드 선택 (Mode)", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=0)

c1, c2 = st.sidebar.columns(2)
with c1: st.link_button("🛍️ 스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with c2: st.link_button("📷 인스타", "https://instagram.com/perucoffee.origins", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("🛠️ 유틸리티")
u1, u2 = st.sidebar.columns(2)
with u1: st.sidebar.download_button("📥 템플릿", get_template_csv().encode('utf-8-sig'), "template.csv", "text/csv", use_container_width=True)
with u2: st.sidebar.link_button("⚡ Web Logger", "https://roastinglog.netlify.app/", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("📂 레퍼런스 센터")

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

is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

# =========================================================
# 6. 모드별 메인 로직
# =========================================================
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids = st.sidebar.multiselect(f"비교할 그래프 선택 ({len(uids)}개)", uids)
        if selected_ids:
            fig, ax1 = plt.subplots(figsize=(12, 7))
            colors = plt.cm.tab10.colors
            for i, rid in enumerate(selected_ids):
                target_df = full_df[full_df['Roast_ID'] == rid]
                plot_professional_roast(target_df, ax1, colors[i%10], rid, is_main=True, fill_style=(i%2==0))
            ax1.set_xlabel("Time (s)"); ax1.set_ylabel("Temp (℃)"); ax1.grid(True, ls='--', alpha=0.3)
            ax1.legend(loc='upper left', title="파일 이름 (Legend)")
            st.pyplot(fig)
    else: st.info("데이터가 없습니다. CSV 파일을 업로드하세요.")

else:
    st.title("🔥 Professional Coffee Roasting Log")
    ref_id = None
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_choice = st.sidebar.selectbox("📉 배경 레퍼런스 선택", ["(선택 안 함)"] + uids)
        if ref_choice != "(선택 안 함)": ref_id = ref_choice

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        intl_date = get_intl_date_str()
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        bean_name = r1c1.text_input("원두 이름", value="Geisha")
        roast_id = r1c2.text_input("ID", value=f"{bean_name}_{intl_date}")
        roaster_name = r1c3.text_input("로스터 이름", value="")
        method = r1c4.selectbox("방식", ["드럼 (Drum)", "열풍 (Hot Air)", "하이브리드 (Hybrid)", "직화 (Direct Fire)"])
        r2c1, r2c2 = st.columns(2)
        initial_temp = r2c1.number_input("투입온도 (℃)", value=200)
        # ✅ 생두 무게 0.1g 단위로 변경 (step=0.1)
        green_weight = r2c2.number_input("생두 무게 (g)", value=250.0, step=0.1, format="%.1f")

    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        now_ts = time.time()
        elapsed_all = int(now_ts - st.session_state.start_time) if st.session_state.timer_state == "running" else st.session_state.stop_elapsed
        elapsed_split = int(now_ts - st.session_state.last_record_time) if (st.session_state.timer_state == "running" and st.session_state.last_record_time) else 0

        t_col1, t_col2, t_col3 = st.columns([1, 2, 2])
        with t_col1:
            if st.session_state.timer_state == "idle":
                if st.button("▶️ START", type="primary", use_container_width=True):
                    st.session_state.start_time = now_ts; st.session_state.last_record_time = now_ts
                    st.session_state.timer_state = "running"
                    st.session_state.points = [{"Time": 0, "Temp": int(initial_temp), "Gas": 0.0, "Event": "Charge"}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET", use_container_width=True):
                    st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()

        t_col2.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
        t_col3.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split))

        with st.form("auto_rec", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns([1, 1, 2, 1])
            cur_t = f1.number_input("온도", 0, 300, int(initial_temp))
            cur_g = f2.number_input("가스", 0.0, 15.0, step=0.1)
            cur_e = f3.selectbox("이벤트", ["기록", "TP", "Yellowing", "1C Start", "1C End", "2C", "Drop"])
            if f4.form_submit_button("기록 (Enter)", use_container_width=True):
                st.session_state.last_record_time = time.time()
                rec_t = int(st.session_state.last_record_time - st.session_state.start_time)
                st.session_state.points.append({"Time": rec_t, "Temp": cur_t, "Gas": cur_g, "Event": cur_e if cur_e != "기록" else None})
                if is_drop_event(cur_e):
                    st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
                st.rerun()
    else: # Manual Mode
        st.subheader("2. 수동 기록 (Manual)")
        # ... (수동 기록 로직 기존 유지)

    # 그래프 출력 (실시간/수동 공용)
    if st.session_state.points:
        st.write("---")
        fig, ax = plt.subplots(figsize=(12, 7))
        if ref_id and ref_id != "(선택 안 함)":
            plot_professional_roast(full_df[full_df['Roast_ID']==ref_id], ax, "gray", f"Ref: {ref_id}", is_main=False, fill_style=False)
        plot_professional_roast(pd.DataFrame(st.session_state.points), ax, "#c0392b", "Current", is_main=True, fill_style=True)
        ax.set_xlabel("Time (s)"); ax.set_ylabel("Temp (℃)"); ax.grid(True, ls='--', alpha=0.3)
        st.pyplot(fig)

# =========================================================
# 7. QC 결과 분석 및 저장 섹션 (완전 복구)
# =========================================================
if not is_analysis_mode and st.session_state.points:
    st.markdown("---")
    st.subheader("3. 품질 분석 및 결과 저장 (QC & Save)")
    
    c_res, c_save = st.columns([2, 1])
    df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c_f = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r.get('Event', ""))[0]), None)

    with c_res:
        st.markdown("#### 📊 로스팅 리포트")
        if t_1c_f:
            total_t = df_f.iloc[-1]['Time']
            dtr = ((total_t - t_1c_f) / total_t) * 100
            st.markdown(f"""
            <div style="background-color:#f9fdf9; padding:20px; border-radius:12px; border:2px solid #228B22; margin-bottom:15px;">
                <h3 style="margin-top:0; color:#228B22;">DTR: {dtr:.1f}%</h3>
                {get_dtr_feedback(dtr)}
            </div>
            """, unsafe_allow_html=True)
        
        # 열량 및 수율 계산
        r1, r2 = st.columns(2)
        rw = r1.number_input("배출 무게 (Output Weight, g)", 0.0, step=0.1)
        if rw > 0 and green_weight > 0:
            lw = green_weight - rw; last_t = df_f.iloc[-1]['Temp']
            q = (lw*2260 + rw*1.6*(last_t-25))/1000
            r1.info(f"🔥 흡수 열량: {q:.1f} kJ")
            r2.metric("수율 (Yield)", f"{(rw/green_weight)*100:.1f}%")

    with c_save:
        st.markdown("#### 🎨 QC 분석 가이드")
        do_agtron = st.checkbox("아그트론(Agtron) 분석 진행?")
        if do_agtron:
            st.info("💡 아그트론 색상표(종이)와 원두를 함께 촬영하세요.")
            st.camera_input("원두 촬영")
        
        st.warning("📝 비고란에 [이용 열량 값]을 함께 적어주세요.")
        note = st.text_area("비고 (열량 및 메모)", placeholder="예: 1540kJ / 산미 발현 우수")
        
        if st.button("💾 최종 데이터베이스 저장", type="primary", use_container_width=True):
            df_f['Roast_ID'] = roast_id
            df_f.to_csv(DEFAULT_DATA_FILE, mode='a', header=not os.path.exists(DEFAULT_DATA_FILE), index=False, encoding='utf-8-sig')
            st.success("데이터베이스에 저장되었습니다."); st.session_state.points = []; st.session_state.timer_state = "idle"; st.rerun()
