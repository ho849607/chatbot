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
import pdfplumber
from pptx import Presentation
from PIL import Image
import cv2
import numpy as np
import subprocess
import tempfile

# 추가: 구글 OAuth 라이브러리
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests

# 추가: 스트림릿 드로어블 캔버스
from streamlit_drawable_canvas import st_canvas

###############################################################################
# NLTK 설정
###############################################################################
nltk_data_dir = "/tmp/nltk_data"
os.makedirs(nltk_data_dir, exist_ok=True)
os.environ["NLTK_DATA"] = nltk_data_dir
nltk.data.path.append(nltk_data_dir)
nltk.download("stopwords", download_dir=nltk_data_dir)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', download_dir=nltk_data_dir)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', download_dir=nltk_data_dir)

korean_stopwords = [
    '이', '그', '저', '것', '수', '등', '들', '및', '더', '로', '를', '에',
    '의', '은', '는', '가', '와', '과', '하다', '있다', '되다', '이다',
    '으로', '에서', '까지', '부터', '만', '그리고', '하지만', '그러나'
]
english_stopwords = set(stopwords.words('english'))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# Streamlit 페이지 설정
###############################################################################
st.set_page_config(page_title="studyhelper", layout="centered")

###############################################################################
# .env 로드 및 OpenAI API 키 설정 (서버 측에 보관)
###############################################################################
dotenv_path = Path('.env')
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("서버에 OpenAI API 키가 설정되지 않았습니다.")
    st.stop()
openai.api_key = OPENAI_API_KEY

###############################################################################
# 구글 OAuth 설정
###############################################################################
CLIENT_SECRETS_FILE = "client_secret.json"  # 구글 클라이언트 비밀 파일
SCOPES = ["openid", "email", "profile"]
REDIRECT_URI = "http://localhost:8501"  # 로컬 테스트 시 기본 포트 (배포 시 변경)

if "user_email" not in st.session_state:
    st.session_state["user_email"] = None

def create_flow():
    flow = Flow.from_client_secrets_file(
        client_secrets_file=CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    return flow

def google_login_flow():
    flow = create_flow()
    auth_url, _ = flow.authorization_url(prompt="consent")
    st.write("## 구글 로그인 URL")
    st.write("아래 링크로 이동하여 구글 계정 인증을 진행한 후, 주소창에 나타난 'code' 값을 복사해서 입력하세요.")
    st.write(auth_url)
    code_input = st.text_input("인증 코드 입력:")
    if st.button("인증 코드 제출"):
        if code_input.strip():
            try:
                flow.fetch_token(code=code_input.strip())
                credentials = flow.credentials
                request = requests.Request()
                id_info = id_token.verify_oauth2_token(
                    id_token=credentials.id_token,
                    request=request,
                    audience=flow.client_config["client_id"]
                )
                email = id_info.get("email")
                st.session_state["user_email"] = email
                st.success(f"로그인 성공! 이메일: {email}")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"인증 실패: {e}")
        else:
            st.warning("인증 코드를 입력하세요.")

###############################################################################
# GPT 연동 함수 (최신 openai.ChatCompletion 사용)
###############################################################################
def ask_gpt(prompt_text, model_name="gpt-4", temperature=0.0):
    response = openai.ChatCompletion.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": prompt_text}
        ],
        temperature=temperature
    )
    return response.choices[0].message.content.strip()

###############################################################################
# DOCX 고급 분석 (Chunk 분할 + 중요도 평가)
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
    final_summary = "\n".join(final_summary_parts)
    return final_summary

###############################################################################
# 채팅 인터페이스
###############################################################################
def chat_interface():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    for chat in st.session_state.chat_history:
        if chat["role"] == "user":
            with st.chat_message("user"):
                st.write(chat["message"])
        else:
            with st.chat_message("assistant"):
                st.write(chat["message"])
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
# DOCX 텍스트 추출
###############################################################################
def docx_to_text(upload_file):
    try:
        text = docx2txt.process(BytesIO(upload_file.getvalue()))
        return text if text else ""
    except Exception as e:
        st.error(f"DOCX 파일 처리 중 오류: {e}")
        return ""

