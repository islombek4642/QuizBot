import docx
import subprocess
import tempfile
import os
import re
from typing import List, Dict, Optional, Tuple, Any
from core.logger import logger
from constants.messages import Messages

class ParserError(Exception):
    """Custom exception for parser errors."""
    pass

def parse_docx_to_json(file_path: str, lang: str = "UZ") -> Tuple[List[Dict], List[str]]:
    """Parses a docx file."""
    try:
        doc = docx.Document(file_path)
        lines = [para.text for para in doc.paragraphs]
        return parse_lines_to_json(lines, lang)
    except Exception as e:
        logger.error("Failed to parse docx file", path=file_path, error=str(e))
        raise ParserError(Messages.get("PARSER_FILE_ERROR", lang).format(error=str(e)))

def parse_doc_to_json(file_path: str, lang: str = "UZ") -> Tuple[List[Dict], List[str]]:
    """Robustly parses a legacy .doc or RTF file renamed to .doc."""
    try:
        # Read file bytes to check signature
        with open(file_path, 'rb') as f:
            header = f.read(1024)
            f.seek(0)
            file_bytes = f.read()

        # 1. Check for RTF
        if header.startswith(b'{\\rtf'):
            try:
                from striprtf.striprtf import rtf_to_text
                text = rtf_to_text(file_bytes.decode('utf-8', errors='ignore'))
                return parse_lines_to_json(text.splitlines(), lang)
            except:
                 pass

        # 2. Check for DOCX (ZIP)
        if header.startswith(b'PK\x03\x04'):
             return parse_docx_to_json(file_path, lang)

        # 3. Handle as legacy Word
        process = subprocess.run(
            ["antiword", file_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        if process.returncode == 0 and process.stdout.strip():
            lines = process.stdout.splitlines()
        else:
            # Fallback to catdoc
            process_cat = subprocess.run(
                ["catdoc", "-w", file_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            if process_cat.returncode == 0:
                lines = process_cat.stdout.splitlines()
            else:
                raise Exception(f"Antiword & Catdoc failed: {process_cat.stderr}")
            
        return parse_lines_to_json(lines, lang)
    except Exception as e:
        logger.error("Failed to parse .doc file", path=file_path, error=str(e))
        raise ParserError(Messages.get("PARSER_FILE_ERROR", lang).format(error=str(e)))

def parse_lines_to_json(lines: List[str], lang: str = "UZ") -> Tuple[List[Dict[str, Any]], List[str]]:
    """Shared logic to parse lines of text in quiz format."""
    # Ensure full_text join doesn't double newlines
    if lines and lines[0].endswith('\n'):
        full_text = "".join(lines)
    else:
        full_text = "\n".join(lines)

    # Detection logic for different formats
    abc_markers = 0
    # Scan first 100 lines for markers
    for line in lines[:100]:
        t = line.strip()
        if not t: continue
        if "++++" in t:
            # Custom format detected (====== / ++++++)
            return _parse_custom_format(lines, full_text, lang)
        # Check for ABC patterns: "1. ", "A) ", "#A) "
        if re.match(r'^\d+[\.\)]', t) or re.match(r'^#?[A-Z][\.\)]', t, re.I):
            abc_markers += 1
            
    if abc_markers > 5:
        return _parse_abc_format(lines, lang)

    # Fallback to legacy format (?Savol, +To'g'ri, =Xato)
    return _parse_legacy_format(lines, lang)

def _parse_legacy_format(lines: List[str], lang: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    questions = []
    errors = []
    current_question = None
    current_question_start_line = 0

    for i, text in enumerate(lines, 1):
        text = text.strip()
        if not text:
            continue

        try:
            if text.startswith('?'):
                # Validate previous question before starting new one
                if current_question:
                    try:
                        validate_question(current_question, current_question_start_line, lang)
                        questions.append(current_question)
                    except ParserError as e:
                        errors.append(str(e))
                
                current_question = {
                    'question': text[1:].strip(),
                    'options': [],
                    'correct_option_id': None,
                    'last_item_type': 'q'
                }
                current_question_start_line = i
                
            elif text.startswith('+'):
                if not current_question:
                    continue
                    
                if current_question['correct_option_id'] is None:
                    current_question['correct_option_id'] = len(current_question['options'])
                    current_question['options'].append(text[1:].strip())
                    current_question['last_item_type'] = 'c'
                else:
                    current_question['options'].append(text[1:].strip())
                    current_question['last_item_type'] = 'w'

            elif text.startswith('='):
                if not current_question:
                    continue

                current_question['options'].append(text[1:].strip())
                current_question['last_item_type'] = 'w'
                
            elif text.startswith('!') or text.lower().startswith('izoh:'):
                if not current_question:
                    continue
                
                expl = text[1:].strip() if text.startswith('!') else text[5:].strip()
                current_question['explanation'] = expl
                current_question['last_item_type'] = 'e'
                
            else:
                if text.startswith(('-', '*', '•', 'A)', 'B)', '1.')):
                    errors.append(Messages.get("PARSER_INVALID_PREFIX", lang).format(line=i, text=text[:20] + "..."))
                elif current_question:
                    last_type = current_question.get('last_item_type')
                    if last_type == 'q':
                        current_question['question'] += " " + text
                    elif last_type in ('c', 'w') and current_question['options']:
                        current_question['options'][-1] += " " + text

        except Exception as e:
            errors.append(f"Error at line {i}: {str(e)}")

    if current_question:
        try:
            validate_question(current_question, current_question_start_line, lang)
            questions.append(current_question)
        except ParserError as e:
            errors.append(str(e))

    if not questions and not errors:
        raise ParserError(Messages.get("PARSER_NO_QUIZZES", lang))

    return questions, errors

def _parse_custom_format(lines: List[str], full_text: str, lang: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parses custom format with flexible separators:
    Question text
    ====== (min 3 =)
    #Correct
    ======
    Wrong
    ++++++ (min 3 +)
    """
    # 1. Split into raw blocks by question separator
    raw_blocks = [b for b in re.split(r'\n\s*\+{3,}\s*\n?', full_text) if b.strip()]
    
    def rescue_merged_blocks(blk_text: str) -> List[str]:
        parts = [p.strip() for p in re.split(r'\n\s*={3,}\s*\n?', blk_text)]
        correct_indices = [idx for idx, p in enumerate(parts) if p.startswith("#")]
        
        if len(correct_indices) < 2:
            return [blk_text]

        idx1 = correct_indices[0]
        idx2 = correct_indices[1]
        
        for k in range(idx1, idx2 + 1):
            if k >= len(parts): break
            p_text = parts[k]
            if '\n\n' in p_text:
                splits = re.split(r'\n\s*\n', p_text, maxsplit=1)
                if len(splits) < 2: continue
                
                left_segment = splits[0]
                right_segment = splits[1]
                
                b1_parts = parts[:k] + [left_segment]
                b1_str = "\n======\n".join(b1_parts)
                b2_parts = [right_segment] + parts[k+1:]
                b2_str = "\n======\n".join(b2_parts)
                
                return [b1_str] + rescue_merged_blocks(b2_str)
        return [blk_text]

    processed_blocks = []
    for block in raw_blocks:
        processed_blocks.extend(rescue_merged_blocks(block))
            
    raw_blocks = processed_blocks
    questions = []
    errors = []
    
    current_text_pos = 0
    for i_blk, block in enumerate(raw_blocks, 1):
        block_stripped = block.strip()
        if not block_stripped:
            continue
            
        pos = full_text.find(block, current_text_pos)
        if pos != -1:
            line_num = full_text[:pos].count('\n') + 1
            current_text_pos = pos + len(block)
        else:
            line_num = i_blk 
            
        try:
            parts = [p.strip() for p in re.split(r'\n\s*={3,}\s*\n?', block) if p.strip()]
            
            if len(parts) < 3: 
                errors.append(Messages.get("PARSER_BLOCK_INCOMPLETE", lang).format(line=line_num))
                continue
                
            question_text = parts[0]
            
            # Header stripping logic for first block
            if i_blk == 1:
                q_lines = question_text.splitlines()
                if len(q_lines) > 1:
                    found_q_start = -1
                    for q_l_idx, q_l in enumerate(q_lines):
                        qls = q_l.strip()
                        if re.match(r'^\d+[\.\)]', qls) or qls.endswith('?'):
                            found_q_start = q_l_idx
                            break
                    if found_q_start > 0:
                        question_text = "\n".join(q_lines[found_q_start:]).strip()
                    elif len(q_lines) > 1 and not (q_lines[0].strip().endswith('?') or re.match(r'^\d+[\.\)]', q_lines[0].strip())):
                        question_text = "\n".join(q_lines[1:]).strip()
                else:
                    segments = re.split(r'\n\s*\n', question_text)
                    if len(segments) > 1:
                        candidate = segments[-1].strip()
                        if len(candidate) > 0:
                            question_text = candidate

            # Length check relaxation for Q1 specifically
            if i_blk == 1 and len(question_text) > 300:
                 last_nl = question_text.rfind('\n')
                 if last_nl != -1:
                     question_text = question_text[last_nl+1:].strip()
            
            options_raw = parts[1:]
            options = []
            correct_option_id = None
            
            # Handle potential merged option (starts with #) inside question text
            last_q_line_idx = -1
            qls_list = question_text.splitlines()
            for q_idx, line in enumerate(qls_list):
                if line.strip().startswith("#"):
                     last_q_line_idx = q_idx
                     break
            
            if last_q_line_idx != -1:
                real_question = "\n".join(qls_list[:last_q_line_idx]).strip()
                missing_opt = "\n".join(qls_list[last_q_line_idx:]).strip() 
                if real_question:
                    question_text = real_question
                    options_raw.insert(0, missing_opt)

            for idx, opt in enumerate(options_raw):
                clean_opt = opt.strip()
                if not clean_opt: continue
                
                if clean_opt.startswith("#"):
                    if correct_option_id is None:
                        correct_option_id = len(options)
                        clean_opt = clean_opt[1:].strip()
                    else:
                        if options and options[-1] == clean_opt[1:].strip():
                            continue
                        raise ParserError(Messages.get("PARSER_MULTIPLE_CORRECT_BLOCK", lang).format(line=line_num))
                options.append(clean_opt)
            
            q_obj = {
                'question': question_text.strip(),
                'options': options,
                'correct_option_id': correct_option_id
            }
            validate_question(q_obj, line_num, lang) 
            questions.append(q_obj)
            
        except ParserError as pe:
             errors.append(str(pe))
        except Exception as e:
            errors.append(f"❌ Q-Line {line_num}: {str(e)}")
            
    return questions, errors

def _parse_abc_format(lines: List[str], lang: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parses numbered questions with ABC options:
    1. Question?
    A) Option 1
    #B) Correct Option
    C) Option 3
    """
    questions = []
    errors = []
    current_question = None
    current_question_start_line = 0
    
    re_q = re.compile(r'^(\d+)(?:[\.\)\s]+|(?=[A-ZА-Я]))(.*)')
    re_opt = re.compile(r'^#?\s*([A-Z])[\.\)]\s*(.*)', re.IGNORECASE)

    for i, text in enumerate(lines, 1):
        clean_text = text.strip()
        if not clean_text:
            continue
            
        m_q = re_q.match(clean_text)
        m_opt = re_opt.match(clean_text)
        
        if m_q:
            if current_question:
                try:
                    validate_question(current_question, current_question_start_line, lang)
                    questions.append(current_question)
                except ParserError as e:
                    errors.append(str(e))
            
            current_question = {
                'question': m_q.group(2).strip(),
                'options': [],
                'correct_option_id': None,
                'last_item_type': 'q'
            }
            current_question_start_line = i
        elif m_opt:
            if not current_question:
                continue
            is_correct = clean_text.startswith("#") or m_opt.group(2).strip().startswith("#")
            opt_text = m_opt.group(2).strip()
            if opt_text.startswith("#"):
                opt_text = opt_text[1:].strip()
            
            if is_correct:
                current_question['correct_option_id'] = len(current_question['options'])
            current_question['options'].append(opt_text)
            current_question['last_item_type'] = 'o'
            
        elif clean_text.startswith('!') or clean_text.lower().startswith('izoh:'):
            if current_question:
                expl = clean_text[1:].strip() if clean_text.startswith('!') else clean_text[5:].strip()
                current_question['explanation'] = expl
                current_question['last_item_type'] = 'e'
                
        elif current_question:
            last_type = current_question.get('last_item_type')
            if last_type == 'q':
                current_question['question'] += " " + clean_text
            elif last_type == 'o' and current_question['options']:
                current_question['options'][-1] += " " + clean_text
                
    if current_question:
        try:
            validate_question(current_question, current_question_start_line, lang)
            questions.append(current_question)
        except ParserError as e:
            errors.append(str(e))
            
    return questions, errors

def validate_question(q: Dict[str, Any], line_num: int, lang: str):
    """Ensures a question has text, options and a correct answer."""
    if '__error' in q:
        raise ParserError(q['__error'])

    if not q.get('question'):
        raise ParserError(Messages.get("PARSER_EMPTY_QUESTION", lang).format(line=line_num))
        
    if len(q.get('options', [])) < 2:
        msg = Messages.get("PARSER_FEW_OPTIONS", lang).format(line=line_num, text=q['question'][:30] + "...", count=len(q['options']))
        raise ParserError(msg)
        
    if q.get('correct_option_id') is None:
        q['correct_option_id'] = 0
        
    if len(q['options']) > 10:
        msg = Messages.get("PARSER_TOO_MANY_OPTIONS", lang).format(line=line_num, count=len(q['options']))
        raise ParserError(msg)
    
    if len(q['question']) > 500:
        msg = Messages.get("PARSER_QUESTION_TOO_LONG", lang).format(line=line_num, count=len(q['question']))
        raise ParserError(msg)

    for opt in q['options']:
        if len(opt) > 500:
             msg = Messages.get("PARSER_OPTION_TOO_LONG", lang).format(line=line_num, text=opt[:30] + "...", count=len(opt))
             raise ParserError(msg)

    if q.get('explanation') and len(q['explanation']) > 200:
        msg = Messages.get("PARSER_EXPLANATION_TOO_LONG", lang).format(
            line=line_num, 
            count=len(q['explanation'])
        )
        raise ParserError(msg)
