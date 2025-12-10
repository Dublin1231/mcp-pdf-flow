
import asyncio
import os
import base64
import re
import difflib
import fitz  # PyMuPDF
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
try:
    from .convert import markdown_to_docx, docx_to_pdf
except ImportError as e:
    # 如果是依赖缺失（如 pypandoc），直接抛出异常，不要尝试 fallback
    if "pypandoc" in str(e) or "docx2pdf" in str(e):
        raise e
    # 仅在找不到 convert 模块本身时尝试 fallback（兼容直接运行脚本的情况）
    try:
        from convert import markdown_to_docx, docx_to_pdf
    except ImportError:
        # 如果 fallback 也失败，抛出原始异常以便调试
        raise e

from collections import Counter

# 初始化服务器
server = Server("simple-pdf-extractor")

# Windows 控制台编码修复
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

def table_to_markdown(table):
    """
    将 PyMuPDF Table 对象转换为 Markdown 字符串。
    """
    try:
        rows = table.extract()
        if not rows: return ""
        
        # 清理单元格内容
        clean_rows = []
        for row in rows:
            # 过滤全空行 (策略：如果整行都是 None 或空字符串，则丢弃)
            is_empty_row = True
            clean_row = []
            for cell in row:
                if cell is None:
                    clean_row.append("")
                else:
                    raw_text = str(cell)
                    # 1. Check if it's a list (preserve newlines as <br>)
                    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                    
                    if not lines:
                        clean_row.append("")
                        continue
                        
                    is_empty_row = False
                    
                    # Heuristic: If multiple lines and looks like a list, use <br>
                    # otherwise use smart_merge_text to reflow text
                    is_list = False
                    if len(lines) > 1:
                        list_item_count = sum(1 for l in lines if is_list_item_start(l))
                        if list_item_count > 0 and (list_item_count / len(lines)) > 0.3:
                            is_list = True
                            
                    if is_list:
                        clean_row.append("<br>".join(lines))
                    else:
                        clean_row.append(smart_merge_text(raw_text))
            
            if not is_empty_row:
                clean_rows.append(clean_row)
        
        if not clean_rows: return ""

        # 0.5. 尝试合并互斥列 (针对错位问题)
        # 逻辑：如果相邻两列的内容在行上是互斥的（即从未在同一行同时出现），则合并它们。
        # 这通常发生在表格线识别错误，导致一列被拆分为两列的情况。
        if clean_rows:
            max_cols = max(len(r) for r in clean_rows)
            # 补齐行长度
            for r in clean_rows:
                while len(r) < max_cols:
                    r.append("")
            
            j = 0
            while j < max_cols - 1:
                is_exclusive = True
                has_content_j = False
                has_content_next = False
                
                for r_idx in range(len(clean_rows)):
                    v1 = clean_rows[r_idx][j]
                    v2 = clean_rows[r_idx][j+1]
                    if v1: has_content_j = True
                    if v2: has_content_next = True
                    
                    if v1 and v2: # 冲突：同一行两列都有值
                        is_exclusive = False
                        break
                
                # 只有当两列都有内容（不是全空列），且互斥时，才合并
                # 如果某一列全空，会在后续步骤被删除，不需要在此合并
                if is_exclusive and has_content_j and has_content_next:
                    # 合并到 j
                    for r_idx in range(len(clean_rows)):
                        if clean_rows[r_idx][j+1]:
                            clean_rows[r_idx][j] = clean_rows[r_idx][j+1]
                    
                    # 删除 j+1
                    for r in clean_rows:
                        r.pop(j+1)
                    max_cols -= 1
                    # 不增加 j，继续检查新的 j (即合并后的列) 和新的 j+1
                else:
                    j += 1

        # 0. 尝试智能合并表头 (针对 "基本\n工资" 被拆分为两行的情况)
        # 移到 clean_rows 和 合并互斥列 之后，以避免误判
        if len(clean_rows) > 1:
            header1 = clean_rows[0]
            header2 = clean_rows[1]
            
            should_merge = False
            has_content_h2 = False
            
            for cell in header2:
                if cell:
                    has_content_h2 = True
                    break
            
            if has_content_h2:
                conflict_count = 0
                merge_candidates = 0
                
                for i in range(min(len(header1), len(header2))):
                    c1 = header1[i]
                    c2 = header2[i]
                    
                    if c1 and c2:
                        # 同一列都有内容
                        if len(c1) > 4 and len(c2) > 4:
                            conflict_count += 1
                        else:
                            merge_candidates += 1
                    elif c2:
                        merge_candidates += 1
                
                is_data_row_2 = False
                if len(clean_rows) > 2:
                     row3 = clean_rows[2]
                     match_type_count = 0
                     check_count = 0
                     for i in range(min(len(header2), len(row3))):
                         v2 = header2[i]
                         v3 = row3[i]
                         if v2 and v3:
                             check_count += 1
                             if (v2.isdigit() and v3.isdigit()) or (v2 in ['true', 'false'] and v3 in ['true', 'false']):
                                 match_type_count += 1
                     
                     if check_count > 0 and (match_type_count / check_count) > 0.5:
                         is_data_row_2 = True
 
                if not is_data_row_2 and conflict_count == 0:
                    should_merge = True

            if should_merge:
                merged_header = []
                max_len = max(len(header1), len(header2))
                for i in range(max_len):
                    c1 = header1[i] if i < len(header1) else ""
                    c2 = header2[i] if i < len(header2) else ""
                    merged_header.append(c1 + c2)
                
                clean_rows[0] = merged_header
                clean_rows.pop(1)

        # 1. Identify empty columns
        num_cols = len(clean_rows[0])
        is_col_empty = [True] * num_cols
        
        for row in clean_rows:
            for c_idx, cell in enumerate(row):
                if c_idx < num_cols and cell and cell.strip():
                    is_col_empty[c_idx] = False
        
        # 2. Filter columns
        final_rows = []
        for row in clean_rows:
            new_row = []
            for c_idx, cell in enumerate(row):
                if c_idx < num_cols and not is_col_empty[c_idx]:
                    new_row.append(cell)
            final_rows.append(new_row)
            
        if not final_rows or not final_rows[0]: return ""

        # 3. 决定是否使用空表头 (针对 KV 表格或类型一致的表格)
        # 如果第一行看起来像数据（与第二行类型一致），则生成空表头，将第一行作为数据展示
        use_empty_header = False
        if len(final_rows) > 1:
            header_row = final_rows[0]
            first_body = final_rows[1]
            
            match_type_count = 0
            check_count = 0
            
            for i in range(min(len(header_row), len(first_body))):
                v1 = header_row[i].strip()
                v2 = first_body[i].strip()
                
                if v1 and v2:
                    check_count += 1
                    # 检查是否都是布尔值
                    if v1 in ['true', 'false'] and v2 in ['true', 'false']:
                        match_type_count += 1
                    # 检查是否都是数字
                    elif v1.replace('.','',1).isdigit() and v2.replace('.','',1).isdigit():
                        match_type_count += 1
                    # 检查是否都是中文开头 (移除，避免误判)
                    # elif v1 and v2 and is_cjk(v1[0]) and is_cjk(v2[0]):
                    #    match_type_count += 1
            
            # 如果超过 50% 的非空列类型一致，或者完全是 KV 结构（通常 2-3 列，且包含 param/value）
            if check_count > 0 and (match_type_count / check_count) > 0.5:
                use_empty_header = True
            
            # 特殊检查：如果 Header 包含 "true/false" 这种值，绝对不是 Header
            for cell in header_row:
                if cell.strip() in ['true', 'false']:
                    use_empty_header = True
                    break

        md = "\n"
        num_cols = len(final_rows[0])
        
        if use_empty_header:
            # 生成空表头
            md += "| " + " | ".join([" "] * num_cols) + " |\n"
            md += "| " + " | ".join(["---"] * num_cols) + " |\n"
            # 所有行都作为 Body
            rows_to_process = final_rows
        else:
            # 标准表头
            md += "| " + " | ".join(final_rows[0]) + " |\n"
            md += "| " + " | ".join(["---"] * num_cols) + " |\n"
            rows_to_process = final_rows[1:]
        
        # 表体
        for row in rows_to_process:
            # 如果需要，填充行
            if len(row) < num_cols:
                row += [""] * (num_cols - len(row))
            md += "| " + " | ".join(row[:num_cols]) + " |\n"
        md += "\n"
        return md
    except Exception:
        return ""

