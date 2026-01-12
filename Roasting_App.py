import streamlit as st
import pandas as pd
import time
from datetime import datetime
import streamlit.components.v1 as components

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 디자인
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Peru Coffee Roaster Pro", page_icon="☕", layout="wide")

# CSS로 디자인 다듬기 (테이블, 버튼 등)
st.markdown("""
<style>
    div.stButton > button:first-child {
        height: 3em; font-weight: bold; border-radius: 10px;
    }
    .big-font { font-size: 20px !important; font-weight: bold; }
    .stAlert { padding: 10px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 세션 상태 초기화 (데이터 저장소)
# -----------------------------------------------------------------------------
if 'roasting_data' not in st.session_state:
    st.session_state.roasting_data = [] # 시간, 온도, 가스, 이벤트 저장
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'start_time' not in st.session_state:
    st.session_state.start_time = None

# -----------------------------------------------------------------------------
# 3. [핵심] 자바스크립트 실시간 타이머 함수
# -----------------------------------------------------------------------------
def show_realtime_clock():
    """
    Streamlit은 파이썬이라 스스로 갱신이 안 되므로, 
    자바스크립트를 심어서 브라우저가 시간을 계산하게 만듭니다.
    """
    if st.session_state.is_running and st.session_state.start_time:
        # 현재 시작 시간(timestamp)을 자바스크립트로 넘김
        start_ts = st.session_state.start_time
        
        # JS 코드: 현재시간 - 시작시간 = 경과시간 표시
        clock_html = f"""
        <div style="
            font-size: 3.5em; 
            font-weight: 800; 
            text-align: center; 
            color: #2d3436; 
            font-family: 'Courier New', monospace;
            margin: 10px 0;
            background-color: #f0f2f5;
            padding: 10px;
            border-radius: 10px;
        " id="timer_display">00:00</div>
        
        <script>
        function updateTimer() {{
            const startTime = {start_ts} * 1000; // 파이썬 초 -> 밀리초 변환
            const now = new Date().getTime();
            const diff = Math.floor((now - startTime) / 1000);
            
            if (diff < 0) return;

            const m = Math.floor(diff / 60).toString().padStart(2, '0');
            const s = (diff % 60).toString().padStart(2, '0');
            
            const display = document.getElementById('timer_display');
            if(display) {{
                display.innerText = m + ':' + s;
            }}
        }}
        // 1초마다 실행
        setInterval(updateTimer, 1000);
        updateTimer(); // 즉시 실행
        </script>
        """
        components.html(clock_html, height=100)
    else:
        # 멈춰있을 때 혹은 초기화 상태
        st.markdown(f"""
            <div style="font-size: 3.5em; font-weight: 800; text-align: center; color: #b2bec3; font-family: 'Courier New', monospace; margin: 10px 0;">
                00:00
            </div>
        """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. 기능 함수들 (RoR, DTR 등)
# -----------------------------------------------------------------------------
def calculate_ror(data):
    # 간단한 RoR 계산 (현재 - 이전)
    if len(data) < 2:
        return 0.0
    curr = data[-1]
    prev = data[-2]
    time_diff = (curr['Time'] - prev['Time']) / 60.0 # 분 단위
    if time_diff <= 0:
        return 0.0
    return (curr['Temp'] - prev['Temp']) / time_diff

def analyze_roast(final_time, drop_temp):
    df = pd.DataFrame(st.session_state.roasting_data)
    
    # 1차 팝 찾기
    crack_row = df[df['Event'] == '1C Start']
    
    msg = f"⏱ **총 로스팅 시간:** {int(final_time//60)}분 {int(final_time%60)}초\n"
    
    # DTR 계산
    if not crack_row.empty:
        crack_time = crack_row.iloc[0]['Time']
        dev_time = final_time - crack_time
        dtr = (dev_time / final_time) * 100
        
        msg += f"🔥 **디벨롭 시간:** {int(dev_time//60)}분 {int(dev_time%60)}초 (DTR: {dtr:.1f}%)\n\n"
        
        # AI 예상 멘트
        msg += "☕ **[로스팅 결과 예상]**\n"
        if dtr < 15:
            msg += "👉 **Light (약배전):** 산미와 화사한 향이 특징일 것 같아요."
        elif dtr < 20:
            msg += "👉 **Medium-Light (중약배전):** 산미와 단맛의 밸런스가 기대되네요."
        elif dtr < 25:
            msg += "👉 **Medium (중배전):** 단맛과 바디감이 좋은 편안한 맛이겠어요."
        else:
            msg += "👉 **Dark (강배전):** 묵직한 바디감과 쌉싸름함이 느껴지겠네요."
    else:
        msg += "⚠️ 1차 팝이 기록되지 않아 DTR을 계산할 수 없습니다."
        
    return msg

# -----------------------------------------------------------------------------
# 5. UI 구성 (사이드바 - 설정)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("1. 로스팅 준비 (Setup)")
    roast_date = st.date_input("날짜 (Date)", datetime.now())
    roaster_name = st.text_input("로스터 이름", "홍길동")
    
    roast_method = st.selectbox("방식 (Method)", [
        "Half Hot Air (Gas)", "Direct Fire", "Hot Air (Fluid Bed)", 
        "Electric Drum", "Sample Roaster", "Pan Roasting", "Charcoal"
    ])
    
    bean_name = st.text_input("원두 이름", "Example Bean")
    green_weight = st.number_input("생두 무게 (g)", value=250, step=10)
    charge_temp = st.number_input("투입 온도 (℃)", value=200, step=5)

    st.markdown("---")
    st.markdown("### 💾 데이터 관리")
    if st.button("🗑️ 모든 데이터 초기화"):
        st.session_state.roasting_data = []
        st.session_state.is_running = False
        st.session_state.start_time = None
        st.rerun()

# -----------------------------------------------------------------------------
# 6. UI 구성 (메인 - 로스팅 진행)
# -----------------------------------------------------------------------------
st.title("☕ Smart Roasting Logger <Pro>")

# 상단: 타이머 및 컨트롤
col_timer, col_ctrl = st.columns([2, 1])

with col_timer:
    # 여기에 자바스크립트 시계 표시
    show_realtime_clock()

with col_ctrl:
    st.write("## 컨트롤")
    if not st.session_state.is_running:
        if st.button("🔥 로스팅 시작 (START)", type="primary", use_container_width=True):
            st.session_state.is_running = True
            st.session_state.start_time = time.time()
            # 시작 시 Charge 자동 기록
            st.session_state.roasting_data.append({
                "Time": 0, 
                "Temp": charge_temp, 
                "Gas": 0.0, 
                "Event": "Charge", 
                "RoR": 0.0
            })
            st.rerun()
    else:
        if st.button("🛑 강제 종료 (STOP)", type="secondary", use_container_width=True):
            st.session_state.is_running = False
            st.rerun()

st.markdown("---")

# 중단: 데이터 입력 창
st.subheader("2. 데이터 기록 (Process)")

# 입력 폼을 Form으로 감싸면 엔터키 입력 처리가 수월함
with st.form(key='data_entry_form', clear_on_submit=True):
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        current_temp = st.number_input("현재 온도 (℃)", min_value=0.0, max_value=300.0, step=1.0)
    with c2:
        gas_pressure = st.number_input("가스압 (kPa)", min_value=0.0, max_value=15.0, step=0.1)
    with c3:
        event_select = st.selectbox("이벤트", ["(없음)", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"])
    with c4:
        st.write("") 
        st.write("")
        submit_btn = st.form_submit_button("📝 기록 (Enter)", use_container_width=True)

    # 기록 버튼 눌렀을 때 로직
    if submit_btn and st.session_state.is_running:
        # 시간 계산
        elapsed = time.time() - st.session_state.start_time
        
        # 데이터 저장
        new_data = {
            "Time": round(elapsed, 1),
            "Temp": current_temp,
            "Gas": gas_pressure,
            "Event": event_select if event_select != "(없음)" else ""
        }
        
        # 임시 추가 후 RoR 계산
        st.session_state.roasting_data.append(new_data)
        ror = calculate_ror(st.session_state.roasting_data)
        st.session_state.roasting_data[-1]["RoR"] = round(ror, 2) # RoR 업데이트
        
        # Drop 이벤트 발생 시 자동 종료 및 분석
        if event_select == "Drop":
            st.session_state.is_running = False
            st.success("🎉 로스팅이 완료되었습니다! 아래 결과를 확인하세요.")
        
        st.rerun()

# -----------------------------------------------------------------------------
# 7. 차트 및 데이터 테이블 표시
# -----------------------------------------------------------------------------
col_chart, col_table = st.columns([2, 1])

if st.session_state.roasting_data:
    df = pd.DataFrame(st.session_state.roasting_data)
    
    with col_chart:
        st.subheader("📈 프로파일 그래프")
        
        # 차트 그리기 (온도와 RoR)
        chart_data = df[['Time', 'Temp', 'RoR']].set_index('Time')
        st.line_chart(chart_data, height=400)
        
        # 실시간 RoR 상태 메시지
        last_ror = df.iloc[-1]['RoR']
        last_temp = df.iloc[-1]['Temp']
        
        if last_ror >= 15:
            st.error(f"⚠️ 화력이 너무 강합니다! (RoR: {last_ror})")
        elif last_ror < 0:
            st.info(f"📉 온도가 떨어지고 있습니다. (RoR: {last_ror})")

    with col_table:
        st.subheader("📝 기록 데이터")
        # 보기 좋게 컬럼 순서 정리
        st.dataframe(df[['Time', 'Temp', 'Gas', 'RoR', 'Event']], height=400, hide_index=True)

# -----------------------------------------------------------------------------
# 8. 결과 분석 및 저장 (Drop 이후 활성화)
# -----------------------------------------------------------------------------
if not st.session_state.is_running and len(st.session_state.roasting_data) > 1:
    last_event = st.session_state.roasting_data[-1]['Event']
    
    # Drop으로 끝났거나 강제종료 되었을 때
    st.markdown("---")
    st.header("3. 결과 분석 및 저장 (Result)")
    
    c_res1, c_res2 = st.columns(2)
    
    with c_res1:
        # 자동 분석 멘트
        final_time = st.session_state.roasting_data[-1]['Time']
        final_temp = st.session_state.roasting_data[-1]['Temp']
        analysis_text = analyze_roast(final_time, final_temp)
        st.info(analysis_text)
        
    with c_res2:
        # 아그트론 및 무게 입력
        st.write("#### ⚖️ QC 데이터 입력")
        roasted_weight = st.number_input("배출 무게 (g)", value=0)
        agtron_num = st.number_input("아그트론 (Agtron #)", value=0)
        
        if roasted_weight > 0 and green_weight > 0:
            yield_ratio = (roasted_weight / green_weight) * 100
            st.success(f"📉 **수율 (Yield):** {yield_ratio:.1f}%")
            
        if agtron_num > 0:
            # 아그트론 비교 로직 (간단 버전)
            expected = ""
            if final_temp < 205: expected = "Light (80~110)"
            elif final_temp < 215: expected = "Medium-Light (65~80)"
            elif final_temp < 225: expected = "Medium (50~65)"
            else: expected = "Dark (20~50)"
            
            st.caption(f"온도 기반 예상 범위: {expected}")
            st.write(f"측정값: **{agtron_num}**")

    # CSV 다운로드
    csv = df.to_csv(index=False).encode('utf-8-sig')
    file_name = f"Roasting_{roast_date}_{bean_name}.csv"
    
    st.download_button(
        label="💾 CSV 파일로 저장하기",
        data=csv,
        file_name=file_name,
        mime='text/csv',
        type='primary'
    )
