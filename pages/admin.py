import streamlit as st
import sqlite3

st.set_page_config(page_title="관리자 페이지", page_icon="⚙️", layout="wide")

# 관리자 인증
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

if not st.session_state.admin_authenticated:
    st.title("🔒 관리자 로그인")
    with st.form("login_form"):
        password = st.text_input("비밀번호를 입력하세요:", type="password")
        submitted = st.form_submit_button("로그인")
        
        if submitted:
            # 초기 비밀번호는 admin123으로 설정해두었습니다. (필요시 변경)
            if password == "admin123":
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")
    # 인증되지 않았을 경우 아래 코드가 실행되지 않도록 중단
    st.stop()

st.title("⚙️ 관리자 대시보드")
st.caption("데이터베이스에 저장된 QnA 챗봇의 대화 기록을 확인하는 관리자 전용 페이지입니다.")

# 데이터베이스에서 데이터 가져오는 함수
def get_data():
    conn = sqlite3.connect("chatbot.db")
    # 컬럼 이름을 키(key)로 하는 딕셔너리 형태로 결과를 가져오기 위함
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM qa_logs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    # 반환되는 row 객체들을 리스트 안의 딕셔너리로 변환
    return [dict(row) for row in rows]

try:
    data = get_data()
    
    if data:
        # 간단한 통계 계산
        total_logs = len(data)
        fallback_count = sum(1 for row in data if row.get('is_fallback') == 1)
        # fallback 처리되지 않은, 일반 답변 처리에 대한 유사도 목록
        sim_scores = [row.get('similarity_score') for row in data if row.get('similarity_score') is not None]
        avg_sim = sum(sim_scores) / len(sim_scores) if sim_scores else 0
        unique_sessions = len(set(row.get('session_id') for row in data if row.get('session_id')))
        
        # 상단에 통계 메트릭 표시
        st.subheader("📊 통계 요약")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("총 질의응답 수", total_logs)
        col2.metric("학술팀 연결(Fallback)", fallback_count)
        col3.metric("평균 유사도 (일반 응답)", f"{avg_sim:.4f}" if sim_scores else "N/A")
        col4.metric("총 접속 세션 수", unique_sessions)
        
        st.divider()
        
        # 검색 필터
        st.subheader("🔍 로그 검색")
        search_query = st.text_input("질문 또는 답변 내용에 포함된 단어를 검색해보세요.")
        
        # 검색어 기반 필터링
        if search_query:
            filtered_data = [row for row in data if 
                             (row.get('user_question') and search_query.lower() in str(row.get('user_question')).lower()) or 
                             (row.get('bot_answer') and search_query.lower() in str(row.get('bot_answer')).lower())]
        else:
            filtered_data = data
            
        # 데이터프레임 (표) 형태로 출력
        st.subheader(f"📋 전체 로그 내역 ({len(filtered_data)}건)")
        
        # id나 생성 날짜 등의 컬럼 정리를 위해 DataFrame 컬럼명 매핑 (선택적)
        # 여기서는 Streamlit 내부에서 자동으로 표 형태로 렌더링하도록 딕셔너리 리스트를 직접 전달합니다.
        st.dataframe(
            filtered_data,
            column_config={
                "id": "로그 번호",
                "session_id": "세션 ID",
                "user_question": "사용자 질문",
                "bot_answer": "챗봇 답변",
                "matched_question": "매칭된 질문",
                "is_fallback": "안내 메시지 여부",
                "similarity_score": "유사도 점수",
                "created_at": "작성 시간",
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("현재 저장된 챗봇 대화 기록이 없습니다.")
        
except Exception as e:
    st.error(f"데이터베이스 조회 중 오류가 발생했습니다: {e}")
