import docx
from typing import List, Dict, Optional
from core.logger import logger

class ParserError(Exception):
    """Custom exception for parser errors."""
    pass

def parse_docx_to_json(file_path: str) -> List[Dict]:
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
        raise ParserError(f"Faylni ochib bo'lmadi: {str(e)}")

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
                validate_question(current_question, current_question_start_line)
                questions.append(current_question)
            
            current_question = {
                'question': text[1:].strip(),
                'options': [],
                'correct_option_id': None
            }
            current_question_start_line = i
            
        elif text.startswith('+'):
            if not current_question:
                raise ParserError(f"Xatolik {i}-qatorda: Javob varianti savolsiz kiritilgan. Variant: '{text[:20]}...'")
                
            if current_question['correct_option_id'] is not None:
                raise ParserError(f"Xatolik {i}-qatorda: Bitta savolda bir nechta to'g'ri javob (+) bo'lishi mumkin emas. Savol {current_question_start_line}-qatorda boshlangan.")
            
            current_question['correct_option_id'] = len(current_question['options'])
            current_question['options'].append(text[1:].strip())
            
        elif text.startswith('='):
            if not current_question:
                raise ParserError(f"Xatolik {i}-qatorda: Javob varianti savolsiz kiritilgan. Variant: '{text[:20]}...'")
                
            current_question['options'].append(text[1:].strip())
            
        else:
            # Check if this line looks like it belongs to format but has wrong prefix
            if text.startswith(('-', '*', '•', 'A)', 'B)', '1.')):
                 raise ParserError(f"Xatolik {i}-qatorda: Noto'g'ri format. Savollar '?' bilan, to'g'ri javoblar '+' bilan, xato javoblar '=' bilan boshlanishi kerak. Matn: '{text[:20]}...'")
            # Otherwise ignore random text (headers, footers, instructions)

    # Add the last question
    if current_question:
        validate_question(current_question, current_question_start_line)
        questions.append(current_question)

    if not questions:
        raise ParserError("Faylda yaroqli testlar topilmadi. Formatni tekshiring: ?Savol, +To'g'ri, =Xato")

    return questions

def validate_question(q: Dict, line_num: int):
    """Ensures a question has text, options and a correct answer."""
    if not q['question']:
        raise ParserError(f"Xatolik {line_num}-qatorda: Savol matni bo'sh.")
        
    if len(q['options']) < 2:
        raise ParserError(f"Xatolik {line_num}-qatorda: '{q['question'][:20]}...' savolida kamida 2 ta variant bo'lishi kerak. Hozirgi soni: {len(q['options'])}")
        
    if q['correct_option_id'] is None:
        raise ParserError(f"Xatolik {line_num}-qatorda: '{q['question'][:20]}...' savolida to'g'ri javob ko'rsatilmagan. To'g'ri javob oldiga '+' qo'ying.")
        
    if len(q['options']) > 10:
        raise ParserError(f"Xatolik {line_num}-qatorda: Telegram pollari maksimal 10 ta variantni qo'llab-quvvatlaydi. Ssizda {len(q['options'])} ta bor.")
    
    # Check length limits for Telegram
    if len(q['question']) > 300:
        # Instead of truncating, warn user? Or strict error?
        # User asked for error checking.
        # Strict mode: raise error.
        # But practical usage usually prefers truncation for slight oversights.
        # I'll stick to truncation but maybe log? No, strict is better for quality. 
        # But existing code truncated. User asked to "tell where the error is".
        # I will raise error for length too, as that's helpful feedback.
        raise ParserError(f"Xatolik {line_num}-qatorda: Savol matni juda uzun (maksimal 300 belgi). Sizda: {len(q['question'])} belgi.")

    for i, opt in enumerate(q['options']):
        if len(opt) > 100:
             raise ParserError(f"Xatolik {line_num}-qatorda: '{opt[:20]}...' javob varianti juda uzun (maksimal 100 belgi). Sizda: {len(opt)} belgi.")
