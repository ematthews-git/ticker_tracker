import unittest
from unittest.mock import Mock, patch, MagicMock, PropertyMock

from reddit.reddit_client import RedditClient


class TestRedditClient(unittest.TestCase):
    """Test suite for RedditClient class"""

    def setUp(self):
        """Set up test fixtures"""
        self.client_id = "fake_id"
        self.client_secret = "fake_secret"
        self.user_agent = "fake_agent"
        self.mock_pool = MagicMock()

        # Patch praw.Reddit to avoid actual network calls during init
        with patch("praw.Reddit") as mock_reddit:
            self.client = RedditClient(
                self.client_id, self.client_secret, self.user_agent, self.mock_pool
            )
            self.mock_reddit_instance = self.client.reddit

    def test_init(self):
        """Test initialization"""
        self.assertEqual(self.client.connection_pool, self.mock_pool)
        self.assertIsNotNone(self.client.reddit)

    def test_fetch_recent_posts(self):
        """Test fetch_recent_posts returns (posts, stream_comments, per_post_comments)"""
        mock_subreddit = Mock()
        self.mock_reddit_instance.subreddit.return_value = mock_subreddit

        # Mock post with num_comments=0 so per-post comment fetching is skipped
        mock_post = Mock()
        mock_post.id = "post1"
        mock_post.title = "Test Post"
        mock_post.selftext = "Content"
        mock_post.link_flair_text = "News"
        mock_post.created_utc = 1609459200.0
        mock_post.score = 100
        mock_post.upvote_ratio = 0.9
        mock_post.num_comments = 0
        mock_post.author.name = "user1"
        mock_post.author.created_utc = 1609459200.0
        mock_post.author.comment_karma = 100
        mock_post.author.link_karma = 200

        # Mock stream comment
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

        posts, stream_comments, per_post_comments = self.client.fetch_recent_posts(
            "test_sub", limit=1
        )

        # 1 post, 1 stream comment, 0 per-post comments (num_comments=0)
        self.assertEqual(len(posts), 1)
        self.assertEqual(len(stream_comments), 1)
        self.assertEqual(len(per_post_comments), 0)

        self.assertEqual(posts[0].id, "post1")
        self.assertEqual(posts[0].type, "post")
        self.assertEqual(posts[0].user_id, "user1")

        self.assertEqual(stream_comments[0].id, "comment1")
        self.assertEqual(stream_comments[0].type, "comment")
        self.assertEqual(stream_comments[0].user_id, "user2")

    def test_fetch_recent_posts_per_post_comments(self):
        """Test that per-post comments are fetched for posts with num_comments > 0"""
        mock_subreddit = Mock()
        self.mock_reddit_instance.subreddit.return_value = mock_subreddit

        mock_post = Mock()
        mock_post.id = "post1"
        mock_post.title = "Active Post"
        mock_post.selftext = ""
        mock_post.link_flair_text = None
        mock_post.created_utc = 1609459200.0
        mock_post.score = 50
        mock_post.upvote_ratio = 0.8
        mock_post.num_comments = 5
        mock_post.author.name = "user1"
        mock_post.author.created_utc = 1609459200.0
        mock_post.author.comment_karma = 100
        mock_post.author.link_karma = 50

        mock_per_post_comment = Mock()
        mock_per_post_comment.id = "ppc1"
        mock_per_post_comment.body = "Per-post comment"
        mock_per_post_comment.created_utc = 1609459300.0
        mock_per_post_comment.submission.id = "post1"
        mock_per_post_comment.score = 5
        mock_per_post_comment.author.name = "user2"
        mock_per_post_comment.author.created_utc = 1609459200.0
        mock_per_post_comment.author.comment_karma = 20
        mock_per_post_comment.author.link_karma = 5

        mock_post.comments.list.return_value = [mock_per_post_comment]
        mock_subreddit.new.return_value = [mock_post]
        mock_subreddit.comments.return_value = []

        posts, stream_comments, per_post_comments = self.client.fetch_recent_posts(
            "test_sub", limit=1, top_posts_for_comments=1
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(len(stream_comments), 0)
        self.assertEqual(len(per_post_comments), 1)
        self.assertEqual(per_post_comments[0].id, "ppc1")
        mock_post.comments.replace_more.assert_called_once_with(limit=5, threshold=10)

    def test_fetch_recent_posts_api_error(self):
        """API errors propagate so callers can record the failure (used to be silently swallowed)."""
        self.mock_reddit_instance.subreddit.side_effect = Exception("API Error")

        with self.assertRaises(Exception) as ctx:
            self.client.fetch_recent_posts("test_sub")
        self.assertIn("API Error", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
