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

def test_multi_word_phrase_scored_atomically(analyser):
    """Multi-word bearish phrases score negative even when the constituent words are neutral."""
    # "paper hands" is bearish; "paper" and "hands" alone are not.
    paper_hands_score = analyser.analyse_text("Bunch of paper hands in here.")
    neutral_score = analyser.analyse_text("Bunch of paper in here.")
    assert paper_hands_score < -0.2
    assert paper_hands_score < neutral_score

    # "short squeeze" flips the otherwise-neutral 'short' into a positive signal.
    assert analyser.analyse_text("Classic short squeeze setup.") > 0.2


def test_emoji_sentiment(analyser):
    """Registered emojis contribute to sentiment even without any pattern match."""
    assert analyser.analyse_text("AAPL 📈📈📈") > 0.2
    assert analyser.analyse_text("AAPL 📉📉📉") < -0.2
    assert analyser.analyse_text("Rainbow 🐻 says bye") < 0.0


def test_modality_dampening(analyser):
    """Conditional/hypothetical language dampens score magnitude."""
    declarative = analyser.analyse_text("This stock is going to the moon.")
    conditional = analyser.analyse_text("If this might moon maybe it could go up.")
    assert declarative > 0.3
    # conditional still positive but materially weaker
    assert abs(conditional) < abs(declarative)


def test_sarcasm_dampening(analyser):
    """Sarcasm markers halve magnitude but do not flip sign."""
    sincere = analyser.analyse_text("This is a great buy.")
    sarcastic = analyser.analyse_text("This is a great buy /s")
    assert sincere > 0.3
    assert 0 < sarcastic < sincere  # dampened, not flipped

    # Clown + bullish language
    clown = analyser.analyse_text("Going to the moon 🤡")
    straight = analyser.analyse_text("Going to the moon")
    assert 0 < clown < straight


def test_question_dampening(analyser):
    """Posts dominated by questions score weaker than declarative equivalents."""
    declarative = analyser.analyse_text("This is a great buy. Going to the moon.")
    question = analyser.analyse_text("Is this a great buy? Going to the moon?")
    assert declarative > 0.3
    assert 0 < question < declarative


def test_categorise_sentiment(analyser):
    """Test sentiment categorization."""
    assert analyser.categorise_sentiment(0.6) == SentimentCategory.VERY_POSITIVE
    assert analyser.categorise_sentiment(0.2) == SentimentCategory.POSITIVE
    assert analyser.categorise_sentiment(0.0) == SentimentCategory.NEUTRAL
    assert analyser.categorise_sentiment(-0.2) == SentimentCategory.NEGATIVE
    assert analyser.categorise_sentiment(-0.6) == SentimentCategory.VERY_NEGATIVE
