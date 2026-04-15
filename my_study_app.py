import streamlit as st

# 1. 디자인 설정 (지문 박스용 CSS)
st.markdown("""
<style>
.passage-container {
    background-color: #fdfdfd;
    border: 1px solid #e1e4e8;
    border-left: 5px solid #4A90E2;
    padding: 20px;
    border-radius: 8px;
    white-space: pre-wrap; 
}
</style>
""", unsafe_allow_html=True)

# 2. 사이드바 구성 (에러 유발 요소를 모두 제거함)
with st.sidebar:
    st.title("⚙️ 설정 테스트")
    
    # [핵심] f-string을 쓰지 않고 가장 안전한 멀티라인 문자열로 정의
    # 만약 여기에 변수를 넣고 싶다면 반드시 .format()이나 별도 출력을 사용해야 함
    st.info("🪄 AI 출제 프롬프트 가이드")
    
    prompt_text = """[Q]
<지문>
여기에 소설이나 시 지문 입력 (줄바꿈 가능)
</지문>
문제 내용(발문) 입력

[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 핵심 키워드"""

    # 다른 로직 없이 바로 코드 박스 출력
    st.code(prompt_text, language="text")
    
    st.divider()
    st.write("위의 박스가 잘 보인다면 코드가 정상 작동하는 것입니다.")

# 3. 메인 화면
st.title("🧪 프롬프트 노출 테스트")
st.write("사이드바를 열어 프롬프트 창이 보이는지 확인하세요.")

# 샘플 지문 출력 테스트 (메인 화면에서도 확인용)
st.markdown('<div class="passage-container">이것은 지문 출력 테스트입니다.<br>태그가 잘 작동하는지 확인하세요.</div>', unsafe_allow_html=True)
