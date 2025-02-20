import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import openai
from pathlib import Path
import hashlib

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import docx2txt

try:
    from pptx import Presentation
    PPTX_ENABLED = True
except ImportError:
    st.error("pptx 모듈이 설치되어 있지 않습니다. 'python-pptx' 패키지를 설치해 주세요.")
    st.stop()

###############################################################################
# NLTK 설정 (stopwords 등)
###############################################################################
nltk_data_dir = "/tmp/nltk_data"
os.makedirs(nltk_data_dir, exist_ok=True)
os.environ["NLTK_DATA"] = nltk_data_dir
nltk.data.path.append(nltk_data_dir)

try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", download_dir=nltk_data_dir)
try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download("stopwords", download_dir=nltk_data_dir)

korean_stopwords = [
    "이","그","저","것","수","등","들","및","더","로","를","에",
    "의","은","는","가","와","과","하다","있다","되다","이다",
    "으로","에서","까지","부터","만","그리고","하지만","그러나"
]
english_stopwords = set(stopwords.words("english"))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# Streamlit 페이지 설정
###############################################################################
st.set_page_config(page_title="studyhelper", layout="centered")

###############################################################################
# .env 로드 및 OpenAI API 키 설정
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    st.stop()

openai.api_key = OPENAI_API_KEY

###############################################################################
# (openai>=1.0.0) ChatCompletion 함수
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.0):
    """
    messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
    """
    try:
        response = openai.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# 긴 텍스트 -> 청크 분할 (문자 기준)
###############################################################################
def split_text_into_chunks(text, max_chars=3000):
    chunks = []
    start_idx = 0
    while start_idx < len(text):
        end_idx = min(start_idx + max_chars, len(text))
        chunk = text[start_idx:end_idx]
        chunks.append(chunk)
        start_idx = end_idx
    return chunks

###############################################################################
# 긴 문서 -> 부분 요약 -> 최종 요약(중요문장/질문)
###############################################################################
def docx_global_processing(docx_text):
    """
    문서를 청크로 분할해 부분 요약 후, 최종 요약/중요문장/질문을 생성
    """
    chunks = split_text_into_chunks(docx_text, max_chars=3000)

    partial_summaries = []
    for i, chunk in enumerate(chunks):
        prompt_chunk = f"""
        아래는 문서의 일부입니다 (청크 {i+1}/{len(chunks)}).
        ---
        {chunk}
        ---
        이 텍스트를 간단히 요약해 주세요.
        """
        summary = ask_gpt([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt_chunk.strip()},
        ], model_name="gpt-4")
        partial_summaries.append(summary)

    combined_text = "\n\n".join(partial_summaries)
    final_prompt = f"""
    아래는 여러 부분 요약을 합친 내용입니다:
    ---
    {combined_text}

    이 문서를 최종 요약해 주세요.
    그리고 이 문서에서 가장 중요한 문장 3개를 골라 제시하고,
    사용자에게 묻고 싶은 질문 2개를 만들어 주세요.
    """
    final_result = ask_gpt([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": final_prompt.strip()},
    ], model_name="gpt-4")

    return final_result

def docx_to_text(upload_file):
    try:
        text = docx2txt.process(BytesIO(upload_file.getvalue()))
        return text if text else ""
    except Exception as e:
        st.error(f"DOCX 파일 처리 오류: {e}")
        return ""

###############################################################################
# GPT 채팅 인터페이스
###############################################################################
def chat_interface():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for chat in st.session_state.chat_history:
        role = chat["role"]
        content = chat["message"]
        with st.chat_message(role):
            st.write(content)

    user_chat_input = st.chat_input("메시지를 입력하세요:")
    if user_chat_input:
        st.session_state.chat_history.append({"role": "user", "message": user_chat_input})
        with st.chat_message("user"):
            st.write(user_chat_input)

        with st.spinner("GPT가 응답 중입니다..."):
            response = ask_gpt([
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": user_chat_input}
            ], model_name="gpt-4")

        st.session_state.chat_history.append({"role": "assistant", "message": response})
        with st.chat_message("assistant"):
            st.write(response)

