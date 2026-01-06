import unittest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from datetime import datetime, timezone

from reddit.reddit_client import RedditClient
from models import Post, Author

class TestRedditClient(unittest.TestCase):
    """Test suite for RedditClient class"""

    def setUp(self):
        """Set up test fixtures"""
        self.client_id = "fake_id"
        self.client_secret = "fake_secret"
        self.user_agent = "fake_agent"
        self.mock_pool = MagicMock()
        
        # Patch praw.Reddit to avoid actual network calls during init
        with patch('praw.Reddit') as mock_reddit:
            self.client = RedditClient(
                self.client_id, 
                self.client_secret, 
                self.user_agent, 
                self.mock_pool
            )
            self.mock_reddit_instance = self.client.reddit

    def test_init(self):
        """Test initialization"""
        self.assertEqual(self.client.connection_pool, self.mock_pool)
        self.assertIsNotNone(self.client.reddit)

    @patch('reddit.reddit_client.get_author_data')
    def test_get_author_data_cache_hit(self, mock_get_author_data):
        """Test _get_author_data_from_cache_or_api with cache hit"""
        # Setup
        mock_author_praw = Mock()
        mock_author_praw.name = "test_user"
        
        cached_author = Author(
            username="test_user",
            created_utc=datetime.now(timezone.utc),
            comment_karma=100,
            link_karma=200,
            last_updated=datetime.now(timezone.utc)
        )
        mock_get_author_data.return_value = cached_author
        
        authors_to_cache = []
        
        # Execute
        result = self.client._get_author_data_from_cache_or_api(mock_author_praw, authors_to_cache)
        
        # Verify
        self.assertEqual(result, cached_author)
        mock_get_author_data.assert_called_once_with(self.mock_pool, "test_user")
        self.assertEqual(len(authors_to_cache), 0) # Should not add to cache list if hit

    @patch('reddit.reddit_client.get_author_data')
    def test_get_author_data_cache_miss(self, mock_get_author_data):
        """Test _get_author_data_from_cache_or_api with cache miss"""
        # Setup
        mock_get_author_data.return_value = None
        
        mock_author_praw = Mock()
        mock_author_praw.name = "test_user"
        mock_author_praw.created_utc = 1609459200.0 # 2021-01-01
        mock_author_praw.comment_karma = 50
        mock_author_praw.link_karma = 10
        
        authors_to_cache = []
        
        # Execute
        result = self.client._get_author_data_from_cache_or_api(mock_author_praw, authors_to_cache)
        
        # Verify
        self.assertEqual(result.username, "test_user")
        self.assertEqual(result.comment_karma, 50)
        self.assertEqual(len(authors_to_cache), 1)
        self.assertEqual(authors_to_cache[0], result)

    def test_get_author_data_deleted_user(self):
        """Test _get_author_data_from_cache_or_api with None author (deleted)"""
        authors_to_cache = []
        result = self.client._get_author_data_from_cache_or_api(None, authors_to_cache)
        
        self.assertEqual(result.username, "[DELETED]")
        self.assertEqual(len(authors_to_cache), 0)

    @patch('storage.database_manager.get_authors_batch')
    @patch('reddit.reddit_client.RedditClient._batch_upsert_authors')
    def test_fetch_recent_posts(self, mock_batch_upsert, mock_get_authors_batch):
        """Test fetch_recent_posts yielding posts"""
        # Setup mocks
        mock_subreddit = Mock()
        self.mock_reddit_instance.subreddit.return_value = mock_subreddit
        
        # Create mock posts
        mock_post = Mock()
        mock_post.id = "post1"
        mock_post.title = "Test Post"
        mock_post.selftext = "Content"
        mock_post.link_flair_text = "News"
        mock_post.created_utc = 1609459200.0
        mock_post.score = 100
        mock_post.upvote_ratio = 0.9
        mock_post.num_comments = 10
        mock_post.author.name = "user1"
        mock_post.author.created_utc = 1609459200.0
        mock_post.author.comment_karma = 100
        mock_post.author.link_karma = 200
        
        # Create mock comments
        mock_comment = Mock()
        mock_comment.id = "comment1"
        mock_comment.body = "Test Comment"
        mock_comment.created_utc = 1609459200.0
        mock_comment.submission.id = "post1"
        mock_comment.score = 20
        mock_comment.author.name = "user2"
        mock_comment.author.created_utc = 1609459200.0
        mock_comment.author.comment_karma = 50
        mock_comment.author.link_karma = 10
        
        mock_subreddit.new.return_value = [mock_post]
        mock_subreddit.comments.return_value = [mock_comment]
        
        # Mock database batch get to return empty (all cache miss)
        mock_get_authors_batch.return_value = {}
        
        # Execute
        results = list(self.client.fetch_recent_posts("test_sub", limit=1))
        
        # Verify
        self.assertEqual(len(results), 2) # 1 post + 1 comment
        
        # Check Post
        self.assertEqual(results[0].id, "post1")
        self.assertEqual(results[0].type, "post")
        self.assertEqual(results[0].user_id, "user1")
        
        # Check Comment
        self.assertEqual(results[1].id, "comment1")
        self.assertEqual(results[1].type, "comment")
        self.assertEqual(results[1].user_id, "user2")

    def test_fetch_recent_posts_api_error(self):
        """Test graceful handling of API errors"""
        self.mock_reddit_instance.subreddit.side_effect = Exception("API Error")
        
        results = list(self.client.fetch_recent_posts("test_sub"))
        
        self.assertEqual(len(results), 0)

if __name__ == "__main__":
    unittest.main()
