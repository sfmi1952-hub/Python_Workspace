"""
담보매핑 CSV 변환 스크립트
사용법: 
1. 이 스크립트와 같은 폴더에 'mapping_raw.txt' 파일로 탭구분 데이터 저장
2. python convert_mapping.py 실행
3. data/담보매핑.csv 파일 생성됨
"""
import csv
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
input_path = os.path.join(script_dir, "mapping_raw.txt")
output_path = os.path.join(script_dir, "data", "담보매핑.csv")

# CSV 헤더 (프로그램에서 사용하는 형식)
header = ["대표담보코드", "담보코드", "대표담보명", "담보명", "구분값", "확인필요"]

rows = []

with open(input_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if i == 0:  # 헤더 스킵
        continue
    
    line = line.strip()
    if not line:
        continue
    
    parts = line.split("\t")
    if len(parts) >= 5:
        row = [
            parts[0].strip(),  # 대표담보코드
            parts[2].strip(),  # 담보코드
            parts[1].strip(),  # 대표담보명(약관) → 대표담보명
            parts[3].strip(),  # 담보명
            parts[4].strip(),  # 구분 → 구분값
            ""                 # 확인필요 (빈칸)
        ]
        rows.append(row)

# CSV 저장
with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f"변환 완료: {len(rows)}건 → {output_path}")
