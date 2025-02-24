import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import openai
from pathlib import Path
import hashlib
import base64

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import docx2txt

import pdfplumber
from pptx import Presentation
from pptx.slide import Slide
from pptx.shapes.picture import Picture
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE

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
# .env 로드 + OpenAI API 키
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    st.stop()

openai.api_key = OPENAI_API_KEY

###############################################################################
# GPT 함수 (openai>=1.0.0)
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    """
    messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
    """
    try:
        resp = openai.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# 파일 분석 로직
###############################################################################
def parse_docx(file_bytes: bytes) -> str:
    try:
        text = docx2txt.process(BytesIO(file_bytes))
        return text if text else ""
    except Exception as e:
        return f"DOCX 파일 처리 오류: {e}"

def parse_pdf(file_bytes: bytes):
    text_list = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                text_list.append(page_text)
        merged_text = "\n".join(text_list)
        return merged_text
    except Exception as e:
        return f"PDF 파일 처리 오류: {e}"

def parse_ppt(file_bytes: bytes):
    # PPT 텍스트 + 밑줄/색상 + 이미지 크기 등을 추출하는 예시
    # 여기서는 텍스트만 결합한 형태 반환
    text_runs = []
    try:
        prs = Presentation(BytesIO(file_bytes))
        for slide_idx, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            text_runs.append(run.text)
        merged_text = "\n".join(text_runs)
        return merged_text
    except Exception as e:
        return f"PPT 파일 처리 오류: {e}"

def parse_image(file_bytes: bytes) -> str:
    """
    이미지 파일을 분석하는 예시.
    - 실제로는 OCR, Vision API 등으로 텍스트 추출 가능
    - 여기서는 base64 인코딩 + GPT에 '이 이미지는 어떤 것 같아?' 라고 묻는 예시
    """
    b64 = base64.b64encode(file_bytes).decode('utf-8')
    # returning a pseudo text "Base64: <some substring>"
    # GPT 프롬프트에서 요약 가능하도록
    short_b64 = b64[:500] + "...(생략)"
    return f"[이미지 파일] Base64 데이터(일부): {short_b64}"

def analyze_file_for_gpt(fileinfo) -> str:
    """
    fileinfo = {"name":..., "ext":..., "data":...}
    1) 파일 확장자별로 텍스트 추출
    2) GPT 요약 프롬프트 생성
    3) GPT로부터 요약/분석 결과 반환
    """
    name = fileinfo["name"]
    ext = fileinfo["ext"]
    data = fileinfo["data"]

    extracted_text = ""
    if ext in ["docx"]:
        extracted_text = parse_docx(data)
    elif ext in ["pdf"]:
        extracted_text = parse_pdf(data)
    elif ext in ["pptx"]:
        extracted_text = parse_ppt(data)
    elif ext in ["jpg", "jpeg", "png"]:
        extracted_text = parse_image(data)
    else:
        return f"지원하지 않는 파일 형식: {ext}"

    if not extracted_text.strip():
        return f"{name}에서 텍스트를 추출할 수 없습니다."

    # GPT 요약/분석 요청
    prompt = f"""
    업로드된 파일({name})에서 추출된 텍스트입니다:
    ---
    {extracted_text}
    ---
    위 내용을 분석/요약해 주세요.
    1) 주요 내용 요약
    2) 핵심 키워드 5개
    3) 사용자에게 묻고 싶은 질문(또는 퀴즈) 2~3개
    """
    messages = [
        {"role": "system", "content": "당신은 유용한 AI 비서입니다."},
        {"role": "user", "content": prompt.strip()},
    ]
    result = ask_gpt(messages, model_name="gpt-4", temperature=0.7)
    return result

###############################################################################
# GPT 채팅 탭 + 파일 업로드 -> 자동 분석
###############################################################################
def gpt_chat_tab():
    st.header("GPT 채팅")

    # 채팅 기록
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # 1) 채팅 기록 표시
    for msg in st.session_state.chat_messages:
        role = msg["role"]
        content = msg["message"]
        with st.chat_message(role):
            st.write(content)

    # 2) 파일 업로드 -> 자동 분석
    uploaded_files = st.file_uploader(
        "파일을 업로드하면 곧바로 분석 후 채팅에 추가됩니다 (이미지/PDF/PPTX/DOCX)",
        type=["png", "jpg", "jpeg", "pdf", "pptx", "docx"],
        accept_multiple_files=True
    )
    if uploaded_files:
        for uf in uploaded_files:
            file_bytes = uf.getvalue()
            file_name = uf.name
            file_ext = file_name.split(".")[-1].lower()
            fileinfo = {
                "name": file_name,
                "ext": file_ext,
                "data": file_bytes
            }
            # 분석
            with st.spinner(f"{file_name} 분석 중..."):
                analysis_result = analyze_file_for_gpt(fileinfo)
            # 채팅 기록에 메시지 추가
            st.session_state.chat_messages.append({
                "role": "system",
                "message": f"파일 {file_name} 분석 완료."
            })
            st.session_state.chat_messages.append({
                "role": "assistant",
                "message": analysis_result
            })
        st.experimental_rerun()  # 업로드 후 즉시 새 메시지 표시를 위해

    # 3) 일반 채팅 입력
    user_msg = st.chat_input("메시지를 입력하세요:")
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "message": user_msg})
        with st.chat_message("user"):
            st.write(user_msg)

        with st.spinner("GPT 응답 중..."):
            # 전체 대화 -> GPT
            role_messages = [
                {"role": m["role"], "content": m["message"]}
                for m in st.session_state.chat_messages
            ]
            gpt_response = ask_gpt(role_messages, model_name="gpt-4", temperature=0.7)

        st.session_state.chat_messages.append({
            "role": "assistant",
            "message": gpt_response
        })
        with st.chat_message("assistant"):
            st.write(gpt_response)

