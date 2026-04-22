import re
import streamlit as st
import google.generativeai as genai

def natural_sort_key(s):
    """문자열 내의 숫자를 숫자로 인식하여 정렬 (퀴즈2 < 퀴즈11)"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', str(s))]


def clean_text(text):
    if not text: return ""
    text = text.replace(r"^{\circ}", "°").replace(r"^\circ", "°").replace(r"\circ", "°")
    text = text.replace("`", "").replace(r"\$", "$")
    text = text.replace(r"\(", "$").replace(r"\)", "$")
    text = text.replace(r"\[", "$$").replace(r"\]", "$$")
    text = text.replace("**", "").strip()
    return text

def check_subjective_answer(user_ans, correct_ans_raw):
    """
    주관식 정답을 비교합니다.
    1차: 코드 기반 정규화 비교 (비용 없음)
    2차: AI를 통한 문맥 및 동의어 비교 (유연한 채점)
    """
    if not user_ans: return False
    
    # --- [1단계] 코드 기반 1차 검사 (기존 로직 유지) ---
    def normalize(text):
        t = str(text)
        t = re.sub(r'[\[\]\(\)]', '', t)
        t = t.replace(" ", "").lower()
        # 엑셀 특유의 0/1 처리
        if t == "0": return "false"
        if t == "1": return "true"
        return t

    user_clean = normalize(user_ans)
    if not user_clean: return False

    c_raw = str(correct_ans_raw)
    raw_parts = re.split(r'[\(\)/,\[\]]', c_raw)
    
    candidates = [c_raw] 
    for p in raw_parts:
        p_strip = p.strip()
        if p_strip:
            candidates.append(p_strip)
            
    # 코드 기반으로 일치하면 바로 True 반환
    for cand in candidates:
        if user_clean == normalize(cand):
            return True

    # --- [2단계] AI 기반 2차 검사 (1차에서 오답인 경우만 실행) ---
    # API 키는 보안상 st.secrets에서 가져오거나 관리자 설정에서 가져온다고 가정합니다.
    api_key = st.secrets.get("GEMINI_API_KEY") # 혹은 app_settings에서 전달받도록 수정 가능
    if not api_key:
        return False # API 키가 없으면 AI 채점 건너뜀

    try:
        genai.configure(api_key=api_key)
        
        # 제공해주신 모델 리스트 참조
        models_to_try = [
            'gemini-2.5-flash-lite', 
            'gemini-2.5-flash', 
            'gemini-3.1-pro-preview'
        ]
        
        # AI 채점용 프롬프트
        ai_prompt = f"""
        너는 아주 엄격한 엑셀 및 데이터 처리 전문 채점관이야. 
        아래 두 답변이 논리적, 문맥적으로 완벽히 동일한지 판단하여 채점해줘.

        [채점 기준]
        1. 논리적 동의어: 0과 FALSE, 1과 TRUE, '참'과 TRUE 등 엑셀 논리값 동의어는 '정답' 인정.
        2. 허용 범위: 대소문자 구분 없음, 단어 사이나 양 끝의 공백 차이는 '정답' 인정.
        3. 철자 엄격 제한 (중요): 의미가 통하더라도 철자 오타(Typos)가 단 하나라도 있으면 무조건 '오답'.
        - 예: VLOOKUP을 VLOOKP로 쓴 경우 -> 오답
        - 예: INDEX를 INDX로 쓴 경우 -> 오답
        4. 수식/함수: 함수명이나 인자의 철자가 틀리면 문맥이 같아도 무조건 '오답'.

        - 기준 정답: {correct_ans_raw}
        - 사용자의 답변: {user_ans}

        결과를 출력할 때는 다른 부연 설명 없이 반드시 '정답' 또는 '오답' 중 하나만 출력해.
        """

        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(ai_prompt)
                
                if response.text and "정답" in response.text:
                    return True
                elif response.text and "오답" in response.text:
                    return False
                
            except:
                continue # 다음 모델로 재시도
                
    except Exception:
        pass # AI 호출 실패 시 최종 오답 처리

    return False

def robust_parse(text):
    if not text: return []
    
    first_q_pos = text.find("[Q")
    if first_q_pos != -1:
        text = text[first_q_pos:]
    
    parsed = []
    chunks = re.split(r"\[Q\d*\]|\[Q\]", text)
    
    for chunk in chunks:
        if not chunk.strip(): continue
        try:
            q_match = re.search(r'(.*?)(?=\[O\])', chunk, re.S)
            o_match = re.search(r'\[O\](.*?)(?=\[A\])', chunk, re.S)
            a_match = re.search(r'\[A\](.*?)(?=\[K\]|\[E\]|$)', chunk, re.S)
            k_match = re.search(r'\[K\](.*?)(?=\[E\]|$)', chunk, re.S)
            e_match = re.search(r'\[E\](.*)', chunk, re.S)
            
            if not (q_match and o_match and a_match):
                continue
                
            q_raw = q_match.group(1)
            o_raw = o_match.group(1).strip()
            a_raw = a_match.group(1).strip()
            k_raw = k_match.group(1).strip() if k_match else ""
            e_raw = e_match.group(1).strip() if e_match else "제공된 해설이 없습니다."
            
            passage = ""
            question_text = q_raw
            passage_match = re.search(r'<지문>(.*?)</지문>', q_raw, re.S)
            if passage_match:
                passage = clean_text(passage_match.group(1))
                question_text = re.sub(r'<지문>.*?</지문>', '', q_raw, flags=re.S)
            
            question_text = clean_text(question_text)
            
            if "주관식" in o_raw:
                opts = ["주관식"]
                ans = clean_text(a_raw)
            else:
                opts = re.findall(r'[①-⑤]\s*[^①-⑤]+', o_raw)
                opts = [re.sub(r'[①-⑤]\s*', '', opt).strip() for opt in opts]
                
                ans = -1
                ans_symbols = ['①', '②', '③', '④', '⑤', '1', '2', '3', '4', '5']
                for idx, sym in enumerate(ans_symbols):
                    if sym in a_raw:
                        ans = idx % 5
                        break
            
            parsed.append({
                "p": passage,
                "q": question_text,
                "o": opts,
                "a": ans,
                "k": clean_text(k_raw),
                "e": clean_text(e_raw)
            })
        except:
            continue
            
    return parsed

def generate_quiz_with_ai(q_topic):
    api_key = st.secrets.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    from prompts import QUIZ_GENERATION_PROMPT
    full_prompt = f"{QUIZ_GENERATION_PROMPT}\n\n주제: [{q_topic}]"
    
    models_to_try = [
        'gemini-2.5-flash-lite',
        'gemini-2.5-flash',
        'gemini-3.1-pro-preview'    ]
    
    last_error = None
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(full_prompt)
            
            if response.text:
                return response.text 
                
        except Exception as e:
            last_error = str(e)
            continue
            
    raise Exception(f"모든 AI 모델 호출 실패. 마지막 에러: {last_error}")
