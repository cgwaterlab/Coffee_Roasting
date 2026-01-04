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

# --- [함수] CSV 파일 읽기 및 표준화 (호환성 강화) ---
def load_and_standardize_csv(file, file_name):
    """
    업로드된 파일이나 기존 파일을 읽어서 표준 형식(Time, Temp, Gas, Event)으로 변환
    """
    try:
        # 1. 파일 읽기 (인코딩 처리)
        try:
            df = pd.read_csv(file, encoding='utf-8-sig')
        except:
            file.seek(0)
            df = pd.read_csv(file, encoding='cp949')

        # 2. 헤더 위치 찾기 (Time, Temp 컬럼이 있는 줄 찾기)
        # 이미 읽은 df의 컬럼이나 데이터에서 키워드 탐색
        # Streamlit 업로드 객체는 seek 가능하지만, 간단히 df 상태에서 처리 시도
        
        # 만약 첫 줄이 헤더가 아니라면 다시 찾기
        cols = [str(c).lower() for c in df.columns]
        if not any('time' in c or '시간' in c for c in cols):
            # 헤더가 중간에 있는 경우: 다시 읽기 (파일 포인터 리셋 필요)
            if hasattr(file, 'seek'):
                file.seek(0)
                lines = file.readlines()
                header_row = 0
                for i, line in enumerate(lines):
                    # 바이너리인 경우 디코딩
                    if isinstance(line, bytes):
                        line = line.decode('utf-8', errors='ignore')
                    if ('시간' in line or 'Time' in line) and ('온도' in line or 'Temp' in line):
                        header_row = i
                        break
                if hasattr(file, 'seek'): file.seek(0)
                df = pd.read_csv(file, header=header_row, encoding='utf-8-sig')

        # 3. 컬럼 매핑
        df.columns = [str(c).strip() for c in df.columns]
        
        # 필요한 컬럼 찾기
        time_col = next((c for c in df.columns if '시간' in c or 'Time' in c), None)
        temp_col = next((c for c in df.columns if '온도' in c or 'Temp' in c), None)
        gas_col = next((c for c in df.columns if '가스' in c or 'Gas' in c or '압력' in c), None)
        event_col = next((c for c in df.columns if '이벤트' in c or 'Event' in c or '비고' in c), None)
        id_col = next((c for c in df.columns if 'Roast_ID' in c), None)

        if not time_col or not temp_col:
            return None # 필수 컬럼 없음

        # 4. 데이터 표준화
        standard_df = pd.DataFrame()
        
        # 시간 변환 (mm:ss 처리 등은 복잡하므로 일단 숫자/초 단위 가정)
        # 문자열인 경우 파싱 로직이 필요할 수 있으나, 여기선 숫자 변환 시도
        standard_df['Time'] = pd.to_numeric(df[time_col], errors='coerce')
        standard_df['Temp'] = pd.to_numeric(df[temp_col], errors='coerce')
        
        if gas_col:
            standard_df['Gas'] = pd.to_numeric(df[gas_col], errors='coerce')
        else:
            standard_df['Gas'] = 0
            
        if event_col:
            standard_df['Event'] = df[event_col]
        else:
            standard_df['Event'] = None

        # 결측치 제거
        standard_df = standard_df.dropna(subset=['Time', 'Temp'])
        
        # Roast_ID 부여 (파일에 없으면 파일명 사용)
        if id_col:
            standard_df['Roast_ID'] = df[id_col].iloc[0] if not df[id_col].empty else file_name.replace('.csv', '')
        else:
            standard_df['Roast_ID'] = file_name.replace('.csv', '')
            
        return standard_df

    except Exception as e:
        # st.error(f"파일 읽기 오류 ({file_name}): {e}")
        return None

# --- 1. 사이드바: 데이터 로드 및 비교 선택 ---
st.sidebar.title("📂 로스팅 데이터 센터")

# (1) 통합 DB 파일 로드
all_history = []

if os.path.exists(DEFAULT_DATA_FILE):
    try:
        # 통합 DB는 형식이 일정하다고 가정
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        # 필수 컬럼 확인
        if 'Roast_ID' in db_df.columns:
            all_history.append(db_df)
    except Exception as e:
        st.sidebar.error(f"DB 파일 로드 실패: {e}")

# (2) [신규 기능] 외부 CSV 파일 업로드
uploaded_files = st.sidebar.file_uploader("기존 CSV 파일 업로드 (다중 선택 가능)", accept_multiple_files=True, type=['csv'])

if uploaded_files:
    for uploaded_file in uploaded_files:
        # 업로드된 파일을 표준 형식으로 변환하여 리스트에 추가
        processed_df = load_and_standardize_csv(uploaded_file, uploaded_file.name)
        if processed_df is not None:
            all_history.append(processed_df)

# (3) 데이터 합치기 및 선택 메뉴
if all_history:
    # 모든 데이터를 하나의 DataFrame으로 병합
    full_history_df = pd.concat(all_history, ignore_index=True)
    
    # ID 목록 추출 (최신순)
    # Roast_ID 별로 그룹화해서 대표 정보 보여주기 등은 생략하고 단순 목록 표시
    unique_ids = full_history_df['Roast_ID'].unique()
    
    st.sidebar.write("---")
    st.sidebar.header("📊 비교 그래프 선택")
    selected_ids = st.sidebar.multiselect(
        f"비교할 데이터 선택 (총 {len(unique_ids)}개)", 
        unique_ids
    )
