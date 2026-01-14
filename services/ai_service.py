import json
import httpx
from typing import List, Dict, Optional, Tuple, Callable, Awaitable
from core.config import settings
from core.logger import logger
import fitz  # PyMuPDF
from docx import Document as DocxDocument


class AIService:
    """Service for AI-powered quiz generation using Groq API."""
    
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        
    async def generate_quiz(self, topic: str, count: int = 30, lang: str = "UZ") -> Tuple[List[Dict], Optional[str]]:
        """
        Generate quiz questions using Groq AI.
        
        Args:
            topic: The topic for quiz generation
            count: Number of questions to generate (default 30)
            lang: Language code (UZ or EN)
            
        Returns:
            Tuple of (questions list, error message or None)
        """
        if not self.api_key:
            return [], "GROQ_API_KEY is not configured"
        
        # Build the prompt
        if lang == "UZ":
            system_prompt = """Siz test yaratuvchi sun'iy intellektsiz. Sizning vazifangiz berilgan mavzu bo'yicha test savollarini yaratish.

MUHIM QOIDALAR:
1. Har bir savol aniq va tushunarli bo'lsin
2. Har bir savolda AYNAN 4 ta javob varianti bo'lsin (1 ta to'g'ri, 3 ta noto'g'ri)
3. Savol matni maksimal 280 belgidan oshmasin
4. Har bir javob varianti maksimal 95 belgidan oshmasin
5. Savollar bir-biridan farq qilsin, takrorlanmasin
6. Javoblar mantiqiy va ishonchli bo'lsin

Javobni FAQAT quyidagi JSON formatida qaytaring, boshqa hech narsa yozmang:
[
  {
    "question": "Savol matni",
    "options": ["To'g'ri javob", "Noto'g'ri 1", "Noto'g'ri 2", "Noto'g'ri 3"],
    "correct_option_id": 0
  }
]

correct_option_id har doim 0 bo'lsin (birinchi variant to'g'ri javob)."""

            user_prompt = f"Quyidagi mavzu bo'yicha {count} ta test savoli yarating: {topic}"
        else:
            system_prompt = """You are a quiz generator AI. Your task is to create quiz questions on the given topic.

IMPORTANT RULES:
1. Each question should be clear and understandable
2. Each question must have EXACTLY 4 answer options (1 correct, 3 incorrect)
3. Question text must not exceed 280 characters
4. Each answer option must not exceed 95 characters
5. Questions should be unique and not repeat
6. Answers should be logical and believable

Return ONLY the following JSON format, nothing else:
[
  {
    "question": "Question text",
    "options": ["Correct answer", "Wrong 1", "Wrong 2", "Wrong 3"],
    "correct_option_id": 0
  }
]

correct_option_id should always be 0 (first option is the correct answer)."""

            user_prompt = f"Create {count} quiz questions on the following topic: {topic}"

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 8000
                    }
                )
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error("Groq API error", status=response.status_code, error=error_text)
                    return [], f"API error: {response.status_code}"
                
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                # Parse JSON from response
                questions = self._parse_response(content)
                
                if not questions:
                    return [], "Failed to parse AI response"
                
                # Validate and fix questions
                validated_questions = self._validate_questions(questions)
                
                logger.info("AI quiz generated", topic=topic, count=len(validated_questions))
                return validated_questions, None
                
        except httpx.TimeoutException:
            logger.error("Groq API timeout", topic=topic)
            return [], "Request timeout - please try again"
        except Exception as e:
            logger.error("AI generation error", error=str(e), topic=topic)
            return [], str(e)

    async def convert_quiz(self, raw_text: str, lang: str = "UZ", on_progress: Optional[Callable[[int, int, int], Awaitable[None]]] = None) -> Tuple[List[Dict], Optional[str]]:
        """
        Convert raw text from PDF/Word to our quiz format using AI.
        Processes in batches to avoid token limits.
        
        Args:
            raw_text: The text to convert
            lang: Language code
            on_progress: Async callback(current_batch, total_batches, found_questions)
        """
        if not self.api_key:
            return [], "GROQ_API_KEY is not configured"

        # Smaller chunk size ensures we don't exceed output token limits for complex text
        # Approx 10,000 chars per chunk
        chunk_size = 10000 
        chunks = [raw_text[i:i + chunk_size] for i in range(0, len(raw_text), chunk_size)]
        
        all_questions = []
        
        system_prompt = """You are a professional test converter. Your task is to extract quiz questions from RAW TEXT and convert them to JSON format.

RULES:
1. Identify each question and its options.
2. Each question MUST have EXACTLY 4 options (1 correct, 3 incorrect).
3. Question text max 280 chars.
4. Option text max 95 chars.
5. If the correct answer is marked, use it. If not, determine it.
6. Language: {lang_full}

Return ONLY a valid JSON array of objects. No additional text, no explanations.
[
  {{
    "question": "Question text...",
    "options": ["Correct", "Wrong 1", "Wrong 2", "Wrong 3"],
    "correct_option_id": 0
  }}
]"""

        lang_full = "Uzbek" if lang == "UZ" else "English"
        system_prompt = system_prompt.format(lang_full=lang_full)

        async with httpx.AsyncClient(timeout=180.0) as client:
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {i+1}/{len(chunks)} for conversion")
                
                try:
                    response = await client.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"Convert this text to quiz questions JSON:\n\n{chunk}"}
                            ],
                            "temperature": 0.1, # Even lower for stricter format
                            "max_tokens": 8000 # Increased limit
                        }
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Batch {i+1} failed", status=response.status_code)
                        continue
                        
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    chunk_questions = self._parse_response(content)
                    if chunk_questions:
                        validated = self._validate_questions(chunk_questions)
                        all_questions.extend(validated)
                        
                    # Trigger progress callback
                    if on_progress:
                        await on_progress(i + 1, len(chunks), len(all_questions))
                        
                except Exception as e:
                    logger.error(f"Error in batch {i+1}", error=str(e))
                    continue

        if not all_questions:
            return [], "Could not extract any questions from the file."
            
        return all_questions, None
    
    def _parse_response(self, content: str) -> List[Dict]:
        """Parse JSON from AI response, handling potential formatting issues and truncation."""
        content = content.strip()
        
        # Helper to try parsing a string as JSON
        def try_parse(s):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                # If it's a truncated array, try to close it
                if s.startswith('[') and not s.endswith(']'):
                    try:
                        # Try to find the last complete object
                        last_obj_end = s.rfind('}')
                        if last_obj_end != -1:
                            fixed = s[:last_obj_end + 1] + ']'
                            return json.loads(fixed)
                    except:
                        pass
                return None

        # 1. Try direct parse
        parsed = try_parse(content)
        if parsed is not None: return parsed
        
        # 2. Try to extract JSON from markdown code block
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                parsed = try_parse(content[start:end].strip())
                if parsed is not None: return parsed
            else:
                # Truncated code block
                parsed = try_parse(content[start:].strip())
                if parsed is not None: return parsed

        # 3. Try to find JSON array
        if "[" in content:
            start = content.find("[")
            end = content.rfind("]") + 1
            if end > start:
                parsed = try_parse(content[start:end])
                if parsed is not None: return parsed
            else:
                # Truncated but has start
                parsed = try_parse(content[start:])
                if parsed is not None: return parsed
        
        logger.error("Failed to parse AI response", content=content[:500])
        return []
    
    def _validate_questions(self, questions: List[Dict]) -> List[Dict]:
        """Validate and fix questions to meet requirements."""
        validated = []
        
        for q in questions:
            try:
                # Check required fields
                if "question" not in q or "options" not in q or "correct_option_id" not in q:
                    continue
                
                # Ensure exactly 4 options
                options = q["options"]
                if len(options) < 4:
                    continue
                if len(options) > 4:
                    options = options[:4]
                
                # Truncate if too long
                question_text = q["question"][:280] if len(q["question"]) > 280 else q["question"]
                options = [opt[:95] if len(opt) > 95 else opt for opt in options]
                
                # Ensure correct_option_id is valid
                correct_id = q["correct_option_id"]
                if not isinstance(correct_id, int) or correct_id < 0 or correct_id >= len(options):
                    correct_id = 0
                
                validated.append({
                    "question": question_text,
                    "options": options,
                    "correct_option_id": correct_id
                })
                
            except Exception as e:
                logger.warning("Question validation failed", error=str(e))
                continue
        
        return validated