###############################################################################
# 커뮤니티 탭
###############################################################################
def community_tab():
    st.header("커뮤니티 (파일/이미지 업로드 + 자동 등록 + 분석)")

    # 커뮤니티 게시글 목록
    if "community_posts" not in st.session_state:
        st.session_state.community_posts = []

    st.subheader("새로운 문제/아이디어 올리기")
    post_title = st.text_input("제목", "")
    post_content = st.text_area("내용 (간략 소개)", "")

    # 파일 업로드 (이미지/PDF/PPTX/DOCX)
    uploaded_files = st.file_uploader(
        "파일을 등록하세요",
        type=["png", "jpg", "jpeg", "pdf", "pptx", "docx"],
        accept_multiple_files=True
    )

    if st.button("등록"):
        if post_title.strip() and post_content.strip():
            # 업로드된 파일들
            files_info = []
            analysis_msgs = []
            if uploaded_files:
                for uf in uploaded_files:
                    file_bytes = uf.getvalue()
                    file_name = uf.name
                    file_ext = file_name.split(".")[-1].lower()
                    info = {
                        "name": file_name,
                        "ext": file_ext,
                        "data": file_bytes
                    }
                    files_info.append(info)

            # 자동 분석
            for finfo in files_info:
                with st.spinner(f"{finfo['name']} 분석 중..."):
                    ares = analyze_file_for_gpt(finfo)
                # 분석 결과를 게시글 내부에 저장(analysis_history)
                analysis_msgs.append({
                    "file_name": finfo["name"],
                    "analysis_result": ares
                })

            # 새 게시글
            new_post = {
                "title": post_title,
                "content": post_content,
                "comments": [],
                "files": files_info,  # 원본 파일
                "analysis_history": analysis_msgs,  # 분석 결과
            }
            st.session_state.community_posts.append(new_post)
            st.success("게시글이 등록/분석되었습니다!")
        else:
            st.warning("제목과 내용을 입력하세요.")

    st.write("---")
    st.subheader("커뮤니티 목록")
    if len(st.session_state.community_posts) == 0:
        st.write("아직 게시글이 없습니다.")
    else:
        for idx, post in enumerate(st.session_state.community_posts):
            with st.expander(f"{idx+1}. {post['title']}"):
                st.write(f"**내용**: {post['content']}")
                # 첨부 파일 목록
                if post.get("files"):
                    st.write("#### 첨부 파일")
                    for fobj in post["files"]:
                        fn = fobj["name"]
                        ext = fobj["ext"]
                        data = fobj["data"]
                        st.write(f"- {fn}")
                        if ext in ["png", "jpg", "jpeg"]:
                            st.image(data)
                        else:
                            # 다운로드 버튼
                            st.download_button(
                                label=f"다운로드: {fn}",
                                data=data,
                                file_name=fn
                            )
                else:
                    st.write("첨부 파일 없음")

                # 분석 결과 표시
                if post.get("analysis_history"):
                    st.write("#### 자동 분석 결과")
                    for ah in post["analysis_history"]:
                        st.write(f"**파일명**: {ah['file_name']}")
                        st.write(ah["analysis_result"])
                else:
                    st.write("분석 기록 없음")

                st.write("#### 댓글")
                if len(post["comments"]) == 0:
                    st.write("(아직 댓글이 없습니다.)")
                else:
                    for cidx, cmt in enumerate(post["comments"]):
                        st.write(f"- {cmt}")

                cmt_input = st.text_input("댓글 달기", key=f"comment_{idx}")
                if st.button(f"등록 (#{idx+1})"):
                    if cmt_input.strip():
                        post["comments"].append(cmt_input.strip())
                        st.success("댓글이 등록되었습니다!")
                        st.experimental_rerun()
                    else:
                        st.warning("댓글 내용을 입력하세요.")

###############################################################################
# 메인
###############################################################################
def main():
    st.title("studyhelper")

    tab = st.sidebar.radio("메뉴 선택", ("GPT 채팅", "커뮤니티"))
    if tab == "GPT 채팅":
        gpt_chat_tab()
    else:
        community_tab()

    st.write("---")
    st.info("GPT 응답은 참고용입니다. 중요한 내용은 직접 검증하세요.")

if __name__ == "__main__":
    main()
