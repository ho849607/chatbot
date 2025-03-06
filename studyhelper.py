import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv

# OpenAI 모듈이 없어도 Gemini API로 대체할 수 있도록 설정
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from pathlib import Path
import docx2txt
import pdfplumber
from pptx import Presentation
import random
import subprocess
import nltk
from nltk.corpus import stopwords
import google.generativeai as genai
import PIL.Image
import requests
from concurrent.futures import ThreadPoolExecutor
import datetime
from PIL import Image
import io
from google.genai import types

###############################################################################
# 환경 변수 로드 및 설정
###############################################################################
dotenv_path = ".env"
load_dotenv(dotenv_path=dotenv_path)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini API 설정
genai.configure(api_key=GEMINI_API_KEY)

###############################################################################
# Streamlit 및 NLTK 설정
###############################################################################
nltk_data_dir = "/tmp/nltk_data"
os.makedirs(nltk_data_dir, exist_ok=True)
nltk.data.path.append(nltk_data_dir)

@st.cache_data(show_spinner=False)
def get_stopwords():
    try:
        sw = stopwords.words("english")
    except LookupError:
        nltk.download("stopwords", download_dir=nltk_data_dir)
        sw = stopwords.words("english")
    return set(sw)

english_stopwords = get_stopwords()
korean_stopwords = {"이", "그", "저", "것", "수", "등", "들", "및", "더"}
final_stopwords = english_stopwords.union(korean_stopwords)

###############################################################################
# 오버헤드 감소: 최대한 빠른 처리 위해 병렬 제한
###############################################################################
MAX_WORKERS = 2  # 병렬 스레드 수 제한

###############################################################################
# OpenAI와 Gemini API 키 설정
###############################################################################
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_GEMINI_ALWAYS = os.getenv("USE_GEMINI_ALWAYS", "False").lower() == "true"

# OpenAI 클라이언트
if not OPENAI_API_KEY or OpenAI is None or USE_GEMINI_ALWAYS:
    # Gemini 강제 사용
    use_gemini_always = True
    client = None
else:
    use_gemini_always = False
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

###############################################################################
# 캐싱을 통해 Gemini 응답 속도 개선
###############################################################################
@st.cache_data(show_spinner=False)
def ask_gemini_cached(prompt, temperature=0.2):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            prompt=prompt,
            generation_config={"temperature": temperature}
        )
        return response.text.strip()
    except Exception as e:
        return f"Gemini API 호출 오류: {e}"

###############################################################################
# OpenAI 호출 실패 시 Gemini로 fallback
###############################################################################
@st.cache_data(show_spinner=False)
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    if use_gemini_always or client is None:
        # Gemini 사용 (fallback)
        return _ask_gemini(messages, temperature)
    else:
        # OpenAI 시도
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return _ask_gemini(messages, temperature)

def _ask_gemini(messages, temperature=0.7):
    try:
        system_msg = next((m["content"] for m in messages if m["role"]=="system"), "")
        user_msg = next((m["content"] for m in messages if m["role"]=="user"), "")
        prompt = f"{system_msg}\n\n사용자 질문: {user_msg}"
        return ask_gemini_cached(prompt, temperature=temperature)
    except Exception as e:
        return f"Gemini API fallback 오류: {e}"

###############################################################################
# 이미지 리사이즈 후 Gemini에 전달 (빠른 속도)
###############################################################################
@st.cache_data(show_spinner=False)
def analyze_image_resized(file_bytes, max_size=(800, 800)):
    try:
        image = PIL.Image.open(io.BytesIO(file_bytes))
        image.thumbnail(max_size)
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        resized_image_bytes = buffer.getvalue()

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            [types.Part.from_bytes(resized_image_bytes, mime_type='image/jpeg')],
            generation_config={"temperature": 0.2}
        )
        return response.text.strip()
    except Exception as e:
        return f"이미지 분석 오류: {e}"

###############################################################################
# 기본 파일 파싱 (문서)
###############################################################################
@st.cache_data(show_spinner=False)
def parse_docx(file_bytes):
    try:
        return docx2txt.process(file_bytes)
    except Exception:
        return "📄 DOCX 파일 분석 오류"

@st.cache_data(show_spinner=False)
def parse_pdf(file_bytes):
    text_list = []
    try:
        with pdfplumber.open(file_bytes) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                text_list.append(text)
        return "\n".join(text_list)
    except Exception:
        return "📄 PDF 파일 분석 오류"

@st.cache_data(show_spinner=False)
def parse_ppt(file_bytes):
    text_list = []
    try:
        prs = Presentation(file_bytes)
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text_list.append(shape.text)
        return "\n".join(text_list)
    except Exception:
        return "📄 PPTX 파일 분석 오류"

###############################################################################
def analyze_file(file_info):
    ext = file_info["ext"]
    data = file_info["data"]
    if ext == "docx":
        return parse_docx(BytesIO(data))
    elif ext == "pdf":
        return parse_pdf(BytesIO(data))
    elif ext == "pptx":
        return parse_ppt(BytesIO(data))
    elif ext in ["png", "jpg", "jpeg"]:
        # 리사이즈 후 분석
        return analyze_image_resized(data)
    else:
        return "❌ 지원하지 않는 파일 형식입니다."

###############################################################################
# 여러 파일 병합 (병렬 처리)
###############################################################################
@st.cache_data(show_spinner=False)
def merge_documents(file_list):
    def process_file(f):
        bytes_data = f.getvalue()
        return analyze_file({
            "ext": f.name.split(".")[-1].lower(),
            "data": bytes_data
        })

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(process_file, file_list))

    return "\n\n".join(results)