def is_valid_table(table):
    """
    判断表格是否有效。
    用于过滤误判的文本块（例如只有一列有内容，或空列占比极高的伪表格）。
    """
    try:
        data = table.extract()
        if not data:
            return False
        
        num_rows = len(data)
        
        # 策略5: 丢弃单行表格
        # 单行表格在 Markdown 中会被渲染为仅有表头的表格，通常不适合展示数据
        # 且常用于误判的 Key-Value 布局或标题栏
        if num_rows < 2:
            return False

        num_cols = len(data[0])
        
        # 统计每一列的字符总量
        col_char_counts = [0] * num_cols
        total_chars = 0
        
        for row in data:
            for c_idx, cell in enumerate(row):
                if cell:
                    text_len = len(str(cell).strip())
                    col_char_counts[c_idx] += text_len
                    total_chars += text_len
                    
        # 策略1: 丢弃单列表格 (通常是普通文本)
        # 只要字符占比 > 10% 就算有效列
        valid_cols = 0
        for count in col_char_counts:
            if total_chars > 0 and (count / total_chars) > 0.1:
                valid_cols += 1
            elif total_chars == 0 and count > 0:
                 valid_cols += 1
                 
        if valid_cols < 2:
            return False

        # 策略2: 丢弃空列占比过高的表格
        # 如果某一列几乎没有字符 (< 5)，视为无效空列
        empty_cols = 0
        for count in col_char_counts:
            if count < 5:
                empty_cols += 1
        
        if num_cols > 0 and (empty_cols / num_cols) >= 0.5:
            return False
            
        # 策略3: 对于少行数的表格 (rows < 3)，如果有极高稀疏度，通常是误判的文本行
        # 计算稀疏度
        total_cells = num_rows * num_cols
        empty_cells = 0
        for row in data:
            for cell in row:
                 if not cell or not str(cell).strip():
                     empty_cells += 1
        
        if num_rows < 3 and total_cells > 0 and (empty_cells / total_cells) > 0.6:
            return False

        # 策略12: 过滤过度切分的稀疏表格 (Over-segmented Sparse Table)
        # 特征: 列数过多 (>8)，且稀疏度低 (<30%)，且每行有效单元格少
        # 这种情况通常是 PyMuPDF 将对齐的文本误判为多列表格，导致大量空列和碎片
        non_empty_cells = total_cells - empty_cells
        saturation = non_empty_cells / total_cells if total_cells > 0 else 0
        
        if num_cols > 8 and saturation < 0.3:
            # 计算每行平均有效单元格数
            avg_cells_per_row = non_empty_cells / num_rows if num_rows > 0 else 0
            if avg_cells_per_row < 4:
                return False

        # 策略4: 过滤代码块误判为表格的情况
        # 特征: 包含一列连续的数字(行号)，且内容包含代码关键字或符号
        has_line_numbers = False
        has_code_indicators = False
        
        # 检查是否存在行号列
        for c_idx in range(num_cols):
            col_values = []
            for row in data:
                cell_text = str(row[c_idx]).strip() if row[c_idx] else ""
                if cell_text:
                    # 处理可能存在的换行符，只取第一部分，处理 "1\n2" 这种粘连情况
                    parts = cell_text.replace('\n', ' ').split()
                    for p in parts:
                        if p.isdigit():
                            col_values.append(int(p))
            
            # 如果这一列包含了至少3个数字
            if len(col_values) >= 3:
                # 检查是否大致连续
                sorted_vals = sorted(list(set(col_values)))
                if len(sorted_vals) > 1:
                    consecutive_count = 0
                    for i in range(len(sorted_vals)-1):
                        if sorted_vals[i+1] == sorted_vals[i] + 1:
                            consecutive_count += 1
                    
                    # 如果70%以上是连续的，视为行号列
                    if len(sorted_vals) > 0 and (consecutive_count / len(sorted_vals)) > 0.7:
                        has_line_numbers = True
                        break
        
        # 检查是否存在代码特征
        # 增强代码特征库，包含 HTML/XML 标签
        code_chars = {'{', '}', ';', '(', ')', '[', ']', '->', '//', '/*', '<', '>', '/>', 'class=', 'type=', '</'}
        code_keywords = {
            'public', 'class', 'void', 'int', 'String', 'return', 'import', 'package', 
            'if', 'else', 'for', 'while', 'try', 'catch', 'synchronized', 'extends', 'implements',
            'div', 'span', 'li', 'input', 'html', 'body', 'dependency', 'groupId', 'artifactId', 'version'
        }
        
        found_code_indicators = 0
        total_text_cells = 0
        
        for row in data:
            for cell in row:
                if cell:
                    text = str(cell).strip()
                    if not text: continue
                    total_text_cells += 1
                    
                    # 检查关键字
                    words = set(text.replace('(', ' ').replace(')', ' ').replace('{', ' ').replace('<', ' ').replace('>', ' ').split())
                    if words & code_keywords:
                        found_code_indicators += 1
                        continue
                        
                    # 检查符号
                    for char in code_chars:
                        if char in text:
                            found_code_indicators += 1
                            break
        
        indicator_ratio = (found_code_indicators / total_text_cells) if total_text_cells > 0 else 0

        # 如果包含代码特征的单元格占比超过 20%
        if total_text_cells > 0 and indicator_ratio > 0.2:
            has_code_indicators = True
        
        # 情况A: 有行号且有代码特征 -> 肯定是代码块
        if has_line_numbers and has_code_indicators:
            return False

        # 策略6: 纯代码块/HTML 误判 (无行号但特征极高)
        # 如果超过 50% 的单元格包含代码特征，视为无效表格
        if total_text_cells > 0 and indicator_ratio > 0.5:
            return False

        # 策略7: 长文本/段落误判
        # 如果表格行数较少，且单元格内容多为长文本（>50字符），通常是文本段落
        long_cell_count = 0
        total_cells_check = 0
        for row in data:
            for cell in row:
                if cell and str(cell).strip():
                    total_cells_check += 1
                    if len(str(cell).strip()) > 30:
                        long_cell_count += 1
        
        if total_cells_check > 0 and (long_cell_count / total_cells_check) > 0.5:
            if num_rows < 10 and num_cols < 4:
                 return False

        # 策略8: 错位布局误判 (文本换行被解析为多列)
        # 检查连续行的有效列是否"互斥"（即上一行在A列，下一行在B列，且无重叠）
        # 这种情况常见于普通文本被误判为多列表格
        if num_rows > 1 and num_cols > 1:
            row_active_cols = []
            for row in data:
                active_cols = {i for i, cell in enumerate(row) if cell and str(cell).strip()}
                if active_cols:
                    row_active_cols.append(active_cols)
            
            if len(row_active_cols) > 1:
                disjoint_count = 0
                for i in range(len(row_active_cols) - 1):
                    if row_active_cols[i].isdisjoint(row_active_cols[i+1]):
                        disjoint_count += 1
                
                # 如果超过 50% 的行转换是互斥的，且表格行数不多
                if (disjoint_count / (len(row_active_cols) - 1)) >= 0.5 and num_rows < 10:
                     return False

        # 策略9: 过滤文本列表误判为表格的情况 (针对冒泡排序案例)
        # 特征: 
        # 1. 某一列(通常是第一列)包含高比例的列表项标记 (1., 2., •)
        # 2. 且该列内容极短(通常只有序号)
        # 3. 且表格行数较多时，其他列的文本长度分布极不均匀
        
        list_marker_col_idx = -1
        for c_idx in range(num_cols):
            list_markers = 0
            short_content_count = 0
            
            for row in data:
                cell_text = str(row[c_idx]).strip() if row[c_idx] else ""
                if is_list_item_start(cell_text):
                    list_markers += 1
                if len(cell_text) < 5: # 序号通常很短
                    short_content_count += 1
            
            # 如果这一列超过 60% 是列表标记，且 80% 内容很短
            if num_rows > 0 and (list_markers / num_rows) > 0.6 and (short_content_count / num_rows) > 0.8:
                list_marker_col_idx = c_idx
                break
        
        # 如果找到了明确的列表标记列，且表格列数很少 (<= 3)，通常是文本列表
        if list_marker_col_idx != -1 and num_cols <= 3:
             # 进一步确认：如果是列表，通常其右侧内容会很长
             return False

        # 策略10: 过滤长文本段落误判
        # 特征: 只有2列，且某一行包含极长的文本(>100 chars)，且看起来是被拆分的
        if num_cols == 2:
            long_split_row_count = 0
            for row in data:
                c1 = str(row[0]).strip() if row[0] else ""
                c2 = str(row[1]).strip() if row[1] else ""
                
                # 如果两列都有内容，且加起来很长，且看起来像一句话被切断（难以程序化判断切断，主要靠长度）
                if len(c1) > 30 and len(c2) > 30:
                    long_split_row_count += 1
            
            # 如果存在这种行，且表格总行数很少
            if long_split_row_count > 0 and num_rows < 5:
                return False

        # 策略11: 过滤长文本列表误判 (针对冒泡排序案例 - 变种)
        # 特征: 
        # 1. 有一列主要是列表项 (1. xxx, 2. xxx)
        # 2. 该列文本较长 (不是短序号)
        # 3. 其他列大部分为空
        
        list_content_col_idx = -1
        for c_idx in range(num_cols):
            list_markers_count = 0
            long_content_count = 0
            empty_other_cols_count = 0
            
            for r_idx, row in enumerate(data):
                cell_text = str(row[c_idx]).strip() if row[c_idx] else ""
                
                # 检查是否以列表标记开头 (1., 2., (1), etc.)
                if is_list_item_start(cell_text):
                    list_markers_count += 1
                
                # 检查内容长度 (长文本)
                if len(cell_text) > 15:
                    long_content_count += 1
                
                # 检查该行其他列是否为空
                is_other_empty = True
                for other_c_idx in range(num_cols):
                    if other_c_idx != c_idx:
                        other_text = str(row[other_c_idx]).strip() if row[other_c_idx] else ""
                        if other_text:
                            is_other_empty = False
                            break
                if is_other_empty:
                    empty_other_cols_count += 1
            
            # 判定条件:
            # 1. 至少 40% 的行以列表标记开头 (宽松一点，因为可能有换行被切断)
            # 2. 至少 40% 的行内容较长 (排除纯序号列)
            # 3. 至少 60% 的行其他列为空 (说明主要是这一列在承载内容)
            if num_rows > 0:
                ratio_list = list_markers_count / num_rows
                ratio_long = long_content_count / num_rows
                ratio_empty_others = empty_other_cols_count / num_rows
                
                if ratio_list > 0.4 and ratio_long > 0.4 and ratio_empty_others > 0.6:
                    return False

        return True
    except Exception:
        return False

