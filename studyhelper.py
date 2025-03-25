import os
import streamlit as st
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from authlib.integrations.requests_client import OAuth2Session
import datetime

# 페이지 설정
# ※ Google Cloud Console에서 승인된 리디렉션 URI가
#    https://chatbot-3vyflfufldvf7d882bmvgm.streamlit.app
#    라고 되어 있다면 아래도 완전히 동일하게 맞춰주세요 (슬래시 포함 여부 등).
st.set_page_config(page_title="ThinkHelper - 법률 도우미", layout="centered")

# 환경변수 로드
load_dotenv()
LAWGOKR_API_KEY = os.getenv("LAWGOKR_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# 구글 콘솔에서 등록한 리디렉션 URI와 정확히 일치해야 함.
REDIRECT_URI = "https://chatbot-3vyflfufldvf7d882bmvgm.streamlit.app"

# 초기 세션 상태
if "favorites" not in st.session_state:
    st.session_state.favorites = {}
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

###############################################################################
# 1. 구글 로그인 함수
###############################################################################
def google_login():
    """
    Google OAuth 로그인 함수
    - 리디렉션 URI는 구글 콘솔에 등록된 것과 동일해야 함
    - 한 번 사용한 code는 재사용 불가능
    - authlib 모듈 설치 필요: pip install authlib
    """
    oauth = OAuth2Session(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=["openid", "email", "profile"]
    )

    query_params = st.query_params  # st.experimental_get_query_params() -> st.query_params (최신)
    if "code" not in query_params:
        # 승인되지 않은 상태 -> 로그인 버튼
        auth_url, _ = oauth.create_authorization_url(
            "https://accounts.google.com/o/oauth2/v2/auth",
            access_type="offline",
            prompt="consent"
        )
        st.markdown(f"[🔐 구글 로그인]({auth_url})", unsafe_allow_html=True)
    else:
        # code가 이미 존재 -> Google 리디렉션 상태
        code = query_params["code"][0]
        try:
            token = oauth.fetch_token(
                "https://oauth2.googleapis.com/token",
                code=code
            )
            userinfo = oauth.get("https://www.googleapis.com/oauth2/v3/userinfo").json()
            st.session_state["user"] = userinfo
            st.success(f"👋 환영합니다, {userinfo.get('name','사용자')} 님!")

            # 인증 후에는 code 파라미터 제거 (중복 사용 방지)
            st.experimental_set_query_params()

        except Exception as e:
            st.error(f"OAuth 오류: {e}")
            st.write("Google Cloud Console 설정 및 .env 파일을 다시 확인해주세요.")

###############################################################################
# 2. 국가법령정보센터 연동 함수 (법령/판례)
###############################################################################
@st.cache_data(show_spinner=False)
def law_search(keyword: str):
    if not keyword.strip():
        return []
    url = (
        f"https://www.law.go.kr/DRF/lawSearch.do?"
        f"OC={LAWGOKR_API_KEY}&target=law&type=XML&query={keyword}"
    )
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return [
        {"name": item.findtext("법령명한글"), "id": item.findtext("법령ID")}
        for item in tree.findall("law")
    ]

@st.cache_data(show_spinner=False)
def law_view(law_id: str):
    url = (
        f"https://www.law.go.kr/DRF/lawView.do?"
        f"OC={LAWGOKR_API_KEY}&target=law&type=XML&ID={law_id}"
    )
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return tree.findtext("조문내용") or "본문 없음"

@st.cache_data(show_spinner=False)
def precedent_search(keyword: str):
    if not keyword.strip():
        return []
    url = (
        f"https://www.law.go.kr/DRF/caseSearch.do?"
        f"OC={LAWGOKR_API_KEY}&target=case&type=XML&query={keyword}"
    )
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return [
        {"name": item.findtext("판례명"), "id": item.findtext("판례ID")}
        for item in tree.findall("case")
    ]

@st.cache_data(show_spinner=False)
def precedent_view(case_id: str):
    url = (
        f"https://www.law.go.kr/DRF/caseView.do?"
        f"OC={LAWGOKR_API_KEY}&target=case&type=XML&ID={case_id}"
    )
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return tree.findtext("판시내용") or "본문 없음"

###############################################################################
# 3. Gemini API (AI)
###############################################################################
def call_gemini_api(prompt: str):
    if not GEMINI_API_KEY:
        return "Gemini API Key가 설정되지 않았습니다."
    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        response_data = response.json()
        return (
            response_data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "응답 없음")
        )
    else:
        return f"❌ Gemini API 오류: {response.status_code}"

