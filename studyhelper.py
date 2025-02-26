import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import openai
from pathlib import Path
import hashlib
import base64
import random
import subprocess

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import docx2txt
import pdfplumber
from pptx import Presentation

###############################################################################
# NLTK 설정
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

korean_stopwords = ["이", "그", "저", "것", "수", "등", "들", "및", "더"]
english_stopwords = set(stopwords.words("english"))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# 환경 변수 로드 & OpenAI API 키 설정
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 디버그용(선택): 실제로 로드된 키가 무엇인지 확인
# 주석 해제 시, 실행 로그에 API 키가 노출될 수 있으므로 주의하세요.
# print("DEBUG: OPENAI_API_KEY =", OPENAI_API_KEY)

if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다. (.env 또는 환경 변수 확인 필요)")
    st.stop()

# API 키 설정 (OpenAI 클래스 인스턴스 생성 없이 사용)
openai.api_key = OPENAI_API_KEY

###############################################################################
# OpenAI API 마이그레이션 기능
###############################################################################
def migrate_openai_api():
    """
    예전 버전의 openai 라이브러리를 사용할 때 "no longer supported" 오류가 발생하면
    자동으로 'openai migrate' 명령을 시도하는 함수.
    현재 openai>=1.0.0 환경에서는 보통 사용되지 않음.
    """
    try:
        result = subprocess.run(["openai", "migrate"], capture_output=True, text=True, check=True)
        st.info("OpenAI API 마이그레이션이 완료되었습니다. 앱을 재시작해주세요.")
        st.stop()
    except Exception as e:
        st.error("API 마이그레이션에 실패했습니다. 터미널에서 'openai migrate' 명령을 직접 실행해주세요.")
        st.stop()

