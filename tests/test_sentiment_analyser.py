import sys
from pathlib import Path
# Add src to path to match application behavior
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from analysis.sentiment_analyser import SentimentAnalyser
from models import SentimentCategory

@pytest.fixture
def analyser():
    return SentimentAnalyser()

def test_initialization(analyser):
    """Test that the analyser is initialized with the correct lexicon updates."""
    # Check a few custom terms
    assert 'moon' in analyser.analyser.lexicon
    assert analyser.analyser.lexicon['moon'] == 3.5
    assert 'rugpull' in analyser.analyser.lexicon
    assert analyser.analyser.lexicon['rugpull'] == -4.0

def test_normalise_text(analyser):
    """Test text normalization."""
    text = "Check out [Google](https://google.com)   it is   cool!"
    cleaned = analyser._normalise_text(text)
    assert cleaned == "Check out Google it is cool!"
    
    text_with_url = "This is a link https://example.com/foo"
    cleaned = analyser._normalise_text(text_with_url)
    assert cleaned == "This is a link"

def test_apply_pattern_boost(analyser):
    """Test pattern boosting."""
    # Base score 0
    text = "to the moon"
    boosted = analyser._apply_pattern_boost(text, 0.0)
    assert boosted == 0.2

    text = "rug pull"
    boosted = analyser._apply_pattern_boost(text, 0.0)
    assert boosted == -0.2
    
    # Check clamping
    boosted = analyser._apply_pattern_boost("to the moon", 0.9)
    assert boosted == 1.0
    
    boosted = analyser._apply_pattern_boost("rug pull", -0.9)
    assert boosted == -1.0

def test_analyse_text(analyser):
    """Test sentiment analysis of text."""
    # Empty text
    assert analyser.analyse_text("") == 0.0
    assert analyser.analyse_text("   ") == 0.0
    
    # Bullish text
    assert analyser.analyse_text("This stock is going to the moon! 🚀") > 0.5
    
    # Bearish text
    assert analyser.analyse_text("This is a rug pull scam.") < -0.5
    
    # Neutral text
    # "The stock is trading at $10" might have slight sentiment due to VADER, but should be near 0
    score = analyser.analyse_text("The stock is trading at $10.")
    assert -0.2 < score < 0.2

def test_analyse_batch(analyser):
    """Test batch analysis."""
    texts = ["Moon!", "Scam!", "Neutral."]
    scores = analyser.analyse_batch(texts)
    assert len(scores) == 3
    assert scores[0] > 0
    assert scores[1] < 0

def test_categorise_sentiment(analyser):
    """Test sentiment categorization."""
    assert analyser.categorise_sentiment(0.6) == SentimentCategory.VERY_POSITIVE
    assert analyser.categorise_sentiment(0.2) == SentimentCategory.POSITIVE
    assert analyser.categorise_sentiment(0.0) == SentimentCategory.NEUTRAL
    assert analyser.categorise_sentiment(-0.2) == SentimentCategory.NEGATIVE
    assert analyser.categorise_sentiment(-0.6) == SentimentCategory.VERY_NEGATIVE
