import os
import json
from bs4 import BeautifulSoup
from markdownify import markdownify
import tiktoken
import hashlib

ENC = tiktoken.get_encoding("cl100k_base")

MAX_TOKENS = 450
MIN_TOKENS = 60

INPUT_FILE = r"C:\Users\dell\Desktop\ITI_2024\ITI_TA_TASK\data\scraped_pages.json"   # single json for all pages
OUTPUT_DIR = "chunks"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def html_to_clean_markdown(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav","footer","iframe","script","style","noscript","header","aside","form","button","input"]):
        tag.decompose()
    md = markdownify(str(soup), strip=['img'])
    return md


def token_len(t):
    return len(ENC.encode(t))


def chunk_heading_recursive(lines):
    chunks=[]
    cur=[]
    for ln in lines:
        if ln.startswith("#"):
            if cur:
                txt="\n".join(cur).strip()
                if token_len(txt)>MIN_TOKENS:
                    chunks.append(txt)
                cur=[]
        cur.append(ln)
        if token_len("\n".join(cur)) > MAX_TOKENS:
            txt="\n".join(cur).strip()
            chunks.append(txt)
            cur=[]
    if cur:
        txt="\n".join(cur).strip()
        if token_len(txt)>MIN_TOKENS:
            chunks.append(txt)
    return chunks


pages = json.load(open(INPUT_FILE,encoding="utf-8"))

for p_i, data in enumerate(pages):
    url  = data["url"]
    html = data["html"]
    title = data.get("title","")

    md = html_to_clean_markdown(html)
    lines = [ln.strip() for ln in md.split("\n") if ln.strip()]

    parts = chunk_heading_recursive(lines)

    for c_i,part in enumerate(parts):
        ck = hashlib.md5(part.encode()).hexdigest()
        out = {
            "url": url,
            "title": title,
            "position": c_i,
            "text": part,
            "checksum": ck,
        }
        outname=f"page_{p_i}_chunk_{c_i}.json"
        json.dump(out, open(os.path.join(OUTPUT_DIR,outname),"w",encoding="utf-8"),ensure_ascii=False,indent=2)

print("✅ Done: ALL pages chunked global")
