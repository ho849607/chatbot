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

###############################################################################
# NLTK 설정 및 불용어 처리 (캐싱 적용)
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
# 환경 변수 및 API 키 설정
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USE_GEMINI_ALWAYS = os.getenv("USE_GEMINI_ALWAYS", "False").lower() == "true"

# OpenAI API를 사용할 수 없거나 USE_GEMINI_ALWAYS가 True이면 Gemini API 사용
if USE_GEMINI_ALWAYS or not OPENAI_API_KEY or OpenAI is None:
    use_gemini_always = True
else:
    use_gemini_always = False
    client = OpenAI(api_key=OPENAI_API_KEY)

###############################################################################
# OpenAI API 마이그레이션 (필요 시)
###############################################################################
def migrate_openai_api():
    try:
        subprocess.run(["openai", "migrate"], capture_output=True, text=True, check=True)
        st.info("OpenAI API 마이그레이션 완료. 앱 재시작 후 사용하세요.")
        st.stop()
    except Exception as e:
        st.error(f"API 마이그레이션 실패: {e}")
        st.stop()

###############################################################################
# GPT API 호출 함수 (OpenAI 및 Gemini)
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    """OpenAI GPT 호출, 실패 시 Gemini API 호출."""
    if use_gemini_always:
        return ask_gemini(messages, temperature=temperature)
    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return ask_gemini(messages, temperature=temperature)

def ask_gemini(messages, temperature=0.7):
    """
    Gemini API 호출 함수 (GenerativeModel 방식).
    시스템 메시지와 사용자 메시지를 결합하여 프롬프트를 생성하고 generate_content()를 호출합니다.
    """
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        system_message = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_message = next((m["content"] for m in messages if m["role"] == "user"), "")
        prompt = f"{system_message}\n\n사용자 질문: {user_message}"
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            prompt,
            generation_config={"temperature": temperature}
        )
        return response.text.strip()
    except Exception as e:
        st.error(f"🚨 Gemini API (GenerativeModel 방식) 호출 에러: {e}")
        return ""

###############################################################################
# Gemini API 예제 (OpenAI 방식 호출)
###############################################################################
def gemini_api_example():
    """
    OpenAI 모듈을 이용하여 Gemini API를 호출하는 예제입니다.
    base_url을 Gemini API 엔드포인트로 설정하여 호출합니다.
    """
    try:
        example_client = OpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        response = example_client.chat.completions.create(
            model="gemini-2.0-flash",
            n=1,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain to me how AI works"}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Gemini API 예제 호출 에러: {e}"

###############################################################################
# 문서 및 이미지 파싱 함수 (캐싱 적용)
###############################################################################
@st.cache_data(show_spinner=False)
def parse_docx(file_bytes):
    try:
        return docx2txt.process(BytesIO(file_bytes))
    except Exception:
        return "📄 DOCX 파일 분석 오류"

@st.cache_data(show_spinner=False)
def parse_pdf(file_bytes):
    text_list = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text_list.append(page.extract_text() or "")
        return "\n".join(text_list)
    except Exception:
        return "📄 PDF 파일 분석 오류"

@st.cache_data(show_spinner=False)
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
        return "📄 PPTX 파일 분석 오류"

@st.cache_data(show_spinner=False)
def analyze_image(file_bytes):
    try:
        image = PIL.Image.open(BytesIO(file_bytes))
        width, height = image.size
        return f"이미지 분석 결과: 이미지 크기는 {width}x{height} 픽셀입니다."
    except Exception as e:
        return f"이미지 분석 오류: {e}"

def analyze_file(fileinfo):
    ext = fileinfo["ext"]
    data = fileinfo["data"]
    if ext == "docx":
        return parse_docx(data)
    elif ext == "pdf":
        return parse_pdf(data)
    elif ext == "pptx":
        return parse_ppt(data)
    elif ext in ["png", "jpg", "jpeg"]:
        return analyze_image(data)
    else:
        return "❌ 지원하지 않는 파일 형식입니다. (PDF, PPTX, DOCX, PNG, JPG, JPEG 지원)"

###############################################################################
# 여러 파일 병합 (병렬 처리 적용)
###############################################################################
def merge_documents(file_list):
    def process_file(file):
        file_bytes = file.getvalue()
        fileinfo = {
            "name": file.name,
            "ext": file.name.split(".")[-1].lower(),
            "data": file_bytes
        }
        return f"\n\n--- {file.name} ---\n\n" + analyze_file(fileinfo)
    
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(process_file, file_list))
    return "".join(results)

###############################################################################
# GPT 문서 분석, 질문, 맞춤법 수정 기능
###############################################################################
def gpt_document_review(text):
    summary_prompt = [
        {"role": "system", "content": "주어진 파일 내용을 요약하고 주요 내용을 정리하세요."},
        {"role": "user", "content": text}
    ]
    summary = ask_gpt(summary_prompt)
    question_prompt = [
        {"role": "system", "content": "주어진 파일 내용을 검토하고, 사용자가 수정하거나 고려해야 할 질문을 3가지 제시하세요."},
        {"role": "user", "content": text}
    ]
    questions = ask_gpt(question_prompt)
    correction_prompt = [
        {"role": "system", "content": "이 파일에서 맞춤법과 문법 오류를 수정하고, 수정한 부분을 강조하세요."},
        {"role": "user", "content": text}
    ]
    corrections = ask_gpt(correction_prompt)
    return summary, questions, corrections

