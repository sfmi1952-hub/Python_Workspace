import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

def create_samples():
    # 1. Excel (Benefit List)
    print("Generating sample_benefits.xlsx...")
    data = {
        '상품코드': ['P001', 'P001', 'P001'],
        '담보코드': ['C001', 'C002', 'C003'],
        '담보명_출력물명칭': ['상해사망', '암진단비(유사암제외)', '뇌출혈진단비'],
        '세부담보템플릿명': ['', '', ''] # To be filled
    }
    df = pd.DataFrame(data)
    df.to_excel("sample_benefits.xlsx", index=False)
    
    # 2. PDF (Policy)
    print("Generating sample_policy.pdf...")
    c = canvas.Canvas("sample_policy.pdf", pagesize=letter)
    width, height = letter
    
    # Page 1
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Total Health Insurance Policy")
    
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 100, "Section 1. General Provisions")
    c.drawString(50, height - 120, "This policy covers various risks...")
    c.showPage()
    
    # Page 2 (Special Terms)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Special Terms and Conditions")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 100, "1. Injury Death Benefit (상해사망)")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 120, "If the insured suffers an injury and dies within 2 years, the company pays the sum insured.")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 160, "2. Cancer Diagnosis Benefit (Excluding Similar Cancer) (암진단비)")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 180, "Upon diagnosis of Cancer (C00-C97), excluding Thyroid/Skin cancer, the company pays 100% of the limit.")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 220, "3. Cerebral Hemorrhage Diagnosis (뇌출혈진단비)")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 240, "Upon diagnosis of I60, I61, or I62, the company pays the diagnosis benefit.")
    
    c.save()
    print("Samples created.")

if __name__ == "__main__":
    create_samples()
