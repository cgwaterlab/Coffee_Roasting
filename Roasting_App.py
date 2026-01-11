import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time # 시간 계산용
import matplotlib.patheffects as pe

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Roasting Analysis Center", layout="wide", page_icon="☕")

# 한글 폰트 설정
try: plt.rcParams['font.family'] = 'Malgun Gothic' 
except: plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- 함수 모음 ---
def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"

def get_dtr_feedback(dtr):
    """DTR 수치에 따른 맛 평가 멘트"""
    if dtr < 10: return "⚠️ 언더 디벨롭 (Under Developed): 풋내나 떫은 맛이 날 수 있어요. 시간을 조금 더 늘려보세요."
    elif dtr <= 15: return "🍓 노르딕/라이트 (Light): 꽃향기와 화사한 산미, 차(Tea) 같은 깔끔함이 특징이에요."
    elif dtr <= 20: return "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 황금 비율이에요! (추천)"
    elif dtr <= 25: return "🍫 미디엄 다크 (Medium Dark): 산미는 줄고 바디감과 초콜릿 향이 살아나요."
    else: return "🔥 다크 (Dark): 묵직한 바디감, 스모키함, 쌉쌀한 맛이 강조돼요."

def format_mmss(seconds):
    m = int(seconds // 60); s = int(seconds % 60)
    return f"{m}:{s:02d}"

def load_and_standardize_csv(file, file_name_fallback):
    try:
        file.seek(0)
        raw = file.read()
        if isinstance(raw, str): content = raw
        else:
            try: content = raw.decode("utf-8-sig")
            except: content = raw.decode("cp949", errors="ignore")
        lines = content.splitlines()
        candidates = [",", "\t", ";"]
        header_row_idx = None
        delimiter = ","
        extracted_id = None
        for i, line in enumerate(lines):
            if not line.strip(): continue
            if ("원두" in line) or ("bean" in line.lower()):
                parts = [p.strip() for p in re.split(r"[,\t;]", line)]
                if len(parts) > 1 and parts[1]: extracted_id = parts[1]
            for d in candidates:
                cells = [c.strip().lower() for c in line.split(d)]
                if any(("time" in c) or ("시간" in c) for c in cells) and any(("temp" in c) or ("온도" in c) for c in cells):
                    header_row_idx = i; delimiter = d; break
            if header_row_idx is not None: break
        if header_row_idx is None: return None
        data_text = "\n".join(lines[header_row_idx:])
        rows = list(csv.reader(io.StringIO(data_text), delimiter=delimiter))
        if not rows: return None
        header = [str(c).strip() for c in rows[0]]
        while header and header[-1] == "": header.pop()
        expected = len(header)
        cleaned = []
        for r in rows[1:]:
            r = [str(c).strip() for c in r]
            if not any(r): continue
            if len(r) > expected: r = r[:expected]
            elif len(r) < expected: r = r + [""] * (expected - len(r))
            cleaned.append(r)
        df = pd.DataFrame(cleaned, columns=header)
        df.columns = [str(c).strip() for c in df.columns]
        col_map = {}
        for col in df.columns:
            c = col.lower()
            if ("time" in c) or ("시간" in c): col_map[col] = "Time"
            elif ("temp" in c) or ("온도" in c): col_map[col] = "Temp"
            elif ("gas" in c) or ("가스" in c): col_map[col] = "Gas"
            elif ("event" in c) or ("이벤트" in c): col_map[col] = "Event"
        df.rename(columns=col_map, inplace=True)
        if ("Time" not in df.columns) or ("Temp" not in df.columns): return None
        out = pd.DataFrame()
        out["Time"] = pd.to_numeric(df["Time"], errors="coerce")
        out["Temp"] = pd.to_numeric(df["Temp"], errors="coerce")
        out["Gas"] = pd.to_numeric(df["Gas"], errors="coerce").fillna(0) if "Gas" in df.columns else 0
        if "Event" in df.columns:
            out["Event"] = df["Event"].fillna("").astype(str)
            out.loc[out["Event"].str.lower() == "nan", "Event"] = ""
        else: out["Event"] = ""
        out = out.dropna(subset=["Time", "Temp"])
        out["Roast_ID"] = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        return out
    except: return None

def get_template_csv():
    return """파일 이름,Sample_01\n날짜,2026-Jan-01\n원두 이름,Geisha\n결과무게,215\n비고,템플릿\n\nTime(sec),Temp(C),Gas,Event\n0,200,0.5,Charge\n60,90,5.0,TP\n300,150,4.0,Yellowing\n540,192,2.0,1C Start\n600,205,0,Drop"""

def check_is_crack(event_str):
    e = event_str.lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e) and not ("2" in e)
    is_2c = any(k in e for k in ["2c", "2nd", "second"])
    return is_1c, is_2c

