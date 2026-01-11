import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import matplotlib.patheffects as pe # 텍스트 테두리 효과용

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Roasting Analysis Center", layout="wide", page_icon="☕")

# 한글 폰트 설정
try: plt.rcParams['font.family'] = 'Malgun Gothic' 
except: plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- [함수] 날짜 포맷 변환 ---
def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"

# --- [함수] CSV 파싱 (기존 유지) ---
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
    return """파일명,Sample_01\n날짜,2026-Jan-01\n원두,Geisha\n결과무게,215\n비고,템플릿\n\nTime(sec),Temp(C),Gas,Event\n0,200,0.5,Charge\n60,90,5.0,TP\n300,150,4.0,Yellowing\n540,192,2.0,1C Start\n600,205,0,Drop"""

# --- [신규] 이벤트 감지 및 포맷 ---
def check_is_crack(event_str):
    e = event_str.lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e) and not ("2" in e)
    is_2c = any(k in e for k in ["2c", "2nd", "second"])
    return is_1c, is_2c

def format_mmss(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"

# --- 사이드바 ---
st.sidebar.markdown("## 🇵🇪 PERU COFFEE ORIGINS")
st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**\n\n지속 가능한 커피 문화를 위해 최고의 농장과 함께합니다.")
c1, c2 = st.sidebar.columns(2)
with c1: st.link_button("🛍️ 스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with c2: st.link_button("📷 인스타", "https://instagram.com/perucoffee.origins", use_container_width=True)
st.sidebar.markdown("---")
st.sidebar.caption("🛠️ 유틸리티")
c3, c4 = st.sidebar.columns(2)
with c3: st.download_button("📥 템플릿", get_template_csv().encode('utf-8-sig'), "template.csv", "text/csv", use_container_width=True)
with c4: st.link_button("⚡ 웹 로거", "https://roastinglog.netlify.app/", use_container_width=True)
st.sidebar.markdown("---")
st.sidebar.caption("📂 데이터 센터")

all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns: all_history.append(db_df)
    except: pass
uploaded_files = st.sidebar.file_uploader("비교 분석용 CSV 업로드", accept_multiple_files=True, type=['csv'])
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None: all_history.append(pdf)

full_df = pd.DataFrame()
selected_ids = []
if all_history:
    full_df = pd.concat(all_history, ignore_index=True)
    uids = list(full_df['Roast_ID'].unique())
    selected_ids = st.sidebar.multiselect(f"비교 선택 ({len(uids)})", uids)
else: st.sidebar.text("데이터 없음")

# --- 메인 ---
st.title("☕ Roasting Analysis Center")
with st.expander("1. 설정", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1: 
        intl_date = get_intl_date_str() 
        bean_name = st.text_input("생두", value="Geisha")
    with c2: roast_id = st.text_input("ID", value=f"{bean_name}_{intl_date}")
    with c3: initial_temp = st.number_input("투입온도", 200); green_weight = st.number_input("생두(g)", 250.0)

if 'points' not in st.session_state: st.session_state.points = [] 
EVT = ["Charge", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"]

st.subheader("2. 볶은 기록 입력")
c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2, 1])
with c1: m = st.number_input("분", 0, 60, 0); s = st.number_input("초", 0, 59, 0); t_sec = m*60+s
with c2: temp = st.number_input("온도", 0, 300, int(initial_temp))
with c3: gas = st.number_input("가스", 0.0, 15.0, 0.0, step=0.1)
with c4: evt = st.selectbox("이벤트", ["기록"]+EVT)
with c5:
    st.write(""); st.write("")
    if st.button("추가", type="primary", use_container_width=True):
        st.session_state.points.append({"Time": t_sec, "Temp": temp, "Gas": gas, "Event": evt if evt!="기록" else None, "Roast_ID": roast_id})

if st.session_state.points:
    st.markdown("##### 📝 수정")
    edited = st.data_editor(pd.DataFrame(st.session_state.points), num_rows="dynamic", use_container_width=True, key="editor",
                            column_config={"Event": st.column_config.SelectboxColumn("이벤트", options=EVT)})
    if not pd.DataFrame(st.session_state.points).equals(edited):
        st.session_state.points = edited.to_dict('records'); st.rerun()

st.write("---")
fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx()

# --- [그래프 그리기 함수: 색상 동기화 및 겹침 방지] ---
def plot_roast_data(ax_temp, ax_gas, df, color_temp, color_gas, label_prefix, is_main=False):
    t_1c, t_2c = None, None
    idx_1c = None
    
    # 1. 팝 시점 찾기
    for i, row in df.iterrows():
        e = str(row['Event']).lower()
        if not e or e == "nan": continue
        is_1c_evt, is_2c_evt = check_is_crack(e)
        if is_1c_evt and t_1c is None:
            t_1c = row['Time']
            idx_1c = i
        if is_2c_evt and t_2c is None:
            t_2c = row['Time']

    # 2. 선 그리기 (두께 8로 강화)
    label_added = False
    if idx_1c is not None and is_main:
        # 일반 구간
        ax_temp.plot(df.iloc[:idx_1c+1]['Time'], df.iloc[:idx_1c+1]['Temp'], 
                     marker='o', markersize=6, color=color_temp, linewidth=2, label=label_prefix)
        # 디벨롭먼트 구간 (두께 8)
        ax_temp.plot(df.iloc[idx_1c:]['Time'], df.iloc[idx_1c:]['Temp'], 
                     marker='o', markersize=6, color=color_temp, linewidth=8, alpha=0.9) 
        label_added = True
    else:
        marker = 'o' if is_main else '.'
        lw = 2 if is_main else 1
        ax_temp.plot(df['Time'], df['Temp'], marker=marker, markersize=6 if is_main else 4, 
                     color=color_temp, linewidth=lw, label=label_prefix, alpha=1.0 if is_main else 0.5)
        label_added = True

    if is_main or (not is_main and 'Gas' in df.columns and df['Gas'].sum() > 0):
        ls = '--' if is_main else ':'
        alpha = 0.7 if is_main else 0.3
        ax_gas.plot(df['Time'], df['Gas'], drawstyle='steps-post', marker='x', markersize=5, 
                    linestyle=ls, color=color_gas, alpha=alpha, label='Gas' if is_main else None)

    # 3. 텍스트 겹침 방지 (Zig-zag 배치 로직)
    # 이벤트가 있는 포인트만 추출
    event_points = []
    for _, row in df.iterrows():
        e = str(row['Event'])
        if e and e != "nan" and e != "None":
            event_points.append(row)

    # 이벤트 루프
    for i, row in enumerate(event_points):
        e = str(row['Event'])
        label_text = e
        
        # Drop 시간 계산
        if "drop" in e.lower() or "배출" in e:
            if t_2c is not None: label_text = f"Drop (+2C {format_mmss(row['Time']-t_2c)})"
            elif t_1c is not None: label_text = f"Drop (+1C {format_mmss(row['Time']-t_1c)})"
        
        is_1c_evt, is_2c_evt = check_is_crack(e)
        
        # [수정] 텍스트 위치 지능형 배치 (위/아래 번갈아 가며)
        # 짝수번째 이벤트는 위로(+20), 홀수번째는 아래로(-25) 배치하여 겹침 최소화
        y_offset = 25 if i % 2 == 0 else -30 
        va_align = 'bottom' if i % 2 == 0 else 'top'

        # 텍스트 가독성 (흰색 테두리 효과)
        path_eff = [pe.withStroke(linewidth=3, foreground="white")]

        if is_1c_evt or is_2c_evt:
            # [수정] 별표 색상 = 선 색상 (color_temp)
            ax_temp.scatter(row['Time'], row['Temp'], marker='*', s=400, 
                            facecolors=color_temp, edgecolors='black', linewidths=1.5, zorder=10)
            
            ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, y_offset), 
                             textcoords='offset points', ha='center', va=va_align,
                             weight='bold', color='black', fontsize=11, path_effects=path_eff)
        else:
            if "drop" in e.lower() or "배출" in e:
                # Drop은 항상 잘 보이게 위쪽 고정 + 보라색
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, 30), 
                                 textcoords='offset points', ha='center', weight='bold', 
                                 color='purple', fontsize=12, path_effects=path_eff,
                                 arrowprops=dict(arrowstyle="-", color='purple', alpha=0.5))
            else:
                # 일반 이벤트 (상자 + 화살표)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, y_offset), 
                                 textcoords='offset points', ha='center', va=va_align, fontsize=9, 
                                 color='black', weight='bold', path_effects=path_eff,
                                 bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color_temp, alpha=0.9),
                                 arrowprops=dict(arrowstyle="-", color=color_temp, alpha=0.5))