def is_block_in_table(block_bbox, tables):
    """
    检查文本块是否位于检测到的表格内。
    """
    b_rect = fitz.Rect(block_bbox)
    for table in tables:
        t_rect = fitz.Rect(table.bbox)
        # 检查相交
        intersect = b_rect & t_rect
        # 如果相交面积超过文本块的 60%，则认为它是表格的一部分
        if intersect.get_area() > (b_rect.get_area() * 0.6):
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

def estimate_body_right_margin(blocks, page_width):
    """
    估计正文的右边界 (x1)。
    通过统计所有文本块的 x1 坐标，找到最靠右的密集区域。
    """
    x1s = []
    for b in blocks:
        if b["type"] == 0:
            # 忽略太短的块（可能是页码或标题）
            text_len = sum(len(span["text"]) for line in b["lines"] for span in line["spans"])
            if text_len > 10: 
                x1s.append(b["bbox"][2])
    
    if not x1s:
        # 如果没有足够的数据，回退到页面宽度的 85%
        return page_width * 0.85
        
    # 找到最大的 x1 (排除可能的页码或极端异常值，取 90% 分位点或者直接取最大值如果方差不大)
    # 简单起见，我们取最大的几个值的平均，排除最极端的
    x1s.sort(reverse=True)
    # 取前 20% 的平均值，代表正文右边界
    top_n = max(1, len(x1s) // 5)
    avg_max_x1 = sum(x1s[:top_n]) / top_n
    
    return avg_max_x1

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

import json
import glob

async def extract_content(file_path: str, page_range: str = "1", keyword: str = None, format: str = "text", include_text: bool = True, include_images: bool = False, use_local_images_only: bool = True, image_output_dir: str = None, image_link_base: str = None, skip_table_detection: bool = False):
    """
    提取PDF指定页面的文本和图片。
    :param file_path: PDF文件路径
    :param page_range: 页码范围，例如 "1-5", "1,3,5" (从1开始)，或 "all" 提取所有页面
    :param keyword: 关键词，如果提供，则仅提取包含该关键词的页面（忽略 page_range）
    :param format: 输出格式，'text' (默认), 'markdown' 或 'json'
    :param use_local_images_only: 如果为True，图片仅保存到本地并在文本中引用路径，不返回Base64数据（避免上下文溢出）
    :param image_output_dir: (可选) 图片保存的根目录，默认为当前目录下的 extracted_images
    :param image_link_base: (可选) Markdown中引用图片的基础路径，默认为 extracted_images
    :param skip_table_detection: (可选) 是否跳过表格检测（纯文本极速模式）
    :return: 包含文本和图片的列表
    """
    if not os.path.exists(file_path):
        return [types.TextContent(type="text", text=f"Error: 文件不存在 - {file_path}")]

    result_content = []
    
    # 存储 JSON 格式的结构化数据
    json_data = {
        "file_path": file_path,
        "meta": {
            "page_range": page_range,
            "format": format,
            "include_text": include_text,
            "include_images": include_images,
            "use_local_images_only": use_local_images_only,
            "note": "To get Base64 image data, set 'use_local_images_only' to false." if use_local_images_only and include_images else "Base64 image data included."
        },
        "pages": []
    }
    
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        
        pages_to_extract = []
        
        # 1. 如果指定了关键词，优先按关键词搜索
        if keyword and keyword.strip():
            if format != 'json':
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

        if format != 'json':
            # 根据模式显示不同的元数据信息
            mode_text = "极速纯文本 (Fast Mode)" if skip_table_detection else "标准模式 (Normal Mode)"
            summary_text = f"正在处理文件: {file_path}\n页码范围: {page_range} (共 {len(pages_to_extract)} 页)\n处理模式: {mode_text}\n内容类型: {'文本' if include_text else ''}{'/' if include_text and include_images else ''}{'图片' if include_images else ''}\n"
            result_content.append(types.TextContent(type="text", text=summary_text))

        # 准备图片输出目录
        pdf_filename = os.path.basename(file_path)
        pdf_name_no_ext = os.path.splitext(pdf_filename)[0]
        
        if image_output_dir:
            output_dir = os.path.join(image_output_dir, pdf_name_no_ext)
        else:
            cwd = os.getcwd()
            output_dir = os.path.join(cwd, "extracted_images", pdf_name_no_ext)
        
        # 如果需要提取图片，先创建目录
        has_images = False
        if include_images:
            os.makedirs(output_dir, exist_ok=True)

        for i in pages_to_extract:
            page_num = i + 1
            page = doc[i]
            
            page_data = {
                "page": page_num,
                "text": "",
                "images": []
            }
            
            # 存储当前页的图片路径，用于插入到 Markdown
            page_image_paths = []
            image_content_objects = []

            # 1. 先处理图片（保存并获取路径）
            if include_images:
                image_list = page.get_images()
                if image_list:
                    if not has_images:
                        has_images = True
                        if format != 'json':
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
                            
                            # 计算相对引用路径
                            if image_link_base:
                                rel_path = f"{image_link_base}/{pdf_name_no_ext}/{img_filename}"
                            else:
                                rel_path = f"extracted_images/{pdf_name_no_ext}/{img_filename}"
                            
                            # 记录 JSON 数据
                            img_info = {
                                "filename": img_filename,
                                "local_path": img_path,
                                "rel_path": rel_path
                            }
                            
                            # 如果需要返回 Base64
                            if not use_local_images_only:
                                img_b64 = base64.b64encode(image_bytes).decode('utf-8')
                                img_info["base64"] = img_b64
                                img_info["mime_type"] = f"image/{ext}"
                                
                                if format != 'json':
                                    image_content_objects.append(types.ImageContent(
                                        type="image",
                                        data=img_b64,
                                        mimeType=f"image/{ext}"
                                    ))
                                    result_content.append(types.TextContent(type="text", text=f"  - Saved: {img_filename}\n"))
                            
                            page_data["images"].append(img_info)
                            
                        except Exception as img_err:
                            if format != 'json':
                                result_content.append(types.TextContent(type="text", text=f"  Warning: Failed to extract image {j+1}: {img_err}\n"))

            # 2. 提取文本
            if include_text:
                # 2.1 检测表格
                tables = []
                try:
                    if not skip_table_detection:
                        raw_tables = page.find_tables()
                        for t in raw_tables:
                            if is_valid_table(t):
                                tables.append(t)
                except Exception:
                    pass

                blocks = page.get_text("dict", sort=True)["blocks"]
                body_size = estimate_body_size(blocks)
                
                # 计算正文右边界
                body_right_margin = estimate_body_right_margin(blocks, page.rect.width)
                
                # 2.2 处理文本块（过滤和预处理）
                processed_paragraphs = [] # 列表元素：{y0, text}
                current_para_text = ""
                current_para_y0 = 0
                last_bbox = None
                
                # 刷新当前段落的辅助函数
                def flush_para():
                    nonlocal current_para_text, current_para_y0
                    if current_para_text:
                        processed_paragraphs.append({"y0": current_para_y0, "type": "text", "content": current_para_text})
                        current_para_text = ""

                for b in blocks:
                    if b["type"] != 0:
                        continue
                    
                    # 如果在表格中则跳过
                    if is_block_in_table(b["bbox"], tables):
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
                        flush_para()
                        processed_paragraphs.append({
                            "y0": curr_bbox[1], 
                            "type": "text", 
                            "content": f"\n\n{prefix}{block_text}\n\n"
                        })
                        last_bbox = curr_bbox
                        continue

                    should_merge = False
                    if current_para_text:
                        if last_bbox:
                            v_dist = curr_bbox[1] - last_bbox[3]
                            if v_dist < 15.0:
                                if not is_sentence_end(current_para_text.strip()[-1]):
                                    should_merge = True
                                last_x0 = last_bbox[0]
                                if abs(curr_x0 - last_x0) > 5.0:
                                    should_merge = False
                                last_x1 = last_bbox[2]
                                # 使用计算出的正文右边界，允许一定的误差 (e.g. 5 points)
                                if last_x1 < (body_right_margin - 5):
                                    should_merge = False
                                if is_list_item_start(block_text):
                                    should_merge = False
                        if should_merge:
                            if is_cjk(current_para_text[-1]) and is_cjk(block_text[0]):
                                current_para_text += block_text
                            else:
                                current_para_text += " " + block_text
                            last_bbox = curr_bbox
                        else:
                            flush_para()
                            current_para_text = block_text
                            current_para_y0 = curr_bbox[1]
                            last_bbox = curr_bbox
                    else:
                        current_para_text = block_text
                        current_para_y0 = curr_bbox[1]
                        last_bbox = curr_bbox
                
                flush_para()

                # 2.3 集成表格
                final_items = processed_paragraphs
                for table in tables:
                    md_table = table_to_markdown(table)
                    if md_table:
                        final_items.append({
                            "y0": table.bbox[1],
                            "type": "table",
                            "content": md_table
                        })
                
                # 2.4 排序和拼接
                final_items.sort(key=lambda x: x["y0"])
                
                full_page_text = ""
                for item in final_items:
                    content = item["content"]
                    if item["type"] == "text":
                        if full_page_text and not full_page_text.endswith("\n\n") and not content.startswith("\n\n"):
                             full_page_text += "\n\n"
                        full_page_text += content
                    else:
                        # 表格
                        full_page_text += "\n\n" + content + "\n\n"

                safe_text = full_page_text.encode('utf-8', errors='replace').decode('utf-8')
                
                # 记录纯文本到 JSON
                page_data["text"] = safe_text
                
                # 在文本末尾追加图片引用 (Markdown 模式)
                if format == 'markdown' and page_image_paths:
                    safe_text += "\n\n"
                    for img_file in page_image_paths:
                        # 引用路径
                        if image_link_base:
                            rel_path = f"{image_link_base}/{pdf_name_no_ext}/{img_file}"
                        else:
                            rel_path = f"extracted_images/{pdf_name_no_ext}/{img_file}"
                        
                        # 转义空格
                        rel_path = rel_path.replace(" ", "%20")
                        safe_text += f"![Image]({rel_path})\n"

                if format == 'markdown':
                    if skip_table_detection:
                        page_header = f"## 第 {page_num} 页\n\n"
                    else:
                        page_header = f"## Page {page_num}\n\n"
                elif format == 'text':
                    if skip_table_detection:
                        page_header = f"\n--- 第 {page_num} 页 ---\n"
                    else:
                        page_header = f"\n{'='*20} Page {page_num} {'='*20}\n"
                else:
                    page_header = ""
                
                if format != 'json':
                    page_content = page_header + (safe_text if safe_text.strip() else "(No text content)") + "\n"
                    result_content.append(types.TextContent(type="text", text=page_content))
            
            # 添加到 JSON 结果列表
            json_data["pages"].append(page_data)
            
            # 3. 添加图片对象 (如果启用 Base64 返回 且非 JSON 模式)
            if format != 'json' and not use_local_images_only and image_content_objects:
                result_content.extend(image_content_objects)

        doc.close()
        
        # 如果是 JSON 格式，返回整个 JSON 字符串
        if format == 'json':
            return [types.TextContent(type="text", text=json.dumps(json_data, ensure_ascii=False, indent=2))]
        
    except Exception as e:
        result_content.append(types.TextContent(type="text", text=f"Error processing PDF: {str(e)}"))

    return result_content

import concurrent.futures
import functools

def _process_single_pdf_tables(args):
    """
    批量提取表格的工作函数。
    args: (pdf_path, output_dir)
    """
    pdf_path, output_dir = args
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            
        pdf_name = os.path.basename(pdf_path)
        pdf_name_no_ext = os.path.splitext(pdf_name)[0]
        output_file_path = os.path.join(output_dir, f"{pdf_name_no_ext}_tables.md")
        
        doc = fitz.open(pdf_path)
        tables_found_count = 0
        md_content = f"# Tables Extracted from: {pdf_name}\n\n"
        has_content = False
        
        for i in range(len(doc)):
            page = doc[i]
            try:
                raw_tables = page.find_tables()
                valid_tables = []
                for t in raw_tables:
                    if is_valid_table(t):
                        valid_tables.append(t)
                
                if valid_tables:
                    page_has_table = False
                    page_content = ""
                    for idx, tab in enumerate(valid_tables):
                        md = table_to_markdown(tab)
                        if md:
                            page_has_table = True
                            tables_found_count += 1
                            page_content += f"## Page {i+1} - Table {idx+1}\n\n"
                            page_content += md + "\n\n"
                    
                    if page_has_table:
                        has_content = True
                        md_content += page_content
            except Exception:
                continue
                
        doc.close()
        
        if has_content:
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            return (True, pdf_name, output_file_path, tables_found_count)
        else:
            return (True, pdf_name, None, 0)
            
    except Exception as e:
        return (False, os.path.basename(pdf_path), None, str(e))

def get_output_paths_for_mode(root_dir, include_images, include_text, skip_table_detection):
    """
    根据模式计算输出目录路径
    Returns: (mode_dir, image_output_dir)
    """
    base_output = os.path.join(root_dir, "output")
    
    if include_images and not include_text:
        mode_dir_name = "output_only_image"
    elif include_images:
        if skip_table_detection:
            mode_dir_name = "output_fast_with_image_no_table"
        else:
            mode_dir_name = "output_standard_with_image"
    elif skip_table_detection:
        mode_dir_name = "output_fast_no_image_and_table"
    else:
        mode_dir_name = "output_standard_no_image"
        
    mode_dir = os.path.join(base_output, mode_dir_name)
    image_output_dir = os.path.join(mode_dir, "extracted_images")
    
    return mode_dir, image_output_dir

def _process_single_pdf_worker(args):
    """
    用于批量处理的工作函数。
    必须是顶层函数以便于 pickling。
    """
    pdf_path, format, include_text, include_images, use_local_images_only, custom_output_dir, custom_image_output_dir, skip_table_detection, create_folder, root_output_dir = args
    
    try:
        pdf_name = os.path.basename(pdf_path)
        # 确定源信息
        pdf_dir = os.path.dirname(pdf_path)
        pdf_name_no_ext = os.path.splitext(pdf_name)[0]
        
        output_ext = "json" if format == "json" else "md" if format == "markdown" else "txt"
        
        # 1. 确定输出路径
        if custom_output_dir:
            os.makedirs(custom_output_dir, exist_ok=True)
            final_output_dir = custom_output_dir
        else:
            final_output_dir = pdf_dir
        
        # 如果需要为每个 PDF 创建专属文件夹
        if create_folder:
            final_output_dir = os.path.join(final_output_dir, pdf_name_no_ext)
            os.makedirs(final_output_dir, exist_ok=True)
            
        output_file_path = os.path.join(final_output_dir, f"{pdf_name_no_ext}.{output_ext}")
        
        # 2. 确定图片输出路径
        image_link_base = "extracted_images"
        image_output_dir = None
        
        if custom_image_output_dir:
            try:
                os.makedirs(custom_image_output_dir, exist_ok=True)
                # 使用子目录避免冲突
                image_output_dir = os.path.join(custom_image_output_dir, pdf_name_no_ext)
                
                # 计算相对路径
                rel_path = os.path.relpath(image_output_dir, final_output_dir)
                image_link_base = rel_path.replace("\\", "/")
            except Exception:
                # 如果 relpath 失败（例如跨驱动器），则回退到绝对路径或默认行为
                pass
        else:
            # 如果创建了专属文件夹，图片最好也放在里面
            if create_folder:
                image_output_dir = os.path.join(final_output_dir, "images")
                image_link_base = "images"
            else:
                 # 默认行为: 将图片放在输出根目录下的 extracted_images 文件夹中
                 # 这样可以保持 output 目录的整洁，并且支持 relative path
                 if root_output_dir:
                     try:
                         image_output_dir = os.path.join(root_output_dir, "extracted_images")
                         # 注意: extract_content 会自动在 image_output_dir 后追加 pdf_name_no_ext
                         # 所以这里我们只需要指向 extracted_images 根
                         
                         # 计算 image_link_base (相对路径)
                         # image_link_base 应该是从 markdown 文件所在目录 (final_output_dir) 到 extracted_images 根目录的相对路径
                         rel_path = os.path.relpath(image_output_dir, final_output_dir)
                         image_link_base = rel_path.replace("\\", "/")
                     except Exception:
                         pass
            
        # 运行提取（异步函数的同步包装）
        # 为此进程创建一个新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        content_list = loop.run_until_complete(extract_content(
            file_path=pdf_path,
            page_range="all",
            format=format,
            include_text=include_text,
            include_images=include_images,
            use_local_images_only=use_local_images_only,
            image_output_dir=image_output_dir,
            image_link_base=image_link_base,
            skip_table_detection=skip_table_detection
        ))
        loop.close()
        
        # 将结果写入文件
        # 如果是"仅提取图片"模式 (include_text=False, include_images=True)，则不写入 Markdown 文件
        if include_text or (not include_images):
            full_text = ""
            for item in content_list:
                if item.type == "text":
                    full_text += item.text
                    
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(full_text)
            
        return (True, pdf_name, output_file_path, None)
        
    except Exception as e:
        return (False, os.path.basename(pdf_path), None, str(e))