###############################################################################
# Gemini 캐시 관리 함수
###############################################################################
def manage_gemini_cache():
    from google import genai
    from google.genai import types

    try:
        cache_client = genai.Client(api_key=GEMINI_API_KEY)
        model_name = "models/gemini-1.5-flash-002"

        # 캐시 생성
        cache = cache_client.caches.create(
            model=model_name,
            config=types.CreateCachedContentConfig(contents=['hello'])
        )
        st.write("캐시 생성됨:", cache)

        # 캐시 TTL 업데이트 (2시간)
        ttl_seconds = int(datetime.timedelta(hours=2).total_seconds())
        cache_client.caches.update(
            name=cache.name,
            config=types.UpdateCachedContentConfig(ttl=f"{ttl_seconds}s")
        )
        st.write("캐시 TTL이 2시간으로 업데이트됨.")

        # 캐시 삭제
        cache_client.caches.delete(name=cache.name)
        st.write("캐시 삭제됨.")
    except Exception as e:
        st.error(f"Gemini 캐시 관리 에러: {e}")

###############################################################################
# Streamlit UI
###############################################################################
def main():
    st.title("📚 Thinkhelper")
    st.markdown("""
**Thinkhelper**는 AI 기반으로 파일(문서/이미지)을 빠르게 분석하고, 자유롭게 대화할 수 있도록 설계되었습니다.

- 파일을 업로드하면 분석 결과(요약, 수정 제안 등)를 볼 수 있습니다.
- 파일 없이도 자유로운 AI 대화 가능합니다.
- 커뮤니티 탭에서는 익명 게시글 및 댓글을 통해 협업할 수 있습니다.
""")

    # 사이드바에서 Gemini 캐시 관리 버튼
    if st.sidebar.button("Gemini Cache 관리"):
        manage_gemini_cache()

    tab = st.sidebar.radio("🔎 메뉴 선택", ("파일 분석 & GPT 채팅", "커뮤니티"))

    if tab == "파일 분석 & GPT 채팅":
        st.info("파일(문서, 이미지)을 업로드하면 분석하고, 업로드 없이도 AI와 대화 가능합니다.")
        uploaded_files = st.file_uploader(
            "📎 파일 업로드 (PDF, PPTX, DOCX, 이미지)",
            type=["pdf", "pptx", "docx", "png", "jpg", "jpeg"],
            accept_multiple_files=True
        )

        if "analysis_result" not in st.session_state:
            st.session_state.analysis_result = ""

        if uploaded_files:
            with st.spinner("파일 분석 중..."):
                analysis = merge_documents(uploaded_files)
                st.session_state.analysis_result = analysis

            st.subheader("📌 분석 결과")
            st.write(st.session_state.analysis_result)

        st.subheader("💬 GPT와 대화하기")
        user_input = st.text_input("질문을 입력하세요")
        if st.button("전송"):
            if user_input:
                prompt_context = st.session_state.analysis_result
                prompt = f"파일 내용: {prompt_context}\n질문: {user_input}" if prompt_context else user_input

                # Gemini 호출 (캐싱)
                response = ask_gemini_cached(prompt, temperature=0.2)
                st.write("AI:", response)

    else:
        # 커뮤니티 탭
        st.info("익명으로 게시글 및 댓글을 작성하고 협업할 수 있습니다.")
        if "community_posts" not in st.session_state:
            st.session_state.community_posts = []

        search_query = st.text_input("🔍 검색 (제목 또는 내용)")
        st.subheader("새 게시글 작성")
        title = st.text_input("제목")
        content = st.text_area("내용")
        files_uploaded = st.file_uploader("📎 파일 업로드 (선택)", type=["pdf", "pptx", "docx", "png", "jpg", "jpeg"], accept_multiple_files=True)

        if st.button("게시글 등록"):
            if title.strip() and content.strip():
                post_files = []
                if files_uploaded:
                    for uf in files_uploaded:
                        ext = uf.name.split(".")[-1].lower()
                        file_bytes = uf.getvalue()
                        post_files.append({"name": uf.name, "ext": ext, "data": file_bytes})
                new_post = {"title": title, "content": content, "files": post_files, "comments": []}
                st.session_state.community_posts.append(new_post)
                st.success("게시글이 등록되었습니다.")
            else:
                st.error("제목과 내용을 모두 입력해야 합니다.")

        st.subheader("📜 게시글 목록")
        for idx, post in enumerate(st.session_state.community_posts):
            if (not search_query) or (search_query.lower() in post["title"].lower() or search_query.lower() in post["content"].lower()):
                with st.expander(f"{idx+1}. {post['title']}"):
                    st.write(post["content"])
                    comment = st.text_input("댓글 작성 (익명)", key=f"comment_{idx}")
                    if st.button("댓글 등록", key=f"comment_btn_{idx}"):
                        if comment.strip():
                            st.session_state.community_posts[idx]["comments"].append(f"익명_{random.randint(100,999)}: {comment}")
                        else:
                            st.error("댓글 내용을 입력해주세요.")
                    for c in post["comments"]:
                        st.write(c)

if __name__ == "__main__":
    main()

st.markdown("""
---
**저작권 주의 문구**

- 본 코드는 저작권법에 의해 보호됩니다. 무단 복제, 배포, 수정 또는 상업적 사용은 금지됩니다.
- 사용 시 출처를 명확히 표기해야 하며, 개인적/비상업적 용도로만 이용 가능합니다.
- 파일 업로드 시 발생하는 저작권 침해 문제에 대해서는 책임지지 않습니다.
""")
