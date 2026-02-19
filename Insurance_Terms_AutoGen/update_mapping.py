"""담보매핑 CSV 업데이트 스크립트"""
import csv

# 사용자 제공 데이터 (탭 구분)
raw_data = """대표담보코드	대표담보명(약관)	담보코드	담보명	구분
ZD0021010	유사암 최초수술비	ZD0021010	유사암 최초수술비	질병
ZD0021010	유사암 최초수술비	ZD3201010	[건강]유사암 최초수술비	질병
ZD0021010	유사암 최초수술비	ZR0021010	유사암 최초수술비	질병
ZD0021010	유사암 최초수술비	ZR0828010	[통합간편]유사암 최초수술비	질병
ZD0021010	유사암 최초수술비	ZR3201010	[갱신형][건강]유사암 최초수술비	질병
ZD0033010	2대 심장질환 진단비	ZD0033010	2대 심장질환 진단비	질병
ZD0033010	2대 심장질환 진단비	ZD3202010	[건강]2대 심장질환 진단비	질병
ZD0033010	2대 심장질환 진단비	ZR0033010	[갱신형] 2대 심장질환 진단비	질병
ZD0033010	2대 심장질환 진단비	ZR0829010	[통합간편]2대 심장질환 진단비	질병
ZD0033010	2대 심장질환 진단비	ZR3202010	[갱신형][건강]2대 심장질환 진단비	질병
ZD0041010	5대 심장질환 진단비	ZD0041010	5대 심장질환 진단비	질병
ZD0041010	5대 심장질환 진단비	ZD3203010	[건강]5대 심장질환 진단비	질병
ZD0041010	5대 심장질환 진단비	ZR0041010	[갱신형] 5대 심장질환 진단비	질병
ZD0041010	5대 심장질환 진단비	ZR0830010	[통합간편]5대 심장질환 진단비	질병
ZD0041010	5대 심장질환 진단비	ZR3203010	[갱신형][건강]5대 심장질환 진단비	질병"""

# 파일에서 전체 데이터 읽기 (사용자가 제공한 전체 데이터를 별도 파일로 저장)
# 여기서는 샘플 데이터만 포함

output_path = r"c:\Users\Shin-Nyum\Desktop\Python_Workspace\Insurance_Terms_AutoGen\data\담보매핑.csv"

# CSV 헤더
header = ["대표담보코드", "담보코드", "대표담보명", "담보명", "구분값", "확인필요"]

rows = []
lines = raw_data.strip().split("\n")
for line in lines[1:]:  # 헤더 스킵
    parts = line.split("\t")
    if len(parts) >= 5:
        row = [
            parts[0].strip(),  # 대표담보코드
            parts[2].strip(),  # 담보코드
            parts[1].strip(),  # 대표담보명
            parts[3].strip(),  # 담보명
            parts[4].strip(),  # 구분값
            ""                 # 확인필요
        ]
        rows.append(row)

with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f"저장 완료: {len(rows)}건")
