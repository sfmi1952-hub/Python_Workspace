
import pandas as pd
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Directories
base_dir = r"c:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step2\data"
os.makedirs(os.path.join(base_dir, "code"), exist_ok=True)
os.makedirs(os.path.join(base_dir, "new"), exist_ok=True)

# 1. Diagnosis Code Mapping Excel
code_data = {
    "진단분류": ["악성신생물(암)", "상피내암", "경계성종양", "갑상선암", "기타피부암", "대장점막내암", "뇌졸중", "급성심근경색"],
    "분류번호": ["C00-C97", "D00-D09", "D37-D48", "C73", "C44", "C18-C20(with conditions)", "I60-I63", "I21-I23"]
}
df_code = pd.DataFrame(code_data)
df_code.to_excel(os.path.join(base_dir, "code", "diagnosis_mapping.xlsx"), index=False)
print("Created diagnosis_mapping.xlsx")

# 2. Target Benefit List Excel (Output of Step 1)
benefit_data = {
    "담보명_출력물명칭": ["일반암진단비", "유사암진단비", "뇌졸중진단비", "급성심근경색증진단비"],
    "세부담보템플릿명": ["암(유사암제외)진단", "유사암진단", "뇌졸중진단", "급성심근경색증진단"],
    "Inferred_Template_Name": ["암(유사암제외)진단", "유사암진단", "뇌졸중진단", "급성심근경색증진단"], # As if inferred perfectly
    "Reference_Page": ["5", "5", "10", "12"]
}
df_benefit = pd.DataFrame(benefit_data)
df_benefit.to_excel(os.path.join(base_dir, "new", "target_benefit_list.xlsx"), index=False)
print("Created target_benefit_list.xlsx")

# 3. Dummy Policy PDF
pdf_path = os.path.join(base_dir, "new", "target_policy.pdf")
c = canvas.Canvas(pdf_path, pagesize=A4)

# Function to draw text (Simulating Korean text - might look broken if font missing, but content exists for extraction)
# In real scenario we use a font, here we just output English representations for simplicity of testing 
# OR we assume pypdf extracts byte string correctly. 
# Let's write English text that implies Korean context to avoid font issues in generation but usable for logic.

text_content = """
--- Policy Terms ---

Article 3 (Definition of Cancer)
1. "Cancer" (Malignant Neoplasm) refers to diseases classified under C00-C97 in the KCD. 
   However, C44 (Other Skin Cancer), C73 (Thyroid Cancer), and Carcinoma in situ (D00-D09) are excluded.
   Borderline Tumors (D37-D48) are also excluded.

Article 4 (Definition of Similar Cancer)
"Similar Cancer" includes:
- Other Skin Cancer (C44)
- Thyroid Cancer (C73)
- Carcinoma in situ (D00-D09)
- Borderline Tumor (D37-D48)
- Colorectal Mucosal Cancer

Article 10 (Definition of Stroke)
"Stroke" includes Subarachnoid hemorrhage (I60), Intracerebral hemorrhage (I61), 
and Cerebral infarction (I63).
Note: I64 is not covered unless specified.

Article 12 (Definition of Acute Myocardial Infarction)
"Acute Myocardial Infarction" covers I21, I22, I23.
"""

c.drawString(100, 800, "Reference Policy Document")
y = 750
for line in text_content.split('\n'):
    c.drawString(50, y, line)
    y -= 15

c.save()
print("Created target_policy.pdf")
