import os
print("♻️ Rebuilding pipeline (scrape → chunk → index)...")
os.system("python cli_tools/crawl.py")
os.system("python cli_tools/embed.py")
os.system("python cli_tools/index.py")