# --- 그래프 실행 ---
if st.session_state.points:
    curr_df = pd.DataFrame(st.session_state.points).sort_values('Time').reset_index(drop=True)
    plot_roast_data(ax1, ax2, curr_df, '#c0392b', '#2980b9', f'Current: {roast_id}', is_main=True)

if selected_ids and not full_df.empty:
    colors = plt.cm.tab10.colors 
    for i, pid in enumerate(selected_ids):
        p = full_df[full_df['Roast_ID'] == pid].sort_values('Time').reset_index(drop=True)
        if not p.empty:
            c = colors[i % len(colors)]
            plot_roast_data(ax1, ax2, p, c, c, f'{pid}', is_main=False)

ax1.set_xlabel("Time (sec)"); ax1.set_ylabel("Temp (C)", color='#c0392b'); ax2.set_ylabel("Gas", color='#2980b9')
ax2.set_ylim(0, 10); ax1.grid(True, ls='--', alpha=0.5); ax1.legend(loc='upper left')
st.pyplot(fig)

# --- 저장 ---
st.subheader("3. 저장")
c1, c2, c3 = st.columns([1, 2, 1])
calc_E = None
with c1:
    rw = st.number_input("배출무게", 0.0)
    if rw>0 and green_weight>0:
        lw = green_weight - rw
        q = (lw*2260 + rw*1.6*(st.session_state.points[-1]['Temp']-25 if st.session_state.points else 175))/1000
        calc_E = f"{q:.1f} kJ"; st.info(f"🔥 열량: {calc_E}")

with c2: 
    note = st.text_input("메모", placeholder="맛, 특이사항")
    intl_date = get_intl_date_str()
    save_name = st.text_input("파일 이름", value=f"Roasting_{intl_date}_{bean_name}")

with c3:
    st.write(""); st.write("")
    if st.session_state.points:
        sdf = pd.DataFrame(st.session_state.points)
        buf = io.StringIO()
        buf.write(f"파일 이름,{save_name}\n날짜,{get_intl_date_str()}\n원두,{bean_name}\n결과무게,{rw}\n흡수열량,{calc_E}\n비고,{note}\n\n")
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
