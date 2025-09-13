import fitz  # PyMuPDF
import re
import pandas as pd
from datetime import datetime
from dateutil import parser

# Constants for color matching - defined once at module level
RED_COLOR = (220, 13, 38)  # RGB for outbound transactions
GREEN_COLOR = (6, 140, 120)  # RGB for incoming transactions
COLOR_TOLERANCE = 20
Y_POSITION_TOLERANCE = 5  # Tolerance for grouping elements on same line

# Transaction keywords for description detection
TRANSACTION_KEYWORDS = [
    'TRF', 'PAY', 'QR', 'BIAYA', 'DBT', 'CRD', 'TRANSFER', 
    'PAYMENT', 'PURCHASE', 'TARIK', 'SETOR', 'BALEN', 'ADM'
]

# Regex patterns compiled once for efficiency
AMOUNT_PATTERN = re.compile(r'Rp\s*([\d,]+\.?\d*)')
DATE_PATTERNS = [
    re.compile(r'(\d{1,2}\s+\w+\s+\d{4})'),  # "31 August 2025"
    re.compile(r'(\d{1,2}/\d{1,2}/\d{4})'),    # "31/08/2025"
    re.compile(r'(\d{4}-\d{2}-\d{2})'),        # "2025-08-31"
]
CLEANUP_PATTERN = re.compile(r'\s+')

def check_color_match(color_int, target_rgb, tolerance=COLOR_TOLERANCE):
    """Generic color matching function"""
    if color_int is None:
        return False
    
    r = (color_int & 0xFF0000) >> 16
    g = (color_int & 0x00FF00) >> 8
    b = (color_int & 0x0000FF)
    
    return all(abs(actual - target) < tolerance 
              for actual, target in zip((r, g, b), target_rgb))

def is_red_color(color_int):
    """Check if color is red (outbound transaction)"""
    return check_color_match(color_int, RED_COLOR)

def is_green_color(color_int):
    """Check if color is green (incoming transaction)"""
    return check_color_match(color_int, GREEN_COLOR)

def extract_amount(text):
    """Extract amount from text containing 'Rp'"""
    match = AMOUNT_PATTERN.search(text)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            pass
    return None

def extract_date_from_text(text):
    """Try to extract date from transaction text"""
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return parser.parse(match.group(1))
            except:
                continue
    return None

def get_text_elements(page):
    """Extract and sort all text elements from a page"""
    text_instances = page.get_text("dict")
    elements = []
    
    for block in text_instances["blocks"]:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if text:
                        bbox = span.get("bbox")
                        elements.append({
                            'text': text,
                            'color': span.get("color"),
                            'y': bbox[1],
                            'x': bbox[0]
                        })
    
    return sorted(elements, key=lambda x: x['y'])

def group_elements_by_line(elements):
    """Group text elements that appear on the same line"""
    if not elements:
        return []
    
    lines = []
    current_line = [elements[0]]
    current_y = elements[0]['y']
    
    for elem in elements[1:]:
        if abs(elem['y'] - current_y) < Y_POSITION_TOLERANCE:
            current_line.append(elem)
        else:
            lines.append(current_line)
            current_line = [elem]
            current_y = elem['y']
    
    if current_line:
        lines.append(current_line)
    
    return lines

def determine_transaction_type(line_elements):
    """Determine transaction type based on color of amount element"""
    for elem in line_elements:
        if "Rp" in elem['text'] and elem['color']:
            if is_red_color(elem['color']):
                return "outbound"
            elif is_green_color(elem['color']):
                return "incoming"
    
    # Fallback to last element's color
    if line_elements and line_elements[-1]['color']:
        color = line_elements[-1]['color']
        if is_red_color(color):
            return "outbound"
        elif is_green_color(color):
            return "incoming"
    
    return "unknown"

