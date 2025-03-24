import os
import streamlit as st
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

# 페이지 설정은 최상단에 배치합니다.
st.set_page_config(page_title="ThinkHelper 법령/판례 검색", layout="wide")

# 환경변수 로드 (.env 파일에 API 키들을 설정)
load_dotenv()
LAWGOKR_API_KEY = os.getenv("LAWGOKR_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not LAWGOKR_API_KEY:
    st.error("LAWGOKR_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

###############################################################################
# 국가법령정보센터 API 함수: 법령 검색/본문 조회
###############################################################################
@st.cache_data(show_spinner=False)
def law_search(keyword):
    """법령 검색 API 호출 함수"""
    url = f"https://www.law.go.kr/DRF/lawSearch.do?OC={LAWGOKR_API_KEY}&target=law&type=XML&query={keyword}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"법령 API 호출 실패: 상태 코드 {response.status_code}")
    try:
        tree = ET.fromstring(response.content)
    except ET.ParseError as pe:
        raise Exception(f"법령 XML 파싱 오류: {pe}")
    results = []
    for item in tree.findall("law"):
        law_name = item.findtext("법령명한글")
        law_id = item.findtext("법령ID")
        results.append({"name": law_name, "id": law_id})
    return results

@st.cache_data(show_spinner=False)
def law_view(law_id):
    """법령 본문 조회 API 호출 함수"""
    url = f"https://www.law.go.kr/DRF/lawView.do?OC={LAWGOKR_API_KEY}&target=law&type=XML&ID={law_id}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"법령 본문 API 호출 실패: 상태 코드 {response.status_code}")
    try:
        tree = ET.fromstring(response.content)
    except ET.ParseError as pe:
        raise Exception(f"법령 XML 파싱 오류: {pe}")
    content = tree.findtext("조문내용") or "본문 없음"
    return content

###############################################################################
# 국가법령정보센터 API 함수: 판례 검색/본문 조회
###############################################################################
@st.cache_data(show_spinner=False)
def precedent_search(keyword):
    """판례 검색 API 호출 함수 (엔드포인트 및 XML 요소 이름은 실제 문서를 참고하여 수정 필요)"""
    url = f"https://www.law.go.kr/DRF/caseSearch.do?OC={LAWGOKR_API_KEY}&target=case&type=XML&query={keyword}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"판례 API 호출 실패: 상태 코드 {response.status_code}")
    try:
        tree = ET.fromstring(response.content)
    except ET.ParseError as pe:
        raise Exception(f"판례 XML 파싱 오류: {pe}")
    results = []
    # 실제 XML 구조에 맞춰 요소 이름을 수정하세요.
    for item in tree.findall("case"):
        case_name = item.findtext("판례명")
        case_id = item.findtext("판례ID")
        results.append({"name": case_name, "id": case_id})
    return results

@st.cache_data(show_spinner=False)
def precedent_view(case_id):
    """판례 본문 조회 API 호출 함수 (엔드포인트 및 XML 요소 이름은 실제 문서를 참고하여 수정 필요)"""
    url = f"https://www.law.go.kr/DRF/caseView.do?OC={LAWGOKR_API_KEY}&target=case&type=XML&ID={case_id}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"판례 본문 API 호출 실패: 상태 코드 {response.status_code}")
    try:
        tree = ET.fromstring(response.content)
    except ET.ParseError as pe:
        raise Exception(f"판례 XML 파싱 오류: {pe}")
    content = tree.findtext("판시내용") or "본문 없음"
    return content

###############################################################################
# Google Gemini API 함수
###############################################################################
def call_gemini_api(prompt):
    """Gemini API를 호출하여 응답 생성"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            response_data = response.json()
            generated_text = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "응답 내용 없음")
            return generated_text
        else:
            return f"Gemini API 호출 실패: 상태 코드 {response.status_code} / 응답: {response.text}"
    except Exception as e:
        return f"Gemini API 호출 중 오류: {e}"

###############################################################################
# Streamlit UI
###############################################################################
def main():
    st.title("📚 ThinkHelper - 국가법령정보센터 API 연동")
    st.markdown("""
    **ThinkHelper 법령/판례 검색 도우미**는 국가법령정보센터의 API를 활용해
    법률 문서를 빠르게 검색하고, 관련 판례(사례)도 함께 확인할 수 있는 서비스입니다.
    
    - **법령 검색**: 법령명을 키워드로 검색하여 법령 전문을 확인합니다.
    - **판례 검색**: 키워드로 관련 판례를 검색하여 사례 전문을 확인합니다.
    """)
    
    tab = st.sidebar.radio("🧭 메뉴", ["법령 검색", "판례 검색"])
    
    if tab == "법령 검색":
        st.header("🔍 법령 검색")
        keyword = st.text_input("법령 키워드 입력", placeholder="예: 개인정보보호법, 산업안전보건법")
        if st.button("검색 (법령)"):
            if not keyword.strip():
                st.warning("검색어를 입력해주세요.")
            else:
                with st.spinner("법령 검색 중..."):
                    try:
                        results = law_search(keyword)
                        if results:
                            st.success(f"총 {len(results)}개의 법령 검색 결과가 있습니다.")
                            for idx, r in enumerate(results):
                                with st.expander(f"{idx+1}. {r['name']}"):
                                    if st.button("📄 본문 보기", key=f"law_view_{r['id']}"):
                                        with st.spinner("법령 본문 불러오는 중..."):
                                            try:
                                                content = law_view(r["id"])
                                                st.text_area("법령 본문", content, height=300)
                                            except Exception as e:
                                                st.error(f"법령 본문 조회 중 오류: {e}")
                                                prompt = f"다음 법령에 대한 간략한 설명을 제공해 주세요: {r['name']}"
                                                gemini_response = call_gemini_api(prompt)
                                                st.write("**주의:** 아래 정보는 AI에 의해 생성되었으며, 최신 또는 정확한 정보가 아닐 수 있습니다. 공식 법령 정보는 국가법령정보센터를 참조하세요.")
                                                st.write("**대체 정보 (Gemini API):**", gemini_response)
                        else:
                            st.info("법령 검색 결과가 없습니다.")
                    except Exception as e:
                        st.error(f"법령 검색 중 오류 발생: {e}")
                        prompt = f"다음 법령에 대한 간략한 설명을 제공해 주세요: {keyword}"
                        gemini_response = call_gemini_api(prompt)
                        st.write("**주의:** 아래 정보는 AI에 의해 생성되었으며, 최신 또는 정확한 정보가 아닐 수 있습니다. 공식 법령 정보는 국가법령정보센터를 참조하세요.")
                        st.write("**대체 정보 (Gemini API):**", gemini_response)
                        
    elif tab == "판례 검색":
        st.header("🔍 판례 검색")
        keyword = st.text_input("판례 키워드 입력", placeholder="예: 근로, 계약, 손해배상")
        if st.button("검색 (판례)"):
            if not keyword.strip():
                st.warning("검색어를 입력해주세요.")
            else:
                with st.spinner("판례 검색 중..."):
                    try:
                        results = precedent_search(keyword)
                        if results:
                            st.success(f"총 {len(results)}개의 판례 검색 결과가 있습니다.")
                            for idx, r in enumerate(results):
                                with st.expander(f"{idx+1}. {r['name']}"):
                                    if st.button("📄 판례 본문 보기", key=f"case_view_{r['id']}"):
                                        with st.spinner("판례 본문 불러오는 중..."):
                                            try:
                                                content = precedent_view(r["id"])
                                                st.text_area("판례 본문", content, height=300)
                                            except Exception as e:
                                                st.error(f"판례 본문 조회 중 오류: {e}")
                                                prompt = f"다음 판례에 대한 간략한 설명을 제공해 주세요: {r['name']}"
                                                gemini_response = call_gemini_api(prompt)
                                                st.write("**주의:** 아래 정보는 AI에 의해 생성되었으며, 최신 또는 정확한 정보가 아닐 수 있습니다. 공식 판례 정보는 국가법령정보센터를 참조하세요.")
                                                st.write("**대체 정보 (Gemini API):**", gemini_response)
                        else:
                            st.info("판례 검색 결과가 없습니다.")
                    except Exception as e:
                        st.error(f"판례 검색 중 오류 발생: {e}")
                        prompt = f"다음 판례에 대한 간략한 설명을 제공해 주세요: {keyword}"
                        gemini_response = call_gemini_api(prompt)
                        st.write("**주의:** 아래 정보는 AI에 의해 생성되었으며, 최신 또는 정확한 정보가 아닐 수 있습니다. 공식 판례 정보는 국가법령정보센터를 참조하세요.")
                        st.write("**대체 정보 (Gemini API):**", gemini_response)

if __name__ == "__main__":
    main()

st.markdown("""
---
**저작권 안내**
- 본 서비스는 [국가법령정보센터](https://www.law.go.kr)의 API를 이용하며,
  법령 및 판례 정보는 공공데이터로 제공됩니다.
- 저작권 및 서비스 이용에 대한 책임은 사용자에게 있습니다.
""")
