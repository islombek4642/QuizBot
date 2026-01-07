import docx
from typing import List, Dict, Optional
from core.logger import logger

class ParserError(Exception):
    """Custom exception for parser errors."""
    pass

def parse_docx_to_json(file_path: str) -> List[Dict]:
    """
    Parses a docx file with strict validation.
    Format:
    ?Question
    +Correct Answer
    =Wrong Answer
    """
    try:
        doc = docx.Document(file_path)
    except Exception as e:
        logger.error("Failed to open docx file", path=file_path, error=str(e))
        raise ParserError(f"Faylni ochib bo'lmadi: {str(e)}")

    questions = []
    current_question = None

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        if text.startswith('?'):
            # Save previous question if valid
            if current_question:
                validate_question(current_question)
                questions.append(current_question)
            
            current_question = {
                'question': text[1:].strip(),
                'options': [],
                'correct_option_id': None
            }
        elif text.startswith('+'):
            if current_question:
                if current_question['correct_option_id'] is not None:
                    logger.warning("Multiple correct options found for question", question=current_question['question'])
                
                current_question['correct_option_id'] = len(current_question['options'])
                current_question['options'].append(text[1:].strip())
        elif text.startswith('='):
            if current_question:
                current_question['options'].append(text[1:].strip())

    # Add the last question
    if current_question:
        try:
            validate_question(current_question)
            questions.append(current_question)
        except ParserError as e:
            logger.warning("Skipping invalid last question", error=str(e))

    if not questions:
        raise ParserError("Faylda yaroqli testlar topilmadi. Formatni tekshiring.")

    return questions

def validate_question(q: Dict):
    """Ensures a question has text, options and a correct answer."""
    if not q['question']:
        raise ParserError("Savol matni bo'sh bo'lishi mumkin emas.")
    if len(q['options']) < 2:
        raise ParserError(f"Savolda kamida 2 ta variant bo'lishi kerak: {q['question'][:30]}...")
    if q['correct_option_id'] is None:
        raise ParserError(f"Savolda to'g'ri javob ko'rsatilmagan: {q['question'][:30]}...")
    if len(q['options']) > 10:
        raise ParserError(f"Telegram pollari maksimal 10 ta variantni qo'llab-quvvatlaydi.")
    
    # Check length limits for Telegram
    if len(q['question']) > 300:
        q['question'] = q['question'][:297] + "..."
    
    for i in range(len(q['options'])):
        if len(q['options'][i]) > 100:
            q['options'][i] = q['options'][i][:97] + "..."
