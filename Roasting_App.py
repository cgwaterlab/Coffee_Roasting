import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Roasting Analysis Center", layout="wide", page_icon="☕")

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic' 
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# 기본 저장 파일
DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- [함수] CSV 파싱 로직 (기존 유지) ---
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
                has_time = any(("time" in c) or ("시간" in c) for c in cells)
                has_temp = any(("temp" in c) or ("온도" in c) for c in cells)
                if has_time and has_temp:
                    header_row_idx = i
                    delimiter = d
                    break
            if header_row_idx is not None: break

        if header_row_idx is None: return None

        data_text = "\n".join(lines[header_row_idx:])
        reader = csv.reader(io.StringIO(data_text), delimiter=delimiter)
        rows = list(reader)
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
            elif ("gas" in c) or ("가스" in c) or ("압력" in c): col_map[col] = "Gas"
            elif ("event" in c) or ("이벤트" in c) or ("비고" in c): col_map[col] = "Event"
        
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
        final_id = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        out["Roast_ID"] = final_id
        return out
    except: return None

# --- [함수] 템플릿 생성 ---
def get_template_csv():
    return """파일명,Geisha_Sample_01
날짜,2026-01-01
원두,Geisha_Panama
결과무게,215
비고,샘플 파일입니다.

Time(sec),Temp(C),Gas,Event
0,200,0.5,Charge
60,90,5.0,TP
120,105,4.5,
300,150,4.0,Yellowing
420,165,3.0,Cinnamon
540,192,2.0,1st Pop
600,205,0,Drop
"""

# ==========================================
# 1. 사이드바 (통합 UX/UI 개선)
# ==========================================
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")

# 브랜드 소개 (요청하신 문구)
st.sidebar.info(
    "**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**\n\n"
    "지속 가능한 커피 문화를 위해 최고의 농장과 함께합니다."
)

# 링크 모음 (네이버 스토어 + 인스타)
col_link1, col_link2 = st.sidebar.columns(2)
with col_link1:
    st.link_button("🛍️ 네이버 스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with col_link2:
    st.link_button("📷 인스타그램", "https://instagram.com/perucoffee.origins", use_container_width=True)

st.sidebar.markdown("---")

# 유틸리티 모음 (템플릿 다운 + HTML 로거 링크)
st.sidebar.caption("🛠️ 유틸리티 도구")
col_util1, col_util2 = st.sidebar.columns(2)

with col_util1:
    # 템플릿 다운로드
    template_data = get_template_csv().encode('utf-8-sig')
    st.download_button(
        label="📥 템플릿 다운",
        data=template_data,
        file_name="roasting_template.csv",
        mime="text/csv",
        key="dl_temp_sidebar",
        use_container_width=True
    )

with col_util2:
    # HTML 로거로 이동
    st.link_button(
        "⚡ 웹 로거(Lite)", 
        "https://roastinglog.netlify.app/", 
        help="현장에서 가볍게 쓸 수 있는 HTML 로거로 이동합니다.",
        use_container_width=True
    )

st.sidebar.markdown("---")
st.sidebar.caption("📂 데이터 센터")

# 데이터 관리 로직
all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns: all_history.append(db_df)
    except: pass

uploaded_files = st.sidebar.file_uploader("CSV 파일 업로드 (비교 분석용)", accept_multiple_files=True, type=['csv'])
if uploaded_files:
    for uploaded_file in uploaded_files:
        processed_df = load_and_standardize_csv(uploaded_file, uploaded_file.name)
        if processed_df is not None: all_history.append(processed_df)

full_history_df = pd.DataFrame()
selected_ids = []
if all_history:
    full_history_df = pd.concat(all_history, ignore_index=True)
    unique_ids = list(full_history_df['Roast_ID'].unique())
    selected_ids = st.sidebar.multiselect(f"📈 비교할 그래프 선택 ({len(unique_ids)}개)", unique_ids)
else:
    st.sidebar.text("데이터가 없습니다.")


# ==========================================
# 2. 메인 화면 (분석 센터)
# ==========================================
st.title("☕ Roasting Analysis Center")

# (1) 정보 설정
with st.expander("1. 로스팅 정보 설정", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        today = datetime.now().strftime("%Y%m%d")
        bean_name = st.text_input("생두 품종", value="Geisha")
    with c2:
        roast_id = st.text_input("로스팅 ID", value=f"{bean_name}_{today}")
    with c3:
        initial_temp = st.number_input("투입 온도 (℃)", value=200, step=10)
        green_weight = st.number_input("생두 무게 (g)", value=250.0)

if 'points' not in st.session_state: st.session_state.points = [] 

EVENT_OPTIONS = ["Charge", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"]

# (2) 입력 패널
st.subheader("2. 볶은 기록(Roasting) 입력")
c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2, 1])
with c1:
    m = st.number_input("분", 0, 60, 0)
    s = st.number_input("초", 0, 59, 0)
    total_sec = m * 60 + s
with c2:
    temp = st.number_input("온도 (℃)", 0, 300, int(initial_temp))
with c3:
    gas = st.number_input("가스압", 0.0, 15.0, 0.0, step=0.1)
with c4:
    evt = st.selectbox("이벤트", ["기록"] + EVENT_OPTIONS)
with c5:
    st.write("")
    st.write("")
    if st.button("추가 (Enter)", type="primary", use_container_width=True):
        st.session_state.points.append({
            "Time": total_sec, "Temp": temp, "Gas": gas,
            "Event": evt if evt != "기록" else None, "Roast_ID": roast_id
        })

# (3) 데이터 에디터
if st.session_state.points:
    st.markdown("##### 📝 데이터 수정")
    df_to_edit = pd.DataFrame(st.session_state.points)
    edited_df = st.data_editor(
        df_to_edit, num_rows="dynamic", use_container_width=True,
        column_config={
            "Time": st.column_config.NumberColumn("시간(초)", min_value=0, format="%d"),
            "Temp": st.column_config.NumberColumn("온도(℃)", min_value=0, format="%d"),
            "Gas": st.column_config.NumberColumn("가스압", min_value=0, max_value=15, step=0.1, format="%.1f"),
            "Event": st.column_config.SelectboxColumn("이벤트", options=EVENT_OPTIONS, required=False)
        }, key="editor"
    )
    if not df_to_edit.equals(edited_df):
        st.session_state.points = edited_df.to_dict('records')
        st.rerun()

# (4) 그래프
st.write("---")
fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx()

# 현재 데이터
if st.session_state.points:
    curr_df = pd.DataFrame(st.session_state.points).sort_values('Time')
    ax1.plot(curr_df['Time'], curr_df['Temp'], marker='o', markersize=8, color='#c0392b', linewidth=2, label=f'Current: {roast_id}')
    ax2.plot(curr_df['Time'], curr_df['Gas'], drawstyle='steps-post', marker='x', markersize=8, linestyle='--', color='#2980b9', alpha=0.7, label='Gas')
    for _, row in curr_df.iterrows():
        if row['Event']:
            ax1.annotate(row['Event'], (row['Time'], row['Temp']), xytext=(0, 15), textcoords='offset points', ha='center', fontsize=11, weight='bold', bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="red"))

