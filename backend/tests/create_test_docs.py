"""Create realistic test PDF documents for cross-document validation testing."""

import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


OUTPUT_DIR = "/tmp/test_docs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_w2():
    """Create a realistic W-2 form."""
    path = os.path.join(OUTPUT_DIR, "W2_2024_Jane_Doe.pdf")
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, 750, "Form W-2 Wage and Tax Statement")
    c.setFont("Helvetica", 11)
    c.drawString(50, 710, "Tax Year: 2024")
    c.drawString(50, 685, "Employee SSN: XXX-XX-4567")
    c.drawString(50, 660, "Employee Name: Jane Marie Doe")
    c.drawString(50, 635, "Employee Address: 123 Main Street, Austin, TX 78701")
    c.drawString(50, 600, "Employer Name: Acme Technology Solutions Inc.")
    c.drawString(50, 575, "Employer EIN: 12-3456789")
    c.drawString(50, 550, "Employer Address: 500 Commerce Dr, Austin, TX 78702")
    c.drawString(50, 515, "Box 1 - Wages, tips, other compensation: $95,000.00")
    c.drawString(50, 490, "Box 2 - Federal income tax withheld: $18,500.00")
    c.drawString(50, 465, "Box 3 - Social security wages: $95,000.00")
    c.drawString(50, 440, "Box 4 - Social security tax withheld: $5,890.00")
    c.drawString(50, 415, "Box 5 - Medicare wages and tips: $95,000.00")
    c.drawString(50, 390, "Box 6 - Medicare tax withheld: $1,377.50")
    c.save()
    print(f"Created: {path}")
    return path


def create_pay_stub():
    """Create a realistic pay stub."""
    path = os.path.join(OUTPUT_DIR, "PayStub_Jan2025_Jane_Doe.pdf")
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(200, 750, "PAY STUB")
    c.setFont("Helvetica", 11)
    c.drawString(50, 720, "Employer: Acme Technology Solutions Inc.")
    c.drawString(50, 695, "Pay Period: 01/01/2025 - 01/15/2025")
    c.drawString(50, 670, "Pay Date: 01/17/2025")
    c.drawString(50, 640, "Employee: Jane M. Doe")
    c.drawString(50, 615, "Employee ID: EMP-10234")
    c.drawString(50, 590, "SSN: XXX-XX-4567")
    c.drawString(50, 565, "Job Title: Senior Software Engineer")
    c.drawString(50, 530, "--- Earnings ---")
    c.drawString(50, 505, "Regular Pay (80 hrs @ $45.67/hr):      $3,653.85")
    c.drawString(50, 480, "Current Gross Pay:                      $3,653.85")
    c.drawString(50, 455, "YTD Gross Pay:                          $3,653.85")
    c.drawString(50, 420, "--- Deductions ---")
    c.drawString(50, 395, "Federal Tax:         $712.00")
    c.drawString(50, 370, "State Tax (TX):      $0.00")
    c.drawString(50, 345, "Social Security:     $226.54")
    c.drawString(50, 320, "Medicare:            $52.98")
    c.drawString(50, 295, "401(k):              $182.69")
    c.drawString(50, 260, "Net Pay:             $2,479.64")
    c.drawString(50, 225, "YTD Net Pay:         $2,479.64")
    c.save()
    print(f"Created: {path}")
    return path


def create_bank_statement():
    """Create a realistic bank statement."""
    path = os.path.join(OUTPUT_DIR, "BankStatement_Jan2025_Jane_Doe.pdf")
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(200, 750, "BANK STATEMENT")
    c.setFont("Helvetica", 11)
    c.drawString(50, 720, "First National Bank")
    c.drawString(50, 695, "Account Holder: Jane M Doe")
    c.drawString(50, 670, "Account Number: XXXX-XXXX-4321")
    c.drawString(50, 645, "Statement Period: January 1, 2025 - January 31, 2025")
    c.drawString(50, 610, "Beginning Balance:    $12,450.00")
    c.drawString(50, 585, "Ending Balance:       $18,923.45")
    c.drawString(50, 555, "--- Deposits ---")
    c.drawString(50, 530, "01/17/2025  ACH Direct Deposit - Acme Technology   $2,479.64")
    c.drawString(50, 505, "01/31/2025  ACH Direct Deposit - Acme Technology   $2,479.64")
    c.drawString(50, 480, "Total Deposits:                                     $4,959.28")
    c.drawString(50, 445, "--- Withdrawals ---")
    c.drawString(50, 420, "01/03/2025  Online Transfer to Savings             $1,000.00")
    c.drawString(50, 395, "01/05/2025  Debit Card Purchase - Whole Foods       $156.78")
    c.drawString(50, 370, "01/10/2025  Check #1023                             $1,500.00")
    c.drawString(50, 345, "01/15/2025  Debit Card - AT&T                       $89.00")
    c.drawString(50, 320, "01/20/2025  Online Bill Pay - Mortgage              $1,875.00")
    c.drawString(50, 295, "01/25/2025  Debit Card - Target                    $245.50")
    c.drawString(50, 250, "Average Daily Balance: $15,233.20")
    c.save()
    print(f"Created: {path}")
    return path


if __name__ == "__main__":
    create_w2()
    create_pay_stub()
    create_bank_statement()
    print(f"\nAll test documents created in {OUTPUT_DIR}")