###############################################################################
# GPT 함수
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    """
    OpenAI ChatCompletion API를 통해 GPT 모델에게 메시지를 전달하고 응답을 받는 함수.
    """
    try:
        resp = openai.ChatCompletion.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        error_message = str(e)
        # 예전 openai 버전과 호환되지 않을 경우, 자동 마이그레이션 시도
        if "no longer supported" in error_message:
            migrate_openai_api()
        st.error(f"OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# 파일 분석 로직 (PDF, PPTX, DOCX, 이미지)
###############################################################################
def parse_docx(file_bytes):
    try:
        return docx2txt.process(BytesIO(file_bytes))
    except Exception:
        return "DOCX 파일 분석 오류"

def parse_pdf(file_bytes):
    text_list = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text_list.append(page.extract_text() or "")
        return "\n".join(text_list)
    except Exception:
        return "PDF 파일 분석 오류"

def parse_ppt(file_bytes):
    text_list = []
    try:
        prs = Presentation(BytesIO(file_bytes))
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text_list.append(shape.text)
        return "\n".join(text_list)
    except Exception:
        return "PPTX 파일 분석 오류"

def parse_image(file_bytes):
    """
    현재는 단순히 문자열을 반환하지만,
    OCR 등 이미지 분석 기능을 추가할 수 있습니다.
    """
    return "[이미지 파일] OCR 분석 기능 추가 가능"

def analyze_file(fileinfo):
    """
    업로드된 파일의 확장자에 따라 적절한 파싱 함수 호출.
    """
    ext = fileinfo["ext"]
    data = fileinfo["data"]
    if ext == "docx":
        return parse_docx(data)
    elif ext == "pdf":
        return parse_pdf(data)
    elif ext == "pptx":
        return parse_ppt(data)
    elif ext in ["jpg", "jpeg", "png"]:
        return parse_image(data)
    else:
        return "지원하지 않는 파일 형식입니다."

###############################################################################
# GPT 채팅 탭
###############################################################################
def gpt_chat_tab():
    st.header("📌 GPT 채팅")
    st.info("""
        **[GPT 채팅 사용법 안내]**
        1. 아래의 파일 업로드 영역에서 PDF, PPTX, DOCX, JPG, PNG 파일을 선택하면 파일 내용이 자동 분석됩니다.
        2. 파일 분석 후, 채팅 기록에 분석 결과가 표시됩니다.
        3. 하단의 메시지 입력란에 질문을 작성하면 ChatGPT가 답변을 제공합니다.
        """)
    
    # 세션 스테이트에 채팅 로그 보관
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    
    # 기존 대화 내용 표시
    for msg in st.session_state.chat_messages:
        role, content = msg["role"], msg["content"]
        with st.chat_message(role):
            st.write(content)
    
    # 파일 업로드 후 자동 분석
    uploaded_files = st.file_uploader(
        "파일을 업로드하세요 (PDF/PPTX/DOCX/이미지 지원)",
        type=["pdf", "pptx", "docx", "jpg", "png"],
        accept_multiple_files=True
    )
    if uploaded_files:
        for uf in uploaded_files:
            file_bytes = uf.getvalue()
            fileinfo = {"name": uf.name, "ext": uf.name.split(".")[-1].lower(), "data": file_bytes}
            with st.spinner(f"📖 {fileinfo['name']} 분석 중..."):
                analysis_result = analyze_file(fileinfo)
            # 분석 결과를 채팅 메시지로 추가
            st.session_state.chat_messages.append({"role": "system", "content": f"📄 {fileinfo['name']} 분석 완료."})
            st.session_state.chat_messages.append({"role": "assistant", "content": analysis_result})
    
    # 사용자 입력
    user_msg = st.chat_input("메시지를 입력하세요:")
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.write(user_msg)
        
        # GPT 호출
        with st.spinner("GPT 응답 중..."):
            gpt_response = ask_gpt(st.session_state.chat_messages)
        
        st.session_state.chat_messages.append({"role": "assistant", "content": gpt_response})
        with st.chat_message("assistant"):
            st.write(gpt_response)

###############################################################################
# 커뮤니티 탭
###############################################################################
def community_tab():
    st.header("🌍 커뮤니티 (문서 공유 및 토론)")
    st.info("""
        **[커뮤니티 사용법 안내]**
        1. 상단의 검색창에서 제목 또는 내용을 입력하여 기존 게시글을 검색할 수 있습니다.
        2. '새로운 게시글 작성' 영역에서 제목, 내용 및 파일(PDF/PPTX/DOCX, 이미지)을 첨부하여 게시글을 등록할 수 있습니다.
        3. 게시글 상세보기 영역에서 댓글을 작성할 수 있으며, 댓글 작성 시 임의의 '유저_숫자'가 부여됩니다.
        """)
    
    # 검색 기능
    search_query = st.text_input("🔍 검색 (제목 또는 내용 입력)")
    
    # 커뮤니티 게시글 초기화
    if "community_posts" not in st.session_state:
        st.session_state.community_posts = []
    
    # 새 게시글 작성
    st.subheader("📤 새로운 게시글 작성")
    title = st.text_input("제목")
    content = st.text_area("내용")
    uploaded_files = st.file_uploader("📎 파일 업로드", type=["pdf", "pptx", "docx", "jpg", "png"], accept_multiple_files=True)
    
    if st.button("게시글 등록"):
        if title.strip() and content.strip():
            files_info = (
                [{"name": uf.name, "ext": uf.name.split(".")[-1].lower(), "data": uf.getvalue()} for uf in uploaded_files]
                if uploaded_files else []
            )
            new_post = {"title": title, "content": content, "files": files_info, "comments": []}
            st.session_state.community_posts.append(new_post)
            st.success("✅ 게시글이 등록되었습니다!")
    
    # 게시글 목록 표시
    st.subheader("📜 게시글 목록")
    for idx, post in enumerate(st.session_state.community_posts):
        # 검색어 필터
        if search_query.lower() in post["title"].lower() or search_query.lower() in post["content"].lower():
            with st.expander(f"{idx+1}. {post['title']}"):
                st.write(post["content"])
                
                # 댓글 작성
                comment = st.text_input(f"💬 댓글 작성 (작성자: 유저_{random.randint(100,999)})", key=f"comment_{idx}")
                if st.button("댓글 등록", key=f"comment_btn_{idx}"):
                    post["comments"].append(f"📝 유저_{random.randint(100,999)}: {comment}")
                
                # 댓글 목록
                for c in post["comments"]:
                    st.write(c)

###############################################################################
# 메인 실행
###############################################################################
def main():
    st.title("📚 StudyHelper")
    st.markdown("""
        ## StudyHelper 사용법 안내
        - **GPT 채팅:** 파일 업로드를 통해 문서를 분석하고, ChatGPT와 실시간 대화를 나눌 수 있습니다.
        - **커뮤니티:** 게시글을 작성하고, 문서를 공유하며, 댓글을 통해 의견을 나눌 수 있습니다.
        
        **주의사항**
        - **저작권 안내:** 업로드하신 파일 및 콘텐츠는 저작권 보호 대상일 수 있습니다.
          본 플랫폼은 사용자가 제공한 자료에 대한 저작권 책임을 지지 않으므로, 자료 업로드 전 관련 법규 및 저작권 사항을 반드시 확인해 주세요.
        - **중요 정보 확인:** ChatGPT의 답변은 참고용으로 제공되며, 오류나 부정확한 정보가 포함될 수 있으므로
          중요한 정보나 의사결정을 위해서는 반드시 추가 확인하시기 바랍니다.
        """)
    
    tab = st.sidebar.radio("🔎 메뉴 선택", ("GPT 채팅", "커뮤니티"))
    if tab == "GPT 채팅":
        gpt_chat_tab()
    else:
        community_tab()

if __name__ == "__main__":
    main()
