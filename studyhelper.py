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

# 구글 OAuth 라이브러리
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests

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
# 구글 OAuth 설정
###############################################################################
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["openid", "email", "profile"]

# **강제 리디렉션**: localhost:8501
REDIRECT_URI = "http://localhost:8501/"

if "user_email" not in st.session_state:
    st.session_state["user_email"] = None

def create_flow():
    """Google OAuth Flow 객체 생성"""
    return Flow.from_client_secrets_file(
        client_secrets_file=CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

def google_login_flow():
    """
    ✅ 구글 로그인 플로우
    - URL에서 'code' 파라미터 확인 후 자동 로그인
    - 로그인 후 localhost:8501로 자동 리디렉션
    """
    query_params = st.experimental_get_query_params()
    if "code" in query_params:
        code = query_params["code"][0]
        flow = create_flow()
        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials
            request_obj = requests.Request()
            id_info = id_token.verify_oauth2_token(
                id_token=credentials.id_token,
                request=request_obj,
                audience=flow.client_config["client_id"]
            )
            email = id_info.get("email")
            st.session_state["user_email"] = email
            st.success(f"✅ 로그인 성공! 이메일: {email}")

            # ✅ 자동 리디렉션
            st.experimental_rerun()
        except Exception as e:
            st.error(f"❌ 토큰 교환 실패: {e}")
    else:
        flow = create_flow()
        auth_url, _ = flow.authorization_url(prompt="consent")
        st.markdown(f"[🔑 구글로 로그인하기]({auth_url})", unsafe_allow_html=True)

###############################################################################
# 메인 함수
###############################################################################
def main():
    st.title("📝 studyhelper")
    st.write("✅ 이 앱은 구글 로그인으로 인증 후, GPT 채팅 / DOCS 분석 / 커뮤니티 기능을 제공합니다.")
    st.warning("⚠️ 저작권에 유의하여 파일을 업로드하세요. GPT는 부정확할 수 있으니 중요한 정보는 검증하세요.")
    
    # ✅ 구글 로그인 여부 체크
    if not st.session_state.get("user_email"):
        st.info("🔑 구글 로그인을 먼저 진행해 주세요.")
        google_login_flow()
        return
    else:
        st.success(f"✅ 로그인됨: {st.session_state['user_email']}")
        if st.button("🚪 로그아웃"):
            st.session_state["user_email"] = None
            st.experimental_rerun()
    
    # ✅ 로그인 후 메뉴 표시
    tab = st.sidebar.radio("📌 메뉴 선택", ("GPT 채팅", "DOCS 분석", "커뮤니티"))

    if tab == "GPT 채팅":
        st.subheader("💬 GPT 채팅")
        chat_interface()
    elif tab == "DOCS 분석":
        st.subheader("📄 DOCS 분석 (DOCX 고급 분석 예시)")
        uploaded_file = st.file_uploader("📂 문서를 업로드하세요 (예: docx)", type=["docx"])
        if uploaded_file:
            raw_text = docx_to_text(uploaded_file)
            if raw_text.strip():
                with st.spinner("🔍 문서 분석 중..."):
                    advanced_summary = docx_advanced_processing(raw_text, language='korean')
                    st.write("📌 **분석 결과**")
                    st.write(advanced_summary)
            else:
                st.error("⚠️ 텍스트를 추출할 수 없습니다.")
    elif tab == "커뮤니티":
        st.subheader("🗣️ 커뮤니티")
        community_tab()

    st.write("---")

if __name__ == "__main__":
    main()
