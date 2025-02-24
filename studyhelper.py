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
from pptx.slide import Slide
from pptx.shapes.picture import Picture
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE

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
# GPT 함수 (openai>=1.0.0)
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
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
# 간단 채팅 인터페이스 (기존 예시)
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

        with st.spinner("GPT가 응답 중..."):
            role_messages = []
            for msg in st.session_state.chat_history:
                if msg["role"] in ("system", "user", "assistant"):
                    role_messages.append({"role": msg["role"], "content": msg["message"]})

            response_text = ask_gpt(role_messages, model_name="gpt-4", temperature=0.7)

        st.session_state.chat_history.append({"role": "assistant", "message": response_text})
        with st.chat_message("assistant"):
            st.write(response_text)

###############################################################################
# [수정] 커뮤니티 탭: 이미지 뿐 아니라 PDF/PPT/DOCX도 업로드 가능
###############################################################################
def community_tab():
    st.header("커뮤니티 (문제/아이디어 공유)")

    if "community_ideas" not in st.session_state:
        st.session_state.community_ideas = []

    st.subheader("새로운 문제/아이디어 제안하기")
    idea_title = st.text_input("제목", "")
    idea_content = st.text_area("내용 (간략 소개)", "")

    # 여러 형식의 파일(이미지/PDF/PPTX/DOCX) 허용
    uploaded_files = st.file_uploader(
        "파일을 등록하세요 (이미지/PDF/PPTX/DOCX 등)",
        type=["png", "jpg", "jpeg", "pdf", "pptx", "docx"],
        accept_multiple_files=True
    )

    if st.button("등록"):
        if idea_title.strip() and idea_content.strip():
            # 업로드된 파일들을 저장
            files_data = []
            if uploaded_files:
                for uf in uploaded_files:
                    file_bytes = uf.getvalue()
                    file_ext = uf.name.split(".")[-1].lower()
                    files_data.append({
                        "name": uf.name,
                        "ext": file_ext,
                        "data": file_bytes
                    })

            new_idea = {
                "title": idea_title,
                "content": idea_content,
                "comments": [],
                # 다양한 파일들(이미지/PDF/PPTX/DOCX)
                "files": files_data,
            }
            st.session_state.community_ideas.append(new_idea)
            st.success("등록되었습니다!")
        else:
            st.warning("제목과 내용을 입력하세요.")

    st.write("---")
    st.subheader("커뮤니티 목록")
    if len(st.session_state.community_ideas) == 0:
        st.write("아직 등록된 문제가 없습니다.")
    else:
        for idx, idea in enumerate(st.session_state.community_ideas):
            with st.expander(f"{idx+1}. {idea['title']}"):
                st.write(f"**내용**: {idea['content']}")

                # 업로드된 파일들
                if idea.get("files"):
                    st.write("### 첨부 파일")
                    for f_idx, fileinfo in enumerate(idea["files"]):
                        f_name = fileinfo["name"]
                        f_ext = fileinfo["ext"]
                        f_data = fileinfo["data"]

                        st.write(f"- **파일명**: {f_name}")
                        # 이미지 미리보기
                        if f_ext in ["png", "jpg", "jpeg"]:
                            st.image(f_data)
                        else:
                            # PDF / PPTX / DOCX 등 -> 다운로드 버튼 제공
                            download_label = f"다운로드 ({f_name})"
                            st.download_button(
                                label=download_label,
                                data=f_data,
                                file_name=f_name
                            )
                else:
                    st.write("첨부 파일 없음")

                st.write("### 댓글")
                if len(idea["comments"]) == 0:
                    st.write("아직 댓글이 없습니다.")
                else:
                    for c_idx, comment in enumerate(idea["comments"]):
                        st.write(f"- {comment}")

                # 댓글 입력
                comment_text = st.text_input("댓글 달기", key=f"comment_{idx}")
                if st.button(f"댓글 등록 #{idx+1}"):
                    if comment_text.strip():
                        idea["comments"].append(comment_text.strip())
                        st.success("댓글이 등록되었습니다!")
                        st.experimental_rerun()
                    else:
                        st.warning("댓글 내용을 입력하세요.")

###############################################################################
# 메인
###############################################################################
def main():
    st.title("studyhelper")
    st.write("""
    이 예시는 커뮤니티 탭에서 이미지뿐 아니라 PDF/PPTX/DOCX 파일도 업로드/공유할 수 있도록 수정한 버전입니다.
    """)

    st.markdown("---")
    st.header("GPT 채팅")
    chat_interface()

    st.markdown("---")
    community_tab()

    st.write("---")
    st.info("GPT 응답은 참고용입니다. 중요 내용은 직접 검증하세요.")

if __name__ == "__main__":
    main()