###############################################################################
# 커뮤니티 (아이디어 공유 & 투자)
###############################################################################
def community_investment_tab():
    st.header("아이디어 공유 & 투자 커뮤니티")
    if "community_ideas" not in st.session_state:
        st.session_state.community_ideas = []
    st.subheader("새로운 아이디어 제안하기")
    idea_title = st.text_input("아이디어 제목", "")
    idea_content = st.text_area("아이디어 내용(간략 소개)", "")
    if st.button("아이디어 등록"):
        if idea_title.strip() and idea_content.strip():
            st.session_state.community_ideas.append({
                "title": idea_title,
                "content": idea_content,
                "comments": [],
                "likes": 0,
                "dislikes": 0,
                "investment": 0
            })
            st.success("아이디어가 등록되었습니다!")
        else:
            st.warning("제목과 내용을 입력하세요.")
    st.write("---")
    st.subheader("커뮤니티 아이디어 목록")
    if len(st.session_state.community_ideas) == 0:
        st.write("아직 등록된 아이디어가 없습니다.")
    else:
        for idx, idea in enumerate(st.session_state.community_ideas):
            with st.expander(f"{idx+1}. {idea['title']}"):
                st.write(f"**내용**: {idea['content']}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"👍 좋아요: {idea['likes']}")
                    if st.button(f"좋아요 (아이디어 #{idx+1})"):
                        idea["likes"] += 1
                        st.experimental_rerun()
                with col2:
                    st.write(f"👎 싫어요: {idea['dislikes']}")
                    if st.button(f"싫어요 (아이디어 #{idx+1})"):
                        idea["dislikes"] += 1
                        st.experimental_rerun()
                with col3:
                    st.write(f"💰 현재 투자액: {idea['investment']}")
                    invest_amount = st.number_input(
                        f"투자 금액 입력 (아이디어 #{idx+1})",
                        min_value=0,
                        step=10,
                        key=f"investment_input_{idx}"
                    )
                    if st.button(f"투자하기 (아이디어 #{idx+1})"):
                        idea["investment"] += invest_amount
                        st.success(f"{invest_amount}만큼 투자했습니다!")
                        st.experimental_rerun()
                st.write("### 댓글")
                if len(idea["comments"]) == 0:
                    st.write("아직 댓글이 없습니다.")
                else:
                    for c_idx, comment in enumerate(idea["comments"]):
                        st.write(f"- {comment}")
                comment_text = st.text_input(
                    f"댓글 달기 (아이디어 #{idx+1})",
                    key=f"comment_input_{idx}"
                )
                if st.button(f"댓글 등록 (아이디어 #{idx+1})"):
                    if comment_text.strip():
                        idea["comments"].append(comment_text.strip())
                        st.success("댓글이 등록되었습니다!")
                        st.experimental_rerun()
                    else:
                        st.warning("댓글 내용을 입력하세요.")
                st.write("---")
                st.write("### GPT 추가 기능")
                if st.button(f"SWOT 분석 (아이디어 #{idx+1})"):
                    with st.spinner("SWOT 분석 중..."):
                        prompt_swot = f"""
                        아래 아이디어에 대해 간략하게 SWOT(Strengths, Weaknesses, Opportunities, Threats)을 해주세요.

                        아이디어:
                        {idea['content']}
                        """
                        swot_result = ask_gpt(prompt_swot, "gpt-4", 0.3)
                        st.write("**SWOT 분석 결과**:")
                        st.write(swot_result)
                if st.button(f"주제별 분류 (아이디어 #{idx+1})"):
                    with st.spinner("아이디어 주제 분류 중..."):
                        prompt_category = f"""
                        아래 아이디어가 어느 분야(기술, 푸드, 교육, 금융, 건강, 기타)인지 추정해 주세요.
                        간단한 근거와 함께 알려주면 감사하겠습니다.

                        아이디어:
                        {idea['content']}
                        """
                        category_result = ask_gpt(prompt_category, "gpt-4", 0.3)
                        st.write("**주제별 분류 결과**:")
                        st.write(category_result)
                st.write("---")

###############################################################################
# 메인 함수
###############################################################################
def main():
    st.title("studyhelper")
    st.warning("저작권에 유의해 파일을 업로드하세요.")
    st.info("ChatGPT는 실수를 할 수 있습니다. 중요한 정보를 반드시 추가 확인하세요.")

    # 사이드바 라디오 버튼: "구글 로그인", "GPT 채팅", "DOCX 분석", "커뮤니티", "이미지 분석"
    tab = st.sidebar.radio("메뉴 선택", ("구글 로그인", "GPT 채팅", "DOCX 분석", "커뮤니티", "이미지 분석"))

    if tab == "구글 로그인":
        st.subheader("구글 로그인")
        if st.session_state.get("user_email"):
            st.success(f"로그인됨: {st.session_state['user_email']}")
            if st.button("로그아웃"):
                st.session_state["user_email"] = None
                st.experimental_rerun()
        else:
            google_login_flow()

    elif tab == "GPT 채팅":
        st.subheader("GPT-4 채팅")
        if not st.session_state.get("user_email"):
            st.warning("구글 로그인을 먼저 진행해 주세요.")
        else:
            chat_interface()

    elif tab == "DOCX 분석":
        st.subheader("DOCX 문서 분석 (고급 Chunk 단위 분석)")
        if not st.session_state.get("user_email"):
            st.warning("구글 로그인을 먼저 진행해 주세요.")
        else:
            uploaded_file = st.file_uploader(
                "DOCX 파일을 업로드하세요 (문서 내에 '===Heading:'이라는 구분자를 추가해보세요!)",
                type=['docx']
            )
            if uploaded_file is not None:
                filename = uploaded_file.name
                file_bytes = uploaded_file.getvalue()
                file_hash = hashlib.md5(file_bytes).hexdigest()
                if ("uploaded_file_hash" not in st.session_state or
                    st.session_state.uploaded_file_hash != file_hash):
                    st.session_state.uploaded_file_hash = file_hash
                    st.session_state.extracted_text = ""
                    st.session_state.summary = ""
                    st.session_state.processed = False
                if not st.session_state.processed:
                    raw_text = docx_to_text(uploaded_file)
                    if raw_text.strip():
                        with st.spinner("문서 고급 분석 진행 중..."):
                            advanced_summary = docx_advanced_processing(raw_text, language='korean')
                            st.session_state.summary = advanced_summary
                            st.session_state.extracted_text = raw_text
                            st.success("DOCX 고급 분석 완료!")
                    else:
                        st.error("DOCX에서 텍스트를 추출할 수 없습니다.")
                        st.session_state.summary = ""
                    st.session_state.processed = True
                if st.session_state.get("processed", False):
                    if st.session_state.get("summary", "").strip():
                        st.write("## (고급) Chunk 기반 요약 & 중요도 결과")
                        st.write(st.session_state.summary)
                    else:
                        st.write("## 요약 결과를 표시할 수 없습니다.")
    elif tab == "커뮤니티":
        community_investment_tab()
    elif tab == "이미지 분석":
        st.subheader("이미지 분석 (밑줄 강조 및 핵심 요약)")
        if not st.session_state.get("user_email"):
            st.warning("구글 로그인을 먼저 진행해 주세요.")
        else:
            uploaded_img = st.file_uploader("이미지 파일을 업로드하세요 (PNG, JPG, JPEG)", type=['png', 'jpg', 'jpeg'])
            if uploaded_img is not None:
                image = Image.open(uploaded_img).convert("RGB")
                st.image(image, caption="업로드된 이미지", use_column_width=True)
                st.write("아래 캔버스에서 이미지에 밑줄 또는 형광펜으로 강조할 부분을 표시하세요.")
                canvas_result = st_canvas(
                    fill_color="rgba(255, 255, 0, 0.3)",
                    stroke_width=3,
                    stroke_color="#FF0000",
                    background_image=image,
                    update_streamlit=True,
                    height=image.height,
                    width=image.width,
                    drawing_mode="freedraw",
                    key="canvas_img"
                )
                if canvas_result.json_data is not None and canvas_result.json_data.get("objects"):
                    st.write("강조된 영역이 감지되었습니다. 해당 영역에 대해 GPT에게 분석을 요청합니다.")
                    prompt_annotation = "사용자가 이미지에서 강조한 부분의 핵심 내용을 요약해 주세요."
                    annotation_summary = ask_gpt(prompt_annotation, model_name="gpt-4", temperature=0.0)
                    st.write("### 강조 영역 분석 결과")
                    st.write(annotation_summary)
                else:
                    st.info("아직 캔버스에서 강조된 영역이 없습니다. 강조 표시를 해 보세요.")
    st.write("---")

if __name__ == "__main__":
    main()