else:
    full_history_df = pd.DataFrame()
    selected_ids = []
    st.sidebar.info("저장된 데이터나 업로드된 파일이 없습니다.")


# --- 2. 메인: 입력 및 시각화 ---
st.title("☕ Smart Roasting Logger")

# (1) 기본 정보 입력
with st.expander("1. 로스팅 정보 입력 (Setup)", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        today = datetime.now().strftime("%Y%m%d")
        bean_name = st.text_input("생두 품종", value="Geisha")
    with col2:
        roast_id = st.text_input("로스팅 ID (자동 생성)", value=f"{bean_name}_{today}")
    with col3:
        initial_temp = st.number_input("투입 온도 (℃)", value=200, step=10)
        green_weight = st.number_input("생두 무게 (g)", value=250.0)

# (2) 실시간 기록 (입력)
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
            "Roast_ID": roast_id # 현재 작업 ID
        })

# (3) 그래프 시각화 (현재 + 비교)
st.write("---")
fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx() # 가스압용 축

# A. 현재 작성 중인 데이터 그리기
if st.session_state.points:
    curr_df = pd.DataFrame(st.session_state.points)
    # 온도 (빨강, 실선)
    ax1.plot(curr_df['Time'], curr_df['Temp'], marker='o', color='#c0392b', linewidth=2, label=f'Current: {roast_id}')
    # 가스 (파랑, 점선)
    ax2.plot(curr_df['Time'], curr_df['Gas'], linestyle='--', color='#2980b9', alpha=0.7, label='Current Gas')
    
    # 이벤트 표시
    for _, row in curr_df.iterrows():
        if row['Event']:
            ax1.annotate(row['Event'], (row['Time'], row['Temp']), 
                         xytext=(0, 15), textcoords='offset points', ha='center', 
                         fontsize=11, color='black', weight='bold',
                         bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="red", alpha=0.8))

# B. 사이드바에서 선택한 과거 데이터 그리기 (비교)
if selected_ids and not full_history_df.empty:
    # 색상 팔레트 (여러 개 비교 시 색상 구분)
    colors = plt.cm.tab10.colors 
    
    for i, pid in enumerate(selected_ids):
        p_data = full_history_df[full_history_df['Roast_ID'] == pid].sort_values('Time')
        if not p_data.empty:
            color = colors[i % len(colors)]
            # 비교 대상은 조금 투명하게 그림
            ax1.plot(p_data['Time'], p_data['Temp'], linestyle='-', linewidth=1.5, color=color, alpha=0.6, label=f'{pid}')
            
            # 비교 대상의 1st Pop 표시
            pop_pt = p_data[p_data['Event'].astype(str).str.contains('Pop', na=False)]
            if not pop_pt.empty:
                 ax1.scatter(pop_pt['Time'], pop_pt['Temp'], marker='*', s=100, color=color, zorder=10)

# 그래프 꾸미기
ax1.set_xlabel("Time (Seconds)")
ax1.set_ylabel("Temperature (℃)", color='#c0392b')
ax2.set_ylabel("Gas Pressure", color='#2980b9')
ax2.set_ylim(0, 15)
ax1.grid(True, linestyle='--', alpha=0.5)
ax1.legend(loc='upper left')

st.pyplot(fig)

# 데이터 테이블 확인
if st.session_state.points:
    with st.expander("📝 현재 입력 데이터 확인/수정"):
        st.dataframe(pd.DataFrame(st.session_state.points))
        if st.button("마지막 입력 취소"):
            st.session_state.points.pop()
            st.rerun()

# (4) 저장
st.subheader("3. 종료 및 저장 (Save)")
col_s1, col_s2, col_s3 = st.columns([1, 2, 1])

with col_s1:
    r_weight = st.number_input("배출 원두 무게(g)", 0.0)
    if r_weight > 0:
        st.caption(f"수율: {(r_weight/green_weight)*100:.1f}%")

with col_s2:
    notes = st.text_input("메모", placeholder="맛, 날씨 등")
    save_name = st.text_input("저장 파일명", value=f"Roasting_{today}_{bean_name}")

with col_s3:
    st.write("")
    st.write("")
    if st.button("💾 저장하기", type="primary"):
        if not st.session_state.points:
            st.error("데이터가 없습니다!")
        else:
            save_df = pd.DataFrame(st.session_state.points)
            # 메타데이터 추가
            save_df['Roast_ID'] = roast_id
            save_df['Date'] = datetime.now().strftime("%Y-%m-%d")
            save_df['Bean'] = bean_name
            save_df['Notes'] = notes
            
            # 1. 개별 CSV 저장
            csv_name = f"{save_name}.csv"
            save_df.to_csv(csv_name, index=False, encoding='utf-8-sig')
            
            # 2. 통합 DB에 추가 (없으면 생성, 있으면 이어쓰기)
            if not os.path.exists(DEFAULT_DATA_FILE):
                save_df.to_csv(DEFAULT_DATA_FILE, index=False, encoding='utf-8-sig')
            else:
                save_df.to_csv(DEFAULT_DATA_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
            
            st.success(f"저장 완료! ({csv_name})")
            
            # 초기화 및 새로고침 (즉시 사이드바 반영을 위해)
            st.session_state.points = []
            st.rerun()
