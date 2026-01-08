import docx
from typing import List, Dict, Optional
from core.logger import logger
from constants.messages import Messages

class ParserError(Exception):
    """Custom exception for parser errors."""
    pass

def parse_docx_to_json(file_path: str, lang: str = "UZ") -> List[Dict]:
    """
    Parses a docx file with strict validation and error reporting.
    Format:
    ?Question text
    +Correct Answer
    =Wrong Answer
    """
    try:
        doc = docx.Document(file_path)
    except Exception as e:
        logger.error("Failed to open docx file", path=file_path, error=str(e))
        raise ParserError(Messages.get("PARSER_FILE_ERROR", lang).format(error=str(e)))

    questions = []
    current_question = None
    current_question_start_line = 0

    for i, para in enumerate(doc.paragraphs, 1):
        text = para.text.strip()
        if not text:
            continue

        if text.startswith('?'):
            # Validate previous question before starting new one
            if current_question:
                validate_question(current_question, current_question_start_line, lang)
                questions.append(current_question)
            
            current_question = {
                'question': text[1:].strip(),
                'options': [],
                'correct_option_id': None
            }
            current_question_start_line = i
            
        elif text.startswith('+'):
            if not current_question:
                msg = Messages.get("PARSER_OPTION_WITHOUT_QUESTION", lang).format(line=i, text=text[:20] + "...")
                raise ParserError(msg)
                
            if current_question['correct_option_id'] is not None:
                msg = Messages.get("PARSER_MULTIPLE_CORRECT", lang).format(line=i, start_line=current_question_start_line)
                raise ParserError(msg)
            
            current_question['correct_option_id'] = len(current_question['options'])
            current_question['options'].append(text[1:].strip())
            
        elif text.startswith('='):
            if not current_question:
                msg = Messages.get("PARSER_OPTION_WITHOUT_QUESTION", lang).format(line=i, text=text[:20] + "...")
                raise ParserError(msg)
                
            current_question['options'].append(text[1:].strip())
            
        else:
            # Check if this line looks like it belongs to format but has wrong prefix
            if text.startswith(('-', '*', '•', 'A)', 'B)', '1.')):
                 msg = Messages.get("PARSER_INVALID_PREFIX", lang).format(line=i, text=text[:20] + "...")
                 raise ParserError(msg)
            # Otherwise ignore random text (headers, footers, instructions)

    # Add the last question
    if current_question:
        validate_question(current_question, current_question_start_line, lang)
        questions.append(current_question)

    if not questions:
        raise ParserError(Messages.get("PARSER_NO_QUIZZES", lang))

    return questions

def validate_question(q: Dict, line_num: int, lang: str):
    """Ensures a question has text, options and a correct answer."""
    if not q['question']:
        raise ParserError(Messages.get("PARSER_EMPTY_QUESTION", lang).format(line=line_num))
        
    if len(q['options']) < 2:
        msg = Messages.get("PARSER_FEW_OPTIONS", lang).format(line=line_num, text=q['question'][:20] + "...", count=len(q['options']))
        raise ParserError(msg)
        
    if q['correct_option_id'] is None:
        msg = Messages.get("PARSER_NO_CORRECT_OPTION", lang).format(line=line_num, text=q['question'][:20] + "...")
        raise ParserError(msg)
        
    if len(q['options']) > 10:
        # Telegram limit: max 10 options. Slice silently as requested.
        q['options'] = q['options'][:10]
        # Ensure correct option is still within range if it was > 9? 
        # Actually parse_docx_to_json sets correct_option_id based on index.
        # If the correct answer was index 11, it is now lost or invalid.
        # But 'correct_option_id' is an integer index.
        # If we slice options, we must ensure correct_option_id < 10.
        if q['correct_option_id'] >= 10:
            # If the correct answer was cut off, this question is invalid functionally.
            # But "format" might be okay. 
            # However, a quiz without correct answer is broken.
            # I will raise error ONLY if correct answer is lost by slicing.
            raise ParserError(Messages.get("PARSER_NO_CORRECT_OPTION", lang).format(line=line_num, text=q['question'][:20] + "..."))
    
    # Check length limits for Telegram - Truncate instead of error
    if len(q['question']) > 300:
        q['question'] = q['question'][:297] + "..."

    for i, opt in enumerate(q['options']):
        if len(opt) > 100:
             q['options'][i] = opt[:97] + "..."
