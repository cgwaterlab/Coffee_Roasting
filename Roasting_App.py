import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import io
import re
import csv
import time  # 시간 계산용

# =========================================================
# 로고 설정 (✅ 프로젝트 폴더에 pco_logo.png 넣으면 적용)
# =========================================================
LOGO_PATH = "pco_logo.png"  # app.py와 같은 폴더에 두세요.

# --- 설정 및 스타일 ---
st.set_page_config(page_title="Roasting Analysis Center", layout="wide", page_icon="☕")

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

DEFAULT_DATA_FILE = 'saemmulter_roasting_db.csv'


# --- 함수 모음 ---
def get_intl_date_str():
    now = datetime.now()
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{now.year}{months[now.month]}{now.day:02d}"


def get_dtr_feedback(dtr):
    """DTR 수치에 따른 맛 평가 멘트"""
    if dtr < 10:
        return "⚠️ 언더 디벨롭 (Under Developed): 풋내나 떫은 맛이 날 수 있어요. 시간을 조금 더 늘려보세요."
    elif dtr <= 15:
        return "🍓 노르딕/라이트 (Light): 꽃향기와 화사한 산미, 차(Tea) 같은 깔끔함이 특징이에요."
    elif dtr <= 20:
        return "⚖️ 미디엄/밸런스 (Medium): 단맛과 산미가 가장 조화로운 황금 비율이에요! (추천)"
    elif dtr <= 25:
        return "🍫 미디엄 다크 (Medium Dark): 산미는 줄고 바디감과 초콜릿 향이 살아나요."
    else:
        return "🔥 다크 (Dark): 묵직한 바디감, 스모키함, 쌉쌀한 맛이 강조돼요."


def format_mmss(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def load_and_standardize_csv(file, file_name_fallback):
    try:
        file.seek(0)
        raw = file.read()
        if isinstance(raw, str):
            content = raw
        else:
            try:
                content = raw.decode("utf-8-sig")
            except:
                content = raw.decode("cp949", errors="ignore")

        lines = content.splitlines()
        candidates = [",", "\t", ";"]
        header_row_idx = None
        delimiter = ","
        extracted_id = None

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            # 기존 로직 유지 (원두/bean 라인에서 id 추출 시도)
            if ("원두" in line) or ("bean" in line.lower()):
                parts = [p.strip() for p in re.split(r"[,\t;]", line)]
                if len(parts) > 1 and parts[1]:
                    extracted_id = parts[1]

            for d in candidates:
                cells = [c.strip().lower() for c in line.split(d)]
                if any(("time" in c) or ("시간" in c) for c in cells) and any(("temp" in c) or ("온도" in c) for c in cells):
                    header_row_idx = i
                    delimiter = d
                    break
            if header_row_idx is not None:
                break

        if header_row_idx is None:
            return None

        data_text = "\n".join(lines[header_row_idx:])
        rows = list(csv.reader(io.StringIO(data_text), delimiter=delimiter))
        if not rows:
            return None

        header = [str(c).strip() for c in rows[0]]
        while header and header[-1] == "":
            header.pop()
        expected = len(header)

        cleaned = []
        for r in rows[1:]:
            r = [str(c).strip() for c in r]
            if not any(r):
                continue
            if len(r) > expected:
                r = r[:expected]
            elif len(r) < expected:
                r = r + [""] * (expected - len(r))
            cleaned.append(r)

        df = pd.DataFrame(cleaned, columns=header)
        df.columns = [str(c).strip() for c in df.columns]

        col_map = {}
        for col in df.columns:
            c = col.lower()
            if ("time" in c) or ("시간" in c):
                col_map[col] = "Time"
            elif ("temp" in c) or ("온도" in c):
                col_map[col] = "Temp"
            elif ("gas" in c) or ("가스" in c):
                col_map[col] = "Gas"
            elif ("event" in c) or ("이벤트" in c):
                col_map[col] = "Event"

        df.rename(columns=col_map, inplace=True)

        if ("Time" not in df.columns) or ("Temp" not in df.columns):
            return None

        out = pd.DataFrame()
        out["Time"] = pd.to_numeric(df["Time"], errors="coerce")
        out["Temp"] = pd.to_numeric(df["Temp"], errors="coerce")
        out["Gas"] = pd.to_numeric(df["Gas"], errors="coerce").fillna(0) if "Gas" in df.columns else 0

        if "Event" in df.columns:
            out["Event"] = df["Event"].fillna("").astype(str)
            out.loc[out["Event"].str.lower() == "nan", "Event"] = ""
        else:
            out["Event"] = ""

        out = out.dropna(subset=["Time", "Temp"])
        out["Roast_ID"] = extracted_id if extracted_id else file_name_fallback.replace(".csv", "")
        return out
    except:
        return None


def get_template_csv():
    return """파일 이름,Sample_01
날짜,2026-Jan-01
원두 이름,Geisha
로스터 이름,Sample Roaster
방식,드럼 (Drum)
결과무게,215
비고,템플릿

Time(sec),Temp(C),Gas,Event
0,200,0.0,Preheat
30,200,0.5,Charge
60,90,5.0,TP
300,150,4.0,Yellowing
540,192,2.0,1C Start
630,205,0,Drop
"""


def check_is_crack(event_str):
    e = event_str.lower().strip()
    is_1c = any(k in e for k in ["1c", "1st", "first", "pop"]) and not ("end" in e) and not ("2" in e)
    is_2c = any(k in e for k in ["2c", "2nd", "second"])
    return is_1c, is_2c


def is_drop_event(e: str) -> bool:
    if not e:
        return False
    s = str(e).lower().strip()
    return ("drop" in s) or ("배출" in s)


# =========================================================
# 사이드바
# =========================================================
# ✅ 페루 국기 대신 로고 이미지 표시
if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, use_container_width=True)
    st.sidebar.markdown("### PERU COFFEE ORIGINS")
