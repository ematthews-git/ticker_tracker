import sys
from pathlib import Path
# Add src to path to match application behavior
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from unittest.mock import MagicMock, patch
from analysis.mention_analyser import MentionAnalyser
from models import Post, SentimentCategory

@pytest.fixture
def mock_sentiment_analyser():
    with patch('analysis.mention_analyser.SentimentAnalyser') as MockClass:
        mock_instance = MockClass.return_value
        yield mock_instance

@pytest.fixture
def mention_analyser(mock_sentiment_analyser):
    return MentionAnalyser()

@pytest.fixture
def sample_posts():
    return [
        Post(
            id="1",
            subreddit="stocks",
            type="post",
            text="I think AAPL is going to the moon!",
            link_flair_text=None,
            created_utc=1000.0,
            origin_id=None,
            user_id="user1",
            score=10,
            upvote_ratio=0.9,
            num_comments=5,
            author_quality=None
        ),
        Post(
            id="2",
            subreddit="investing",
            type="post",
            text="TSLA is going to crash hard.",
            link_flair_text=None,
            created_utc=2000.0,
            origin_id=None,
            user_id="user2",
            score=20,
            upvote_ratio=0.8,
            num_comments=10,
            author_quality=None
        ),
        Post(
            id="3",
            subreddit="stocks",
            type="post",
            text="AAPL earnings are next week.",
            link_flair_text=None,
            created_utc=3000.0,
            origin_id=None,
            user_id="user3",
            score=5,
            upvote_ratio=1.0,
            num_comments=2,
            author_quality=None
        )
    ]

def test_analyse_post_sentiment(mention_analyser, mock_sentiment_analyser):
    """Test analysing a single post's sentiment."""
    post = Post(
        id="1", 
        subreddit="stocks", 
        type="post", 
        text="Text", 
        link_flair_text=None,
        created_utc=1.0, 
        origin_id=None,
        user_id="user1",
        score=1, 
        upvote_ratio=1.0,
        num_comments=1,
        author_quality=None
    )
    mock_sentiment_analyser.analyse_text.return_value = 0.5
    
    score = mention_analyser.analyse_post_sentiment(post)
    
    assert score == 0.5
    mock_sentiment_analyser.analyse_text.assert_called_with("Text")

def test_analyse_ticker_sentiment(mention_analyser, mock_sentiment_analyser, sample_posts):
    """Test analysing sentiment for a specific ticker across posts."""
    # Setup mock returns
    # Post 1 (AAPL): 0.8
    # Post 2 (TSLA): -0.8 (Should be ignored for AAPL)
    # Post 3 (AAPL): 0.0
    
    def side_effect(text):
        if "moon" in text: return 0.8
        if "crash" in text: return -0.8
        return 0.0
    
    mock_sentiment_analyser.analyse_text.side_effect = side_effect
    
    result = mention_analyser.analyse_ticker_sentiment(sample_posts, "AAPL")
    
    # Expected:
    # Sentiments: [0.8, 0.0]
    # Avg: 0.4
    # Positive (>0.1): 1/2 = 0.5
    # Negative (<-0.1): 0/2 = 0.0
    
    assert result['avg_sentiment'] == 0.4
    assert result['positive_ratio'] == 0.5
    assert result['negative_ratio'] == 0.0

def test_analyse_ticker_sentiment_no_matches(mention_analyser, sample_posts):
    """Test behaviour when ticker is not found."""
    result = mention_analyser.analyse_ticker_sentiment(sample_posts, "XYZ")
    assert result['avg_sentiment'] == 0.0
    assert result['positive_ratio'] == 0.0
    assert result['negative_ratio'] == 0.0

def test_calculate_weighted_sentiment(mention_analyser, mock_sentiment_analyser, sample_posts):
    """Test weighted sentiment calculation."""
    # Post 1 (AAPL): Score 10, Comments 5 -> Weight = 10 + 2.5 = 12.5. Sentiment 0.8
    # Post 3 (AAPL): Score 5, Comments 2 -> Weight = 5 + 1.0 = 6.0. Sentiment 0.0
    
    def side_effect(text):
        if "moon" in text: return 0.8
        return 0.0
    mock_sentiment_analyser.analyse_text.side_effect = side_effect
    
    weighted_score = mention_analyser.calculate_weighted_sentiment(sample_posts, "AAPL")
    
    # Calculation:
    # (0.8 * 12.5 + 0.0 * 6.0) / (12.5 + 6.0)
    # 10.0 / 18.5 = 0.5405...
    
    assert weighted_score == round(10.0 / 18.5, 4)

def test_get_sentiment_cat_distribution(mention_analyser, mock_sentiment_analyser, sample_posts):
    """Test sentiment category distribution."""
    # Mock categories
    mock_sentiment_analyser.categorise_sentiment.side_effect = [
        SentimentCategory.VERY_POSITIVE, # Post 1
        SentimentCategory.NEUTRAL        # Post 3
    ]
    # Mock analyse_text to ensure it's called (though return value doesn't matter for this test as we mock categorise)
    mock_sentiment_analyser.analyse_text.return_value = 0.0 

    dist = mention_analyser.get_sentiment_cat_distribution(sample_posts, "AAPL")
    
    assert dist['VERY_POSITIVE'] == 1
    assert dist['NEUTRAL'] == 1
    assert 'NEGATIVE' not in dist or dist['NEGATIVE'] == 0

def test_analyse_sentiment_trend(mention_analyser, mock_sentiment_analyser, sample_posts):
    """Test sentiment trend analysis."""
    # Post 1: time 1000.0, sentiment 0.8
    # Post 3: time 3000.0, sentiment 0.0
    
    def side_effect(text):
        if "moon" in text: return 0.8
        return 0.0
    mock_sentiment_analyser.analyse_text.side_effect = side_effect
    
    trend = mention_analyser.analyse_sentiment_trend(sample_posts, "AAPL")
    
    assert len(trend) == 2
    assert trend[0] == (1000.0, 0.8)
    assert trend[1] == (3000.0, 0.0)

def test_compare_subreddit_sentiment(mention_analyser, mock_sentiment_analyser, sample_posts):
    """Test comparing sentiment across subreddits."""
    # Post 1 (stocks): 0.8
    # Post 3 (stocks): 0.0
    
    def side_effect(text):
        if "moon" in text: return 0.8
        return 0.0
    mock_sentiment_analyser.analyse_text.side_effect = side_effect
    
    comparison = mention_analyser.compare_subreddit_sentiment(sample_posts, "AAPL")
    
    assert "stocks" in comparison
    assert comparison["stocks"] == 0.4 # Average of 0.8 and 0.0
    assert "investing" not in comparison # TSLA post not included
