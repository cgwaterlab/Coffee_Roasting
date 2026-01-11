import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re


# --- 설정 및 스타일 ---
st.set_page_config(page_title="Roasting Log", layout="wide")

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic' 
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# 기본 저장 파일 (통합 DB)
DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- [핵심 함수] CSV 파일 스마트 읽기 (Parser Upgrade) ---
def load_and_standardize_csv(file, file_name_fallback):
    """
    - 상단 메타데이터 + 중간 헤더 + 데이터 구조 자동 파싱
    - 콤마(,), 탭(\t), 세미콜론(;) 자동 감지
    - 엑셀에서 저장된 '탭 구분' CSV(사실상 TSV)도 정상 처리
    - 어떤 행은 열이 더 많은 경우(예: 마지막에 99 같은 값) -> 초과 열 잘라냄
    """
    try:
        # 1) 파일 내용 읽기 (바이트/문자 모두 대응 + 인코딩 대응)
        file.seek(0)
        raw = file.read()

        if isinstance(raw, str):
            content = raw
        else:
            try:
                content = raw.decode("utf-8-sig")
            except Exception:
                try:
                    content = raw.decode("cp949", errors="ignore")
                except Exception:
                    content = raw.decode("latin-1", errors="ignore")

        lines = content.splitlines()

        # 2) 헤더 행 + 구분자 찾기
        #    (Time/시간 AND Temp/온도 포함된 줄을 찾고, 해당 줄의 구분자도 결정)
        delims = ["\t", ",", ";"]
        header_row_idx = None
        delimiter = ","
        extracted_id = None

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            # (옵션) 메타데이터에서 원두/bean 이름 추출 (탭/콤마/세미콜론 모두 대응)
            if ("원두" in line) or ("bean" in line.lower()):
                parts = [p.strip() for p in re.split(r"[\t,;]", line)]
                if len(parts) > 1 and parts[1]:
                    extracted_id = parts[1]

            # 헤더 탐색: 가능한 구분자별로 셀 분리 후 time/temp 포함 여부 확인
            for d in delims:
                cells = [c.strip().lower() for c in line.split(d)]
                has_time = any(("time" in c) or ("시간" in c) for c in cells)
                has_temp = any(("temp" in c) or ("온도" in c) for c in cells)
                if has_time and has_temp:
                    header_row_idx = i
                    delimiter = d
                    break

            if header_row_idx is not None:
                break

        if header_row_idx is None:
            return None

        # 3) pandas.read_csv 대신 csv.reader로 "가변 열" 안전 파싱
        import csv as pycsv
        reader = pycsv.reader(io.StringIO(content), delimiter=delimiter)
        rows = list(reader)

        def _strip_row(r):
            return [str(c).strip() for c in r]

        header = _strip_row(rows[header_row_idx])

        # 엑셀 탭 파일은 뒤에 빈 컬럼이 딸려오는 경우가 많아서 제거
        while header and header[-1] == "":
            header.pop()

        if not header:
            return None

        data_rows = []
        for r in rows[header_row_idx + 1:]:
            r = _strip_row(r)
            if not any(cell for cell in r):
                continue

            # 행의 컬럼 수가 헤더보다 많으면 초과 부분 제거(예: '1st Pop 끝' 뒤에 99)
            if len(r) > len(header):
                r = r[:len(header)]
            # 부족하면 빈칸으로 패딩
            elif len(r) < len(header):
                r = r + [""] * (len(header) - len(r))

            data_rows.append(r)

        df = pd.DataFrame(data_rows, columns=header)

        # 4) 컬럼명 표준화
        df.columns = [str(c).strip() for c in df.columns]

        col_map = {}
        for col in df.columns:
            c_low = col.lower()
            if ("time" in c_low) or ("시간" in c_low):
                col_map[col] = "Time"
            elif ("temp" in c_low) or ("온도" in c_low):
                col_map[col] = "Temp"
            elif ("gas" in c_low) or ("가스" in c_low) or ("압력" in c_low):
                col_map[col] = "Gas"
            elif ("event" in c_low) or ("이벤트" in c_low) or ("비고" in c_low):
                col_map[col] = "Event"

        df.rename(columns=col_map, inplace=True)

        # 필수 확인
        if ("Time" not in df.columns) or ("Temp" not in df.columns):
            return None

        # 5) 데이터 정제
        standard_df = pd.DataFrame()
        standard_df["Time"] = pd.to_numeric(df["Time"], errors="coerce")
        standard_df["Temp"] = pd.to_numeric(df["Temp"], errors="coerce")

        if "Gas" in df.columns:
            standard_df["Gas"] = pd.to_numeric(df["Gas"], errors="coerce").fillna(0)
        else:
            standard_df["Gas"] = 0

        if "Event" in df.columns:
            standard_df["Event"] = df["Event"].fillna("").astype(str)
            standard_df.loc[standard_df["Event"].str.lower() == "nan", "Event"] = ""
        else:
            standard_df["Event"] = ""

        # 숫자 필드 없는 줄 제거 (메타데이터 잔여물 방지)
        standard_df = standard_df.dropna(subset=["Time", "Temp"])

        # Roast_ID
        final_id = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        standard_df["Roast_ID"] = final_id

        return standard_df

    except Exception:
        return None