async def batch_extract_pdf_content(
    directory: str,
    pattern: str = "**/*.pdf",
    format: str = "markdown",
    include_text: bool = True,
    include_images: bool = False,
    use_local_images_only: bool = True,
    custom_output_dir: str = None,
    skip_table_detection: bool = False,
    create_folder: bool = False,
    preserve_structure: bool = True
):
    """
    批量处理指定目录下的PDF文件 (并行加速版)。
    如果 custom_output_dir 为 None，默认输出到当前工作目录下的 'output' 文件夹。
    create_folder: 如果为 True，将为每个 PDF 文件创建一个同名的子文件夹。
    preserve_structure: 如果为 True (默认)，保持源文件的目录层级结构。如果为 False，所有文件将平铺到输出目录（可能存在同名覆盖风险）。
    """
    if not os.path.isdir(directory):
        return [types.TextContent(type="text", text=f"Error: 目录不存在 - {directory}")]
    
    # 确定输出根目录和模式目录
    root_output_base = custom_output_dir if custom_output_dir else os.getcwd()
    target_mode_dir, _ = get_output_paths_for_mode(root_output_base, include_images, include_text, skip_table_detection)
    
    # 使用计算出的目录
    custom_output_dir = target_mode_dir
        
    # 确保输出目录存在
    if custom_output_dir:
         os.makedirs(custom_output_dir, exist_ok=True)
 
     
    # 支持递归搜索
    search_path = os.path.join(directory, pattern)
    files = glob.glob(search_path, recursive=True)
    
    if not files:
        return [types.TextContent(type="text", text=f"未找到匹配的文件: {search_path}")]

    file_count = len(files)
    summary = [f"=== 批量处理报告 (并行) ===\n"]
    
    # 使用 CPU 计数，但限制在合理范围内以避免如果有很多文件导致 IO 抖动
    max_workers = min(32, os.cpu_count() or 4)
    summary.append(f"找到 {file_count} 个文件。正在使用 {max_workers} 个工作进程处理...\n")
    
    # 为每个任务准备参数
    tasks_args = []
    for pdf_path in files:
        if os.path.isfile(pdf_path):
            target_output_dir = custom_output_dir
            
            if preserve_structure:
                # Calculate output directory preserving structure
                try:
                    # relative path from source directory to the file's directory
                    rel_path = os.path.relpath(os.path.dirname(pdf_path), directory)
                except ValueError:
                    # Fallback if on different drive or other issue
                    rel_path = ""
                
                # Combine with custom output dir
                target_output_dir = os.path.join(custom_output_dir, rel_path)
            
            tasks_args.append((
                pdf_path, format, include_text, include_images, 
                use_local_images_only, target_output_dir, None,
                skip_table_detection, create_folder, custom_output_dir
            ))
    
    success_count = 0
    fail_count = 0
    
    # 使用 ProcessPoolExecutor 执行 CPU 密集型任务
    loop = asyncio.get_running_loop()
    
    # 我们在一个线程中运行阻塞的 executor map，以避免阻塞 asyncio 循环
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = await loop.run_in_executor(
            None, 
            functools.partial(list, executor.map(_process_single_pdf_worker, tasks_args))
        )
        
    for success, name, out_path, error in results:
        if success:
            success_count += 1
            summary.append(f"[OK] {name}")
        else:
            fail_count += 1
            summary.append(f"[FAIL] {name}: {error}")
            
    summary.append(f"\nTotal: {file_count}, Success: {success_count}, Failed: {fail_count}")
    return [types.TextContent(type="text", text="\n".join(summary))]


