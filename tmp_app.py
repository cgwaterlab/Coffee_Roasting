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
    if seconds is None or seconds < 0: return "00:00"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def get_dtr_feedback(dtr):
    if dtr < 10: return "⚠️ 언더 디벨롭 (Under Developed): 풋내나 떫은 맛이 날 수 있어요. 시간을 조금 더 늘려보세요."
    elif dtr <= 15: return "🍓 노르딕/라이트 (Light): 꽃향기와 화사한 산미, 차(Tea) 같은 깔끔함이 특징이에요."
    elif dtr <= 20: return "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 황금 비율이에요! (추천)"
    elif dtr <= 25: return "🍫 미디엄 다크 (Medium Dark): 산미는 줄고 바디감과 초콜릿 향이 살아나요."
    else: return "🔥 다크 (Dark): 묵직한 바디감, 스모키함, 쌉쌀한 맛이 강조돼요."

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
# 4. 사이드바 구성 (인스타, 스토어 링크 유지)
# =========================================================
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)
st.sidebar.markdown("### PERU COFFEE ORIGINS")
st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**\n\n지속 가능한 커피 문화를 위해 최고의 농장과 함께합니다.")

mode = st.sidebar.radio("모드 선택 (Mode)", ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"], index=2)

c1, c2 = st.sidebar.columns(2)
with c1: st.link_button("🛍️ 스마트\n스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with c2: st.link_button("📷 Instagram", "https://instagram.com/perucoffee.origins", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("🛠️ 유틸리티")
c3, c4 = st.sidebar.columns(2)
with c3: st.download_button("📥 파일\n템플릿", get_template_csv().encode('utf-8-sig'), "template.csv", "text/csv", use_container_width=True)
with c4: st.link_button("⚡ Web\nRoasting\nLogger", "https://roastinglog.netlify.app/", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("📂 레퍼런스 센터")

all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns: all_history.append(db_df)
    except: pass

uploaded_files = st.sidebar.file_uploader("로스팅 기록 파일 업로드", accept_multiple_files=True, type=['csv'])
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None: all_history.append(pdf)
full_df = pd.concat(all_history, ignore_index=True) if all_history else pd.DataFrame()

selected_ids_analysis = []
reference_id_roasting = None
is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

# =========================================================
# 5. 메인 로직
# =========================================================
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids_analysis = st.sidebar.multiselect(f"비교할 그래프 선택 ({len(uids)}개)", uids)
    else: st.info("데이터가 없습니다. CSV 파일을 업로드하세요.")

else:
    st.title("🔥 Professional Roasting Log")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_options = ["(선택 안 함)"] + uids
        selected_ref = st.sidebar.selectbox("📉 배경 레퍼런스 선택 (Single Reference)", ref_options)
        if selected_ref != "(선택 안 함)": reference_id_roasting = selected_ref

    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        intl_date = get_intl_date_str()
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1: bean_name = st.text_input("원두 이름 (Bean Name)", value="Geisha")
        with r1c2: roast_id = st.text_input("ID", value=f"{bean_name}_{intl_date}")
        with r1c3: roaster_name = st.text_input("로스터 이름 (Roaster Name)", value="")
        with r1c4: method = st.selectbox("방식 (Method)", ["드럼 (Drum)", "열풍 (Hot Air)", "하이브리드 (Hybrid)", "직화 (Direct Fire)", "기타 (Other)"])
        r2c1, r2c2 = st.columns(2)
        with r2c1: initial_temp = st.number_input("투입온도 (Charge Temp, ℃)", min_value=0, max_value=300, value=200, step=10)
        with r2c2: green_weight = st.number_input("생두 무게 (Green Weight, g)", 250.0)

    EVT = ["예열(Preheat)", "Charge", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"]

    # -----------------------------------------------------
    # Auto Timer 핵심 로직 (요청하신 시간 기록 기능 통합)
    # -----------------------------------------------------
    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        
        # 실시간 시간 계산
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
                    st.session_state.points = [{"Time": 0, "Temp": int(initial_temp), "Gas": 0.0, "Event": "Charge", "Roast_ID": roast_id}]
                    st.rerun()
            else:
                if st.button("⏹️ RESET", use_container_width=True):
                    st.session_state.timer_state = "idle"; st.session_state.points = []; st.rerun()

        with t_col2: st.metric("⏳ 전체 로스팅 시간", format_mmss(elapsed_all))
        with t_col3: st.metric("⏱️ 구간 경과 시간", format_mmss(elapsed_split), help="마지막 기록 시점부터 지난 시간")

        # 입력 폼
        can_rec = (st.session_state.timer_state == "running")
        c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 2, 1])
        with c1: st.text_input("현재 시간", value=format_mmss(elapsed_all), disabled=True)
        with c2: temp = st.number_input("온도", 0, 300, int(initial_temp), disabled=not can_rec, key="at_t")
        with c3: gas = st.number_input("가스", 0.0, 15.0, 0.0, step=0.1, disabled=not can_rec, key="at_g")
        with c4: evt = st.selectbox("이벤트", ["기록"] + EVT, disabled=not can_rec, key="at_e")
        with c5:
            st.write(""); st.write("")
            if st.button("기록", type="primary", use_container_width=True, disabled=not can_rec):
                st.session_state.last_record_time = time.time() # 구간 시계 리셋
                rec_t = int(st.session_state.last_record_time - st.session_state.start_time)
                st.session_state.points.append({"Time": rec_t, "Temp": temp, "Gas": gas, "Event": evt if evt != "기록" else None, "Roast_ID": roast_id})
                if is_drop_event(evt):
                    st.session_state.timer_state = "stopped"; st.session_state.stop_elapsed = rec_t
                st.rerun()

    else:
        st.subheader("2. 실시간 기록 (Manual Input)")
        m1, m2, m3, m4, m5 = st.columns([1, 1, 1, 2, 1])
        t_sec = m1.number_input("분", 0, 60, 0) * 60 + m1.number_input("초", 0, 59, 0)
        temp = m2.number_input("온도", 0, 300, int(initial_temp))
        gas = m3.number_input("가스", 0.0, 15.0, 0.0, step=0.1)
        evt = m4.selectbox("이벤트", ["기록"] + EVT)
        if m5.button("추가", type="primary", use_container_width=True):
            st.session_state.points.append({"Time": t_sec, "Temp": temp, "Gas": gas, "Event": evt if evt != "기록" else None, "Roast_ID": roast_id})

    # 공통 데이터 수정/타임라인
    if st.session_state.points:
        st.markdown("##### 📝 데이터 수정 및 타임라인")
        dfp = pd.DataFrame(st.session_state.points).sort_values("Time")
        # 구간 소요 시간 자동 계산 (Δprev)
        timeline = dfp[dfp["Event"].notna()].copy()
        if not timeline.empty:
            timeline["누적"] = timeline["Time"].apply(format_mmss)
            timeline["구간소요"] = timeline["Time"].diff().fillna(0).astype(int).apply(format_mmss)
            st.dataframe(timeline[["Event", "누적", "구간소요", "Temp", "Gas"]], use_container_width=True)
        
        edited = st.data_editor(dfp, num_rows="dynamic", use_container_width=True, key="editor")
        if not dfp.equals(edited):
            st.session_state.points = edited.to_dict('records'); st.rerun()

# =========================================================
# 6. 통합 그래프 시각화 (Matplotlib)
# =========================================================
if (is_analysis_mode and 'selected_ids_analysis' in locals() and selected_ids_analysis) or st.session_state.points:
    st.write("---")
    fig, ax1 = plt.subplots(figsize=(12, 7))
    ax2, ax_ror = ax1.twinx(), ax1.twinx()
    ax_ror.set_ylim(0, 150); ax_ror.axis('off')

    def plot_roast(df, color, label, is_main=False):
        df = df.sort_values('Time')
        ax1.plot(df['Time'], df['Temp'], marker='o', color=color, label=label, alpha=0.9 if is_main else 0.3, lw=2 if is_main else 1)
        if is_main:
            for _, r in df.iterrows():
                if r['Event']: ax1.annotate(r['Event'], (r['Time'], r['Temp']), xytext=(0,15), textcoords='offset points', ha='center', weight='bold')

    if is_analysis_mode:
        for i, pid in enumerate(selected_ids_analysis): plot_roast(full_df[full_df['Roast_ID']==pid], plt.cm.tab10(i%10), pid, True)
    else:
        if reference_id_roasting: plot_roast(full_df[full_df['Roast_ID']==reference_id_roasting], "gray", "Reference")
        if st.session_state.points: plot_roast(pd.DataFrame(st.session_state.points), "#c0392b", "Current", True)

    ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (C)"); ax1.legend(); st.pyplot(fig)

# =========================================================
# 7. 저장 섹션 & DTR 평가
# =========================================================
if not is_analysis_mode and st.session_state.points:
    st.subheader("3. 저장 (Save)")
    c1, c2, c3 = st.columns([1, 2, 1])
    df_f = pd.DataFrame(st.session_state.points).sort_values('Time')
    t_1c = next((r['Time'] for _, r in df_f.iterrows() if check_is_crack(r['Event'])[0]), None)

    with c1:
        rw = st.number_input("배출무게 (g)", 0.0)
        if rw > 0 and green_weight > 0:
            lw = green_weight - rw; last_t = df_f.iloc[-1]['Temp']
            q = (lw*2260 + rw*1.6*(last_t-25))/1000
            st.info(f"🔥 열량: {q:.1f} kJ")

    with c2:
        if t_1c:
            dtr = ((df_f.iloc[-1]['Time'] - t_1c) / df_f.iloc[-1]['Time']) * 100
            st.markdown(f"""<div style="background-color:#e8f6f3; padding:15px; border-radius:10px; border:1px solid #1abc9c;">
                <strong>📊 DTR: {dtr:.1f}%</strong><br>{get_dtr_feedback(dtr)}</div>""", unsafe_allow_html=True)

    with c3:
        note = st.text_input("메모")
        save_name = st.text_input("파일 이름", value=f"Roasting_{intl_date}_{bean_name}")
        buf = io.StringIO()
        buf.write(f"파일 이름,{save_name}\n원두,{bean_name}\n로스터,{roaster_name}\n방식,{method}\n결과무게,{rw}\n비고,{note}\n\n")
        df_f[['Time','Temp','Gas','Event']].to_csv(buf, index=False)
        def save():
            df_save = df_f.copy(); df_save['Roast_ID'] = roast_id
            df_save.to_csv(DEFAULT_DATA_FILE, mode='a', header=not os.path.exists(DEFAULT_DATA_FILE), index=False, encoding='utf-8-sig')
            st.session_state.points = []; st.session_state.timer_state = "idle"; st.success("저장 완료!")
        st.download_button("💾 CSV 저장 및 다운로드", buf.getvalue().encode('utf-8-sig'), f"{save_name}.csv", "text/csv", type="primary", on_click=save, use_container_width=True)
