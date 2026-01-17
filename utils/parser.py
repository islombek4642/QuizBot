import docx
import subprocess
import tempfile
import os
from typing import List, Dict, Optional, Tuple
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

def parse_lines_to_json(lines: List[str], lang: str = "UZ") -> Tuple[List[Dict], List[str]]:
    """Shared logic to parse lines of text in quiz format."""
    questions = []
    errors = []
    current_question = None
    current_question_start_line = 0

    for i, text in enumerate(lines, 1):
        if "++++++" in text:
            # Detected new format separator, switch strategy
            return _parse_custom_format(lines, lang)

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
                    'last_item_type': 'q' # Track if last content was question 'q', correct option 'c', or wrong 'w'
                }
                current_question_start_line = i
                
            elif text.startswith('+'):
                if not current_question:
                    continue
                    
                if current_question['correct_option_id'] is not None:
                     current_question['__error'] = Messages.get("PARSER_MULTIPLE_CORRECT", lang).format(line=i, start_line=current_question_start_line)

                current_question['correct_option_id'] = len(current_question['options'])
                current_question['options'].append(text[1:].strip())
                current_question['last_item_type'] = 'c'
                
            elif text.startswith('='):
                if not current_question:
                    continue
                current_question['options'].append(text[1:].strip())
                current_question['last_item_type'] = 'w'
                
            else:
                if text.startswith(('-', '*', '•', 'A)', 'B)', '1.')):
                    errors.append(Messages.get("PARSER_INVALID_PREFIX", lang).format(line=i, text=text[:20] + "..."))
                elif current_question:
                    # Multiline support: append to last item
                    last_type = current_question.get('last_item_type')
                    if last_type == 'q':
                        current_question['question'] += " " + text
                    elif last_type in ('c', 'w') and current_question['options']:
                        current_question['options'][-1] += " " + text

        except Exception as e:
            errors.append(f"Error at line {i}: {str(e)}")

    if current_question:
        try:
            if '__error' in current_question:
                raise ParserError(current_question['__error'])
            validate_question(current_question, current_question_start_line, lang)
            questions.append(current_question)
        except ParserError as e:
            errors.append(str(e))

    if not questions and not errors:
        raise ParserError(Messages.get("PARSER_NO_QUIZZES", lang))

    return questions, errors

import re