# --- 사이드바 ---
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")
st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**\n\n지속 가능한 커피 문화를 위해 최고의 농장과 함께합니다.")

# [핵심] 모드 3가지로 확장
mode = st.sidebar.radio(
    "모드 선택 (Mode)", 
    ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"],
    index=0
)

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

full_df = pd.DataFrame()
if all_history:
    full_df = pd.concat(all_history, ignore_index=True)

# 전역 변수 설정
selected_ids_analysis = []
reference_id_roasting = None
is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_manual_mode = (mode == "🔥 로스팅 (Manual)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")

# ==========================================
# 3. 모드별 로직
# ==========================================

# [A] 데이터 분석 모드
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids_analysis = st.sidebar.multiselect(f"비교할 그래프 선택 ({len(uids)}개)", uids)
    else:
        st.info("데이터가 없습니다. CSV 파일을 업로드하세요.")

# [B] & [C] 로스팅 모드 (Manual / Auto)
else:
    st.title("🔥 Professional Roasting")
    
    # 레퍼런스 선택
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_options = ["(선택 안 함)"] + uids
        selected_ref = st.sidebar.selectbox("📉 배경 레퍼런스 선택 (Single Reference)", ref_options)
        if selected_ref != "(선택 안 함)": reference_id_roasting = selected_ref
    
    # 셋업
    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1: 
            intl_date = get_intl_date_str() 
            bean_name = st.text_input("원두 이름", value="Geisha")
        with c2: roast_id = st.text_input("ID", value=f"{bean_name}_{intl_date}")
        with c3: 
            initial_temp = st.number_input("투입온도 (℃)", min_value=0, max_value=300, value=200, step=10)
            green_weight = st.number_input("생두 무게(g)", 250.0)

    if 'points' not in st.session_state: st.session_state.points = [] 
    if 'start_time' not in st.session_state: st.session_state.start_time = None
    
    EVT = ["Charge", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"]

    # --- [C] 자동 시간 모드 전용 로직 ---
    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")
        
        # 타이머 시작/리셋 버튼
        t_col1, t_col2 = st.columns([1, 4])
        with t_col1:
            if st.session_state.start_time is None:
                if st.button("▶️ START (시작)", type="primary"):
                    st.session_state.start_time = time.time()
                    st.rerun()
            else:
                if st.button("⏹️ RESET (초기화)"):
                    st.session_state.start_time = None
                    st.session_state.points = []
                    st.rerun()
        
        with t_col2:
            if st.session_state.start_time:
                elapsed = int(time.time() - st.session_state.start_time)
                st.metric("경과 시간", format_mmss(elapsed))
            else:
                st.info("시작 버튼을 누르면 타이머가 작동합니다.")

        # 입력 폼 (시간 자동 계산)
        if st.session_state.start_time:
            c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
            with c1: 
                # 현재 경과 시간 자동 계산
                now_elapsed = int(time.time() - st.session_state.start_time)
                # 사용자에게 보여주기만 함 (disabled)
                st.text_input("현재 시간", value=format_mmss(now_elapsed), disabled=True)
            with c2: temp = st.number_input("온도", 0, 300, int(initial_temp))
            with c3: evt = st.selectbox("이벤트", ["기록"]+EVT)
            with c4: 
                st.write(""); st.write("")
                if st.button("기록 (Record)", type="primary", use_container_width=True):
                    # 버튼 누른 순간의 정확한 시간 사용
                    rec_time = int(time.time() - st.session_state.start_time)
                    # 가스압은 이전 값을 가져오거나 0 (간소화)
                    last_gas = st.session_state.points[-1]['Gas'] if st.session_state.points else 0.0
                    gas = st.number_input("가스(후입력)", 0.0, 15.0, last_gas, step=0.1, key="auto_gas")
                    
                    st.session_state.points.append({
                        "Time": rec_time, "Temp": temp, "Gas": gas, 
                        "Event": evt if evt!="기록" else None, "Roast_ID": roast_id
                    })
                    st.rerun()

    # --- [B] 수동 모드 로직 (기존 유지) ---
    else:
        st.subheader("2. 실시간 기록 (Manual Input)")
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2, 1])
        with c1: m = st.number_input("분", 0, 60, 0); s = st.number_input("초", 0, 59, 0); t_sec = m*60+s
        with c2: temp = st.number_input("온도", 0, 300, int(initial_temp))
        with c3: gas = st.number_input("가스", 0.0, 15.0, 0.0, step=0.1)
        with c4: evt = st.selectbox("이벤트", ["기록"]+EVT)
        with c5:
            st.write(""); st.write("")
            if st.button("추가", type="primary", use_container_width=True):
                st.session_state.points.append({"Time": t_sec, "Temp": temp, "Gas": gas, "Event": evt if evt!="기록" else None, "Roast_ID": roast_id})

    # 공통 데이터 에디터
    if st.session_state.points:
        st.markdown("##### 📝 데이터 수정")
        edited = st.data_editor(pd.DataFrame(st.session_state.points), num_rows="dynamic", use_container_width=True, key="editor",
                                column_config={"Event": st.column_config.SelectboxColumn("이벤트", options=EVT)})
        if not pd.DataFrame(st.session_state.points).equals(edited):
            st.session_state.points = edited.to_dict('records'); st.rerun()