###############################################################################
# GPT/AI 채팅 및 파일 분석 탭
###############################################################################
def gpt_chat_tab():
    st.info("파일을 업로드하면 AI가 자동으로 파일을 분석합니다. 파일 업로드 없이도 자유롭게 대화할 수 있습니다.")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    # 파일 업로드: 선택 사항
    uploaded_files = st.file_uploader(
        "📎 파일을 업로드하세요 (선택: PDF, PPTX, DOCX, PNG, JPG, JPEG 지원)",
        type=["pdf", "pptx", "docx", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    if uploaded_files is not None and len(uploaded_files) > 0:
        with st.spinner("파일을 분석 중..."):
            document_text = merge_documents(uploaded_files)
            summary, questions, corrections = gpt_document_review(document_text)
            st.session_state.document_text = document_text
            st.session_state.summary = summary
            st.session_state.questions = questions
            st.session_state.corrections = corrections
    # 파일 미업로드 시에도 대화가 가능하도록 기본값 유지
    if "document_text" not in st.session_state:
        st.session_state.document_text = ""
    st.subheader("💬 AI와 대화하기")
    user_input = st.text_input("질문을 입력하세요", key="chat_input")
    if st.button("전송"):
        if user_input.strip():
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            prompt_context = f"파일 내용: {st.session_state.document_text}" if st.session_state.document_text else "자유로운 대화"
            chat_prompt = [
                {"role": "system", "content": f"당신은 {prompt_context}를 기반으로 사용자와 대화하는 도우미입니다."},
                {"role": "user", "content": user_input}
            ]
            ai_response = ask_gpt(chat_prompt)
            st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
        else:
            st.error("질문을 입력해 주세요.")
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.write(f"**사용자**: {message['content']}")
        else:
            st.write(f"**AI**: {message['content']}")
    # Gemini API 예제 버튼 추가 (OpenAI 방식)
    if st.button("Gemini API 예제 (OpenAI 방식)"):
        result = gemini_api_example()
        st.write("Gemini API 예제 결과:", result)

###############################################################################
# 커뮤니티 탭 (익명 댓글 및 협업)
###############################################################################
def community_tab():
    st.header("🌍 커뮤니티 (파일 공유 및 토론)")
    st.info("""
**커뮤니티 사용법**
- 게시글 작성 시 제목, 내용 및 파일(지원: PDF, PPTX, DOCX, 이미지)을 첨부할 수 있습니다.
- 게시글 검색과 익명 댓글 기능을 통해 파일 및 분석 결과에 대해 토론할 수 있습니다.
    """)
    search_query = st.text_input("🔍 검색 (제목 또는 내용 입력)")
    if "community_posts" not in st.session_state:
        st.session_state.community_posts = []
    st.subheader("📤 새로운 게시글 작성")
    title = st.text_input("제목")
    content = st.text_area("내용")
    uploaded_files = st.file_uploader("📎 파일 업로드", type=["pdf", "pptx", "docx", "png", "jpg", "jpeg"], accept_multiple_files=True)
    if st.button("✅ 게시글 등록"):
        if title.strip() and content.strip():
            files_info = []
            if uploaded_files:
                for uf in uploaded_files:
                    file_bytes = uf.getvalue()
                    ext = uf.name.split(".")[-1].lower()
                    files_info.append({"name": uf.name, "ext": ext, "data": file_bytes})
            new_post = {"title": title, "content": content, "files": files_info, "comments": []}
            st.session_state.community_posts.append(new_post)
            st.success("✅ 게시글이 등록되었습니다!")
        else:
            st.error("제목과 내용을 모두 입력해 주세요.")
    st.subheader("📜 게시글 목록")
    for idx, post in enumerate(st.session_state.community_posts):
        if not search_query or search_query.lower() in post["title"].lower() or search_query.lower() in post["content"].lower():
            with st.expander(f"{idx+1}. {post['title']}"):
                st.write(post["content"])
                # 익명 댓글 작성
                comment = st.text_input(f"💬 댓글 작성 (익명)", key=f"comment_{idx}")
                if st.button("댓글 등록", key=f"comment_btn_{idx}"):
                    if comment.strip():
                        st.session_state.community_posts[idx]["comments"].append(f"익명_{random.randint(100,999)}: {comment}")
                    else:
                        st.error("댓글 내용을 입력해 주세요.")
                for c in post["comments"]:
                    st.write(c)

###############################################################################
# 메인 실행 및 사용법 안내
###############################################################################
def main():
    st.title("📚 Thinkhelper")
    st.markdown("""
**Thinkhelper**는 AI 기반으로 파일(문서 및 이미지)을 자동 분석하여 요약, 수정 제안, 개선 사항을 제공합니다.
또한, 커뮤니티 탭을 통해 파일을 공유하고 익명으로 토론할 수 있습니다.

**사용법**
- **GPT 문서 분석 탭:** 파일을 업로드하면 자동으로 분석 결과(요약, 질문, 수정 사항)를 확인하거나, 파일 없이도 자유롭게 대화할 수 있습니다.
- **커뮤니티 탭:** 게시글을 등록하고 익명 댓글을 통해 파일 및 분석 결과에 대해 토론할 수 있습니다.
    """)
    tab = st.sidebar.radio("🔎 메뉴 선택", ("GPT 문서 분석", "커뮤니티"))
    if tab == "GPT 문서 분석":
        gpt_chat_tab()
    else:
        community_tab()

if __name__ == "__main__":
    main()

st.markdown("""
---
**저작권 주의 문구**

- **코드 사용**: 이 소스 코드는 저작권법에 의해 보호됩니다. 무단 복제, 배포, 수정 또는 상업적 사용은 금지됩니다. 개인적, 비상업적 용도로만 사용할 수 있으며, 사용 시 출처를 명확히 표기해야 합니다.
- **파일 업로드**: 파일 업로드 시 저작권에 유의해 주세요. 저작권 침해 문제가 발생할 경우, 본 서비스는 책임을 지지 않습니다.
""")
