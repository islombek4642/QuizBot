"""
Pytest configuration and fixtures for QuizBot tests.
"""
import sys
import os
import pytest

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture
def sample_questions():
    """Sample quiz questions for testing"""
    return [
        {
            "question": "What is 2+2?",
            "options": ["3", "4", "5", "6"],
            "correct_option_id": 1
        },
        {
            "question": "What is the capital of Uzbekistan?",
            "options": ["Tashkent", "Samarkand", "Bukhara", "Khiva"],
            "correct_option_id": 0
        }
    ]


@pytest.fixture
def legacy_format_lines():
    """Sample lines in legacy format"""
    return [
        "?What is Python?",
        "+A programming language",
        "=A snake",
        "=A movie",
        "?What is 1+1?",
        "+2",
        "=1",
        "=3"
    ]


@pytest.fixture
def abc_format_lines():
    """Sample lines in ABC format"""
    return [
        "1. What is the largest planet?",
        "A) Earth",
        "B) Mars",
        "#C) Jupiter",
        "D) Saturn",
        "2. What is H2O?",
        "#A) Water",
        "B) Salt",
        "C) Sugar"
    ]
