#!/usr/bin/env python3
# invoice_combiner_zip_clean.py
# Clean, production-ready version without escape characters.

import argparse
import csv
import re
import sys
import tempfile
import zipfile
from pathlib import Path
import pandas as pd
import shutil

ASIN_PATTERN = r"[A-Z0-9]{10}"
EXPECTED_COLS = ["Invoice Number","PO #","External ID","Title","ASIN","Model #","Freight Term","Qty","Unit Cost","Amount"]

def sanitize_title(t):
    if t is None:
        return ""
    return str(t).strip().rstrip(' ,"“”')

def clean_numeric(x):
    if x is None:
        return ""
    return str(x).replace("$","").replace(",","").strip()

def parse_line_with_regex(line):
    s = line.strip()
    if s.endswith(','):
        s = s[:-1]

    pat1 = re.compile(
        r'^"(?P<po>[^"]*)",'
        r'"(?P<external>[^"]*)",'
        r'"(?P<title>.*?)'
        r'(?P<asin>' + ASIN_PATTERN + r')",'
        r'"(?P<model>[^"]*)",'
        r'"(?P<freight>[^"]*)",'
        r'"(?P<qty>[^"]*)",'
        r'"(?P<unit>[^"]*)",'
        r'"(?P<amount>[^"]*)"$',
        flags=re.DOTALL
    )
    m = pat1.match(s)
    if m:
        g = m.groupdict()
        title = sanitize_title(g['title'])
        return [
            g['po'], g['external'], title, g['asin'],
            g['model'], g['freight'], g['qty'], g['unit'], g['amount']
        ]

    pat2 = re.compile(
        r'^"(?P<po>[^"]*)",'
        r'"(?P<external>[^"]*)",'
        r'"(?P<title_asin>.*?)",'
        r'"(?P<model>[^"]*)",'
        r'"(?P<freight>[^"]*)",'
        r'"(?P<qty>[^"]*)",'
        r'"(?P<unit>[^"]*)",'
        r'"(?P<amount>[^"]*)"$',
        flags=re.DOTALL
    )
    m2 = pat2.match(s)
    if m2:
        g = m2.groupdict()
        t = g['title_asin']
        a = re.search(ASIN_PATTERN, t)
        if a:
            asin = a.group(0)
            title = sanitize_title(t[:a.start()])
            return [
                g['po'], g['external'], title, asin,
                g['model'], g['freight'], g['qty'], g['unit'], g['amount']
            ]

    parts = [p.strip().strip('"') for p in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', s)]
    if len(parts) >= 9:
        for i,p in enumerate(parts):
            if re.fullmatch(ASIN_PATTERN,p):
                if i >= 3:
                    po = parts[0]
                    external = parts[1]
                    title = sanitize_title(",".join(parts[2:i]))
                    asin = parts[i]
                    remainder = parts[i+1:i+6]
                    while len(remainder)<5:
                        remainder.append("")
                    model, freight, qty, unit, amount = remainder[:5]
                    return [po, external, title, asin, model, freight, qty, unit, amount]

    return None

def process_file(path: Path):
    rows=[]
    m = re.match(r"^(\d{6})", path.name)
    inv = m.group(1) if m else ""
    header=False

    with path.open("r",encoding="utf-8",errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if not header and "PO #" in line and "External ID" in line:
                header=True
                continue
            if not header:
                continue

            try:
                parsed = next(csv.reader([raw]))
            except:
                parsed=None

            if parsed and len(parsed)==9:
                po,ex,title,asin,model,freight,qty,unit,amount=[p.strip().strip('"') for p in parsed]
                rows.append([inv,po,ex,sanitize_title(title),asin,model,freight,clean_numeric(qty),clean_numeric(unit),clean_numeric(amount)])
                continue

            repaired = parse_line_with_regex(raw)
            if repaired:
                po,ex,title,asin,model,freight,qty,unit,amount=repaired
                rows.append([inv,po,ex,title,asin,model,freight,clean_numeric(qty),clean_numeric(unit),clean_numeric(amount)])
                continue

    return rows

def process_zip(zip_path: Path, extract_to: Path):
    with zipfile.ZipFile(zip_path,"r") as z:
        z.extractall(extract_to)
    csvs = list(extract_to.rglob("*invoice_details.csv"))
    rows=[]
    for c in csvs:
        rows.extend(process_file(c))
    return rows

def process_dir(d: Path):
    csvs = list(d.glob("*invoice_details.csv"))
    rows=[]
    for c in csvs:
        rows.extend(process_file(c))
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip",type=str)
    parser.add_argument("--data-dir",type=str)
    parser.add_argument("--outdir",type=str,default=".")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True,exist_ok=True)

    rows=[]
    temp=None

    if args.zip:
        temp = Path(tempfile.mkdtemp())
        rows = process_zip(Path(args.zip), temp)
        shutil.rmtree(temp, ignore_errors=True)
    else:
        d = Path(args.data_dir) if args.data_dir else Path(".")
        rows = process_dir(d)

    df = pd.DataFrame(rows, columns=EXPECTED_COLS)
    df.to_csv(outdir/"master_invoice_combined_cleaned.csv", index=False)
    df.to_excel(outdir/"master_invoice_combined_cleaned.xlsx", index=False)

if __name__=="__main__":
    main()
