
import sys
import os
import argparse
import fitz  # PyMuPDF

def extract_pdf_content(file_path, start_page=1, end_page=None, output_dir="extracted_output"):
    """
    提取PDF指定页面的文本和图片。
    
    :param file_path: PDF文件路径
    :param start_page: 开始页码（从1开始）
    :param end_page: 结束页码（包含），如果为None则提取到最后
    :param output_dir: 图片保存目录
    """
    
    if not os.path.exists(file_path):
        print(f"Error: 文件不存在 - {file_path}")
        return

    print(f"Processing: {file_path}")
    
    # 创建图片输出目录
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    
    # 文本输出文件
    text_output_file = os.path.join(output_dir, "content.txt")
    
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        
        # 处理页码范围
        if end_page is None or end_page > total_pages:
            end_page = total_pages
        
        start_idx = max(0, start_page - 1)
        end_idx = min(total_pages, end_page)
        
        print(f"Extracting pages: {start_page} to {end_page} (Total: {total_pages})")
        print(f"Images will be saved to: {img_dir}")
        print(f"Text will be saved to: {text_output_file}")
        
        with open(text_output_file, "w", encoding="utf-8") as text_file:
            for i in range(start_idx, end_idx):
                page_num = i + 1
                page = doc[i]
                
                header = f"\n{'='*20} Page {page_num} {'='*20}\n"
                print(header.strip())
                text_file.write(header)
                
                # 1. 提取文本
                text = page.get_text()
                # 简单清洗
                safe_text = text.encode('utf-8', errors='replace').decode('utf-8')
                
                if safe_text.strip():
                    print(safe_text[:100] + "..." if len(safe_text) > 100 else safe_text)
                    text_file.write(safe_text + "\n")
                else:
                    print("(No text content)")
                    text_file.write("(No text content)\n")
                
                # 2. 提取图片
                image_list = page.get_images()
                if image_list:
                    print(f"  [Found {len(image_list)} images]")
                    for j, img in enumerate(image_list):
                        try:
                            xref = img[0]
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]
                            
                            filename = f"page_{page_num}_img_{j+1}.{image_ext}"
                            filepath = os.path.join(img_dir, filename)
                            
                            with open(filepath, "wb") as img_file:
                                img_file.write(image_bytes)
                        except Exception as img_err:
                            print(f"  Warning: Failed to extract image {j+1} on page {page_num}: {img_err}")
                
        doc.close()
        print(f"\nDone! All content saved to '{output_dir}'")
        
    except Exception as e:
        print(f"Error processing PDF: {e}")

def main():
    parser = argparse.ArgumentParser(description="Extract text and images from PDF.")
    parser.add_argument("file", help="Path to the PDF file")
    parser.add_argument("-s", "--start", type=int, default=1, help="Start page number (default: 1)")
    parser.add_argument("-e", "--end", type=int, help="End page number (default: last page)")
    parser.add_argument("-o", "--output", default="extracted_output", help="Output directory (default: extracted_output)")
    
    args = parser.parse_args()
    
    extract_pdf_content(args.file, args.start, args.end, args.output)

if __name__ == "__main__":
    main()
