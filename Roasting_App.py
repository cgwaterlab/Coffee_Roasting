import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Saemmulter Roasting Log", layout="wide")

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic' 
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# 기본 저장 파일 (통합 DB)
DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- [핵심 함수] CSV 파일 스마트 읽기 ---
def load_and_standardize_csv(file, file_name_fallback):
    """
    업로드된 파일의 구조(상단 메타데이터 유무)를 파악하여 표준 형식으로 변환
    """
    try:
        # 1. 파일의 모든 줄을 먼저 읽어서 구조 파악
        # (Streamlit UploadedFile 객체는 seek(0)으로 재사용 가능)
        file.seek(0)
        try:
            content = file.read().decode('utf-8-sig')
        except:
            file.seek(0)
            content = file.read().decode('cp949', errors='ignore')
            
        lines = content.splitlines()
        
        # 2. 헤더 행(데이터 시작 줄) 찾기
        header_row_idx = 0
        extracted_id = None
        
        for i, line in enumerate(lines):
            # 메타데이터에서 원두 이름이나 파일명 찾기 (옵션)
            if "원두" in line or "이름" in line or "파일명" in line:
                parts = line.split(',')
                if len(parts) > 1 and parts[1].strip():
                    extracted_id = parts[1].strip()

            # 헤더 키워드 탐색 (Time/시간 AND Temp/온도)
            line_lower = line.lower()
            if ('time' in line_lower or '시간' in line_lower) and \
               ('temp' in line_lower or '온도' in line_lower):
                header_row_idx = i
                break
        
        # 3. 데이터프레임 로드 (찾은 헤더 위치부터 읽기)
        # io.StringIO를 사용하여 문자열을 파일처럼 취급
        df = pd.read_csv(io.StringIO(content), header=header_row_idx)
        
        # 4. 컬럼 표준화
        # 공백 제거 및 소문자 변환하여 비교
        df.columns = [str(c).strip() for c in df.columns]
        
        time_col = next((c for c in df.columns if 'time' in c.lower() or '시간' in c), None)
        temp_col = next((c for c in df.columns if 'temp' in c.lower() or '온도' in c), None)
        gas_col  = next((c for c in df.columns if 'gas' in c.lower() or '가스' in c or '압력' in c), None)
        event_col = next((c for c in df.columns if 'event' in c.lower() or '이벤트' in c or '비고' in c), None)
        
        if not time_col or not temp_col:
            return None # 필수 데이터 없음

        # 5. 최종 데이터 생성
        standard_df = pd.DataFrame()
        standard_df['Time'] = pd.to_numeric(df[time_col], errors='coerce')
        standard_df['Temp'] = pd.to_numeric(df[temp_col], errors='coerce')
        
        if gas_col:
            standard_df['Gas'] = pd.to_numeric(df[gas_col], errors='coerce').fillna(0)
        else:
            standard_df['Gas'] = 0
            
        if event_col:
            standard_df['Event'] = df[event_col].fillna("")
        else:
            standard_df['Event'] = None

        # 결측치 제거 (시간이나 온도가 없는 행은 데이터가 아님)
        standard_df = standard_df.dropna(subset=['Time', 'Temp'])
        
        # Roast_ID 설정 (메타데이터에서 찾았으면 그거 쓰고, 아니면 파일명)
        final_id = extracted_id if extracted_id else file_name_fallback.replace('.csv', '')
        standard_df['Roast_ID'] = final_id
            
        return standard_df

    except Exception as e:
        # 디버깅용 에러 메시지 (필요시 주석 해제)
        # st.error(f"Error parsing {file_name_fallback}: {e}")
        return None

# --- 1. 사이드바: 데이터 센터 ---
st.sidebar.title("📂 로스팅 데이터 센터")

# 데이터 저장소
all_history = []

# (1) 내부 DB 로드
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns:
            all_history.append(db_df)
    except:
        pass

# (2) 외부 파일 업로드 (기존 + 신규 형식 지원)
uploaded_files = st.sidebar.file_uploader("CSV 파일 업로드 (Drag & Drop)", accept_multiple_files=True, type=['csv'])

if uploaded_files:
    for uploaded_file in uploaded_files:
        processed_df = load_and_standardize_csv(uploaded_file, uploaded_file.name)
        if processed_df is not None:
            all_history.append(processed_df)

# (3) 데이터 병합 및 선택
full_history_df = pd.DataFrame()
selected_ids = []

if all_history:
    full_history_df = pd.concat(all_history, ignore_index=True)
    # ID 리스트 (중복 제거)
    unique_ids = list(full_history_df['Roast_ID'].unique())
    
    st.sidebar.write("---")
    st.sidebar.header("📊 그래프 비교 선택")
    selected_ids = st.sidebar.multiselect(
        f"비교할 데이터 ({len(unique_ids)}개)", 
        unique_ids
    )
else:
    st.sidebar.info("데이터가 없습니다.")


# --- 2. 메인: 입력 및 시각화 ---
st.title("☕ Smart Roasting Logger")

