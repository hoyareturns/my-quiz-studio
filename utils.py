import re
import google.generativeai as genai

def clean_text(text):
    if not text: return ""
    text = text.replace(r"^{\circ}", "°").replace(r"^\circ", "°").replace(r"\circ", "°")
    text = text.replace("`", "").replace(r"\$", "$")
    text = text.replace(r"\(", "$").replace(r"\)", "$")
    text = text.replace(r"\[", "$$").replace(r"\]", "$$")
    text = text.replace("**", "").strip()
    return text

def check_subjective_answer(user_ans, correct_ans_raw):
    if not user_ans: return False
    u = re.sub(r"\s+", "", str(user_ans)).lower()
    c_raw = str(correct_ans_raw)
    cleaned_c = re.sub(r'[\[\]]', '', c_raw)
    parts = re.split(r'[\(\)/,]', cleaned_c)
    candidates = [cleaned_c]
    for p in parts:
        p_clean = p.replace(")", "").strip()
        if p_clean: candidates.append(p_clean)
    for cand in candidates:
        if u == re.sub(r"\s+", "", str(cand)).lower(): return True
    return False

def robust_parse(text):
    if not text: return []
    first_q_pos = text.find("[Q")
    if first_q_pos != -1: text = text[first_q_pos:]
    
    parsed = []
    chunks = re.split(r"\[Q\d*\]|\[Q\]", text)
    
    for chunk in chunks:
        if not chunk.strip(): continue
        try:
            q_raw = re.search(r"\[Q\](.*?)(?=\[O\]|\[A\]|\[K\]|\[E\]|$)", chunk, re.S)
            o_raw = re.search(r"\[O\](.*?)(?=\[A\]|\[K\]|\[E\]|$)", chunk, re.S)
            a_raw = re.search(r"\[A\](.*?)(?=\[K\]|\[E\]|$)", chunk, re.S)
            k_raw = re.search(r"\[K\](.*?)(?=\[E\]|$)", chunk, re.S)
            e_raw = re.search(r"\[E\](.*?)$", chunk, re.S)

            raw_question_text = q_raw.group(1) if q_raw else ""
            
            # --- [핵심] 지문(<지문>) 추출 로직 ---
            passage = ""
            passage_match = re.search(r"<지문>(.*?)</지문>", raw_question_text, re.S)
            if passage_match:
                passage = clean_text(passage_match.group(1))
                # 지문 태그 부분을 제외한 나머지만 질문으로 유지
                question_text = clean_text(raw_question_text.replace(passage_match.group(0), ""))
            else:
                question_text = clean_text(raw_question_text)

            a_val = a_raw.group(1).strip() if a_raw else ""
            
            is_subjective = "주관식" in (o_raw.group(1) if o_raw else "")
            if is_subjective:
                opts, ans = ["주관식"], a_val
            else:
                opts_text = o_raw.group(1) if o_raw else ""
                opts = re.findall(r"[①-⑤]\s*(.*?)(?=[①-⑤]|$)", opts_text, re.S)
                opts = [opt.strip() for opt in opts]
                ans = -1
                ans_symbols = ['①', '②', '③', '④', '⑤', '1', '2', '3', '4', '5']
                for idx, sym in enumerate(ans_symbols):
                    if sym in a_val:
                        ans = idx % 5
                        break
            
            parsed.append({
                "p": passage, # 지문 저장
                "q": question_text, 
                "o": opts, "a": ans,
                "k": clean_text(k_raw.group(1)) if k_raw else "",
                "e": clean_text(e_raw.group(1)) if e_raw else ""
            })
        except: continue
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