async def batch_extract_tables(
    directory: str,
    output_dir: str = None,
    pattern: str = "**/*.pdf"
) -> list[types.TextContent]:
    """
    批量提取指定目录下的PDF表格并保存为Markdown文件。
    """
    if not os.path.isdir(directory):
        return [types.TextContent(type="text", text=f"Error: 目录不存在 - {directory}")]
        
    # 确定输出目录
    # 确定输出根目录
    root_output_base = output_dir if output_dir else os.getcwd()
    # 构建完整路径: root/output/output_only_table
    output_dir = os.path.join(root_output_base, "output", "output_only_table")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 搜索文件
    search_path = os.path.join(directory, pattern)
    files = glob.glob(search_path, recursive=True)
    
    if not files:
        return [types.TextContent(type="text", text=f"未找到匹配的文件: {search_path}")]
        
    file_count = len(files)
    summary = [f"=== 批量表格提取报告 ===\n"]
    summary.append(f"Source Directory: {directory}")
    summary.append(f"Output Directory: {output_dir}")
    summary.append(f"Found {file_count} PDF files.\n")
    
    # 准备任务参数
    tasks_args = []
    for pdf_path in files:
        tasks_args.append((pdf_path, output_dir))
        
    max_workers = min(32, os.cpu_count() or 4)
    success_count = 0
    fail_count = 0
    total_tables = 0
    files_with_tables = 0
    
    loop = asyncio.get_running_loop()
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = await loop.run_in_executor(
            None,
            functools.partial(list, executor.map(_process_single_pdf_tables, tasks_args))
        )
        
    for success, name, out_path, result_info in results:
        if success:
            success_count += 1
            table_count = result_info
            if table_count > 0:
                files_with_tables += 1
                total_tables += table_count
                summary.append(f"[OK] {name}: Found {table_count} tables -> {os.path.basename(out_path)}")
            else:
                summary.append(f"[OK] {name}: No tables found")
        else:
            fail_count += 1
            error_msg = result_info
            summary.append(f"[FAIL] {name}: {error_msg}")
            
    summary.append(f"\nProcessing Summary:")
    summary.append(f"- Total Files: {file_count}")
    summary.append(f"- Successful: {success_count}")
    summary.append(f"- Failed: {fail_count}")
    summary.append(f"- Files with Tables: {files_with_tables}")
    summary.append(f"- Total Tables Extracted: {total_tables}")
    
    return [types.TextContent(type="text", text="\n".join(summary))]