else:
    st.sidebar.markdown("## PERU COFFEE ORIGINS")
    st.sidebar.caption("로고를 표시하려면 프로젝트 폴더에 pco_logo.png를 추가하세요.")

st.sidebar.info("**페루의 Micro/Nano Lot 최상급 스페셜티 커피를 소개합니다.**\n\n지속 가능한 커피 문화를 위해 최고의 농장과 함께합니다.")

mode = st.sidebar.radio(
    "모드 선택 (Mode)",
    ["📊 데이터 분석 (Analysis)", "🔥 로스팅 (Manual)", "⏱️ 로스팅 + 시계 (Auto-Timer)"],
    index=0
)

c1, c2 = st.sidebar.columns(2)
with c1:
    st.link_button("🛍️ 스마트\n스토어", "https://smartstore.naver.com/perucoffeeorigins", use_container_width=True)
with c2:
    st.link_button("📷 Instagram", "https://instagram.com/perucoffee.origins", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("🛠️ 유틸리티")
c3, c4 = st.sidebar.columns(2)
with c3:
    st.download_button("📥 파일\n템플릿", get_template_csv().encode('utf-8-sig'), "template.csv", "text/csv", use_container_width=True)
with c4:
    st.link_button("⚡ Web\nRoasting\nLogger", "https://roastinglog.netlify.app/", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("📂 레퍼런스 센터")

all_history = []
if os.path.exists(DEFAULT_DATA_FILE):
    try:
        db_df = pd.read_csv(DEFAULT_DATA_FILE)
        if 'Roast_ID' in db_df.columns:
            all_history.append(db_df)
    except:
        pass

uploaded_files = st.sidebar.file_uploader("로스팅 기록 파일 업로드", accept_multiple_files=True, type=['csv'])
if uploaded_files:
    for f in uploaded_files:
        pdf = load_and_standardize_csv(f, f.name)
        if pdf is not None:
            all_history.append(pdf)

full_df = pd.DataFrame()
if all_history:
    full_df = pd.concat(all_history, ignore_index=True)

selected_ids_analysis = []
reference_id_roasting = None
is_analysis_mode = (mode == "📊 데이터 분석 (Analysis)")
is_manual_mode = (mode == "🔥 로스팅 (Manual)")
is_auto_mode = (mode == "⏱️ 로스팅 + 시계 (Auto-Timer)")


# =========================================================
# 3. 모드별 로직
# =========================================================
if is_analysis_mode:
    st.title("📊 Data Analysis Center")
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        selected_ids_analysis = st.sidebar.multiselect(f"비교할 그래프 선택 ({len(uids)}개)", uids)
    else:
        st.info("데이터가 없습니다. CSV 파일을 업로드하세요.")

else:
    st.title("🔥 Coffee Roasting Log V1.0")

    # 레퍼런스 선택
    if not full_df.empty:
        uids = list(full_df['Roast_ID'].unique())
        ref_options = ["(선택 안 함)"] + uids
        selected_ref = st.sidebar.selectbox("📉 배경 레퍼런스 선택 (Single Reference)", ref_options)
        if selected_ref != "(선택 안 함)":
            reference_id_roasting = selected_ref

    # ✅ 셋업에 로스터/방식 추가
    with st.expander("1. 로스팅 설정 (Setup)", expanded=True):
        intl_date = get_intl_date_str()

        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1:
            bean_name = st.text_input("원두 이름 (Bean Name)", value="Geisha")
        with r1c2:
            roast_id = st.text_input("ID", value=f"{bean_name}_{intl_date}")
        with r1c3:
            roaster_name = st.text_input("로스터 이름 (Roaster Name)", value="")
        with r1c4:
            method = st.selectbox(
                "방식 (Method)",
                ["드럼 (Drum)", "열풍 (Hot Air)", "하이브리드 (Hybrid)", "직화 (Direct Fire)", "기타 (Other)"],
                index=0
            )

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            initial_temp = st.number_input("투입온도 (Charge Temp, ℃)", min_value=0, max_value=300, value=200, step=10)
        with r2c2:
            green_weight = st.number_input("생두 무게 (Green Weight, g)", 250.0)

    # ✅ 세션 상태
    if 'points' not in st.session_state:
        st.session_state.points = []
    if 'start_time' not in st.session_state:
        st.session_state.start_time = None
    if 'timer_state' not in st.session_state:
        st.session_state.timer_state = "idle"  # idle / running / stopped
    if 'stop_elapsed' not in st.session_state:
        st.session_state.stop_elapsed = None

    EVT = ["예열(Preheat)", "Charge", "TP", "Yellowing", "Cinnamon", "1C Start", "1C End", "2C", "Drop"]

    # -----------------------------------------------------
    # Auto Timer
    # -----------------------------------------------------
    if is_auto_mode:
        st.subheader("2. 실시간 기록 (Auto Timer)")

        t_col1, t_col2, t_col3 = st.columns([1, 3, 1])
        with t_col1:
            if st.session_state.timer_state == "idle":
                if st.button("▶️ START (시작)", type="primary"):
                    st.session_state.start_time = time.time()
                    st.session_state.timer_state = "running"
                    st.session_state.stop_elapsed = None

                    # ✅ 시작과 동시에 예열(Preheat) 자동 기록 (Time=0)
                    st.session_state.points = [{
                        "Time": 0,
                        "Temp": int(initial_temp),
                        "Gas": 0.0,
                        "Event": "예열(Preheat)",
                        "Roast_ID": roast_id
                    }]
                    st.rerun()

            else:
                if st.button("⏹️ RESET (초기화)"):
                    st.session_state.start_time = None
                    st.session_state.timer_state = "idle"
                    st.session_state.stop_elapsed = None
                    st.session_state.points = []
                    st.rerun()

        def get_elapsed_now():
            if st.session_state.timer_state == "stopped" and st.session_state.stop_elapsed is not None:
                return int(st.session_state.stop_elapsed)
            if st.session_state.timer_state == "running" and st.session_state.start_time is not None:
                return int(time.time() - st.session_state.start_time)
            return 0

        elapsed = get_elapsed_now()
        with t_col2:
            st.metric("경과 시간", format_mmss(elapsed))

        with t_col3:
            # 화면 표시 업데이트용 (누르면 rerun)
            if st.session_state.timer_state == "running":
                if st.button("↻ 갱신"):
                    st.rerun()

        if st.session_state.timer_state == "stopped":
            st.info("✅ Drop이 기록되어 타이머가 정지되었습니다. (다시 시작하려면 RESET)")

        can_record = (st.session_state.timer_state == "running")

        c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 2, 1])
        with c1:
            st.text_input("현재 시간(표시) (Now)", value=format_mmss(elapsed), disabled=True)

        with c2:
            default_temp = int(st.session_state.points[-1]["Temp"]) if st.session_state.points else int(initial_temp)
            temp = st.number_input("온도 (Temp)", 0, 300, default_temp, disabled=not can_record, key="auto_temp")

        with c3:
            last_gas = float(st.session_state.points[-1]["Gas"]) if st.session_state.points else 0.0
            gas = st.number_input("가스 (Gas)", 0.0, 15.0, last_gas, step=0.1, disabled=not can_record, key="auto_gas")

        with c4:
            evt = st.selectbox("이벤트 (Event)", ["기록"] + EVT, disabled=not can_record, key="auto_evt")

        with c5:
            st.write("")
            st.write("")
            if st.button("기록 (Record)", type="primary", use_container_width=True, disabled=not can_record):
                rec_time = int(time.time() - st.session_state.start_time)
                chosen_evt = evt if evt != "기록" else None

                st.session_state.points.append({
                    "Time": rec_time,
                    "Temp": temp,
                    "Gas": gas,
                    "Event": chosen_evt,
                    "Roast_ID": roast_id
                })

                # ✅ Drop 기록 시 타이머 정지
                if is_drop_event(chosen_evt):
                    st.session_state.timer_state = "stopped"
                    st.session_state.stop_elapsed = rec_time

                st.rerun()

        # ✅ 단계별 기록(고정) 타임라인 표시
        if st.session_state.points:
            dfp = pd.DataFrame(st.session_state.points).sort_values("Time").reset_index(drop=True)
            ev = dfp[dfp["Event"].notna() & (dfp["Event"].astype(str).str.strip() != "")]
            if not ev.empty:
                timeline = ev[["Event", "Time"]].copy()
                timeline["Time(mm:ss)"] = timeline["Time"].apply(format_mmss)
                timeline["Δprev(sec)"] = timeline["Time"].diff().fillna(0).astype(int)
                st.markdown("##### ⏱️ 단계 타임라인 (Timeline)")
                st.dataframe(timeline[["Event", "Time(mm:ss)", "Time", "Δprev(sec)"]], use_container_width=True)

    # -----------------------------------------------------
    # Manual
    # -----------------------------------------------------
    else:
        st.subheader("2. 실시간 기록 (Manual Input)")
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2, 1])
        with c1:
            m = st.number_input("분 (Min)", 0, 60, 0)
            s = st.number_input("초 (Sec)", 0, 59, 0)
            t_sec = m * 60 + s
        with c2:
            temp = st.number_input("온도 (Temp)", 0, 300, int(initial_temp))
        with c3:
            gas = st.number_input("가스 (Gas)", 0.0, 15.0, 0.0, step=0.1)
        with c4:
            evt = st.selectbox("이벤트 (Event)", ["기록"] + EVT)
        with c5:
            st.write("")
            st.write("")
            if st.button("추가 (Add)", type="primary", use_container_width=True):
                st.session_state.points.append({
                    "Time": t_sec, "Temp": temp, "Gas": gas,
                    "Event": evt if evt != "기록" else None, "Roast_ID": roast_id
                })

    # 공통 데이터 에디터
    if st.session_state.points:
        st.markdown("##### 📝 데이터 수정 (Edit)")
        edited = st.data_editor(
            pd.DataFrame(st.session_state.points),
            num_rows="dynamic",
            use_container_width=True,
            key="editor",
            column_config={"Event": st.column_config.SelectboxColumn("이벤트 (Event)", options=EVT)}
        )
        if not pd.DataFrame(st.session_state.points).equals(edited):
            st.session_state.points = edited.to_dict('records')

            # Drop이 에디터에서 추가되면 타이머도 정지 상태로 맞춤
            df_tmp = pd.DataFrame(st.session_state.points).sort_values("Time")
            drop_rows = df_tmp[df_tmp["Event"].astype(str).apply(is_drop_event)]
            if not drop_rows.empty and st.session_state.timer_state != "idle":
                st.session_state.timer_state = "stopped"
                st.session_state.stop_elapsed = int(drop_rows["Time"].max())
            st.rerun()