def _parse_custom_format(lines: List[str], lang: str) -> Tuple[List[Dict], List[str]]:
    """
    Parse questions using custom format with flexible separators:
    Question
    ====== (min 4 =)
    #Correct
    ======
    Wrong
    ++++++ (min 4 +)
    """
    full_text = "\n".join(lines)
    
    # Split by question separator (at least 4 pluses)
    # Using filter to remove empty strings caused by leading/trailing separators
    raw_blocks = [b for b in re.split(r'\n\+{4,}\s*\n?', full_text) if b.strip()]
    
    # 2. Rescuing merged blocks (Missing +++++ separator)
    # The user's file has instances where the "++++++" separator is missing, 
    # merging two questions into one block (e.g. Q1... #A1 ... Q2 ... #A2).
    # We detect this by finding multiple correct answer markers (#) in a single block.
    # We then try to find a natural split point (\n\n) strictly located *between* the correct option of Q1 
    # and the answer of Q2.

    def rescue_merged_blocks(blk_text: str) -> List[str]:
        # Parse into components to locate markers reliably
        parts = [p.strip() for p in re.split(r'\n={4,}\s*\n?', blk_text)]
        # Use simple string checks to locate markers in the parts list
        correct_indices = [idx for idx, p in enumerate(parts) if p.startswith("#")]
        
        # If fewer than 2 distinct correct answers, no merge suspected
        if len(correct_indices) < 2:
            return [blk_text]

        # Scan for a split point between the first and second correct marker
        idx1 = correct_indices[0]
        idx2 = correct_indices[1]
        
        for k in range(idx1, idx2 + 1):
            if k >= len(parts): break
            
            p_text = parts[k]
            # Check for double newline which indicates the boundary
            if '\n\n' in p_text:
                # Found likely split point!
                splits = re.split(r'\n\s*\n', p_text, maxsplit=1)
                if len(splits) < 2: continue
                
                left_segment = splits[0]
                right_segment = splits[1]
                
                # Reconstruct Block 1
                b1_parts = parts[:k] + [left_segment]
                b1_str = "\n======\n".join(b1_parts)
                
                # Reconstruct Block 2
                b2_parts = [right_segment] + parts[k+1:]
                b2_str = "\n======\n".join(b2_parts)
                
                # Recursively process Block 2 in case it has MORE merged questions
                return [b1_str] + rescue_merged_blocks(b2_str)
        
        # If no clean split found, return original
        return [blk_text]

    processed_blocks = []
    for block in raw_blocks:
        processed_blocks.extend(rescue_merged_blocks(block))
            
    raw_blocks = processed_blocks
    
    questions = []
    errors = []
    
    for i_blk, block in enumerate(raw_blocks, 1):
        block = block.strip()
        if not block:
            continue
            
        try:
            # Split by part separator (at least 4 equals)
            parts = [p.strip() for p in re.split(r'\n={4,}\s*\n?', block) if p.strip()]
            
            if len(parts) < 3: 
                # Strict check: Must have Question + at least 2 Options
                # But sometimes users mess up separators.
                errors.append(Messages.get("PARSER_BLOCK_INCOMPLETE", lang).format(line=i_blk))
                continue
                
            question_text = parts[0]
            
            # Heuristic for Block 1: Remove Header if present
            # Always try to clean up Block 1 if it has double newlines
            if i_blk == 1:
                segments = re.split(r'\n\s*\n', question_text)
                if len(segments) > 1:
                    # Take the last segment as the potential question
                    candidate = segments[-1].strip()
                    if len(candidate) > 0:
                        question_text = candidate

            # Length check relaxation for Q1 specifically if it still looks long
            if i_blk == 1 and len(question_text) > 300:
                 # If still too long, just take the last 300 chars? No, that's risky.
                 # Let's just strip everything before the last newline
                 last_nl = question_text.rfind('\n')
                 if last_nl != -1:
                     question_text = question_text[last_nl+1:].strip()
            
            options_raw = parts[1:]
            
            options = []
            correct_option_id = None
            
            # Heuristic: Check if separator was missing between Question and Option 1 (starting with #)
            # ... (Existing logic kept or slightly improved) because regex split helps, 
            # but sometimes users put Space+#Answer.
            
            # Re-implement detailed missing separator logic specific to custom parser text flows
            # If we see lines starting with # inside question text, it's definitely a merged option.
            
            last_q_line_idx = -1
            q_lines = question_text.splitlines()
            for q_idx, line in enumerate(q_lines):
                if line.strip().startswith("#"):
                     last_q_line_idx = q_idx
                     break
            
            if last_q_line_idx != -1:
                real_question = "\n".join(q_lines[:last_q_line_idx]).strip()
                missing_opt = "\n".join(q_lines[last_q_line_idx:]).strip() 
                if real_question:
                    question_text = real_question
                    options_raw.insert(0, missing_opt)

            for idx, opt in enumerate(options_raw):
                clean_opt = opt.strip() # Ensure strip happens first
                if not clean_opt: continue # Skip empty options
                
                # Check for correct answer marker '#'
                if clean_opt.startswith("#"):
                    if correct_option_id is not None:
                         # Instead of erroring, let's just accept the FIRST correct one and warn?
                         # Or maybe the user duplicated the option?
                         # User requirement: "Bir nechta to'g'ri javob (#) belgilangan" is an error.
                         # But let's verify if lines match exactly?
                         pass # Allow logic to proceed to error below for now, OR:
                         
                    if correct_option_id is None:
                        correct_option_id = idx
                        clean_opt = clean_opt[1:].strip()
                    else:
                         # If we already have a correct option, and find another #, it's an error.
                         # CHECK: Is it the SAME option duplicated?
                         if idx > 0 and options[-1] == clean_opt[1:].strip():
                             # Likely a copy-paste error where same line repeated?
                             continue
                         raise ParserError(Messages.get("PARSER_MULTIPLE_CORRECT_BLOCK", lang).format(line=i_blk))
                
                options.append(clean_opt)
            
            q_obj = {
                'question': question_text,
                'options': options,
                'correct_option_id': correct_option_id
            }
            
            # Use shared validator
            validate_question(q_obj, i_blk, lang) 
            questions.append(q_obj)
            
        except ParserError as pe:
             errors.append(str(pe))
        except Exception as e:
            errors.append(f"❌ Block {i_blk}: {str(e)}")
            
    if not questions and not errors:
         raise ParserError(Messages.get("PARSER_NO_QUIZZES", lang))
         
    return questions, errors

def validate_question(q: Dict, line_num: int, lang: str):
    """Ensures a question has text, options and a correct answer."""
    if '__error' in q:
        raise ParserError(q['__error'])

    if not q['question']:
        raise ParserError(Messages.get("PARSER_EMPTY_QUESTION", lang).format(line=line_num))
        
    if len(q['options']) < 2:
        msg = Messages.get("PARSER_FEW_OPTIONS", lang).format(line=line_num, text=q['question'][:20] + "...", count=len(q['options']))
        raise ParserError(msg)
        
    if q['correct_option_id'] is None:
        msg = Messages.get("PARSER_NO_CORRECT_OPTION", lang).format(line=line_num, text=q['question'][:20] + "...")
        raise ParserError(msg)
        
    if len(q['options']) > 10:
        msg = Messages.get("PARSER_TOO_MANY_OPTIONS", lang).format(line=line_num, count=len(q['options']))
        raise ParserError(msg)
    
    if len(q['question']) > 300:
        msg = Messages.get("PARSER_QUESTION_TOO_LONG", lang).format(line=line_num, count=len(q['question']))
        raise ParserError(msg)

    for i, opt in enumerate(q['options']):
        if len(opt) > 100:
             msg = Messages.get("PARSER_OPTION_TOO_LONG", lang).format(line=line_num, text=opt[:20] + "...", count=len(opt))
             raise ParserError(msg)