# --- [함수] 템플릿 CSV 생성 (요청하신 양식 반영) ---
def get_template_csv():
    template_str = """파일명,Geisha_Sample_01
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
    return template_str

# --- 1. 사이드바 ---
st.sidebar.title("📂 로스팅 데이터 센터")

# 템플릿 다운로드 버튼
template_data = get_template_csv().encode('utf-8-sig')
st.sidebar.download_button(
    label="📥 입력용 템플릿(CSV) 다운로드",
    data=template_data,
    file_name="roasting_template.csv",
    mime="text/csv",
    key="download_template_btn"
)
st.sidebar.write("---")

all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns: all_history.append(db_df)
    except: pass

uploaded_files = st.sidebar.file_uploader("CSV 파일 업로드", accept_multiple_files=True, type=['csv'])
if uploaded_files:
    for uploaded_file in uploaded_files:
        processed_df = load_and_standardize_csv(uploaded_file, uploaded_file.name)
        if processed_df is not None: all_history.append(processed_df)

full_history_df = pd.DataFrame()
selected_ids = []
if all_history:
    full_history_df = pd.concat(all_history, ignore_index=True)
    unique_ids = list(full_history_df['Roast_ID'].unique())
    st.sidebar.header("📊 그래프 비교")
    selected_ids = st.sidebar.multiselect(f"데이터 선택 ({len(unique_ids)}개)", unique_ids)
else:
    st.sidebar.info("데이터 없음")

# --- 2. 메인 ---
st.title("☕ Smart Roasting Logger")

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

EVENT_OPTIONS = ["Input Beans", "Turning Point", "Yellowing", "Cinnamon", "1st Pop", "2nd Pop", "Drop"]

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
    if st.button("추가 (Enter)", type="primary"):
        st.session_state.points.append({
            "Time": total_sec, "Temp": temp, "Gas": gas,
            "Event": evt if evt != "기록" else None, "Roast_ID": roast_id
        })

# --- 데이터 편집기 ---
if st.session_state.points:
    st.write("---")
    st.markdown("##### 📝 데이터 수정 (엑셀처럼 클릭해서 수정하세요)")
    
    df_to_edit = pd.DataFrame(st.session_state.points)
    
    edited_df = st.data_editor(
        df_to_edit,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Time": st.column_config.NumberColumn("시간(초)", min_value=0, format="%d"),
            "Temp": st.column_config.NumberColumn("온도(℃)", min_value=0, format="%d"),
            "Gas": st.column_config.NumberColumn("가스압", min_value=0, max_value=15, step=0.1, format="%.1f"),
            "Event": st.column_config.SelectboxColumn("이벤트", options=EVENT_OPTIONS, required=False)
        },
        key="editor"
    )

    if not df_to_edit.equals(edited_df):
        st.session_state.points = edited_df.to_dict('records')
        st.rerun()

# --- 그래프 그리기 ---
fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx()

if st.session_state.points:
    curr_df = pd.DataFrame(st.session_state.points).sort_values('Time')
    ax1.plot(curr_df['Time'], curr_df['Temp'], marker='o', markersize=8, color='#c0392b', linewidth=2, label=f'Current: {roast_id}')
    ax2.plot(curr_df['Time'], curr_df['Gas'], drawstyle='steps-post', marker='x', markersize=8, linestyle='--', color='#2980b9', alpha=0.7, label='Gas')
    
    for _, row in curr_df.iterrows():
        if row['Event']:
            ax1.annotate(row['Event'], (row['Time'], row['Temp']), 
                         xytext=(0, 15), textcoords='offset points', ha='center', 
                         fontsize=11, weight='bold', bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="red"))

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
ax2.set_ylim(0, 10) # 가스압 최대 10으로 제한
ax1.grid(True, linestyle='--', alpha=0.5)
ax1.legend(loc='upper left')
st.pyplot(fig)

# --- 3. 열량 계산 및 저장 ---
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
        
        st.info(f"🔥 총 흡수 열량: {q_total_kj:.1f} kJ")
        st.caption(f"(증발: {q_latent/1000:.1f} kJ + 가열: {q_sensible/1000:.1f} kJ)")
        st.caption(f"수율: {(r_weight/green_weight)*100:.1f}%")

with c2:
    notes = st.text_input("메모", placeholder="맛, 특이사항")
    save_name = st.text_input("파일명", value=f"Roasting_{today}_{bean_name}")

with c3:
    st.write("") # 줄맞춤
    st.write("") 
    
    if st.session_state.points:
        # A. 저장할 CSV 데이터 미리 생성
        save_df = pd.DataFrame(st.session_state.points)
        meta_energy = calculated_energy if calculated_energy else "계산안됨"
        
        csv_buffer = io.StringIO()
        csv_buffer.write(f"파일명,{save_name}\n날짜,{datetime.now().strftime('%Y-%m-%d')}\n원두,{bean_name}\n")
        csv_buffer.write(f"결과무게,{r_weight}\n흡수열량,{meta_energy}\n비고,{notes}\n\n")
        
        # 헤더 이름을 요청하신대로 Time(sec), Temp(C)로 변환하여 저장
        export_df = save_df[['Time', 'Temp', 'Gas', 'Event']].rename(columns={'Time':'Time(sec)', 'Temp':'Temp(C)'})
        export_df.to_csv(csv_buffer, index=False)
        
        csv_data = csv_buffer.getvalue().encode('utf-8-sig')

        def save_to_server_and_clear():
            save_df['Roast_ID'] = roast_id
            mode = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
            header = not os.path.exists(DEFAULT_DATA_FILE)
            save_df.to_csv(DEFAULT_DATA_FILE, mode=mode, header=header, index=False, encoding='utf-8-sig')
            
            st.session_state.points = []
            st.success("서버 저장 및 초기화 완료!")

        st.download_button(
            label="💾 저장 및 다운로드",
            data=csv_data,
            file_name=f"{save_name}.csv",
            mime="text/csv",
            type="primary",
            on_click=save_to_server_and_clear
        )
    else:
        st.button("💾 저장 및 다운로드", disabled=True)
        st.caption("데이터가 없습니다.")