def clean_description(text):
    """Clean and format description text"""
    cleaned = AMOUNT_PATTERN.sub('', text)
    cleaned = CLEANUP_PATTERN.sub(' ', cleaned).strip(' -.:,')
    return cleaned if cleaned else None

def is_description_line(text):
    """Check if line contains transaction keywords but no amount"""
    has_keyword = any(keyword in text.upper() for keyword in TRANSACTION_KEYWORDS)
    has_amount = "Rp" in text
    return has_keyword and not has_amount

def extract_transactions_from_pdf(pdf_path):
    """Main function to extract transactions from PDF with descriptions"""
    doc = fitz.open(pdf_path)
    transactions = []
    current_date = None
    
    print("Starting PDF processing...")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        print(f"Processing page {page_num + 1}")
        
        # Get and group text elements
        elements = get_text_elements(page)
        lines = group_elements_by_line(elements)
        
        pending_description = None
        
        for line_elements in lines:
            line_text = " ".join(elem['text'] for elem in line_elements).strip()
            
            if not line_text:
                continue
            
            # Check for date header
            date_in_line = extract_date_from_text(line_text)
            if date_in_line and "Rp" not in line_text:
                current_date = date_in_line
                print(f"Found date: {current_date}")
                pending_description = None
                continue
            
            # Check for description line
            if is_description_line(line_text):
                pending_description = line_text
                print(f"Pending description: {pending_description}")
                continue
            
            # Check for amount line
            amount = extract_amount(line_text)
            if amount is not None:
                trans_type = determine_transaction_type(line_elements)
                
                # Use pending description or extract from current line
                description = pending_description or clean_description(line_text)
                
                if description:
                    transaction = {
                        'date': current_date.strftime('%Y-%m-%d') if current_date else 'Unknown',
                        'description': description,
                        'amount': amount,
                        'type': trans_type,
                        'raw_text': line_text
                    }
                    
                    transactions.append(transaction)
                    print(f"✓ Added transaction: {description} - Rp {amount:,.2f} ({trans_type})")
                    pending_description = None
                else:
                    print(f"Could not extract description for amount: Rp {amount:,.2f}")
    
    doc.close()
    return transactions

def save_to_csv(transactions, output_file='permata_aug_2025.csv'): # I will add month file name automation later, stay tuned!
    """Save transactions to CSV file"""
    df = pd.DataFrame(transactions)
    df.to_csv(output_file, index=False)
    print(f"Transactions saved to {output_file}")
    return df

def print_summary(df):
    """Print transaction summary"""
    print(f"\nSummary:")
    print(f"- Total transactions: {len(df)}")
    print(f"- Outbound transactions: {len(df[df['type'] == 'outbound'])}")
    print(f"- Incoming transactions: {len(df[df['type'] == 'incoming'])}")
    print(f"- Unknown type: {len(df[df['type'] == 'unknown'])}")

# Main execution
if __name__ == "__main__":
    # change your pdf file name into "permata_mmm_yyyy.pdf" 
    pdf_path = "permata_aug_2025.pdf"
    
    try:
        print("Extracting transactions with descriptions from PDF...")
        transactions = extract_transactions_from_pdf(pdf_path)
        
        if transactions:
            print(f"\nFound {len(transactions)} transactions:")
            print("-" * 100)
            
            # Show first 5 transactions
            for i, trans in enumerate(transactions[:5], 1):
                print(f"{i}. Date: {trans['date']}")
                print(f"   Description: {trans['description']}")
                print(f"   Amount: Rp {trans['amount']:,.2f}")
                print(f"   Type: {trans['type']}")
                print("-" * 100)
            
            if len(transactions) > 5:
                print(f"... and {len(transactions) - 5} more transactions")
            
            # Save to CSV and show summary
            df = save_to_csv(transactions)
            print_summary(df)
            
        else:
            print("No transactions found in the PDF")
            
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        print("Make sure the PDF file exists and PyMuPDF is installed")
        import traceback
        traceback.print_exc()