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

# PPTX 모듈 설치 확인
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
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', download_dir=nltk_data_dir)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', download_dir=nltk_data_dir)

korean_stopwords = [
    '이','그','저','것','수','등','들','및','더','로','를','에',
    '의','은','는','가','와','과','하다','있다','되다','이다',
    '으로','에서','까지','부터','만','그리고','하지만','그러나'
]
english_stopwords = set(stopwords.words('english'))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# Streamlit 페이지 설정
###############################################################################
st.set_page_config(page_title="studyhelper", layout="centered")

###############################################################################
# .env 로드 및 OpenAI API 키 설정
###############################################################################
dotenv_path = Path('.env')
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    st.stop()

openai.api_key = OPENAI_API_KEY

###############################################################################
# GPT 연동 함수 (ChatCompletion API, openai>=1.0.0)
###############################################################################
def ask_gpt(prompt_text, model_name="gpt-4", temperature=0.0):
    """
    OpenAI Python 1.0.0 이상에서는 openai.ChatCompletion.create(...) 대신
    openai.chat.completions.create(...) 를 사용해야 합니다.
    
    :param prompt_text: 사용자 입력 문자열
    :param model_name: 사용할 모델 (기본: gpt-4)
    :param temperature: 생성 텍스트 다양성
    :return: GPT 응답 문자열
    """
    try:
        response = openai.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt_text},
            ],
            temperature=temperature
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        st.error(f"OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# DOCS 분석 (DOCX 고급 분석 예시)
###############################################################################
def chunk_text_by_heading(docx_text):
    lines = docx_text.split('\n')
    chunks = []
    current_chunk = []
    heading_title = "NoHeading"
    chunk_id = 0
    for line in lines:
        if line.strip().startswith("===Heading:"):
            if current_chunk:
                chunks.append({
                    "id": chunk_id,
                    "heading": heading_title,
                    "text": "\n".join(current_chunk)
                })
                chunk_id += 1
                current_chunk = []
            heading_title = line.replace("===Heading:", "").strip()
        else:
            current_chunk.append(line)
    if current_chunk:
        chunks.append({
            "id": chunk_id,
            "heading": heading_title,
            "text": "\n".join(current_chunk)
        })
    return chunks

def gpt_evaluate_importance(chunk_text, language='korean'):
    if language == 'korean':
        prompt = f"""
        아래 텍스트가 있습니다. 이 텍스트가 전체 문서에서 얼마나 중요한지 1~5로 평가하고,
        한두 문장으로 요약해 주세요.

        텍스트:
        {chunk_text}

        형식 예:
        중요도: 4
        요약: ~~
        """
    else:
        prompt = f"""
        Please rate the importance of the following text on a scale of 1 to 5,
        and provide a brief summary.

        Text:
        {chunk_text}

        Example:
        Importance: 4
        Summary: ...
        """
    response = ask_gpt(prompt, model_name="gpt-4", temperature=0.0)
    importance = 3
    short_summary = ""
    for line in response.split('\n'):
        if "중요도:" in line or "Importance:" in line:
            try:
                importance = int(line.split(':')[-1].strip())
            except:
                pass
        if "요약:" in line or "Summary:" in line:
            short_summary = line.split(':', 1)[-1].strip()
    return importance, short_summary

def docx_advanced_processing(docx_text, language='korean'):
    chunks = chunk_text_by_heading(docx_text)
    combined_result = []
    for c in chunks:
        importance, short_summary = gpt_evaluate_importance(c["text"], language=language)
        c["importance"] = importance
        c["short_summary"] = short_summary
        combined_result.append(c)
    final_summary_parts = []
    for c in combined_result:
        part = (
            f"=== [Chunk #{c['id']}] Heading: {c['heading']} ===\n"
            f"중요도: {c['importance']}\n"
            f"요약: {c['short_summary']}\n"
            f"원문 일부:\n{c['text'][:200]}...\n"
        )
        final_summary_parts.append(part)
    return "\n".join(final_summary_parts)

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
            gpt_response = ask_gpt(user_chat_input, model_name="gpt-4", temperature=0.0)
        st.session_state.chat_history.append({"role": "assistant", "message": gpt_response})
        with st.chat_message("assistant"):
            st.write(gpt_response)

###############################################################################
# 커뮤니티 (문제 공유 및 해결책 모색)
###############################################################################
def community_tab():
    st.header("커뮤니티 (문제 공유 및 해결책 모색)")
    if "community_ideas" not in st.session_state:
        st.session_state.community_ideas = []
    st.subheader("새로운 문제/아이디어 제안하기")
    idea_title = st.text_input("제목", "")
    idea_content = st.text_area("내용 (간략 소개)", "")
    if st.button("등록"):
        if idea_title.strip() and idea_content.strip():
            st.session_state.community_ideas.append({
                "title": idea_title,
                "content": idea_content,
                "comments": []
            })
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
# 메인 함수
###############################################################################
def main():
    st.title("studyhelper")
    st.write("이 앱은 GPT 채팅 / DOCS 분석 / 커뮤니티 기능을 제공합니다.")
    st.warning("저작권에 유의하여 파일을 업로드하세요. GPT는 부정확할 수 있으니 중요한 정보는 검증하세요.")
    
    # 메뉴
    tab = st.sidebar.radio("메뉴 선택", ("GPT 채팅", "DOCS 분석", "커뮤니티"))
    
    if tab == "GPT 채팅":
        st.subheader("GPT 채팅")
        chat_interface()
    elif tab == "DOCS 분석":
        st.subheader("DOCS 분석 (DOCX 고급 분석 예시)")
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
                        advanced_summary = docx_advanced_processing(raw_text, language='korean')
                        st.session_state["docs_summary"] = advanced_summary
                        st.success("분석 완료!")
                else:
                    st.error("텍스트를 추출할 수 없습니다.")
                st.session_state["processed"] = True

            if st.session_state.get("processed") and st.session_state.get("docs_summary"):
                st.write("## 분석 결과")
                st.write(st.session_state["docs_summary"])

    elif tab == "커뮤니티":
        st.subheader("커뮤니티")
        community_tab()
    
    st.write("---")

if __name__ == "__main__":
    main()
