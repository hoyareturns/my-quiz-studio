import re
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
    - $ 기호는 엑셀 절대좌표 등을 위해 '유지'합니다.
    - AI가 정답에 섞어 넣는 (), [] 등의 기호는 제거하거나 분리자로 사용합니다.
    """
    if not user_ans: return False
    
    # 1. 텍스트 정규화 함수
    def normalize(text):
        # AI의 부가 설명용 괄호 기호만 제거
        t = re.sub(r'[\[\]\(\)]', '', str(text))
        # 공백 제거 및 소문자화 ($ 기호는 그대로 유지됨)
        t = t.replace(" ", "").lower()
        return t

    user_clean = normalize(user_ans)
    if not user_clean: return False

    # 2. 정답 후보군 생성
    c_raw = str(correct_ans_raw)
    # 기호(/, ,, (, [, ])를 기준으로 정답 후보를 쪼개기
    # 예: "절대참조 ($A$1)" -> ["절대참조 ", " $A$1"]
    raw_parts = re.split(r'[\(\)/,\[\]]', c_raw)
    
    candidates = [c_raw] # 전체 원본 포함
    for p in raw_parts:
        p_strip = p.strip()
        if p_strip:
            candidates.append(p_strip)
            
    # 3. 하나라도 일치하면 정답 인정
    for cand in candidates:
        if user_clean == normalize(cand):
            return True
            
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

def generate_quiz_with_ai(api_key, q_topic):
    genai.configure(api_key=api_key)
    from prompts import QUIZ_GENERATION_PROMPT
    full_prompt = f"{QUIZ_GENERATION_PROMPT}\n\n주제: [{q_topic}]"
    
    models_to_try = [
        'gemini-2.5-flash-lite',
        'gemini-2.5-flash',
        'gemini-3.1-pro-preview'
    ]
    
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
