import re
import google.generativeai as genai

def clean_text(text):
    """불필요한 태그, 마크다운 기호 및 수식 기호 치환"""
    if not text: return ""
    
    # LaTeX 형태의 도(degree) 기호 치환
    text = text.replace(r"^{\circ}", "°")
    text = text.replace(r"^\circ", "°")
    text = text.replace(r"\circ", "°")
    
    # 수식 구분자($) 및 위첨자(^) 제거
    text = text.replace("$", "")
    text = text.replace("^", "")
    
    # 불필요한 마크다운 별표 제거
    text = text.replace("**", "").strip()
    return text

def robust_parse(text):
    """지문(<지문>)과 질문을 명확히 분리하여 파싱"""
    if not text: return []
    
    # 시작 지점 찾기
    first_q_pos = text.find("[Q")
    if first_q_pos != -1:
        text = text[first_q_pos:]
    
    parsed = []
    # [Q] 또는 [Q숫자] 기준으로 분할
    chunks = re.split(r"\[Q\d*\]|\[Q\]", text)
    
    for chunk in chunks:
        if not chunk.strip(): continue
        try:
            # 필드 추출
            q_raw = re.search(r'(.*?)(?=\[O\])', chunk, re.S).group(1)
            o_raw = re.search(r'\[O\](.*?)(?=\[A\])', chunk, re.S).group(1).strip()
            a_raw = re.search(r'\[A\](.*?)(?=\[K\])', chunk, re.S).group(1).strip()
            k_raw = re.search(r'\[K\](.*?)(?=\[E\])', chunk, re.S).group(1).strip()
            e_raw = re.search(r'\[E\](.*)', chunk, re.S).group(1).strip()
            
            # 지문(<지문>) 분리 로직
            passage = ""
            question_text = q_raw
            passage_match = re.search(r'<지문>(.*?)</지문>', q_raw, re.S)
            if passage_match:
                passage = clean_text(passage_match.group(1))
                question_text = re.sub(r'<지문>.*?</지문>', '', q_raw, flags=re.S)
            
            question_text = clean_text(question_text)
            
            # 보기 처리
            if "주관식" in o_raw:
                opts = ["주관식"]
                ans = clean_text(a_raw)
            else:
                opts = re.findall(r'[①-⑤1-5]\s*[^①-⑤1-5]+', o_raw)
                opts = [re.sub(r'[①-⑤1-5]\s*', '', opt).strip() for opt in opts]
                
                # 정답 인덱스 찾기
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
    """AI를 호출하여 프롬프트 규칙에 맞게 퀴즈를 생성합니다."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    from prompts import QUIZ_GENERATION_PROMPT
    full_prompt = f"{QUIZ_GENERATION_PROMPT}\n\n주제: [{q_topic}]"
    
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"오류 발생: {str(e)}"