# (1) 로스팅 정보 입력
with st.expander("1. 로스팅 정보 설정", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        today = datetime.now().strftime("%Y%m%d")
        bean_name = st.text_input("생두 품종", value="Geisha")
    with col2:
        roast_id = st.text_input("로스팅 ID", value=f"{bean_name}_{today}")
    with col3:
        initial_temp = st.number_input("투입 온도 (℃)", value=200, step=10)
        green_weight = st.number_input("생두 무게 (g)", value=250.0)

# (2) 실시간 데이터 입력
if 'points' not in st.session_state:
    st.session_state.points = [] 

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
    evt = st.selectbox("이벤트", ["기록", "Input (투입)", "TP", "Yellowing", "1st Pop", "2nd Pop", "Drop"])
with c5:
    st.write("")
    st.write("")
    if st.button("추가 (Enter)", type="primary"):
        st.session_state.points.append({
            "Time": total_sec,
            "Temp": temp,
            "Gas": gas,
            "Event": evt if evt != "기록" else None,
            "Roast_ID": roast_id
        })

# (3) 그래프 그리기
st.write("---")
fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx()

# A. 현재 데이터
if st.session_state.points:
    curr_df = pd.DataFrame(st.session_state.points)
    ax1.plot(curr_df['Time'], curr_df['Temp'], marker='o', color='#c0392b', linewidth=2, label=f'Current: {roast_id}')
    ax2.plot(curr_df['Time'], curr_df['Gas'], linestyle='--', color='#2980b9', alpha=0.7, label='Gas')
    
    # 이벤트 텍스트
    for _, row in curr_df.iterrows():
        if row['Event']:
            ax1.annotate(row['Event'], (row['Time'], row['Temp']), 
                         xytext=(0, 15), textcoords='offset points', ha='center', 
                         fontsize=10, weight='bold', color='black',
                         bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="red", alpha=0.8))

# B. 비교 데이터
if selected_ids and not full_history_df.empty:
    colors = plt.cm.tab10.colors 
    for i, pid in enumerate(selected_ids):
        p_data = full_history_df[full_history_df['Roast_ID'] == pid].sort_values('Time')
        if not p_data.empty:
            color = colors[i % len(colors)]
            # 온도 (실선, 투명도)
            ax1.plot(p_data['Time'], p_data['Temp'], linestyle='-', linewidth=1.5, color=color, alpha=0.5, label=f'{pid}')
            
            # 가스 (점선, 투명도) - 데이터가 있다면
            if 'Gas' in p_data.columns and p_data['Gas'].sum() > 0:
                 ax2.plot(p_data['Time'], p_data['Gas'], linestyle=':', linewidth=1, color=color, alpha=0.3)

            # 이벤트 1차 팝 표시
            pop_pt = p_data[p_data['Event'].astype(str).str.contains('Pop', na=False, case=False)]
            if not pop_pt.empty:
                 ax1.scatter(pop_pt['Time'], pop_pt['Temp'], marker='*', s=120, color=color, zorder=10, edgecolors='black')

ax1.set_xlabel("Time (Seconds)")
ax1.set_ylabel("Temperature (℃)", color='#c0392b')
ax2.set_ylabel("Gas Pressure", color='#2980b9')
ax2.set_ylim(0, 15)
ax1.grid(True, linestyle='--', alpha=0.5)
ax1.legend(loc='upper left')

st.pyplot(fig)

# (4) 저장 및 다운로드
st.subheader("3. 종료 및 저장")
col_s1, col_s2, col_s3 = st.columns([1, 2, 1])

with col_s1:
    r_weight = st.number_input("배출 무게(g)", 0.0)
    if r_weight > 0:
        st.caption(f"수율: {(r_weight/green_weight)*100:.1f}%")

with col_s2:
    notes = st.text_input("메모", placeholder="맛, 특이사항")
    save_name = st.text_input("파일명", value=f"Roasting_{today}_{bean_name}")

with col_s3:
    st.write("")
    st.write("")
    if st.button("💾 저장하기", type="primary"):
        if st.session_state.points:
            save_df = pd.DataFrame(st.session_state.points)
            # 메타데이터 추가 (상단에 별도 표기 대신 컬럼으로 추가하거나, 별도 파일 구조 생성 가능)
            # 여기서는 요청하신 '메타데이터 상단 + 데이터 하단' 형식으로 저장 구현
            
            csv_buffer = io.StringIO()
            # 1. 메타데이터 쓰기
            csv_buffer.write(f"파일명,{save_name}\n")
            csv_buffer.write(f"날짜,{datetime.now().strftime('%Y-%m-%d')}\n")
            csv_buffer.write(f"원두,{bean_name}\n")
            csv_buffer.write(f"결과무게,{r_weight}\n")
            csv_buffer.write(f"비고,{notes}\n\n")
            # 2. 헤더 및 데이터 쓰기
            save_df[['Time', 'Temp', 'Gas', 'Event']].to_csv(csv_buffer, index=False)
            
            csv_str = csv_buffer.getvalue()
            file_path = f"{save_name}.csv"
            
            # 파일 저장
            with open(file_path, "w", encoding="utf-8-sig") as f:
                f.write(csv_str)
                
            # 통합 DB에도 (간소화하여) 저장
            save_df['Roast_ID'] = roast_id
            if not os.path.exists(DEFAULT_DATA_FILE):
                save_df.to_csv(DEFAULT_DATA_FILE, index=False, encoding='utf-8-sig')
            else:
                save_df.to_csv(DEFAULT_DATA_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')

            st.success(f"저장 완료: {file_path}")
            st.session_state.points = []
            st.rerun()
        else:
            st.error("데이터 없음")