###############################################################################
# 4. 채팅 + 사례 기반 추천
###############################################################################
def chat_ui():
    st.subheader("💬 내 사례를 설명해 보세요")
    user_input = st.text_area("사례 입력", key="chat_input")
    if st.button("AI에게 물어보기"):
        if user_input.strip():
            # 삼중 따옴표 / 이스케이프 주의!
            prompt = (
                f"다음 사례에 가장 알맞은 법령과 판례를 추천하고 간단히 설명해줘:\n"
                f"{user_input}"
            )
            ai_response = call_gemini_api(prompt)
            st.session_state.chat_history.append(("user", user_input))
            st.session_state.chat_history.append(("bot", ai_response))

    # 최근 대화부터 위로 출력
    for role, msg in st.session_state.chat_history[::-1]:
        icon = "👤" if role == "user" else "🤖"
        st.markdown(f"{icon} {msg}")

###############################################################################
# 5. 즐겨찾기 UI
###############################################################################
def favorites_ui():
    st.subheader("⭐ 즐겨찾기")
    email = st.session_state["user"]["email"]
    favs = st.session_state.favorites.get(email, [])
    if not favs:
        st.info("저장된 즐겨찾기가 없습니다.")
    else:
        for f in favs:
            st.markdown(f"**{f['title']}**")
            st.text_area("내용", f['content'], height=100)

###############################################################################
# 6. 메인 함수
###############################################################################
def main():
    st.title("📚 ThinkHelper")

    # 먼저 로그인 시도
    google_login()

    # 로그인 안 된 경우 이용 제한
    if "user" not in st.session_state:
        st.warning("로그인 후 이용할 수 있습니다. 아래 버튼을 클릭하세요.")
        return

    # 로그인 된 경우만 아래 코드 실행
    st.sidebar.success(f"{st.session_state['user']['email']} 님 환영합니다")

    tab = st.sidebar.radio("📂 메뉴", ["AI 사례 추천", "법령 검색", "판례 검색", "즐겨찾기"])

    if tab == "AI 사례 추천":
        chat_ui()

    elif tab == "법령 검색":
        keyword = st.text_input("법령 키워드 입력")
        if st.button("검색 (법령)"):
            results = law_search(keyword)
            if not results:
                st.info("검색 결과가 없습니다.")
            for r in results:
                with st.expander(r["name"]):
                    if st.button("📄 보기", key=f"law_{r['id']}"):
                        content = law_view(r["id"])
                        st.text_area("본문", content, height=250)
                        if st.button("⭐ 저장", key=f"fav_law_{r['id']}"):
                            fav = {"title": r["name"], "content": content}
                            email = st.session_state["user"]["email"]
                            st.session_state.favorites.setdefault(email, []).append(fav)
                            st.success("저장되었습니다.")

    elif tab == "판례 검색":
        keyword = st.text_input("판례 키워드 입력")
        if st.button("검색 (판례)"):
            results = precedent_search(keyword)
            if not results:
                st.info("검색 결과가 없습니다.")
            for r in results:
                with st.expander(r["name"]):
                    if st.button("📄 보기", key=f"case_{r['id']}"):
                        content = precedent_view(r["id"])
                        st.text_area("본문", content, height=250)
                        if st.button("⭐ 저장", key=f"fav_case_{r['id']}"):
                            fav = {"title": r["name"], "content": content}
                            email = st.session_state["user"]["email"]
                            st.session_state.favorites.setdefault(email, []).append(fav)
                            st.success("저장되었습니다.")

    elif tab == "즐겨찾기":
        favorites_ui()

if __name__ == "__main__":
    main()

st.markdown("""
---
**저작권 안내**  
- 본 서비스는 [국가법령정보센터](https://www.law.go.kr)의 API를 이용합니다.  
- 법령 및 판례 정보는 공공데이터로 제공되며, 최종 판단은 법률 전문가와 상의하세요.
""")