# =========================================================
# 4. 통합 그래프
# =========================================================
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
        if not e or e == "nan":
            continue
        is_1c_evt, is_2c_evt = check_is_crack(e)
        if is_1c_evt and t_1c is None:
            t_1c = row['Time']
            idx_1c = i
        if is_2c_evt and t_2c is None:
            t_2c = row['Time']

    final_c_temp = color_temp if (is_main or is_analysis_mode) else "#bdc3c7"
    final_c_gas = color_gas if (is_main or is_analysis_mode) else "#bdc3c7"
    line_style = '-' if (is_main or is_analysis_mode) else '--'
    alpha_val = 0.9 if is_main else 0.7

    if idx_1c is not None and (is_main or is_analysis_mode):
        ax_temp.plot(df.iloc[:idx_1c+1]['Time'], df.iloc[:idx_1c+1]['Temp'], marker='o', markersize=6,
                     color=final_c_temp, linewidth=2, label=label_prefix)
        ax_temp.plot(df.iloc[idx_1c:]['Time'], df.iloc[idx_1c:]['Temp'], marker='o', markersize=6,
                     color=final_c_temp, linewidth=8, alpha=alpha_val)
    else:
        marker = 'o' if (is_main or is_analysis_mode) else None
        ax_temp.plot(df['Time'], df['Temp'], marker=marker, markersize=5, linestyle=line_style,
                     color=final_c_temp, linewidth=2, label=label_prefix, alpha=alpha_val)

    if (is_main or is_analysis_mode) and 'Gas' in df.columns and df['Gas'].sum() > 0:
        ax_gas.plot(df['Time'], df['Gas'], drawstyle='steps-post', marker='x', markersize=5, linestyle=':',
                    color=final_c_gas, alpha=0.5, label='Gas' if is_main else None)

    if show_ror and len(df) > 1:
        prev_ror = 0
        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            dt = (curr['Time'] - prev['Time']) / 60.0
            dtemp = curr['Temp'] - prev['Temp']
            if dt > 0:
                ror = dtemp / dt
                c = "#2ecc71"
                if ror < 5:
                    c = "#3498db"
                elif ror > prev_ror + 2:
                    c = "#e74c3c"
                bar_x = curr['Time'] - (curr['Time'] - prev['Time']) / 2
                ax_ror_bar.bar(bar_x, ror, width=(curr['Time'] - prev['Time']), color=c, alpha=0.6)
                if ror > 3:
                    ax_ror_bar.text(bar_x, ror + 2, f"{ror:.1f}", ha='center', va='bottom', fontsize=8,
                                    color=c, fontweight='bold')
                prev_ror = ror

    if is_main or is_analysis_mode:
        event_points = []
        for _, row in df.iterrows():
            e = str(row['Event'])
            if e and e != "nan" and e != "None":
                event_points.append(row)

        for i, row in enumerate(event_points):
            e = str(row['Event'])
            label_text = e
            is_drop = is_drop_event(e)

            if is_drop:
                if t_2c:
                    label_text = f"Drop (+2C {format_mmss(row['Time']-t_2c)})"
                elif t_1c:
                    label_text = f"Drop (+1C {format_mmss(row['Time']-t_1c)})"

            is_1c_evt, is_2c_evt = check_is_crack(e)
            y_offset = 25 if i % 2 == 0 else -30
            va_align = 'bottom' if i % 2 == 0 else 'top'

            if is_1c_evt or is_2c_evt:
                box_props = dict(boxstyle="round,pad=0.4", fc="gold", ec="black", alpha=1.0)
                ax_temp.scatter(row['Time'], row['Temp'], marker='*', s=400, facecolors=final_c_temp,
                                edgecolors='black', linewidths=1.5, zorder=10)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, 20),
                                 textcoords='offset points', ha='center', weight='bold', color='black',
                                 fontsize=11, bbox=box_props)
            elif is_drop:
                box_props = dict(boxstyle="round,pad=0.4", fc="#9b59b6", ec="black", alpha=1.0)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, 35),
                                 textcoords='offset points', ha='center', weight='bold', color='white',
                                 fontsize=11, bbox=box_props, arrowprops=dict(arrowstyle="-", color='purple'))
            else:
                box_props = dict(boxstyle="round,pad=0.3", fc="white", ec=final_c_temp, alpha=0.9)
                ax_temp.annotate(label_text, (row['Time'], row['Temp']), xytext=(0, y_offset),
                                 textcoords='offset points', ha='center', va=va_align, color='black',
                                 fontsize=10, bbox=box_props, arrowprops=dict(arrowstyle="-", color=final_c_temp))


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
    if reference_id_roasting and not full_df.empty:
        ref_data = full_df[full_df['Roast_ID'] == reference_id_roasting].sort_values('Time').reset_index(drop=True)
        if not ref_data.empty:
            plot_roast_data(ax1, ax2, ax_ror, ref_data, '#bdc3c7', '#bdc3c7',
                            f'Ref: {reference_id_roasting}', is_main=False, show_ror=False)

    if st.session_state.get("points"):
        curr_df = pd.DataFrame(st.session_state.points).sort_values('Time').reset_index(drop=True)
        # 로스팅 모드에서는 roast_id가 항상 존재
        plot_roast_data(ax1, ax2, ax_ror, curr_df, '#c0392b', '#2980b9', f'Current: {roast_id}', is_main=True, show_ror=True)