async def search_pdf_files(
    query: str,
    directory: str = None,
    threshold: float = 0.45,
    limit: int = 10
):
    """
    模糊搜索 PDF 文件位置。
    如果未指定 directory，默认搜索当前目录。
    可以通过环境变量 PDF_SEARCH_PATHS 配置额外的搜索路径 (使用系统路径分隔符分隔)。
    """
    search_dirs = []
    
    if directory:
        if not os.path.exists(directory):
            return [types.TextContent(type="text", text=f"Error: 目录不存在 - {directory}")]
        search_dirs.append(directory)
    else:
        # 默认搜索路径
        cwd = os.getcwd()
        search_dirs.append(cwd)
        
        # 从环境变量获取额外搜索路径
        env_paths = os.environ.get("PDF_SEARCH_PATHS")
        if env_paths:
            # 使用 os.pathsep (Windows是;, Unix是:) 分割
            for p in env_paths.split(os.pathsep):
                p = p.strip()
                if p and os.path.exists(p) and p != cwd:
                    search_dirs.append(p)
    
    matches = []
    scanned_files_count = 0
    
    for search_root in search_dirs:
        # 获取所有 PDF 文件
        # 使用 glob.glob 可能会受限于路径长度或权限，但在 Python 3.10+ 通常表现良好
        # 显式使用 recursive=True
        try:
            search_pattern = os.path.join(search_root, "**", "*.pdf")
            files = glob.glob(search_pattern, recursive=True)
            scanned_files_count += len(files)
            
            query_lower = query.lower()
            
            for file_path in files:
                filename = os.path.basename(file_path)
                filename_lower = filename.lower()
                
                # 1. 精确包含 (优先级最高)
                if query_lower in filename_lower:
                    # 包含匹配给高分，越短的完全匹配分数越高
                    score = 0.8 + (len(query_lower) / len(filename_lower)) * 0.2
                    matches.append((score, file_path))
                    continue
                    
                # 2. 模糊匹配
                ratio = difflib.SequenceMatcher(None, query_lower, filename_lower).ratio()
                if ratio >= threshold:
                    matches.append((ratio, file_path))
                    
        except Exception as e:
            # 忽略权限错误等
            continue
    
    # 去重 (同一文件可能被多次扫描)
    unique_matches = {}
    for score, path in matches:
        if path not in unique_matches or score > unique_matches[path]:
            unique_matches[path] = score
    
    final_matches = [(score, path) for path, score in unique_matches.items()]
    
    # 排序并截取
    final_matches.sort(key=lambda x: x[0], reverse=True)
    top_matches = final_matches[:limit]
    
    if not top_matches:
        search_locations = ", ".join(search_dirs)
        return [types.TextContent(type="text", text=f"未找到匹配 '{query}' 的 PDF 文件\n已搜索路径: {search_locations}\n扫描文件数: {scanned_files_count}")]
        
    result_text = f"=== 搜索结果 (Top {len(top_matches)}) ===\n"
    result_text += f"查询: '{query}' | 扫描文件数: {scanned_files_count}\n"
    
    for score, path in top_matches:
        match_type = "Exact/Sub" if score >= 0.8 else f"Fuzzy({score:.2f})"
        result_text += f"- [{match_type}] {os.path.basename(path)}\n"
        result_text += f"  Path: {path}\n"
        
    return [types.TextContent(type="text", text=result_text)]