# ==========================================
# 4. 통합 그래프
# ==========================================
st.write("---")
fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx()
ax_ror = ax1.twinx() 
ax_ror.set_ylim(0, 150)
ax_ror.axis('off')

def plot_roast_data(ax_temp, ax_gas, ax_ror_bar, df, color_temp, color_gas, label_prefix, is_main=False, show_ror=False):
    t_1c, t_2c, idx_1c = None, None, None
    for i, row in df.iterrows():
        e = str(row['Event']).lower()
        if not e or e == "nan": continue
        is_1c_evt, is_2c_evt = check_is_crack(e)
        if is_1c_evt and t_1c is None: t_1c = row['Time']; idx_1c = i
        if is_2c_evt and t_2c is None: t_2c = row['Time']

    # 온도 선
    final_c_temp = color_temp if (is_main or is_analysis_mode) else "#bdc3c7"
    final_c_gas = color_gas if (is_main or is_analysis_mode) else "#bdc3c7"
    line_style = '-' if (is_main or is_analysis_mode) else '--'
    alpha_val = 0.9 if is_main else 0.7

    if idx_1c is not None and (is_main or is_analysis_mode):
        ax_temp.plot(df.iloc[:idx_1c+1]['Time'], df.iloc[:idx_1c+1]['Temp'], marker='o', markersize=6, color=final_c_temp, linewidth=2, label=label_prefix)
        ax_temp.plot(df.iloc[idx_1c:]['Time'], df.iloc[idx_1c:]['Temp'], marker='o', markersize=6, color=final_c_temp, linewidth=8, alpha=alpha_val)
    else:
        marker = 'o' if (is_main or is_analysis_mode) else None
        ax_temp.plot(df['Time'], df['Temp'], marker=marker, markersize=5, linestyle=line_style, color=final_c_temp, linewidth=2, label=label_prefix, alpha=alpha_val)

    # 가스압
    if (is_main or is_analysis_mode) and 'Gas' in df.columns and df['Gas'].sum() > 0:
        ax_gas.plot(df['Time'], df['Gas'], drawstyle='steps-post', marker='x', markersize=5, linestyle=':', color=final_c_gas, alpha=0.5, label='Gas' if is_main else None)

    # [핵심] RoR Zone Bar + 수치 표시
    if show_ror and len(df) > 1:
        prev_ror = 0
        for i in range(1, len(df)):
            curr = df.iloc[i]; prev = df.iloc[i-1]
            dt = (curr['Time'] - prev['Time']) / 60.0
            dtemp = curr['Temp'] - prev['Temp']
            if dt > 0:
                ror = dtemp / dt
                c = "#2ecc71" # Green
                if ror < 5: c = "#3498db" # Blue
                elif ror > prev_ror + 2: c = "#e74c3c" # Red
                
                # Bar 그리기
                bar_x = curr['Time'] - (curr['Time']-prev['Time'])/2
                ax_ror_bar.bar(bar_x, ror, width=(curr['Time']-prev['Time']), color=c, alpha=0.6)
                
                # [추가] RoR 숫자 표시 (값이 3 이상일 때만, 너무 겹치지 않게)
                if ror > 3:
                    ax_ror_bar.text(bar_x, ror + 2, f"{ror:.1f}", ha='center', va='bottom', fontsize=8, color=c, fontweight='bold')
                
                prev_ror = ror

    # 이벤트
    if is_main or is_analysis_mode:
        event_points = []
        for _, row in df.iterrows():
            e = str(row['Event'])
            if e and e != "nan" and e != "None": event_points.append(row)

        for i, row in enumerate(event_points):
            e = str(row['Event']); label_text = e
            is_drop = "drop" in e.lower() or "배출" in e
            
            if is_drop:
                if t_2c: label_text = f"Drop (+2C {format_mmss(row['Time']-t_2c)})"
                elif t_1c: label_text = f"Drop (+1C {format_mmss(row['Time']-t_1c)})"
            
            is_1c_evt, is_2c_evt = check_is_crack(e)
            y_offset = 25 if i % 2 == 0 else -30 
            va_align = 'bottom' if i % 2 == 0 else 'top'
            
            if is_1c_evt or is_2c_evt:
                box_props = dict(boxstyle="round,pad=0.4", fc="gold", ec="black", alpha=1.0)
                ax_temp.scatter(row['Time'], row['Temp'], marker='*', s=400, facecolors=final_c_temp, edgecolors='black', linewidths=1.5, zorder=10)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, 20), textcoords='offset points', ha='center', weight='bold', color='black', fontsize=11, bbox=box_props)
            elif is_drop:
                box_props = dict(boxstyle="round,pad=0.4", fc="#9b59b6", ec="black", alpha=1.0)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, 35), textcoords='offset points', ha='center', weight='bold', color='white', fontsize=11, bbox=box_props, arrowprops=dict(arrowstyle="-", color='purple'))
            else:
                box_props = dict(boxstyle="round,pad=0.3", fc="white", ec=final_c_temp, alpha=0.9)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, y_offset), textcoords='offset points', ha='center', va=va_align, color='black', fontsize=10, bbox=box_props, arrowprops=dict(arrowstyle="-", color=final_c_temp))

