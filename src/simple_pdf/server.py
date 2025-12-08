
import asyncio
import os
import base64
import re
import fitz  # PyMuPDF
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
try:
    from .convert import markdown_to_docx, docx_to_pdf
except ImportError:
    from convert import markdown_to_docx, docx_to_pdf

from collections import Counter

# 初始化服务器
server = Server("simple-pdf-extractor")

# Windows console encoding fix
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def is_cjk(char):
    """判断字符是否为CJK字符"""
    if len(char) != 1: return False
    code = ord(char)
    return (0x4E00 <= code <= 0x9FFF or  # CJK Unified Ideographs
            0x3400 <= code <= 0x4DBF or  # CJK Unified Ideographs Extension A
            0x20000 <= code <= 0x2A6DF) # CJK Unified Ideographs Extension B

def is_sentence_end(char):
    """判断是否为句子结束符"""
    return char in ['。', '？', '！', '.', '?', '!', ':', '：']

def is_list_item_start(text):
    """
    判断文本是否以列表项符号开头
    支持：
    - Bullet points: •, -, *, ‣, ⁃
    - Numbered lists: 1., 1), (1), a., a), i., i)
    """
    # Use lstrip to handle leading spaces for symbol check
    stripped_text = text.lstrip()
    
    # 1. Common bullet points
    # Use stripped_text to check for bullets (ignoring indentation)
    if stripped_text.startswith(('•', '-', '*', '‣', '⁃', '▪', '●')):
        return True
    
    # 2. Numbered lists (1. or 1) or (1))
    # Matches: "1.", "10.", "a.", "A.", "i.", "I."
    if re.match(r'^(\d+|[a-zA-Z]|[ivxIVX]+)\.\s', stripped_text):
        return True
    
    # Matches: "1)", "a)"
    if re.match(r'^(\d+|[a-zA-Z])\)\s', stripped_text):
        return True
        
    # Matches: "(1)", "(a)"
    if re.match(r'^\((\d+|[a-zA-Z])\)\s', stripped_text):
        return True
        
    return False

def smart_merge_text(text):
    """
    智能合并文本行（块内）：
    """
    if not text:
        return ""
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    if not lines:
        return ""
        
    result = lines[0]
    for i in range(1, len(lines)):
        prev_line = lines[i-1]
        curr_line = lines[i]
        
        last_char = prev_line[-1]
        first_char = curr_line[0]
        
        if is_cjk(last_char) and is_cjk(first_char):
            result += curr_line
        else:
            result += " " + curr_line
    return result

