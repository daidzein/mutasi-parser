# PDF Transaction (Mutasi) Parser

A Python tool to extract transaction details from Permata Bank PDF statements with color-based classification.

## Features
- Extracts transaction dates, amounts, and descriptions
- Color-based transaction type detection (red=outbound, green=incoming)
- Exports to CSV format
- Handles complex PDF layouts with position-based text grouping

## Requirements
- PyMuPDF
- pandas
- python-dateutil

## Installation
```bash 
pip install PyMuPDF pandas python-dateutil
```

## Usage
```bash
python trx_0.2.py
```

## Output

CSV Files with columns: date, transaction description, amount, type (inbound/outbound), raw_text