###############################################################################
# 커뮤니티 탭 (이미지 등록 추가)
###############################################################################
def community_tab():
    st.header("커뮤니티 (문제 공유 및 해결책 모색)")
    if "community_ideas" not in st.session_state:
        st.session_state.community_ideas = []

    st.subheader("새로운 문제/아이디어 제안하기")
    idea_title = st.text_input("제목", "")
    idea_content = st.text_area("내용 (간략 소개)", "")

    # 이미지 업로드 (여러 장)
    image_files = st.file_uploader("이미지를 등록하세요 (선택사항)", type=["png","jpg","jpeg"], accept_multiple_files=True)

    if st.button("등록"):
        if idea_title.strip() and idea_content.strip():
            images_data = []
            if image_files:
                for img in image_files:
                    images_data.append(img.getvalue())  # 바이트로 저장

            new_idea = {
                "title": idea_title,
                "content": idea_content,
                "comments": [],
                "images": images_data,
            }
            st.session_state.community_ideas.append(new_idea)
            st.success("등록되었습니다!")

        else:
            st.warning("제목과 내용을 입력하세요.")

    st.write("---")
    st.subheader("커뮤니티 목록")
    if len(st.session_state.community_ideas) == 0:
        st.write("아직 등록된 문제/아이디어가 없습니다.")
    else:
        for idx, idea in enumerate(st.session_state.community_ideas):
            with st.expander(f"{idx+1}. {idea['title']}"):
                st.write(f"**내용**: {idea['content']}")

                # 이미지 표시
                if idea.get("images"):
                    st.write("### 첨부 이미지")
                    for img_bytes in idea["images"]:
                        st.image(img_bytes)

                st.write("### 댓글")
                if len(idea["comments"]) == 0:
                    st.write("아직 댓글이 없습니다.")
                else:
                    for c_idx, comment in enumerate(idea["comments"]):
                        st.write(f"- {comment}")

                comment_text = st.text_input(f"댓글 달기 (#{idx+1})", key=f"comment_input_{idx}")
                if st.button(f"댓글 등록 (#{idx+1})"):
                    if comment_text.strip():
                        idea["comments"].append(comment_text.strip())
                        st.success("댓글이 등록되었습니다!")
                        st.experimental_rerun()
                    else:
                        st.warning("댓글 내용을 입력하세요.")
                st.write("---")

###############################################################################
# DOCX 분석 탭 (문서 요약) - "긴 문서 자동 청크 + 요약/질문" 문구 제거
###############################################################################
def docs_analysis_tab():
    st.subheader("DOCX 분석 (문서 요약)")
    if "doc_analysis_chat" not in st.session_state:
        st.session_state.doc_analysis_chat = []
    if "docs_summary" not in st.session_state:
        st.session_state.docs_summary = ""

    uploaded_file = st.file_uploader("문서를 업로드하세요 (예: docx)", type=["docx"])
    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.md5(file_bytes).hexdigest()
        if ("uploaded_file_hash" not in st.session_state or
            st.session_state.uploaded_file_hash != file_hash):
            st.session_state.uploaded_file_hash = file_hash
            st.session_state.processed = False

        if not st.session_state.get("processed"):
            raw_text = docx_to_text(uploaded_file)
            if raw_text.strip():
                with st.spinner("문서 분석 중..."):
                    final_summary = docx_global_processing(raw_text)
                    st.session_state["docs_summary"] = final_summary
                    st.success("분석 완료!")
            else:
                st.error("텍스트를 추출할 수 없습니다.")
            st.session_state.processed = True

        if st.session_state.get("processed") and st.session_state.docs_summary:
            st.write("## 분석 결과 (최종 요약)")
            st.write(st.session_state.docs_summary)

###############################################################################
# 메인 함수
###############################################################################
def main():
    st.title("studyhelper")
    st.write("이 앱은 GPT 채팅 / DOCX 분석(문서 요약) / 커뮤니티(이미지 등록) 기능을 제공합니다. (GPT-4)")
    st.warning("GPT는 부정확할 수 있으니 중요한 정보는 별도 검증하세요.")

    tab = st.sidebar.radio("메뉴 선택", ("GPT 채팅", "DOCX 분석", "커뮤니티"))

    if tab == "GPT 채팅":
        st.subheader("GPT 채팅")
        chat_interface()

    elif tab == "DOCX 분석":
        docs_analysis_tab()

    elif tab == "커뮤니티":
        st.subheader("커뮤니티")
        community_tab()

    st.write("---")

if __name__ == "__main__":
    main()