# 그래프 실행
if is_analysis_mode:
    if selected_ids_analysis and not full_df.empty:
        colors = plt.cm.tab10.colors 
        for i, pid in enumerate(selected_ids_analysis):
            p = full_df[full_df['Roast_ID'] == pid].sort_values('Time').reset_index(drop=True)
            if not p.empty:
                c = colors[i % len(colors)]
                plot_roast_data(ax1, ax2, ax_ror, p, c, c, f'{pid}', is_main=True, show_ror=False)
else:
    # 로스팅 모드 (Manual / Auto)
    if reference_id_roasting and not full_df.empty:
        ref_data = full_df[full_df['Roast_ID'] == reference_id_roasting].sort_values('Time').reset_index(drop=True)
        if not ref_data.empty:
            plot_roast_data(ax1, ax2, ax_ror, ref_data, '#bdc3c7', '#bdc3c7', f'Ref: {reference_id_roasting}', is_main=False, show_ror=False)

    if st.session_state.points:
        curr_df = pd.DataFrame(st.session_state.points).sort_values('Time').reset_index(drop=True)
        plot_roast_data(ax1, ax2, ax_ror, curr_df, '#c0392b', '#2980b9', f'Current: {roast_id}', is_main=True, show_ror=True)

ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (C)", color='#c0392b'); ax2.set_ylabel("Gas", color='#2980b9')
ax2.set_ylim(0, 10); ax1.grid(True, ls='--', alpha=0.5); ax1.legend(loc='upper left')
st.pyplot(fig)

