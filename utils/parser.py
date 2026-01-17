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
    
    questions = []
    errors = []
    
    for i, block in enumerate(raw_blocks, 1):
        block = block.strip()
        if not block:
            continue
            
        try:
            # Split by part separator (at least 4 equals)
            parts = [p.strip() for p in re.split(r'\n={4,}\s*\n?', block) if p.strip()]
            
            if len(parts) < 3: 
                # Strict check: Must have Question + at least 2 Options
                # But sometimes users mess up separators.
                errors.append(Messages.get("PARSER_BLOCK_INCOMPLETE", lang).format(line=i))
                continue
                
            question_text = parts[0]
            
            # Heuristic for Block 1: Remove Header if present
            # Always try to clean up Block 1 if it has double newlines
            if i == 1:
                segments = re.split(r'\n\s*\n', question_text)
                if len(segments) > 1:
                    # Take the last segment as the potential question
                    candidate = segments[-1].strip()
                    # Only accept if it's not excessively long (headers usually precede the question)
                    if len(candidate) < 300 and len(candidate) > 0:
                        question_text = candidate

            options_raw = parts[1:]
            
            options = []
            correct_option_id = None
            
            # Heuristic: Check if separator was missing between Question and Option 1 (starting with #)
            # If no options were found (len < 2 check above might fail, but let's say parts was just Q?)
            # Wait, if separator missing, Q text includes Opt1.
            # But earlier check `len(parts) < 3` might filter it out if there was only Q and Opt2.
            # But the user case has Q+#Opt1 (no sep) -> Opt2 (sep) -> Opt3. 
            # So parts = [Q+#Opt1, Opt2, Opt3]. len=3. Passes check.
            
            # We need to check if Q text contains #Opt1
            last_q_line_idx = -1
            q_lines = question_text.splitlines()
            for q_idx, line in enumerate(q_lines):
                if line.strip().startswith("#"):
                     # Found a # line inside question text!
                     # Treat this line and subsequent lines as OPTIONS?
                     # No, just this line is probably the first option (merged).
                     # But what if multiple options merged?
                     # Simple fix: If we find ONE line starting with #, assume it's the Correct Option missing a separator.
                     last_q_line_idx = q_idx
                     break
            
            if last_q_line_idx != -1:
                # We found a # line in Question. Split!
                real_question = "\n".join(q_lines[:last_q_line_idx]).strip()
                missing_opt = "\n".join(q_lines[last_q_line_idx:]).strip() # All remaining lines?
                
                # If there are multiple lines after #, they might be other options too?
                # User case:
                # Wie viele Sekunden hat eine Minute?
                # #60
                # (End of part 0)
                
                if real_question:
                    question_text = real_question
                    # Insert the missing option at the start of options_raw
                    options_raw.insert(0, missing_opt)

            for idx, opt in enumerate(options_raw):
                clean_opt = opt
                # Check for correct answer marker '#'
                if clean_opt.startswith("#"):
                    if correct_option_id is not None:
                         # We raise ParserError here, which is caught below and added to errors
                         raise ParserError(Messages.get("PARSER_MULTIPLE_CORRECT_BLOCK", lang).format(line=i))
                    correct_option_id = idx
                    clean_opt = clean_opt[1:].strip()
                
                options.append(clean_opt)
            
            q_obj = {
                'question': question_text,
                'options': options,
                'correct_option_id': correct_option_id
            }
            
            # Use shared validator
            validate_question(q_obj, i, lang) 
            questions.append(q_obj)
            
        except ParserError as pe:
             errors.append(str(pe))
        except Exception as e:
            errors.append(f"❌ Block {i}: {str(e)}")
            
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