async def generate_index_file(directory: str):
    """
    扫描指定目录下的 Markdown 文件，生成 README_INDEX.md 索引文件。
    """
    if not os.path.isdir(directory):
        return [types.TextContent(type="text", text=f"Error: 目录不存在 - {directory}")]
        
    files = glob.glob(os.path.join(directory, "**/*.md"), recursive=True)
    
    # Filter out README_INDEX.md itself to avoid self-reference loop
    files = [f for f in files if os.path.basename(f) != "README_INDEX.md"]
    
    if not files:
        return [types.TextContent(type="text", text=f"在 {directory} 中未找到 Markdown 文件")]
        
    # Group files by subdirectory if needed, or just list them
    # For now, let's create a flat list or grouped by folder relative to root
    
    index_content = "# Document Index\n\n"
    index_content += f"Generated on: {os.path.basename(directory)}\n\n"
    
    # Sort files by subdirectory to ensure grouping works
    files.sort(key=lambda f: (os.path.dirname(os.path.relpath(f, directory)), os.path.basename(f)))
    
    current_subdir = None
    
    for file_path in files:
        rel_path = os.path.relpath(file_path, directory)
        subdir = os.path.dirname(rel_path)
        filename = os.path.basename(file_path)
        title = os.path.splitext(filename)[0]
        
        if subdir != current_subdir:
            if subdir:
                index_content += f"\n## {subdir}\n\n"
            else:
                index_content += "\n## Root\n\n"
            current_subdir = subdir
            
        # Create link
        # Use forward slashes for compatibility
        link_path = rel_path.replace("\\", "/")
        link_path = link_path.replace(" ", "%20")
        
        index_content += f"- [{title}]({link_path})\n"
        
    index_path = os.path.join(directory, "README_INDEX.md")
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_content)
        return [types.TextContent(type="text", text=f"Index file generated successfully: {index_path}\nIncluded {len(files)} files.")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error generating index file: {str(e)}")]


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_pdf_files",
            description="通过文件名模糊搜索 PDF 文件路径",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "文件名关键词（模糊匹配）",
                    },
                    "directory": {
                        "type": "string",
                        "description": "搜索根目录（可选，默认当前目录）",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "匹配阈值 0.0-1.0 (默认 0.45)",
                        "default": 0.45
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回最大结果数 (默认 10)",
                        "default": 10
                    }
                },
                "required": ["query"],
            },
        ),
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
                        "enum": ["text", "markdown", "json"],
                        "description": "输出格式，可选 'text' (默认), 'markdown' 或 'json'，markdown 格式更适合 LLM 阅读，json 格式适合程序化处理",
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
                    },
                    "custom_output_dir": {
                        "type": "string",
                        "description": "自定义输出目录（可选）"
                    },
                    "skip_table_detection": {
                        "type": "boolean",
                        "description": "是否跳过表格检测（默认false）。设为true可大幅提升纯文本提取速度，但不会识别和格式化表格。",
                        "default": False
                    }
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="batch_extract_pdf_content",
            description="批量提取指定目录下的PDF文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "要搜索的根目录绝对路径",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "文件匹配模式，例如 '**/*.pdf' (支持递归)",
                        "default": "**/*.pdf"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "markdown", "json"],
                        "description": "输出格式",
                        "default": "markdown"
                    },
                    "include_text": {
                        "type": "boolean",
                        "default": True
                    },
                    "include_images": {
                        "type": "boolean",
                        "default": False
                    },
                    "use_local_images_only": {
                        "type": "boolean",
                        "default": True
                    },
                    "custom_output_dir": {
                        "type": "string",
                        "description": "自定义输出目录（可选）"
                    },
                    "skip_table_detection": {
                        "type": "string",
                        "description": "自定义输出目录（可选）"
                    },
                    "custom_image_output_dir": {
                        "type": "string",
                        "description": "自定义图片输出目录（可选）"
                    },
                    "create_folder": {
                        "type": "boolean",
                        "description": "是否为每个PDF创建单独的文件夹（默认false）。如果为true，将在输出目录下为每个PDF创建一个同名文件夹，并将Markdown和图片放入其中。",
                        "default": False
                    },
                    "preserve_structure": {
                        "type": "boolean",
                        "description": "是否保持源文件的目录层级结构（默认true）。如果为false，所有文件将平铺到输出目录。",
                        "default": True
                    },
                    "skip_table_detection": {
                        "type": "boolean",
                        "description": "是否跳过表格检测（默认false）。设为true可大幅提升纯文本提取速度，但不会识别和格式化表格。",
                        "default": False
                    }
                },
                "required": ["directory"],
            },
        ),
        types.Tool(
            name="batch_extract_tables",
            description="批量从目录中的 PDF 文件提取表格并保存为 Markdown",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "要搜索的根目录绝对路径",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出目录 (默认: directory/extracted_tables)",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "文件匹配模式 (默认: **/*.pdf)",
                        "default": "**/*.pdf"
                    }
                },
                "required": ["directory"],
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
        ),
        types.Tool(
            name="generate_index_file",
            description="扫描指定目录下的 Markdown 文件，生成 README_INDEX.md 索引文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "要扫描的目录绝对路径",
                    }
                },
                "required": ["directory"],
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

    if name == "search_pdf_files":
        query = arguments.get("query")
        directory = arguments.get("directory")
        threshold = arguments.get("threshold", 0.45)
        limit = arguments.get("limit", 10)
        return await search_pdf_files(query, directory, threshold, limit)

    elif name == "extract_pdf_content":
        page_range = arguments.get("page_range", "all")
        keyword = arguments.get("keyword")
        format = arguments.get("format", "text")
        include_text = arguments.get("include_text", True)
        include_images = arguments.get("include_images", False)
        use_local_images_only = arguments.get("use_local_images_only", True)
        skip_table_detection = arguments.get("skip_table_detection", False)
        custom_output_dir = arguments.get("custom_output_dir")
        
        # Calculate consistent paths
        root_output_base = custom_output_dir if custom_output_dir else os.getcwd()
        _, image_output_dir = get_output_paths_for_mode(root_output_base, include_images, include_text, skip_table_detection)
        
        return await extract_content(
            file_path, page_range, keyword, format, include_text, include_images, 
            use_local_images_only, 
            image_output_dir=image_output_dir,
            skip_table_detection=skip_table_detection
        )
    
    elif name == "batch_extract_pdf_content":
        directory = arguments.get("directory")
        pattern = arguments.get("pattern", "**/*.pdf")
        format = arguments.get("format", "markdown")
        include_text = arguments.get("include_text", True)
        include_images = arguments.get("include_images", False)
        use_local_images_only = arguments.get("use_local_images_only", True)
        custom_output_dir = arguments.get("custom_output_dir")
        custom_image_output_dir = arguments.get("custom_image_output_dir")
        skip_table_detection = arguments.get("skip_table_detection", False)
        create_folder = arguments.get("create_folder", False)
        preserve_structure = arguments.get("preserve_structure", True)
        return await batch_extract_pdf_content(
            directory, pattern, format, include_text, include_images, use_local_images_only, custom_output_dir, custom_image_output_dir, skip_table_detection, create_folder, preserve_structure
        )

    elif name == "batch_extract_tables":
        directory = arguments.get("directory")
        output_dir = arguments.get("output_dir")
        pattern = arguments.get("pattern", "**/*.pdf")
        return await batch_extract_tables(directory, output_dir, pattern)

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
    
    elif name == "generate_index_file":
        directory = arguments.get("directory")
        return await generate_index_file(directory)

    else:
        raise ValueError(f"Unknown tool: {name}")

async def run_server():
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

def main():
    """Entry point for the application script"""
    asyncio.run(run_server())

if __name__ == "__main__":
    main()