# --- [공통] 저장 섹션 & DTR 평가 ---
if not is_analysis_mode:
    st.subheader("3. 저장 (Save)")
    c1, c2, c3 = st.columns([1, 2, 1])
    calc_E = None
    
    # DTR 자동 계산 (평가용)
    current_dtr = 0
    dtr_feedback = ""
    if st.session_state.points:
        df = pd.DataFrame(st.session_state.points).sort_values('Time')
        # 1차 팝과 마지막 시간 찾기
        t_1c = None
        for _, r in df.iterrows():
            if check_is_crack(str(r['Event']))[0]: # 1차 팝
                t_1c = r['Time']
                break
        
        if t_1c and df.iloc[-1]['Time'] > t_1c:
            total_time = df.iloc[-1]['Time']
            dev_time = total_time - t_1c
            current_dtr = (dev_time / total_time) * 100
            dtr_feedback = get_dtr_feedback(current_dtr)

    with c1:
        rw = st.number_input("배출무게 (g)", 0.0)
        if rw>0 and green_weight>0:
            lw = green_weight - rw
            last_t = st.session_state.points[-1]['Temp'] if st.session_state.points else initial_temp
            q = (lw*2260 + rw*1.6*(last_t-25))/1000
            calc_E = f"{q:.1f} kJ"; st.info(f"🔥 열량: {calc_E}")

    with c2: 
        note = st.text_input("메모", placeholder="맛, 날씨, 특이사항")
        intl_date = get_intl_date_str()
        save_name = st.text_input("파일 이름", value=f"Roasting_{intl_date}_{bean_name}")

    with c3:
        st.write(""); st.write("")
        if st.session_state.points:
            # [신규] DTR 평가 메시지 표시 (저장 버튼 위)
            if dtr_feedback:
                st.markdown(f"""
                <div style="background-color:#e8f6f3; padding:10px; border-radius:5px; border:1px solid #1abc9c; font-size:0.9em; margin-bottom:10px;">
                    <strong>📊 DTR: {current_dtr:.1f}%</strong><br>{dtr_feedback}
                </div>
                """, unsafe_allow_html=True)

            sdf = pd.DataFrame(st.session_state.points)
            buf = io.StringIO()
            buf.write(f"파일 이름,{save_name}\n날짜,{get_intl_date_str()}\n원두 이름,{bean_name}\n결과무게,{rw}\n흡수열량,{calc_E}\n비고,{note}\n\n")
            sdf[['Time','Temp','Gas','Event']].rename(columns={'Time':'Time(sec)','Temp':'Temp(C)'}).to_csv(buf, index=False)
            csv_d = buf.getvalue().encode('utf-8-sig')
            
            def save():
                sdf['Roast_ID'] = roast_id
                m = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
                h = not os.path.exists(DEFAULT_DATA_FILE)
                sdf.to_csv(DEFAULT_DATA_FILE, mode=m, header=h, index=False, encoding='utf-8-sig')
                st.session_state.points = []; st.success("저장 완료!")
            
            st.download_button("💾 CSV 저장 및 다운로드", csv_d, f"{save_name}.csv", "text/csv", type="primary", on_click=save, use_container_width=True)
        else: st.button("💾 CSV 저장", disabled=True, use_container_width=True)
