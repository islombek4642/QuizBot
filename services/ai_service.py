import json
import httpx
import asyncio
import subprocess
import tempfile
import os
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
        
    def _log_rate_limits(self, headers: httpx.Headers):
        """Extract and log Groq rate limit information."""
        remaining_requests = headers.get("x-ratelimit-remaining-requests")
        remaining_tokens = headers.get("x-ratelimit-remaining-tokens")
        
        if remaining_requests or remaining_tokens:
            logger.info(
                "Groq rate limits",
                rem_req=remaining_requests,
                rem_tok=remaining_tokens,
                reset_req=headers.get("x-ratelimit-reset-requests"),
                reset_tok=headers.get("x-ratelimit-reset-tokens")
            )
        
    async def generate_quiz(self, topic: str, count: int = 30, lang: str = "UZ", 
                           on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None) -> Tuple[List[Dict], Optional[str]]:
        """
        Generate quiz questions using Groq AI with batching for large counts.
        """
        if not self.api_key:
            return [], "GROQ_API_KEY is not configured"
        
        all_questions = []
        batch_size = 15 # Generate 15 questions per batch for reliability
        
        # Build base system prompt
        if lang == "UZ":
            system_prompt = """Siz universitet darajasidagi professional professor va imtihon tuzuvchi ekspertsiz. 
Mavzuni chuqur tahlil qiling va talabalarni imtihonga tayyorlash uchun sifatli, Oliy ta'lim standartlariga mos testlar yarating.

SAVOL SIFATIGA QO'YILADIGAN TALABLAR:
1. **Bilim chuqurligi**: Shunchaki faktlarni eslab qolish emas (masalan, "Nima u?"), balki mantiqiy xulosa qilish, tahlil va amaliy qo'llashni talab qiladigan savollar tuzing.
2. **Murakkablik**: Savollar o'ylantiradigan, bir nechta faktni bog'laydigan bo'lsin. Bloom taksonomiyasining tahlil va sintez darajalaridan foydalaning.
3. **Aldamchi variantlar (Distractors)**: Noto'g'ri javoblar ham mantiqan to'g'riga o'xshash, mohiyatan xato, lekin chalg'ituvchi bo'lishi shart. Hazil yoki ochiq-oydin xato variantlar ishlatmang.
4. **Akademik til**: Rasmiy va ilmiy uslubda, imlo xatolarisiz yozing.

Javobni FAQAT quyidagi JSON formatida qaytaring:
{
  "questions": [
    {
      "question": "Mantiqan murakkab savol matni",
      "options": ["To'g'ri javob", "Chalg'ituvchi xato 1", "Chalg'ituvchi xato 2", "Chalg'ituvchi xato 3"],
      "correct_option_id": 0
    }
  ]
}

correct_option_id har doim 0 bo'lsin. Savol max 280 belgi, variantlar max 100 belgi."""
        else:
            system_prompt = """You are a professional university professor and examination expert. 
Analyze the topic deeply and create high-quality quiz questions that meet academic standards for higher education.

QUESTION QUALITY REQUIREMENTS:
1. **Depth of Knowledge**: Do not ask simple recall questions (e.g., "What is X?"). Focus on questions that require logical reasoning, analysis, and practical application.
2. **Complexity**: Questions should be thought-provoking and connect multiple concepts. Use higher-level Bloom's Taxonomy levels (Analysis, Evaluation).
3. **High-Quality Distractors**: Incorrect options must be plausible and logically related to the topic, yet factually incorrect. Avoid obvious or generic wrong answers.
4. **Academic Style**: Use formal, precise, and professional language.

Return ONLY the following JSON format:
{
  "questions": [
    {
      "question": "Logically complex question text",
      "options": ["Correct answer", "Plausible distractor 1", "Plausible distractor 2", "Plausible distractor 3"],
      "correct_option_id": 0
    }
  ]
}

correct_option_id should always be 0. Question max 280 chars, options max 100 chars."""

        async with httpx.AsyncClient(timeout=180.0) as client:
            current_count = 0
            attempts_without_progress = 0
            max_attempts = 10 # Allow up to 10 batches with 0 questions before giving up
            
            while current_count < count and attempts_without_progress < max_attempts:
                remaining = count - current_count
                to_generate = min(batch_size, remaining)
                
                if lang == "UZ":
                    user_prompt = f"Mavzu: {topic}\nSoni: {to_generate} ta yangi (takrorlanmagan) test savoli yarating."
                else:
                    user_prompt = f"Topic: {topic}\nGenerate {to_generate} new (unique) quiz questions."
                
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
                                {"role": "user", "content": user_prompt}
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.8,
                            "max_completion_tokens": 4096
                        }
                    )
                    
                    self._log_rate_limits(response.headers)
                    
                    if response.status_code != 200:
                        logger.error("Groq API error", status=response.status_code, error=response.text)
                        if all_questions: break 
                        return [], f"API error: {response.status_code}"
                    
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Parse JSON
                    try:
                        batch_raw = json.loads(content)
                        batch_questions = batch_raw.get("questions", [])
                    except Exception as je:
                        logger.error("JSON parse failed in batch", error=str(je), content=content[:500])
                        attempts_without_progress += 1
                        continue
                    
                    # Validate and fix
                    validated = self._validate_questions(batch_questions)
                    
                    if not validated:
                        logger.warning("Batch returned 0 valid questions", content=content[:500])
                        attempts_without_progress += 1
                        continue
                        
                    all_questions.extend(validated)
                    
                    # Check if we actually made progress
                    if len(all_questions) > current_count:
                        current_count = len(all_questions)
                        attempts_without_progress = 0
                        logger.info("Generation progress", topic=topic, current=current_count, total=count)
                        # Report progress
                        if on_progress:
                            await on_progress(min(current_count, count), count)
                    else:
                        attempts_without_progress += 1
                        
                    # Slow down slightly to avoid extreme rate limits
                    if count > 50:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.exception(f"Batch generation error: {e}")
                    if all_questions: break
                    return [], f"Generation error: {str(e)}"
        
        if attempts_without_progress >= max_attempts:
            logger.error("AI generation stopped due to lack of progress", topic=topic, generated=len(all_questions))
            if not all_questions:
                return [], "AI failed to generate valid questions after multiple attempts"

        if not all_questions:
            return [], "Failed to generate any questions"
            
        logger.info("AI quiz generated", topic=topic, total=len(all_questions))
        return all_questions[:count], None

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

        # Reduced chunk size to ensure AI output fits within token limits (e.g. 4096 tokens)
        # 4,000 characters of input text usually contains 20-25 questions.
        chunk_size = 4000 
        chunks = [raw_text[i:i + chunk_size] for i in range(0, len(raw_text), chunk_size)]
        
        all_questions = []
        
        system_prompt = """You are a professional university examination expert. Your task is to convert RAW TEXT into a high-quality JSON array of quiz questions.

QUALITY RULES:
1. **Academic Rigor**: Extract complex concepts and transform them into challenging questions that require analysis, not just recall.
2. **Plausible Distractors**: Create incorrect options that are logically related to the text and challenging for students. Avoid obvious or generic wrong answers.
3. **Formal Tone**: Ensure all questions and options use formal, professional language.
4. **Accuracy**: Ensure the "correct" answer is strictly derived from the provided text.

FORMAT RULES:
1. Each question MUST have EXACTLY 4 options.
2. Index 0 of 'options' MUST be the correct answer.
3. 'correct_option_id' MUST always be 0.
4. Question: max 280 chars. 
5. Option: max 100 chars.
6. Language: {lang_full}.

JSON SCHEMA:
[
  {{
    "question": "Logically challenging question text",
    "options": ["Correct answer based on text", "Plausible distractor 1", "Plausible distractor 2", "Plausible distractor 3"],
    "correct_option_id": 0
  }}
]"""

        lang_full = "Uzbek" if lang == "UZ" else "English"
        system_prompt = system_prompt.format(lang_full=lang_full)

        async with httpx.AsyncClient(timeout=180.0) as client:
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                
                try:
                    # Slow down AI to avoid rate limits when having many chunks
                    if i > 0:
                        await asyncio.sleep(1.5)

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
                                {"role": "user", "content": f"Convert to JSON:\n\n{chunk}"}
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.1,
                            "max_completion_tokens": 4096
                        }
                    )
                    
                    self._log_rate_limits(response.headers)
                    
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


def extract_text_from_doc(doc_bytes: bytes) -> str:
    """Extract text from legacy .doc using antiword (Linux)."""
    import subprocess
    import tempfile
    import os
    
    text = ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".doc") as tmp:
        tmp.write(doc_bytes)
        tmp_path = tmp.name

    try:
        # Run antiword command
        process = subprocess.run(
            ["antiword", tmp_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        if process.returncode == 0:
            text = process.stdout
        else:
            # Fallback: if it's not a legacy Word doc, maybe it's a renamed .docx?
            if "is not a Word Document" in process.stderr:
                logger.info("Antiword failed, trying docx fallback", user_id=None)
                try:
                    return extract_text_from_docx(doc_bytes)
                except:
                    pass
            logger.error("Antiword failed", stderr=process.stderr)
    except Exception as e:
        logger.error("DOC extraction failed", error=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    return text
