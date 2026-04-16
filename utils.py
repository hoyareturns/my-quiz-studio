import re

def robust_parse(text):
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