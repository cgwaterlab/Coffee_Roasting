import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Saemmulter Roasting Log", layout="wide")

# 한글 폰트 설정 (Windows/Mac 호환)
try:
    plt.rcParams['font.family'] = 'Malgun Gothic' 
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# 기본 저장 파일 (통합 DB)
DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- [핵심] CSV 파일 스마트 분석 함수 ---
def load_and_standardize_csv(file, file_name_fallback):
    """
    CSV 파일을 읽어 표준 형식(Time, Temp, Gas, Event)으로 변환합니다.
    Time(sec), Temp(C) 같은 다양한 헤더 형식을 처리하고,
    상단 메타데이터를 건너뛰고 실제 데이터를 찾습니다.
    """
    try:
        # 1. 파일 내용 읽기 (인코딩 대응)
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
            line_lower = line.lower()
            
            # 메타데이터 추출 (옵션: 파일 내부에서 ID나 원두명 찾기)
            if "원두" in line or "bean" in line_lower:
                parts = line.split(',')
                if len(parts) > 1 and parts[1].strip():
                    extracted_id = parts[1].strip()

            # **핵심 점검**: 헤더 키워드 탐색
            # Time(sec) 또는 시간, Temp(C) 또는 온도가 포함된 줄을 헤더로 인식
            if ('time' in line_lower or '시간' in line_lower) and \
               ('temp' in line_lower or '온도' in line_lower):
                header_row_idx = i
                break
        
        # 3. 데이터프레임 로드 (찾은 헤더 위치부터 읽기)
        df = pd.read_csv(io.StringIO(content), header=header_row_idx)
        
        # 4. 컬럼 표준화 (Time(sec) -> Time 등으로 매핑)
        # 컬럼명의 공백과 특수문자를 정리해서 비교
        df.columns = [str(c).strip() for c in df.columns]
        
        col_map = {}
        for col in df.columns:
            c_low = col.lower()
            if 'time' in c_low or '시간' in c_low:
                col_map[col] = 'Time'
            elif 'temp' in c_low or '온도' in c_low:
                col_map[col] = 'Temp'
            elif 'gas' in c_low or '가스' in c_low or '압력' in c_low:
                col_map[col] = 'Gas'
            elif 'event' in c_low or '이벤트' in c_low or '비고' in c_low:
                col_map[col] = 'Event'
        
        df.rename(columns=col_map, inplace=True)
        
        # 필수 데이터 확인
        if 'Time' not in df.columns or 'Temp' not in df.columns:
            return None 

        # 5. 데이터 정제
        standard_df = pd.DataFrame()
        standard_df['Time'] = pd.to_numeric(df['Time'], errors='coerce')
        standard_df['Temp'] = pd.to_numeric(df['Temp'], errors='coerce')
        
        if 'Gas' in df.columns:
            standard_df['Gas'] = pd.to_numeric(df['Gas'], errors='coerce').fillna(0)
        else:
            standard_df['Gas'] = 0
            
        if 'Event' in df.columns:
            standard_df['Event'] = df['Event'].fillna("")
        else:
            standard_df['Event'] = None

        # 유효하지 않은 행 제거
        standard_df = standard_df.dropna(subset=['Time', 'Temp'])
        
        # Roast_ID 설정
        final_id = extracted_id if extracted_id else file_name_fallback.replace('.csv', '')
        standard_df['Roast_ID'] = final_id
            
        return standard_df

    except Exception as e:
        return None

# --- 1. 사이드바: 데이터 센터 ---
st.sidebar.title("📂 로스팅 데이터 센터")

all_history = []

# (1) 내부 DB 로드
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns:
            all_history.append(db_df)
    except:
        pass

# (2) 외부 파일 업로드
uploaded_files = st.sidebar.file_uploader("CSV 파일 업로드", accept_multiple_files=True, type=['csv'])

if uploaded_files:
    for uploaded_file in uploaded_files:
        processed_df = load_and_standardize_csv(uploaded_file, uploaded_file.name)
        if processed_df is not None:
            all_history.append(processed_df)

# (3) 데이터 선택
full_history_df = pd.DataFrame()
selected_ids = []

if all_history:
    full_history_df = pd.concat(all_history, ignore_index=True)
    unique_ids = list(full_history_df['Roast_ID'].unique())
    
    st.sidebar.write("---")
    st.sidebar.header("📊 그래프 비교")
    selected_ids = st.sidebar.multiselect(f"비교할 데이터 ({len(unique_ids)}개)", unique_ids)
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

# A. 현재 데이터 그리기
if st.session_state.points:
    curr_df = pd.DataFrame(st.session_state.points)
    
    # [수정] 온도 그래프: 마커('o') 추가
    ax1.plot(curr_df['Time'], curr_df['Temp'], 
             marker='o', markersize=6,  # <-- 마커 추가
             color='#c0392b', linewidth=2, label=f'Current: {roast_id}')
    
    # [수정] 가스 그래프: 마커('x') 추가
    ax2.plot(curr_df['Time'], curr_df['Gas'], 
             marker='x', markersize=6, linestyle='--', # <-- 마커 추가
             color='#2980b9', alpha=0.7, label='Gas')
    
    # 이벤트 텍스트
    for _, row in curr_df.iterrows():
        if row['Event']:
            ax1.annotate(row['Event'], (row['Time'], row['Temp']), 
                         xytext=(0, 15), textcoords='offset points', ha='center', 
                         fontsize=10, weight='bold', color='black',
                         bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="red", alpha=0.8))

# B. 비교 데이터 그리기
if selected_ids and not full_history_df.empty:
    colors = plt.cm.tab10.colors 
    for i, pid in enumerate(selected_ids):
        p_data = full_history_df[full_history_df['Roast_ID'] == pid].sort_values('Time')
        if not p_data.empty:
            color = colors[i % len(colors)]
            
            # 비교 데이터도 포인트 표시 (작게)
            ax1.plot(p_data['Time'], p_data['Temp'], 
                     marker='.', markersize=4, linestyle='-', # <-- 비교군도 작은 마커 추가
                     linewidth=1, color=color, alpha=0.5, label=f'{pid}')
            
            if 'Gas' in p_data.columns and p_data['Gas'].sum() > 0:
                 ax2.plot(p_data['Time'], p_data['Gas'], linestyle=':', linewidth=1, color=color, alpha=0.3)

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
            
            # 요청하신 형식대로 저장 (메타데이터 + 빈 줄 + 헤더/데이터)
            csv_buffer = io.StringIO()
            csv_buffer.write(f"파일명,{save_name}\n")
            csv_buffer.write(f"날짜,{datetime.now().strftime('%Y-%m-%d')}\n")
            csv_buffer.write(f"원두,{bean_name}\n")
            csv_buffer.write(f"결과무게,{r_weight}\n")
            csv_buffer.write(f"비고,{notes}\n\n")
            
            # 헤더 이름 변경하여 저장 (Time(sec), Temp(C) 등 원하는대로)
            export_df = save_df[['Time', 'Temp', 'Gas', 'Event']].copy()
            export_df.columns = ['Time(sec)', 'Temp(C)', 'Gas', 'Event']
            
            export_df.to_csv(csv_buffer, index=False)
            
            csv_str = csv_buffer.getvalue()
            file_path = f"{save_name}.csv"
            
            # 1. 파일 시스템에 쓰기
            with open(file_path, "w", encoding="utf-8-sig") as f:
                f.write(csv_str)
                
            # 2. 통합 DB에는 데이터만 저장
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