def estimate_body_size(blocks):
    """估计正文即最常见的字体大小"""
    sizes = []
    for b in blocks:
        if b["type"] == 0: # text block
            for line in b["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes.append(round(span["size"], 1))
    if not sizes: return 10.0
    return Counter(sizes).most_common(1)[0][0]

def extract_block_text(block):
    """从 dict block 中提取纯文本和平均字号"""
    text = ""
    total_size = 0
    char_count = 0
    for line in block["lines"]:
        for span in line["spans"]:
            t = span["text"]
            text += t
            if t.strip():
                total_size += span["size"] * len(t)
                char_count += len(t)
    
    avg_size = total_size / char_count if char_count > 0 else 0
    return smart_merge_text(text), avg_size

async def get_pdf_metadata(file_path: str):
    """
    提取PDF元数据和目录结构(TOC)。
    """
    if not os.path.exists(file_path):
        return [types.TextContent(type="text", text=f"Error: 文件不存在 - {file_path}")]
    
    try:
        doc = fitz.open(file_path)
        
        # 1. 基础元数据
        metadata_text = "=== PDF 元数据 ===\n"
        meta = doc.metadata
        for key, value in meta.items():
            if value:
                metadata_text += f"{key}: {value}\n"
        metadata_text += f"Total Pages: {doc.page_count}\n"
        
        # 2. 目录结构 (TOC)
        toc = doc.get_toc()
        if toc:
            metadata_text += "\n=== 目录结构 ===\n"
            for item in toc:
                level, title, page = item
                indent = "  " * (level - 1)
                metadata_text += f"{indent}- {title} (Page {page})\n"
        else:
            metadata_text += "\n(未找到目录结构)\n"
            
        doc.close()
        return [types.TextContent(type="text", text=metadata_text)]
        
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error processing PDF metadata: {str(e)}")]

async def extract_content(file_path: str, page_range: str = "1", keyword: str = None, format: str = "text", include_text: bool = True, include_images: bool = False, use_local_images_only: bool = True):
    """
    提取PDF指定页面的文本和图片。
    :param file_path: PDF文件路径
    :param page_range: 页码范围，例如 "1-5", "1,3,5" (从1开始)，或 "all" 提取所有页面
    :param keyword: 关键词，如果提供，则仅提取包含该关键词的页面（忽略 page_range）
    :param format: 输出格式，'text' (默认) 或 'markdown'
    :param use_local_images_only: 如果为True，图片仅保存到本地并在文本中引用路径，不返回Base64数据（避免上下文溢出）
    :return: 包含文本和图片的列表
    """
    if not os.path.exists(file_path):
        return [types.TextContent(type="text", text=f"Error: 文件不存在 - {file_path}")]

    result_content = []
    
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        
        pages_to_extract = []
        
        # 1. 如果指定了关键词，优先按关键词搜索
        if keyword and keyword.strip():
            result_content.append(types.TextContent(type="text", text=f"正在搜索关键词: '{keyword}'...\n"))
            found_pages = []
            for i in range(total_pages):
                page = doc[i]
                text = page.get_text()
                if keyword.lower() in text.lower():
                    found_pages.append(i)
            
            if not found_pages:
                doc.close()
                return [types.TextContent(type="text", text=f"未找到包含关键词 '{keyword}' 的页面")]
            
            pages_to_extract = found_pages
            page_range = f"keyword_search({len(found_pages)} pages)"
            
        # 2. 否则按页码范围处理
        else:
            if str(page_range).lower() == "all":
                pages_to_extract = list(range(total_pages))
            else:
                try:
                    # 解析页码
                    parts = str(page_range).split(',')
                    for part in parts:
                        if '-' in part:
                            start, end = map(int, part.split('-'))
                            # 转换为0-based索引
                            pages_to_extract.extend(range(start - 1, end))
                        else:
                            pages_to_extract.append(int(part) - 1)
                    
                    # 过滤有效页码并去重排序
                    pages_to_extract = sorted(list(set([p for p in pages_to_extract if 0 <= p < total_pages])))
                except Exception:
                    # 解析失败默认提取第一页
                    pages_to_extract = [0]

        summary_text = f"正在处理文件: {file_path}\n页码范围: {page_range} (共 {len(pages_to_extract)} 页)\n内容类型: {'文本' if include_text else ''}{'/' if include_text and include_images else ''}{'图片' if include_images else ''}\n"
        result_content.append(types.TextContent(type="text", text=summary_text))

        # 准备图片输出目录
        pdf_filename = os.path.basename(file_path)
        pdf_name_no_ext = os.path.splitext(pdf_filename)[0]
        cwd = os.getcwd()
        output_dir = os.path.join(cwd, "extracted_images", pdf_name_no_ext)
        
        # 如果需要提取图片，先创建目录
        has_images = False
        if include_images:
            os.makedirs(output_dir, exist_ok=True)

        for i in pages_to_extract:
            page_num = i + 1
            page = doc[i]
            
            # 存储当前页的图片路径，用于插入到 Markdown
            page_image_paths = []
            image_content_objects = []

            # 1. 先处理图片（保存并获取路径）
            if include_images:
                image_list = page.get_images()
                if image_list:
                    if not has_images:
                        has_images = True
                        result_content.append(types.TextContent(type="text", text=f"\n[图片保存目录: {output_dir}]\n"))
                    
                    for j, img in enumerate(image_list):
                        try:
                            xref = img[0]
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image["image"]
                            ext = base_image["ext"]
                            img_filename = f"page_{page_num}_img_{j+1}.{ext}"
                            img_path = os.path.join(output_dir, img_filename)
                            
                            with open(img_path, "wb") as f:
                                f.write(image_bytes)
                            
                            # 记录路径
                            page_image_paths.append(img_filename)
                            
                            # 如果需要返回 Base64，则创建 ImageContent 对象
                            if not use_local_images_only:
                                img_b64 = base64.b64encode(image_bytes).decode('utf-8')
                                image_content_objects.append(types.ImageContent(
                                    type="image",
                                    data=img_b64,
                                    mimeType=f"image/{ext}"
                                ))
                                result_content.append(types.TextContent(type="text", text=f"  - Saved: {img_filename}\n"))
                        except Exception as img_err:
                            result_content.append(types.TextContent(type="text", text=f"  Warning: Failed to extract image {j+1}: {img_err}\n"))

            # 2. 提取文本
            if include_text:
                blocks = page.get_text("dict", sort=True)["blocks"]
                body_size = estimate_body_size(blocks)
                full_page_text = ""
                last_bbox = None
                for b in blocks:
                    if b["type"] != 0:
                        continue
                    block_text, size = extract_block_text(b)
                    if not block_text:
                        continue
                    if block_text.isdigit() and (abs(size - body_size) > 1 or size < body_size):
                        continue
                    prefix = ""
                    is_header = False
                    if format == 'markdown':
                        if size > body_size + 6:
                            prefix = "# "
                            is_header = True
                        elif size > body_size + 3:
                            prefix = "## "
                            is_header = True
                        elif size > body_size + 1:
                            if len(block_text) < 50:
                                prefix = "### "
                                is_header = True
                            else:
                                block_text = f"**{block_text}**"
                    curr_bbox = b["bbox"]
                    curr_x0 = curr_bbox[0]
                    if is_header:
                        full_page_text += f"\n\n{prefix}{block_text}\n\n"
                    else:
                        should_merge = False
                        if full_page_text and not full_page_text.endswith('\n'):
                            if last_bbox:
                                v_dist = curr_bbox[1] - last_bbox[3]
                                if v_dist < 15.0:
                                    if not is_sentence_end(full_page_text.strip()[-1]):
                                        should_merge = True
                                    last_x0 = last_bbox[0]
                                    if abs(curr_x0 - last_x0) > 5.0:
                                        should_merge = False
                                    page_width = page.rect.width
                                    last_x1 = last_bbox[2]
                                    right_margin_threshold = page_width - min(50, page_width * 0.1)
                                    if last_x1 < right_margin_threshold:
                                        should_merge = False
                                    if is_list_item_start(block_text):
                                        should_merge = False
                        if should_merge:
                            if is_cjk(full_page_text[-1]) and is_cjk(block_text[0]):
                                full_page_text += block_text
                            else:
                                full_page_text += " " + block_text
                        else:
                            full_page_text += "\n\n" + block_text
                    last_bbox = curr_bbox
                safe_text = full_page_text.encode('utf-8', errors='replace').decode('utf-8')
                
                # 在文本末尾追加图片引用 (Markdown 模式)
                if format == 'markdown' and page_image_paths:
                    safe_text += "\n\n"
                    for img_file in page_image_paths:
                        # 使用相对路径或绝对路径，这里使用相对路径方便阅读
                        # 注意：Obsidian 等工具可能需要特定格式，这里使用标准 Markdown 图片语法
                        # 引用路径: extracted_images/filename/img.jpg
                        rel_path = f"extracted_images/{pdf_name_no_ext}/{img_file}"
                        # 转义空格
                        rel_path = rel_path.replace(" ", "%20")
                        safe_text += f"![Image]({rel_path})\n"

                if format == 'markdown':
                    page_header = f"## Page {page_num}\n\n"
                else:
                    page_header = f"\n{'='*20} Page {page_num} {'='*20}\n"
                
                page_content = page_header + (safe_text if safe_text.strip() else "(No text content)") + "\n"
                result_content.append(types.TextContent(type="text", text=page_content))
            
            # 3. 添加图片对象 (如果启用 Base64 返回)
            if not use_local_images_only and image_content_objects:
                result_content.extend(image_content_objects)

        doc.close()
        
    except Exception as e:
        result_content.append(types.TextContent(type="text", text=f"Error processing PDF: {str(e)}"))

    return result_content

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="extract_pdf_content",
            description="提取PDF文件的文本和图片（支持指定页码范围或关键词搜索）",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "PDF文件的绝对路径",
                    },
                    "page_range": {
                        "type": "string",
                        "description": "页码范围，例如 '1-5', '1,3,5', 'all' (默认为 'all')",
                        "default": "all"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "可选：根据关键词搜索并提取相关页面（如果提供此参数，将忽略 page_range）"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "markdown"],
                        "description": "输出格式，可选 'text' (默认) 或 'markdown'，markdown 格式更适合 LLM 阅读",
                        "default": "text"
                    },
                    "include_text": {
                        "type": "boolean",
                        "description": "是否提取文本，默认 true",
                        "default": True
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "是否提取图片，默认 false",
                        "default": False
                    },
                    "use_local_images_only": {
                        "type": "boolean",
                        "description": "如果为true(默认)，图片仅保存到本地并在文本中引用路径，不返回Base64数据（避免上下文溢出）；设为false则会返回图片Base64数据流",
                        "default": True
                    }
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="get_pdf_metadata",
            description="提取PDF的元数据信息和目录结构(TOC)",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "PDF文件的绝对路径",
                    }
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="convert_markdown_to_docx",
            description="将 Markdown 内容转换为 Word 文档 (.docx)",
            inputSchema={
                "type": "object",
                "properties": {
                    "markdown_content": {
                        "type": "string",
                        "description": "要转换的 Markdown 文本内容",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "输出 .docx 文件的绝对路径",
                    }
                },
                "required": ["markdown_content", "output_path"],
            },
        ),
        types.Tool(
            name="convert_docx_to_pdf",
            description="将 Word 文档 (.docx) 转换为 PDF (支持 Microsoft Word 或 WPS Office)",
            inputSchema={
                "type": "object",
                "properties": {
                    "docx_path": {
                        "type": "string",
                        "description": "输入的 .docx 文件绝对路径",
                    },
                    "pdf_path": {
                        "type": "string",
                        "description": "可选：输出 .pdf 文件的绝对路径（如果不填则在同目录下生成）",
                    }
                },
                "required": ["docx_path"],
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if not arguments:
        raise ValueError("Missing arguments")

    file_path = arguments.get("file_path")

    if name == "extract_pdf_content":
        page_range = arguments.get("page_range", "all")
        keyword = arguments.get("keyword")
        format = arguments.get("format", "text")
        include_text = arguments.get("include_text", True)
        include_images = arguments.get("include_images", False)
        use_local_images_only = arguments.get("use_local_images_only", True)
        return await extract_content(file_path, page_range, keyword, format, include_text, include_images, use_local_images_only)
    
    elif name == "get_pdf_metadata":
        return await get_pdf_metadata(file_path)

    elif name == "convert_markdown_to_docx":
        md_content = arguments.get("markdown_content")
        out_path = arguments.get("output_path")
        if not md_content or not out_path:
            raise ValueError("Missing markdown_content or output_path")
        
        try:
            # 由于 markdown_to_docx 是同步的，如果耗时较长可能需要 run_in_executor，但 pandoc 转换通常很快
            result_path = markdown_to_docx(md_content, out_path)
            return [types.TextContent(type="text", text=f"Successfully converted to {result_path}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error converting markdown: {str(e)}")]

    elif name == "convert_docx_to_pdf":
        docx_path = arguments.get("docx_path")
        pdf_path = arguments.get("pdf_path")
        if not docx_path:
            raise ValueError("Missing docx_path")
            
        try:
            result_path = docx_to_pdf(docx_path, pdf_path)
            return [types.TextContent(type="text", text=f"Successfully converted to {result_path}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error converting to PDF: {str(e)}")]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="simple-pdf-extractor",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
