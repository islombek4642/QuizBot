import docx
from typing import List, Dict, Optional, Tuple
from core.logger import logger
from constants.messages import Messages

class ParserError(Exception):
    """Custom exception for parser errors."""
    pass

def parse_docx_to_json(file_path: str, lang: str = "UZ") -> Tuple[List[Dict], List[str]]:
    """
    Parses a docx file.
    Returns: (questions, errors)
    """
    try:
        doc = docx.Document(file_path)
    except Exception as e:
        logger.error("Failed to open docx file", path=file_path, error=str(e))
        raise ParserError(Messages.get("PARSER_FILE_ERROR", lang).format(error=str(e)))

    questions = []
    errors = []
    current_question = None
    current_question_start_line = 0

    for i, para in enumerate(doc.paragraphs, 1):
        text = para.text.strip()
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
                    continue # Ignore orphan options
                    
                if current_question['correct_option_id'] is not None:
                     # Skip adding this option, report error?
                     # Better to report error for the whole question later or now?
                     # Let's add an error but keep parsing to see if we can salvage?
                     # No, multiple correct answers break the logic. 
                     # We will mark this question as broken.
                     # However, easiest is to raise error, catch it in outer loop if we wrap the block...
                     # But we are in a loop.
                     # Let's accumulate error string pending validation.
                     pass 

                # We just add it, validate_question will check correct_option_id count/uniqueness
                # Wait, current logic sets generic ID.
                if current_question['correct_option_id'] is not None:
                     current_question['__error'] = Messages.get("PARSER_MULTIPLE_CORRECT", lang).format(line=i, start_line=current_question_start_line)

                current_question['correct_option_id'] = len(current_question['options'])
                current_question['options'].append(text[1:].strip())
                
            elif text.startswith('='):
                if not current_question:
                    continue
                    
                current_question['options'].append(text[1:].strip())
                
            else:
                # Check if this line looks like it belongs to format but has wrong prefix
                if text.startswith(('-', '*', '•', 'A)', 'B)', '1.')):
                     # This is an invalid line. If we are in a question, it might be a malformed option.
                     # We treat it as an error for the current question?
                     # Or just a standalone error?
                     # User wants skipped questions reported.
                     errors.append(Messages.get("PARSER_INVALID_PREFIX", lang).format(line=i, text=text[:20] + "..."))
                # Otherwise ignore random text
        except Exception as e:
            errors.append(f"Error at line {i}: {str(e)}")

    # Add the last question
    if current_question:
        try:
            # Check internal error flag
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
        # Telegram limit: max 10 options.
        msg = Messages.get("PARSER_TOO_MANY_OPTIONS", lang).format(line=line_num, count=len(q['options']))
        raise ParserError(msg)
    
    # Check length limits for Telegram - HARD LIMITS
    # We raise error instead of truncating to avoid API crashes or bad UX
    if len(q['question']) > 300:
        msg = Messages.get("PARSER_QUESTION_TOO_LONG", lang).format(line=line_num, count=len(q['question']))
        raise ParserError(msg)

    for i, opt in enumerate(q['options']):
        if len(opt) > 100:
             msg = Messages.get("PARSER_OPTION_TOO_LONG", lang).format(line=line_num, count=len(opt))
             raise ParserError(msg)
