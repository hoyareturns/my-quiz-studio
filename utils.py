import re

def robust_parse(text):
    first_q_pos = text.find("[Q")
    if first_q_pos != -1: text = text[first_q_pos:]
    
    parsed, ans_map = [], {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
    chunks = re.split(r"\[Q\d*\]", text)
    
    for chunk in chunks:
        # [O] 또는 [A]가 없으면 무시
        if not chunk.strip() or "[A]" not in chunk: continue
        try:
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", chunk)
            q_raw, o_raw, a_raw, k_raw = parts[0].strip(), "", "", "미분류"
            for i in range(len(parts)):
                t = parts[i].strip()
                if t == "[O]": o_raw = parts[i+1].strip()
                elif t == "[A]": a_raw = parts[i+1].strip()
                elif t == "[K]": k_raw = parts[i+1].strip()
            
            opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
            
            # 보기가 추출되지 않았거나 명시적으로 '주관식'이라 적힌 경우 주관식 처리
            if not opts and ("주관식" in o_raw or not o_raw):
                parsed.append({
                    "q": q_raw, 
                    "o": [], # 보기가 빈 리스트면 주관식으로 간주
                    "a": a_raw.strip(), # 주관식 정답 문자열
                    "k": k_raw
                })
            else:
                if not opts: opts = [o.strip() for o in o_raw.split(',') if o.strip()]
                ans_char = a_raw.strip()[0] if a_raw else "1"
                parsed.append({
                    "q": q_raw, 
                    "o": [o.strip() for o in opts], 
                    "a": ans_map.get(ans_char, 0), 
                    "k": k_raw
                })
        except: continue
    return parsed