# 비교 데이터
if selected_ids and not full_history_df.empty:
    colors = plt.cm.tab10.colors 
    for i, pid in enumerate(selected_ids):
        p_data = full_history_df[full_history_df['Roast_ID'] == pid].sort_values('Time')
        if not p_data.empty:
            color = colors[i % len(colors)]
            ax1.plot(p_data['Time'], p_data['Temp'], marker='.', markersize=5, linestyle='-', linewidth=1, color=color, alpha=0.5, label=f'{pid}')
            if 'Gas' in p_data.columns and p_data['Gas'].sum() > 0:
                 ax2.plot(p_data['Time'], p_data['Gas'], drawstyle='steps-post', linestyle=':', linewidth=1, color=color, alpha=0.3)
            pop_pt = p_data[p_data['Event'].astype(str).str.contains('Pop', na=False, case=False)]
            if not pop_pt.empty:
                 ax1.scatter(pop_pt['Time'], pop_pt['Temp'], marker='*', s=150, color=color, zorder=10, edgecolors='black')

ax1.set_xlabel("Time (Seconds)")
ax1.set_ylabel("Temperature (℃)", color='#c0392b')
ax2.set_ylabel("Gas Pressure", color='#2980b9')
ax2.set_ylim(0, 10)
ax1.grid(True, linestyle='--', alpha=0.5)
ax1.legend(loc='upper left')
st.pyplot(fig)

# (5) 저장
st.subheader("3. 종료 및 저장 (열량 분석)")
c1, c2, c3 = st.columns([1, 2, 1])
calculated_energy = None

with c1:
    r_weight = st.number_input("배출 무게(g)", 0.0)
    if r_weight > 0 and green_weight > 0:
        loss_weight = green_weight - r_weight
        q_latent = loss_weight * 2260 
        last_temp = st.session_state.points[-1]['Temp'] if st.session_state.points else 200
        q_sensible = r_weight * 1.6 * (last_temp - 25)
        q_total_kj = (q_latent + q_sensible) / 1000
        calculated_energy = f"{q_total_kj:.1f} kJ"
        st.info(f"🔥 흡수 열량: {calculated_energy}")

with c2:
    notes = st.text_input("메모", placeholder="맛, 특이사항")
    save_name = st.text_input("파일명", value=f"Roasting_{today}_{bean_name}")

with c3:
    st.write("")
    st.write("")
    if st.session_state.points:
        save_df = pd.DataFrame(st.session_state.points)
        meta_energy = calculated_energy if calculated_energy else "계산안됨"
        csv_buffer = io.StringIO()
        csv_buffer.write(f"파일명,{save_name}\n날짜,{datetime.now().strftime('%Y-%m-%d')}\n원두,{bean_name}\n")
        csv_buffer.write(f"결과무게,{r_weight}\n흡수열량,{meta_energy}\n비고,{notes}\n\n")
        
        export_df = save_df[['Time', 'Temp', 'Gas', 'Event']].rename(columns={'Time':'Time(sec)', 'Temp':'Temp(C)'})
        export_df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue().encode('utf-8-sig')

        def save_and_clear():
            save_df['Roast_ID'] = roast_id
            mode = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
            header = not os.path.exists(DEFAULT_DATA_FILE)
            save_df.to_csv(DEFAULT_DATA_FILE, mode=mode, header=header, index=False, encoding='utf-8-sig')
            st.session_state.points = []
            st.success("저장 완료!")

        st.download_button(
            label="💾 저장 및 다운로드",
            data=csv_data,
            file_name=f"{save_name}.csv",
            mime="text/csv",
            type="primary",
            on_click=save_and_clear,
            use_container_width=True
        )
    else:
        st.button("💾 저장 및 다운로드", disabled=True, use_container_width=True)
