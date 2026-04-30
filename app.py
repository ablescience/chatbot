import streamlit as st
import json
import torch
import numpy as np
from sentence_transformers import SentenceTransformer, util
import os
import sqlite3
import uuid

# DB 초기화 함수
def init_db():
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qa_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_question TEXT NOT NULL,
            bot_answer TEXT NOT NULL,
            matched_question TEXT,
            is_fallback BOOLEAN DEFAULT 0,
            similarity_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def insert_qa_log(session_id, user_question, bot_answer, matched_question=None, is_fallback=False, similarity_score=None):
    try:
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO qa_logs (session_id, user_question, bot_answer, matched_question, is_fallback, similarity_score)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, user_question, bot_answer, matched_question, int(is_fallback), float(similarity_score) if similarity_score is not None else None))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Insert Error: {e}")

# 페이지 설정
st.set_page_config(page_title="학술 Q&A 챗봇", page_icon="💡", layout="centered")

# 디자인 스타일 적용
st.markdown("""
<style>
    .main {
        background-color: #f8f9fa;
    }
    .stChatMessage {
        border-radius: 15px;
        padding: 10px;
        margin-bottom: 10px;
    }
    .stChatMessage[data-testid="stChatMessageUser"] {
        background-color: #e3f2fd;
    }
    .stChatMessage[data-testid="stChatMessageAssistant"] {
        background-color: #ffffff;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def load_resources():
    # 데이터 로드
    data = []
    data_path = "data.jsonl"
    if os.path.exists(data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
    
    # 모델 로드 및 임베딩 계산
    model = SentenceTransformer('distiluse-base-multilingual-cased-v1')
    questions = [item['question'] for item in data]
    question_embeddings = model.encode(questions, convert_to_tensor=True)
    
    return data, model, question_embeddings

# 리소스 로딩
with st.spinner("데이터와 모델을 불러오는 중입니다..."):
    try:
        init_db() # DB 초기화
        data, model, question_embeddings = load_resources()
    except Exception as e:
        st.error(f"고급 리소스 로딩 중 오류가 발생했습니다: {e}")
        st.stop()

st.title("💡 학술 QnA 챗봇")
st.caption("에이블사이언스파마 학술팀 QnA 도우미입니다.")

# 대화 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_options" not in st.session_state:
    st.session_state.pending_options = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# 대화 기록 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 관련 질문 버튼 표시 (대화 기록 다음에 노출)
if st.session_state.pending_options:
    with st.chat_message("assistant"):
        st.markdown("정확한 정보를 찾기 위해 아래 질문 중 하나를 선택해 주세요.")
        for idx in st.session_state.pending_options:
            q_text = data[idx]['question']
            answer_text = data[idx]['answer']
            if st.button(q_text, key=f"btn_{idx}_{len(st.session_state.messages)}"):
                # 버튼 클릭 시 실제 답변 표시
                st.session_state.messages.append({"role": "user", "content": q_text})
                st.session_state.messages.append({"role": "assistant", "content": answer_text})
                
                # DB 기록
                user_q = st.session_state.get("last_prompt", q_text)
                insert_qa_log(st.session_state.session_id, user_q, answer_text, q_text, False, None)
                
                st.session_state.pending_options = [] # 선택 완료 후 리스트 초기화
                st.rerun()

# 사용자 입력
if prompt := st.chat_input("질문을 입력하세요..."):
    # 새로운 입력이 들어오면 기존 대기 질문 초기화
    st.session_state.pending_options = []
    st.session_state.last_prompt = prompt
    
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 챗봇 응답 생성
    with st.chat_message("assistant"):
        with st.spinner("답변을 찾는 중..."):
            # 입력 문장 임베딩
            query_embedding = model.encode(prompt, convert_to_tensor=True)
            
            # 코사인 유사도 계산 (상위 5개)
            cos_scores = util.cos_sim(query_embedding, question_embeddings)[0]
            top_results = torch.topk(cos_scores, k=5)
            
            scores = top_results[0].tolist()
            indices = top_results[1].tolist()
            
            # 유사도 임계값 체크
            threshold = 0.35
            high_threshold = 0.85
            gap_threshold = 0.05 # 1등과 2등의 점수 차이 임계값
            
            # 상위 1, 2위 점수 차이 계산
            score_gap = scores[0] - scores[1] if len(scores) > 1 else scores[0]
            
            if scores[0] >= high_threshold or (scores[0] >= threshold and score_gap >= gap_threshold):
                # 점수가 매우 높거나, 2등과의 격차가 크면(의도가 명확하면) 즉시 답변
                answer = data[indices[0]]['answer']
                matched_q = data[indices[0]]['question']
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                insert_qa_log(st.session_state.session_id, prompt, answer, matched_q, False, scores[0])
            elif scores[0] >= threshold:
                # 점수가 중간 정도이고 격차가 작으면 관련 질문 리스트를 세션 스테이트에 저장
                st.session_state.pending_options = [idx for i, idx in enumerate(indices) if scores[i] >= threshold]
                st.rerun() # 버튼을 표시하기 위해 즉시 리런
            else:
                fallback_msg = "해당 문의는 학술팀에 해주세요."
                st.markdown(fallback_msg)
                st.session_state.messages.append({"role": "assistant", "content": fallback_msg})
                insert_qa_log(st.session_state.session_id, prompt, fallback_msg, None, True, scores[0])

    # 입력 후 화면 갱신
    st.rerun()

# 사이드바 정보
with st.sidebar:
    st.header("사용 안내")
    st.info("""
    이 챗봇은 에이블사이언스 데이터베이스에 등록된 학술 데이터를 바탕으로 답변합니다. 
    질문의 의미를 파악하여 가장 유사한 답변을 찾아드립니다.
    
    - 검색된 유사도 점수가 낮으면 학술팀 안내 메시지가 출력됩니다.
    """)
    if st.button("대화 기록 삭제"):
        st.session_state.messages = []
        st.rerun()
