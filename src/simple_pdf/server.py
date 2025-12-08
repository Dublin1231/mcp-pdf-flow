
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

async def extract_content(file_path: str, page_range: str = "1", keyword: str = None, format: str = "text"):
    """
    提取PDF指定页面的文本和图片。
    :param file_path: PDF文件路径
    :param page_range: 页码范围，例如 "1-5", "1,3,5" (从1开始)，或 "all" 提取所有页面
    :param keyword: 关键词，如果提供，则仅提取包含该关键词的页面（忽略 page_range）
    :param format: 输出格式，'text' (默认) 或 'markdown'
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

        summary_text = f"正在处理文件: {file_path}\n页码范围: {page_range} (共 {len(pages_to_extract)} 页)\n"
        result_content.append(types.TextContent(type="text", text=summary_text))

        # 准备图片输出目录
        pdf_filename = os.path.basename(file_path)
        pdf_name_no_ext = os.path.splitext(pdf_filename)[0]
        cwd = os.getcwd()
        output_dir = os.path.join(cwd, "extracted_images", pdf_name_no_ext)
        
        # 如果需要提取图片，先创建目录
        has_images = False

        for i in pages_to_extract:
            page_num = i + 1
            page = doc[i]
            
            # 1. 提取文本 (使用 dict 模式 + 智能合并逻辑)
            blocks = page.get_text("dict", sort=True)["blocks"]
            
            # 估计正文字体大小
            body_size = estimate_body_size(blocks)
            
            full_page_text = ""
            last_bbox = None
            
            for b in blocks:
                if b["type"] != 0: continue # 忽略非文本块
                
                block_text, size = extract_block_text(b)
                if not block_text: continue
                
                # 忽略页码 (简单规则：纯数字且字号偏离正文，或字号过小)
                if block_text.isdigit() and (abs(size - body_size) > 1 or size < body_size):
                    continue
                
                # 判断标题层级
                prefix = ""
                is_header = False
                
                # Markdown 格式才使用标题层级
                if format == 'markdown':
                    if size > body_size + 6: # H1
                        prefix = "# "
                        is_header = True
                    elif size > body_size + 3: # H2
                        prefix = "## "
                        is_header = True
                    elif size > body_size + 1: # Bold / H3
                        # 对于较小的标题，或者长度过长的“标题”（可能是强调段落），降级处理
                        if len(block_text) < 50:
                            prefix = "### "
                            is_header = True
                        else:
                            # 长度过长，可能是强调段落，加粗显示
                            block_text = f"**{block_text}**"
                
                curr_bbox = b["bbox"]
                curr_x0 = curr_bbox[0]
                
                if is_header:
                    full_page_text += f"\n\n{prefix}{block_text}\n\n"
                else:
                    # 正文合并逻辑
                    should_merge = False
                    if full_page_text and not full_page_text.endswith('\n'):
                        # 检查垂直距离
                        if last_bbox:
                            v_dist = curr_bbox[1] - last_bbox[3]
                            if v_dist < 15.0:
                                # 1. 检查前文结束符 (如果是句子结束，通常不合并，除非是列表项中间断开)
                                if not is_sentence_end(full_page_text.strip()[-1]):
                                    should_merge = True
                                
                                # 2. 检查缩进变化 (如果缩进发生显著变化，通常意味着新的段落或列表项)
                                last_x0 = last_bbox[0]
                                if abs(curr_x0 - last_x0) > 5.0:
                                    should_merge = False
                                
                                # 3. 检查上一行是否"提前结束" (Line Width Check)
                                # 如果上一行离右边缘还有较大距离，说明是强制换行(如列表项结束)
                                page_width = page.rect.width
                                last_x1 = last_bbox[2]
                                # 假设右边距约为页宽的 10% 或至少 50pt
                                right_margin_threshold = page_width - min(50, page_width * 0.1)
                                
                                if last_x1 < right_margin_threshold:
                                    should_merge = False
                                
                                # 4. 显式列表项符号检测 (Explicit Symbol Detection)
                                # 如果当前行以 •, 1. 等开头，强制不合并
                                if is_list_item_start(block_text):
                                    should_merge = False

                    if should_merge:
                        if is_cjk(full_page_text[-1]) and is_cjk(block_text[0]):
                            full_page_text += block_text
                        else:
                            full_page_text += " " + block_text
                    else:
                        # 如果是列表项（有缩进且非标题），可以考虑添加标记
                        # 简单判断：如果缩进比正文大，且看起来像短语
                        is_list_item = False
                        # 这里需要更复杂的逻辑来确定"正文缩进"，暂且略过，仅依靠换行修复
                        
                        full_page_text += "\n\n" + block_text
                
                last_bbox = curr_bbox

            safe_text = full_page_text.encode('utf-8', errors='replace').decode('utf-8')
            
            if format == 'markdown':
                page_header = f"## Page {page_num}\n\n"
            else:
                page_header = f"\n{'='*20} Page {page_num} {'='*20}\n"
            
            page_content = page_header + (safe_text if safe_text.strip() else "(No text content)") + "\n"
            result_content.append(types.TextContent(type="text", text=page_content))
            
            # 2. 提取图片
            image_list = page.get_images()
            if image_list:
                # 延迟创建目录，直到真正发现图片
                if not has_images:
                    os.makedirs(output_dir, exist_ok=True)
                    has_images = True
                    result_content.append(types.TextContent(type="text", text=f"\n[图片将保存至: {output_dir}]\n"))

                img_info = f"\n[Page {page_num} Found {len(image_list)} images]\n"
                result_content.append(types.TextContent(type="text", text=img_info))
                
                for j, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        ext = base_image["ext"]
                        
                        # 保存图片到本地
                        img_filename = f"page_{page_num}_img_{j+1}.{ext}"
                        img_path = os.path.join(output_dir, img_filename)
                        with open(img_path, "wb") as f:
                            f.write(image_bytes)
                        
                        # 转换为base64返回给MCP客户端
                        img_b64 = base64.b64encode(image_bytes).decode('utf-8')
                        
                        # 添加图片内容
                        # 注意：这里我们使用 image/png 作为通用格式，虽然实际上可能是 jpeg 等
                        # MCP 客户端通常能处理 base64 数据
                        result_content.append(types.ImageContent(
                            type="image",
                            data=img_b64,
                            mimeType=f"image/{ext}"
                        ))
                        result_content.append(types.TextContent(type="text", text=f"  - Saved: {img_filename}\n"))

                    except Exception as img_err:
                        result_content.append(types.TextContent(type="text", text=f"  Warning: Failed to extract image {j+1}: {img_err}\n"))

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
                        "description": "页码范围，例如 '1-5', '1,3,5', 'all' (默认为 '1')",
                        "default": "1"
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
        page_range = arguments.get("page_range", "1")
        keyword = arguments.get("keyword")
        format = arguments.get("format", "text")
        return await extract_content(file_path, page_range, keyword, format)
    
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
