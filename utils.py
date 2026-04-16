import re

def robust_parse(text):
    first_q_pos = text.find("[Q")
    if first_q_pos != -1: text = text[first_q_pos:]
    
    parsed, ans_map = [], {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
    chunks = re.split(r"\[Q\d*\]", text)
    
    for chunk in chunks:
        if not chunk.strip() or "[O]" not in chunk or "[A]" not in chunk: continue
        try:
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", chunk)
            q_raw, o_raw, a_raw, k_raw = parts[0].strip(), "", "1", "미분류"
            for i in range(len(parts)):
                t = parts[i].strip()
                if t == "[O]": o_raw = parts[i+1].strip()
                elif t == "[A]": a_raw = parts[i+1].strip()
                elif t == "[K]": k_raw = parts[i+1].strip()
            
            # 💡 [핵심 패치] 주관식인지 객관식인지 판별
            if "주관식" in o_raw:
                opts = ["주관식"]
                ans = a_raw.strip() # 주관식은 텍스트 자체가 정답
            else:
                opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
                if not opts: opts = [o.strip() for o in o_raw.split(',') if o.strip()]
                ans_char = a_raw.strip()[0] if a_raw else "1"
                ans = ans_map.get(ans_char, 0)
                
            parsed.append({
                "q": q_raw, 
                "o": opts, 
                "a": ans, 
                "k": k_raw
            })
        except: continue
    return parsed