ax1.set_xlabel("Time (sec)")
ax1.set_ylabel("Temp (C)", color='#c0392b')
ax2.set_ylabel("Gas", color='#2980b9')
ax2.set_ylim(0, 10)
ax1.grid(True, ls='--', alpha=0.5)
ax1.legend(loc='upper left')
st.pyplot(fig)


# =========================================================
# 저장 섹션 & DTR 평가
# =========================================================
if not is_analysis_mode:
    st.subheader("3. 저장 (Save)")
    c1, c2, c3 = st.columns([1, 2, 1])
    calc_E = None

    current_dtr = 0
    dtr_feedback = ""
    if st.session_state.points:
        df = pd.DataFrame(st.session_state.points).sort_values('Time')
        t_1c = None
        for _, r in df.iterrows():
            if check_is_crack(str(r['Event']))[0]:
                t_1c = r['Time']
                break

        if t_1c and df.iloc[-1]['Time'] > t_1c:
            total_time = df.iloc[-1]['Time']
            dev_time = total_time - t_1c
            current_dtr = (dev_time / total_time) * 100
            dtr_feedback = get_dtr_feedback(current_dtr)

    with c1:
        rw = st.number_input("배출무게 (Output Weight, g)", 0.0)
        if rw > 0 and green_weight > 0:
            lw = green_weight - rw
            last_t = st.session_state.points[-1]['Temp'] if st.session_state.points else initial_temp
            q = (lw * 2260 + rw * 1.6 * (last_t - 25)) / 1000
            calc_E = f"{q:.1f} kJ"
            st.info(f"🔥 열량 (Energy): {calc_E}")

    with c2:
        note = st.text_input("메모 (Note)", placeholder="맛, 날씨, 특이사항")
        intl_date = get_intl_date_str()
        save_name = st.text_input("파일 이름 (File Name)", value=f"Roasting_{intl_date}_{bean_name}")

    with c3:
        st.write("")
        st.write("")
        if st.session_state.points:
            if dtr_feedback:
                st.markdown(f"""
                <div style="background-color:#e8f6f3; padding:10px; border-radius:5px; border:1px solid #1abc9c; font-size:0.9em; margin-bottom:10px;">
                    <strong>📊 DTR: {current_dtr:.1f}%</strong><br>{dtr_feedback}
                </div>
                """, unsafe_allow_html=True)

            sdf = pd.DataFrame(st.session_state.points)

            # CSV 다운로드용(메타 포함)
            buf = io.StringIO()
            buf.write(
                f"파일 이름,{save_name}\n"
                f"날짜,{get_intl_date_str()}\n"
                f"원두 이름,{bean_name}\n"
                f"로스터 이름,{roaster_name}\n"
                f"방식,{method}\n"
                f"결과무게,{rw}\n"
                f"흡수열량,{calc_E}\n"
                f"비고,{note}\n\n"
            )
            sdf[['Time', 'Temp', 'Gas', 'Event']].rename(columns={'Time': 'Time(sec)', 'Temp': 'Temp(C)'}).to_csv(buf, index=False)
            csv_d = buf.getvalue().encode('utf-8-sig')

            def save():
                # DB 저장용에는 메타를 각 row에 컬럼으로 넣어둠(분석에 유리)
                to_save = sdf.copy()
                to_save['Roast_ID'] = roast_id
                to_save['Bean_Name'] = bean_name
                to_save['Roaster_Name'] = roaster_name
                to_save['Method'] = method

                m = 'a' if os.path.exists(DEFAULT_DATA_FILE) else 'w'
                h = not os.path.exists(DEFAULT_DATA_FILE)
                to_save.to_csv(DEFAULT_DATA_FILE, mode=m, header=h, index=False, encoding='utf-8-sig')

                # 상태 초기화
                st.session_state.points = []
                st.session_state.timer_state = "idle"
                st.session_state.start_time = None
                st.session_state.stop_elapsed = None
                st.success("저장 완료!")

            st.download_button(
                "💾 CSV 저장 및 다운로드",
                csv_d,
                f"{save_name}.csv",
                "text/csv",
                type="primary",
                on_click=save,
                use_container_width=True
            )
        else:
            st.button("💾 CSV 저장", disabled=True, use_container_width=True)
