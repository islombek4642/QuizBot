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
    """Parses a legacy .doc file using antiword."""
    try:
        process = subprocess.run(
            ["antiword", file_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        if process.returncode != 0:
            raise Exception(process.stderr)
            
        lines = process.stdout.splitlines()
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
                    'correct_option_id': None
                }
                current_question_start_line = i
                
            elif text.startswith('+'):
                if not current_question:
                    continue
                    
                if current_question['correct_option_id'] is not None:
                     current_question['__error'] = Messages.get("PARSER_MULTIPLE_CORRECT", lang).format(line=i, start_line=current_question_start_line)

                current_question['correct_option_id'] = len(current_question['options'])
                current_question['options'].append(text[1:].strip())
                
            elif text.startswith('='):
                if not current_question:
                    continue
                current_question['options'].append(text[1:].strip())
                
            else:
                if text.startswith(('-', '*', '•', 'A)', 'B)', '1.')):
                    errors.append(Messages.get("PARSER_INVALID_PREFIX", lang).format(line=i, text=text[:20] + "..."))
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
             msg = Messages.get("PARSER_OPTION_TOO_LONG", lang).format(line=line_num, count=len(opt))
             raise ParserError(msg)