def generate_docx_from_questions(questions: List[Dict], title: str) -> bytes:
    """
    Generate a .docx file from questions in our format.
    
    Args:
        questions: List of question dicts with 'question', 'options', 'correct_option_id'
        title: Quiz title for the document
        
    Returns:
        bytes: The docx file content
    """
    from docx import Document
    from docx.shared import Pt
    from io import BytesIO
    
    doc = Document()
    
    # Add title
    title_para = doc.add_heading(title, 0)
    
    # Add each question in our format
    for i, q in enumerate(questions, 1):
        # Add question
        doc.add_paragraph(f"?{q['question']}")
        
        # Add options
        correct_id = q['correct_option_id']
        for j, opt in enumerate(q['options']):
            if j == correct_id:
                doc.add_paragraph(f"+{opt}")
            else:
                doc.add_paragraph(f"={opt}")
        
        # Add empty line between questions
        doc.add_paragraph()
    
    # Save to bytes
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF using PyMuPDF."""
    text = ""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        logger.error("PDF extraction failed", error=str(e))
    return text


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract text from Word document including tables using python-docx."""
    text = ""
    try:
        from io import BytesIO
        doc = DocxDocument(BytesIO(docx_bytes))
        
        # 1. Extract from paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"
        
        # 2. Extract from tables
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    if cell_text:
                        row_text.append(cell_text)
                if row_text:
                    text += " | ".join(row_text) + "\n"
                    
    except Exception as e:
        logger.error("DOCX extraction failed", error=str(e))
    return text
