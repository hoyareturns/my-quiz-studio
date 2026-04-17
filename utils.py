import re
import google.generativeai as genai

def clean_text(text):
    """불필요한 태그, 마크다운 기호 및 수식 기호 치환"""
    if not text: return ""
    
    text = text.replace(r"^{\circ}", "°")
    text = text.replace(r"^\circ", "°")
    text = text.replace(r"\circ", "°")
    text = text.replace("$", "")
    text = text.replace("^", "")
    text = text.replace("**", "").strip()
    return text

def robust_parse(text):
    """지문(<지문>)과 질문을 명확히 분리하고 누락된 태그에 유연하게 대처"""
    if not text: return []
    
    parsed = []
    chunks = re.split(r"\[Q\d*\]|\[Q\]", text)
    
    for chunk in chunks:
        if not chunk.strip(): continue
        try:
            # 필수 항목: 질문, 보기
            q_match = re.search(r'(.*?)(?=\[O\])', chunk, re.S)
            o_match = re.search(r'\[O\](.*?)(?=\[A\])', chunk, re.S)
            
            # [K]나 [E]가 생략되더라도 끝까지 매칭되도록 방어 로직 추가
            a_match = re.search(r'\[A\](.*?)(?=\[K\]|\[E\]|$)', chunk, re.S)
            k_match = re.search(r'\[K\](.*?)(?=\[E\]|$)', chunk, re.S)
            e_match = re.search(r'\[E\](.*)', chunk, re.S)
            
            # 문제 내용과 보기, 정답이 없으면 건너뜀
            if not (q_match and o_match and a_match):
                continue
                
            q_raw = q_match.group(1)
            o_raw = o_match.group(1).strip()
            a_raw = a_match.group(1).strip()
            
            # 선택 항목: 키워드, 해설이 없으면 기본 텍스트 삽입
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
                opts = re.findall(r'[①-⑤1-5]\s*[^①-⑤1-5]+', o_raw)
                opts = [re.sub(r'[①-⑤1-5]\s*', '', opt).strip() for opt in opts]
                
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
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    from prompts import QUIZ_GENERATION_PROMPT
    full_prompt = f"{QUIZ_GENERATION_PROMPT}\n\n주제: [{q_topic}]"
    
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"오류 발생: {str(e)}"