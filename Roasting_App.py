import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Saemmulter Roasting Log", layout="wide")
plt.rcParams['font.family'] = 'Malgun Gothic' # Windows 한글 폰트 (Mac은 AppleGothic)
plt.rcParams['axes.unicode_minus'] = False

# 데이터 저장 파일명
DATA_FILE = 'saemmulter_roasting_db.csv'

# --- 1. 사이드바: 과거 데이터 비교 기능 ---
st.sidebar.title("🔍 로스팅 기록 비교")

# 데이터 파일이 있으면 불러오기
if os.path.exists(DATA_FILE):
    history_df = pd.read_csv(DATA_FILE)
    st.sidebar.success(f"총 {len(history_df['Roast_ID'].unique())}개의 기록이 있습니다.")
    
    # 비교할 데이터 선택
    unique_ids = history_df['Roast_ID'].unique()
    selected_ids = st.sidebar.multiselect("비교할 로스팅 ID 선택", unique_ids)
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

# (2) 실시간 온도/시간 기록 (Session State 사용)
if 'points' not in st.session_state:
    st.session_state.points = [] # [(시간, 온도, 이벤트)]

st.subheader("2. 실시간 기록 (Input)")
col_in1, col_in2, col_in3, col_in4 = st.columns([1, 1, 2, 1])

with col_in1:
    curr_time_min = st.number_input("분 (Min)", 0, 20, 0)
    curr_time_sec = st.number_input("초 (Sec)", 0, 59, 0)
    total_sec = curr_time_min * 60 + curr_time_sec
with col_in2:
    curr_temp = st.number_input("현재 온도 (℃)", 0, 300, int(initial_temp))
with col_in3:
    event_type = st.selectbox("이벤트 (선택)", ["기록", "Turning Point", "Yellowing", "1st Pop", "2nd Pop", "Drop(배출)"])
with col_in4:
    st.write("") # 줄맞춤용
    st.write("") 
    if st.button("데이터 추가 (Add)", type="primary"):
        st.session_state.points.append({
            "Time": total_sec,
            "Temp": curr_temp,
            "Event": event_type if event_type != "기록" else None
        })
        st.success(f"{total_sec}초 / {curr_temp}도 기록됨")

# (3) 기록된 데이터 수정/삭제 기능
if st.session_state.points:
    st.write("---")
    # 현재 기록 중인 데이터를 DataFrame으로 변환
    current_df = pd.DataFrame(st.session_state.points)
    
    # 그래프 그리기
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 1. 현재 로스팅 그래프 (빨간색 실선)
    ax.plot(current_df['Time'], current_df['Temp'], marker='o', color='red', label='Current Roast')
    
    # 이벤트 표시 (현재 로스팅)
    for idx, row in current_df.iterrows():
        if row['Event']:
            ax.annotate(row['Event'], (row['Time'], row['Temp']), 
                        xytext=(0, 10), textcoords='offset points', ha='center', fontsize=9, color='red', weight='bold')

    # 2. 비교 데이터 그래프 (회색 점선)
    if not history_df.empty and selected_ids:
        for comp_id in selected_ids:
            comp_data = history_df[history_df['Roast_ID'] == comp_id]
            # 시간순 정렬
            comp_data = comp_data.sort_values('Time')
            ax.plot(comp_data['Time'], comp_data['Temp'], linestyle='--', alpha=0.5, label=f"Compare: {comp_id}")
            
            # 비교 데이터의 1st Pop 표시
            pop_data = comp_data[comp_data['Event'] == '1st Pop']
            if not pop_data.empty:
                 ax.plot(pop_data['Time'], pop_data['Temp'], 'x', color='blue')

    ax.set_xlabel("Time (Seconds)")
    ax.set_ylabel("Temperature (℃)")
    ax.set_title(f"Roasting Profile: {roast_id}")
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.6)
    
    st.pyplot(fig)

    # 데이터 테이블 보여주기 (삭제 가능)
    with st.expander("현재 기록된 데이터 목록 (수정 가능)"):
        st.dataframe(current_df)
        if st.button("마지막 데이터 삭제"):
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
        loss_rate = 100 - yield_rate
        st.info(f"수율(Yield): {yield_rate:.1f}% (손실률: {loss_rate:.1f}%)")
    
with col_end2:
    notes = st.text_area("비고 / 메모 (맛, 날씨, 특이사항)", placeholder="예: 1차 팝 소리가 작았음. 향이 매우 좋음.")

if st.button("로스팅 완료 및 파일 저장 (Save to CSV)", type="primary"):
    if not st.session_state.points:
        st.error("저장할 데이터가 없습니다.")
    else:
        # 저장할 데이터프레임 생성
        save_df = pd.DataFrame(st.session_state.points)
        save_df['Roast_ID'] = roast_id
        save_df['Date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_df['Bean'] = bean_name
        save_df['Green_Weight'] = green_weight
        save_df['Roasted_Weight'] = roasted_weight
        save_df['Notes'] = notes
        
        # 기존 파일이 없으면 헤더 포함 저장, 있으면 내용만 추가
        if not os.path.exists(DATA_FILE):
            save_df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
        else:
            save_df.to_csv(DATA_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
        
        st.success(f"저장 완료! 파일명: {DATA_FILE}")
        
        # 초기화
        st.session_state.points = []
        st.balloons()
