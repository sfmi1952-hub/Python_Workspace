import re

def parse_text_to_data(text):
    data = {
        "benefitType": "ZU5042000",
        "benefitName": "",
        "node": "",
        "accidentType": "=질병",
        "coverageCode": "ZD3529010",
        "diagnosisCode": "",
        "surgeryCode": "",
        "ediCode": "",
        "reduction": "N",
        "limit": "수술당",
        "hospital": "",
        "formula": "가입금액"
    }
    
    if not text:
        return data

    lines = text.split('\n')
    first_line = lines[0] if lines else ""
    
    # Benefit Name
    # Regex: Remove leading numbers/dots, remove trailing '특별약관'
    name = re.sub(r'^[\d\-\.\s]+', '', first_line)
    name = re.sub(r'\s*특별약관\s*$', '', name)
    data["benefitName"] = name.strip()

    # Diagnosis Code
    if "특정순환계질환" in text:
        diag_str = "=특정순환계질환"
        if "분류표" in text:
            # Simple extraction of classification table content
            # Python's regex for multiline matching
            match = re.search(r'분류표[\s\S]*?(?:제\d+조|$)', text)
            if match:
                table_content = match.group(0)
                diseases = re.findall(r'-\s+([^\n]+)', table_content)
                if diseases:
                    clean_list = "; ".join([d.strip() for d in diseases])
                    diag_str += f"\n(상세: {clean_list})"
        data["diagnosisCode"] = diag_str
    elif "뇌혈관질환" in text:
        data["diagnosisCode"] = "=뇌혈관질환"
    
    # Hospital
    hospitals = []
    if "종합전문요양기관" in text or "상급종합병원" in text:
        hospitals.append("종합전문요양기관")
    if "종합병원" in text:
        hospitals.append("종합병원")
    data["hospital"] = "= " + "; ".join(hospitals) if hospitals else ""

    # Surgery
    if "혈전제거술" in text:
        data["surgeryCode"] = "=혈전제거술"
        data["ediCode"] = "M6630; M6631; M6632; M6633; M6634; M6638; M6639; O1950; O0260; O2065"
    
    # Reduction / Formula
    # Match "1년 ... 50%"
    red_match = re.search(r'(\d+)년.*?(\d+)%', text)
    if red_match:
        years = red_match.group(1)
        percent = red_match.group(2)
        data["reduction"] = f"{years}년이내 {percent}%"
        data["formula"] = f"가입금액({years}년미만{percent}%)"
    
    # Node
    if "수술" in text:
        data["node"] = "수술"
    elif "진단" in text:
        data["node"] = "진단"

    return data
