
import fitz
import os

def inspect_list_items(pdf_path, page_num=0):
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    doc = fitz.open(pdf_path)
    page = doc[page_num]
    
    print(f"\n--- Page {page_num + 1} List Analysis ---")
    
    # 使用 dict 模式查看每个 span 的位置
    blocks = page.get_text("dict", sort=True)["blocks"]
    
    for b in blocks:
        if b["type"] != 0: continue
        
        print(f"\nBlock (bbox={b['bbox']}):")
        for line in b["lines"]:
            line_text = ""
            for span in line["spans"]:
                line_text += span["text"]
            
            # 打印每一行，查看是否有明显的缩进或列表标记
            # line["bbox"][0] 是 x0 坐标
            indent = line["bbox"][0]
            print(f"  [x={indent:.1f}] {line_text}")

    doc.close()

if __name__ == "__main__":
    # 检查第一页，通常包含 "JDBC..." 的定义列表
    inspect_list_items("JDBC实战.pdf", 0)
