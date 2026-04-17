import re
import google.generativeai as genai

def robust_parse(text):
    # 📌 [추가] LaTeX 기호 및 특수 기호 전처리
    # Streamlit이 $ 기호를 만나 수식 모드로 오작동하는 것을 방지하고 기호를 정제합니다.
    if text:
        # 1. LaTeX 형태의 도(degree) 기호 치환
        text = text.replace(r"^{\circ}", "°")
        text = text.replace(r"^\circ", "°")
        text = text.replace(r"\circ", "°")
        
        # 2. 수식 구분자($) 제거 (일반 텍스트로 표시하기 위함)
        text = text.replace("$", "")
        
        # 3. 간혹 AI가 생성하는 잘못된 위첨자 표현 정리
        text = text.replace("^", "")

    # 시작 지점 찾기
    first_q_pos = text.find("[Q")
    if first_q_pos != -1:
        text = text[first_q_pos:]
    
    parsed = []
    ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
    
    # [Q] 또는 [Q숫자] 기준으로 분할
    chunks = re.split(r"\[Q\d*\]", text)
    
    for chunk in chunks:
        if not chunk.strip() or "[O]" not in chunk or "[A]" not in chunk:
            continue
            
        try:
            # 해설([E])이 없을 수도 있으므로 유연하게 분할
            parts = re.split(r"(\[O\]|\[A\]|\[K\]|\[E\])", chunk)
            q_raw = parts[0].strip()
            o_raw, a_raw, k_raw, e_raw = "", "1", "일반", "이 문제에 대한 해설이 등록되지 않았습니다."
            
            for i in range(len(parts)):
                tag = parts[i].strip()
                if tag == "[O]": o_raw = parts[i+1].strip()
                elif tag == "[A]": a_raw = parts[i+1].strip()
                elif tag == "[K]": k_raw = parts[i+1].strip()
                elif tag == "[E]": e_raw = parts[i+1].strip()
            
            # 주관식/객관식 판별
            if "주관식" in o_raw:
                opts = ["주관식"]
                ans = a_raw.strip()
            else:
                opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
                if not opts:
                    opts = [o.strip() for o in o_raw.split(',') if o.strip()]
                
                ans_char = a_raw.strip()[0] if a_raw else "①"
                ans = ans_map.get(ans_char, 0)
                
            parsed.append({
                "q": q_raw, 
                "o": opts, 
                "a": ans, 
                "k": k_raw,
                "e": e_raw # 해설 데이터 포함
            })
        except:
            continue
            
    return parsed

def generate_quiz_with_ai(api_key, q_topic, model_name='gemini-2.5-flash'):
    """
    AI를 호출하여 프롬프트 규칙에 맞게 퀴즈를 생성합니다.
    추후 모델이 변경되거나 프롬프트를 수정할 때 이 함수만 건드리면 됩니다.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    # 📌 프롬프트 템플릿 독립 관리
    full_prompt = f"""
    아래 형식에 맞춰 [{q_topic}]에 대한 객관식 10문제를 출제해.
    인사말 쓰지 말고 [Q1]부터 출력해. 그림, 표, 그래프 등 텍스트로 표현할 수 없는 자료는 절대 포함하지 마.

    [객관식 포맷]
    [Q] <지문> (수식은 $ 기호 사용) </지문> 
    [O] ① 보기1 ② 보기2 ③ 보기3 ④ 보기4 ⑤ 보기5
    [A] 정답 기호(예: ②)
    [K] 키워드
    [E] 이 문제가 정답인 이유와 오답들이 틀린 이유를 구체적으로 설명
    """
    
    response = model.generate_content(full_prompt)
    return response.text