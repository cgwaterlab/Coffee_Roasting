import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Saemmulter Roasting Log", layout="wide")
# 한글 폰트 설정 (서버 환경에 따라 다를 수 있으므로 예외처리)
try:
    plt.rcParams['font.family'] = 'Malgun Gothic' 
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# 기본 데이터 파일명 (백업용)
DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'

# --- 1. 사이드바: 과거 데이터 비교 기능 ---
st.sidebar.title("🔍 로스팅 기록 비교")

if os.path.exists(DEFAULT_DATA_FILE):
    try:
        history_df = pd.read_csv(DEFAULT_DATA_FILE)
        st.sidebar.success(f"총 {len(history_df['Roast_ID'].unique())}개의 기록이 있습니다.")
        unique_ids = history_df['Roast_ID'].unique()
        selected_ids = st.sidebar.multiselect("비교할 로스팅 ID 선택", unique_ids)
    except:
        history_df = pd.DataFrame()
        selected_ids = []
else:
    history_df = pd.DataFrame()
    st.sidebar.warning("저장된 데이터가 없습니다.")
    selected_ids = []

# --- 2. 메인: 새 로스팅 기록 입력 ---
st.title("☕ 커피 로스팅 실시간 로거")

# (1) 기본 정보 입력
with st.expander("1. 기본 정보 입력 (Start)", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        today = datetime.now().strftime("%Y%m%d")
        bean_name = st.text_input("생두 품종 (예: Geisha Lalucuma)", value="Geisha")
    with col2:
        roast_id = st.text_input("로스팅 고유번호 (ID)", value=f"{bean_name}_{today}")
    with col3:
        initial_temp = st.number_input("투입 온도 (Charge Temp)", value=200, step=10)
        green_weight = st.number_input("생두 무게 (g)", value=250.0)

# (2) 실시간 데이터 입력 (Session State)
if 'points' not in st.session_state:
    st.session_state.points = [] 

# [수정] 섹션 제목 변경
st.subheader("2. 볶은 기록(Roasting) 입력")

# [수정] 컬럼을 5개로 늘려서 '가스압' 추가
col_in1, col_in2, col_in3, col_in4, col_in5 = st.columns([1, 1, 1, 2, 1])

with col_in1:
    curr_time_min = st.number_input("분 (Min)", 0, 30, 0)
    curr_time_sec = st.number_input("초 (Sec)", 0, 59, 0)
    total_sec = curr_time_min * 60 + curr_time_sec

with col_in2:
    curr_temp = st.number_input("온도 (℃)", 0, 300, int(initial_temp))

with col_in3:
    # [수정] 가스압 입력 항목 추가
    gas_pressure = st.number_input("가스압", 0.0, 15.0, 0.0, step=0.1)

with col_in4:
    # [수정] 'Input (투입)' 이벤트 추가
    event_list = ["기록", "Input (투입)", "Turning Point", "Yellowing", "1st Pop", "2nd Pop", "Drop(배출)"]
    event_type = st.selectbox("이벤트", event_list)

with col_in5:
    st.write("") 
    st.write("") 
    if st.button("추가 (Add)", type="primary"):
        st.session_state.points.append({
            "Time": total_sec,
            "Temp": curr_temp,
            "Gas": gas_pressure,  # 가스압 저장
            "Event": event_type if event_type != "기록" else None
        })
        st.success(f"{total_sec}초 / {curr_temp}℃ / 가스 {gas_pressure} 기록")

# (3) 그래프 및 데이터 확인
if st.session_state.points:
    st.write("---")
    current_df = pd.DataFrame(st.session_state.points)
    
    # 그래프 그리기
    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    # 온도 그래프 (왼쪽 축, 빨간색)
    ax1.plot(current_df['Time'], current_df['Temp'], marker='o', color='red', label='Temp (℃)')
    ax1.set_xlabel("Time (Seconds)")
    ax1.set_ylabel("Temperature (℃)", color='red')
    ax1.tick_params(axis='y', labelcolor='red')
    
    # 가스압 그래프 (오른쪽 축, 파란색 점선)
    ax2 = ax1.twinx()
    ax2.plot(current_df['Time'], current_df['Gas'], linestyle='--', marker='x', color='blue', label='Gas Pressure')
    ax2.set_ylabel("Gas Pressure", color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')
    ax2.set_ylim(0, 15) # 가스압 범위 고정

    # 이벤트 텍스트 표시
    for idx, row in current_df.iterrows():
        if row['Event']:
            ax1.annotate(row['Event'], (row['Time'], row['Temp']), 
                        xytext=(0, 15), textcoords='offset points', ha='center', 
                        fontsize=10, color='black', weight='bold',
                        arrowprops=dict(arrowstyle='->', color='black'))

    # 과거 데이터 비교 (온도만 표시)
    if not history_df.empty and selected_ids:
        for comp_id in selected_ids:
            comp_data = history_df[history_df['Roast_ID'] == comp_id].sort_values('Time')
            if not comp_data.empty:
                ax1.plot(comp_data['Time'], comp_data['Temp'], linestyle=':', color='gray', alpha=0.6, label=f"Ref: {comp_id}")

    plt.title(f"Roasting Profile: {roast_id}")
    fig.legend(loc='upper left', bbox_to_anchor=(0.1, 0.9))
    ax1.grid(True, linestyle='--', alpha=0.5)
    st.pyplot(fig)

    # 데이터 테이블
    with st.expander("현재 데이터 목록 확인"):
        st.dataframe(current_df)
        if st.button("맨 마지막 줄 삭제"):
            st.session_state.points.pop()
            st.rerun()

# (4) 종료 및 저장
st.write("---")
st.subheader("3. 종료 및 저장 (Save)")

col_end1, col_end2 = st.columns(2)
with col_end1:
    roasted_weight = st.number_input("배출 후 원두 무게 (g)", value=0.0)
    if roasted_weight > 0 and green_weight > 0:
        yield_rate = (roasted_weight / green_weight) * 100
        st.info(f"수율(Yield): {yield_rate:.1f}%")

with col_end2:
    notes = st.text_area("메모 (맛, 날씨 등)", placeholder="특이사항을 입력하세요")

# [수정] 파일 이름 입력란 추가
save_filename = st.text_input("저장할 파일 이름 (확장자 .csv 제외)", value=f"Roasting_{today}_{bean_name}")

if st.button("파일 저장하기 (Save)", type="primary"):
    if not st.session_state.points:
        st.error("데이터가 없어 저장할 수 없습니다.")
    else:
        # 데이터프레임 생성
        save_df = pd.DataFrame(st.session_state.points)
        save_df['Roast_ID'] = roast_id
        save_df['Date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_df['Bean'] = bean_name
        save_df['Green_Weight'] = green_weight
        save_df['Roasted_Weight'] = roasted_weight
        save_df['Notes'] = notes
        
        # 1. 개별 파일 저장 (사용자가 지정한 이름)
        file_name_csv = f"{save_filename}.csv"
        save_df.to_csv(file_name_csv, index=False, encoding='utf-8-sig')
        
        # 2. 통합 DB 파일에도 누적 저장 (백업용)
        if not os.path.exists(DEFAULT_DATA_FILE):
            save_df.to_csv(DEFAULT_DATA_FILE, index=False, encoding='utf-8-sig')
        else:
            save_df.to_csv(DEFAULT_DATA_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
        
        st.success(f"파일 저장 완료: {file_name_csv}")
        
        # 데이터 초기화
        st.session_state.points = []
        st.balloons()
