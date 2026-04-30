import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from reddit.ticker_mention_scanner import TickerMentionScanner
from models import Post, MentionDataPoint

class TestTickerMentionScanner(unittest.TestCase):
    """Test suite for TickerMentionScanner class"""

    def setUp(self) -> None:
        """Runs before each test to set up common test data"""
        self.valid_tickers = {'AAPL', 'TSLA', 'NVDA', 'GME', 'BYND'}
        # Create a mock connection pool for tests
        self.mock_pool = MagicMock()
        self.scanner = TickerMentionScanner(self.valid_tickers, self.mock_pool)
        self.test_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # Default values for Post fields
        self.default_user_id = 'test_user'
        self.default_score = 0
        self.default_num_comments = 0
        self.default_author_quality = None

        # Stub the post_mentions writer for every test — psycopg2.extras.execute_batch
        # can't run against a MagicMock cursor.
        self._save_pm_patcher = patch.object(self.scanner, '_batch_save_post_mentions')
        self._save_pm_patcher.start()

    def tearDown(self) -> None:
        """Runs after each test to before cleanup"""
        self._save_pm_patcher.stop()

    #Test 1: Ticker detection from post
    def test_finds_single_ticker(self):
        """Tests that the scanner correctly identifies a single ticker from a post/comment"""
        post = Post(id='test1', 
                    subreddit='pennystocks', 
                    type='post', 
                    text='tim cooked AAPL!', 
                    link_flair_text=None,
                    created_utc=self.test_timestamp.timestamp(),
                    origin_id=None,
                    user_id=self.default_user_id,
                    score=self.default_score,
                    upvote_ratio=1.0,
                    num_comments=self.default_num_comments,
                    author_quality=self.default_author_quality
                )

        #Mock database
        with patch.object(self.scanner, '_get_existing_posts_ids', return_value=set()):
            with patch.object(self.scanner, '_batch_save_posts'):
                result = self.scanner.process_mentions([post])
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticker, 'AAPL')
        self.assertEqual(result[0].subreddit, 'pennystocks')
        self.assertEqual(result[0].mention_count, 1)
    
    #Test 2: Multiple tickers in one post
    def test_finds_multiple_tickers_in_post(self):
        """Tests that the scanner identifies multiple tickers from a post/comment"""
        post = Post(
            id='test2', 
            subreddit='pennystocks', 
            type='comment', 
            text='AAPL, or TSLA? or NVDA.', 
            link_flair_text=None,
            created_utc=self.test_timestamp.timestamp(),
            origin_id=None,
            user_id=self.default_user_id,
            score=self.default_score,
            upvote_ratio=1.0,
            num_comments=self.default_num_comments,
            author_quality=self.default_author_quality
        )

        #Mock database
        with patch.object(self.scanner, '_get_existing_posts_ids', return_value=set()):
            with patch.object(self.scanner, '_batch_save_posts'):
                result = self.scanner.process_mentions([post])
        
        tickers_found = {dp.ticker for dp in result}
        self.assertEqual(len(tickers_found), 3)
        self.assertEqual(len(result), 3)

        self.assertIn('AAPL', tickers_found)
        self.assertIn('TSLA', tickers_found)
        self.assertIn('NVDA', tickers_found)
    
    # Test 3: Ignores invalid tickers
    def test_ignores_invalid_tickers(self):
        """Test that invalid tickers are filtered out"""
        post = Post(
            id='test3',
            subreddit='pennystocks',
            type='post',
            text='AAPL is good but FAKE and INVALID are not real tickers',
            link_flair_text=None,
            created_utc=self.test_timestamp.timestamp(),
            origin_id=None,
            user_id=self.default_user_id,
            score=self.default_score,
            upvote_ratio=1.0,
            num_comments=self.default_num_comments,
            author_quality=self.default_author_quality
        )
        
        with patch.object(self.scanner, '_get_existing_posts_ids', return_value=set()):
            with patch.object(self.scanner, '_batch_save_posts'):
                result = self.scanner.process_mentions([post])
        
        # Should only find AAPL
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticker, 'AAPL')

    # Test 4: Counts only one mention per ticker per post
    def test_counts_one_mention_per_ticker_per_post(self):
        """Test that multiple occurrences of the same ticker in one post count as one mention"""
        post = Post(
            id='test4',
            subreddit='pennystocks',
            type='post',
            text='AAPL AAPL AAPL to the moon! AAPL is the best!',
            link_flair_text=None,
            created_utc=self.test_timestamp.timestamp(),
            origin_id=None,
            user_id=self.default_user_id,
            score=self.default_score,
            upvote_ratio=1.0,
            num_comments=self.default_num_comments,
            author_quality=self.default_author_quality
        )

        with patch.object(self.scanner, '_get_existing_posts_ids', return_value=set()):
            with patch.object(self.scanner, '_batch_save_posts'):
                result = self.scanner.process_mentions([post])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].mention_count, 1)

    # Test 5: Aggregates mentions across multiple posts
    def test_aggregates_mentions_across_posts(self):
        """Test that mentions are aggregated correctly across multiple posts"""
        posts = [
            Post(id='test5a', subreddit='pennystocks', type='post', text='AAPL is great', 
                 link_flair_text=None, created_utc=self.test_timestamp.timestamp(), origin_id=None, user_id=self.default_user_id,
                 score=self.default_score, upvote_ratio=1.0, num_comments=self.default_num_comments,
                 author_quality=self.default_author_quality),
            Post(id='test5b', subreddit='pennystocks', type='post', text='I love AAPL too!', 
                 link_flair_text=None, created_utc=self.test_timestamp.timestamp(), origin_id=None, user_id=self.default_user_id,
                 score=self.default_score, upvote_ratio=1.0, num_comments=self.default_num_comments,
                 author_quality=self.default_author_quality),
            Post(id='test5c', subreddit='pennystocks', type='comment', text='AAPL AAPL, NVDA?', 
                 link_flair_text=None, created_utc=self.test_timestamp.timestamp(), origin_id=None, user_id=self.default_user_id,
                 score=self.default_score, upvote_ratio=1.0, num_comments=self.default_num_comments,
                 author_quality=self.default_author_quality)
        ]
        
        with patch.object(self.scanner, '_get_existing_posts_ids', return_value=set()):
            with patch.object(self.scanner, '_batch_save_posts'):
                result = self.scanner.process_mentions(posts)
        
        #AAPL and NVDA
        self.assertEqual(len(result), 2)

        aapl_entry = next(dp for dp in result if dp.ticker == 'AAPL')
        nvda_entry = next(dp for dp in result if dp.ticker == 'NVDA')

        # One mention per ticker per post: 3 posts mention AAPL = 3, 1 post mentions NVDA = 1
        self.assertEqual(aapl_entry.ticker, 'AAPL')
        self.assertEqual(aapl_entry.mention_count, 3)
        self.assertEqual(nvda_entry.mention_count, 1)

    # Test 6: Handles different subreddits separately
    def test_separates_mentions_by_subreddit(self):
        """Test that mentions in different subreddits create seperate MentionDataPoints"""
        posts = [
            Post(id='test6a', subreddit='pennystocks', type='post', text='AAPL', 
                 link_flair_text=None, created_utc=self.test_timestamp.timestamp(), origin_id=None, user_id=self.default_user_id,
                 score=self.default_score, upvote_ratio=1.0, num_comments=self.default_num_comments,
                 author_quality=self.default_author_quality),
            Post(id='test6b', subreddit='wallstreetbets', type='post', text='AAPL AAPL', 
                 link_flair_text=None, created_utc=self.test_timestamp.timestamp(), origin_id=None, user_id=self.default_user_id,
                 score=self.default_score, upvote_ratio=1.0, num_comments=self.default_num_comments,
                 author_quality=self.default_author_quality)
        ]
        
        with patch.object(self.scanner, '_get_existing_posts_ids', return_value=set()):
            with patch.object(self.scanner, '_batch_save_posts'):
                result = self.scanner.process_mentions(posts)
        
        # Should have 2 entries
        self.assertEqual(len(result), 2)
        
        # Check counts for each subreddit
        pennystocks_entry = next(dp for dp in result if dp.subreddit == 'pennystocks')
        wsb_entry = next(dp for dp in result if dp.subreddit == 'wallstreetbets')
        
        self.assertEqual(pennystocks_entry.mention_count, 1)
        self.assertEqual(wsb_entry.mention_count, 1)
    
    # Test 7: Skips already processed posts
    def test_skips_existing_posts(self):
        """Test that previously processed posts are skipped"""
        posts = [
            Post(id='existing1', subreddit='pennystocks', type='post', text='AAPL', 
                 link_flair_text=None, created_utc=self.test_timestamp.timestamp(), origin_id=None, user_id=self.default_user_id,
                 score=self.default_score, upvote_ratio=1.0, num_comments=self.default_num_comments,
                 author_quality=self.default_author_quality),
            Post(id='new1', subreddit='pennystocks', type='post', text='TSLA', 
                 link_flair_text=None, created_utc=self.test_timestamp.timestamp(), origin_id=None, user_id=self.default_user_id,
                 score=self.default_score, upvote_ratio=1.0, num_comments=self.default_num_comments,
                 author_quality=self.default_author_quality)
        ]
        
        # Mock that 'existing1' is already in database
        with patch('reddit.ticker_mention_scanner.get_existing_post_ids_batch', 
                         return_value={'existing1'}):
            with patch.object(self.scanner, '_batch_save_posts') as mock_save:
                result = self.scanner.process_mentions(posts)
                # Should only save the new post
                self.assertEqual(mock_save.call_count, 1)
                saved_posts = mock_save.call_args[0][0]
                self.assertEqual(len(saved_posts), 1)
                self.assertEqual(saved_posts[0][0], 'new1')
        
        # Should only count TSLA (from new post)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticker, 'TSLA')
    
    # Test 8: Handles empty post list
    def test_handles_empty_post_list(self):
        """Test that empty post list returns empty results"""
        with patch.object(self.scanner, '_get_existing_posts_ids', return_value=set()):
            with patch.object(self.scanner, '_batch_save_posts'):
                result = self.scanner.process_mentions([])
        
        self.assertEqual(len(result), 0)
    
    # Test 9: Lowercase ticker mentions are now matched (inverted from prior behaviour).
    def test_finds_lowercase_tickers(self):
        """Lowercase / mixed-case ticker text is detected and uppercased."""
        post = Post(
            id='test9',
            subreddit='pennystocks',
            type='post',
            text='I think aapl is good but TSLA is better',
            link_flair_text=None,
            created_utc=self.test_timestamp.timestamp(),
            origin_id=None,
            user_id=self.default_user_id,
            score=self.default_score,
            upvote_ratio=1.0,
            num_comments=self.default_num_comments,
            author_quality=self.default_author_quality
        )

        with patch.object(self.scanner, '_batch_save_posts'):
            with patch.object(self.scanner, '_batch_save_post_mentions'):
                result = self.scanner.process_mentions([post])

        tickers_found = {dp.ticker for dp in result}
        self.assertEqual(tickers_found, {'AAPL', 'TSLA'})

    def test_finds_cashtag_lowercase(self):
        """`$tsla` (lowercase, with cashtag) maps to TSLA."""
        post = Post(
            id='test9b',
            subreddit='pennystocks',
            type='post',
            text='loading up on $tsla calls',
            link_flair_text=None,
            created_utc=self.test_timestamp.timestamp(),
            origin_id=None,
            user_id=self.default_user_id,
            score=self.default_score,
            upvote_ratio=1.0,
            num_comments=self.default_num_comments,
            author_quality=self.default_author_quality,
        )

        with patch.object(self.scanner, '_batch_save_posts'):
            with patch.object(self.scanner, '_batch_save_post_mentions'):
                result = self.scanner.process_mentions([post])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticker, 'TSLA')

    def test_finds_mixed_case(self):
        """Mixed-case bare tickers (e.g. `Aapl`) are detected."""
        post = Post(
            id='test9c',
            subreddit='pennystocks',
            type='post',
            text='Aapl earnings tomorrow, Tsla too',
            link_flair_text=None,
            created_utc=self.test_timestamp.timestamp(),
            origin_id=None,
            user_id=self.default_user_id,
            score=self.default_score,
            upvote_ratio=1.0,
            num_comments=self.default_num_comments,
            author_quality=self.default_author_quality,
        )

        with patch.object(self.scanner, '_batch_save_posts'):
            with patch.object(self.scanner, '_batch_save_post_mentions'):
                result = self.scanner.process_mentions([post])

        tickers_found = {dp.ticker for dp in result}
        self.assertEqual(tickers_found, {'AAPL', 'TSLA'})

    def test_lowercase_blacklist_suppresses_common_word(self):
        """Lowercase common-word collisions (`it`, `are`) are filtered, but the
        same symbols in uppercase still match."""
        scanner = TickerMentionScanner({'TSLA', 'IT', 'ARE'}, self.mock_pool)

        # Lowercase `it` and `are` are blacklisted; lowercase `tsla` is not.
        self.assertEqual(
            scanner.find_tickers_in_text("buying tsla but it dipped, are you?"),
            {'TSLA'},
        )
        # Uppercase IT / ARE still pass through (intentional ticker references).
        self.assertEqual(
            scanner.find_tickers_in_text("IT shops ARE buying"),
            {'IT', 'ARE'},
        )
        # Mixed: lowercase `it` filtered, uppercase `ARE` kept.
        self.assertEqual(
            scanner.find_tickers_in_text("ARE you sure it works?"),
            {'ARE'},
        )

    def test_uppercase_bare_ticker_still_detected(self):
        """Regression guard: uppercase bare tickers continue to match."""
        scanner = TickerMentionScanner({'TSLA'}, self.mock_pool)
        self.assertEqual(
            scanner.find_tickers_in_text("TSLA to the moon"),
            {'TSLA'},
        )

    # Test 10: Buckets mentions by post creation hour, not scanner run time
    def test_buckets_mentions_by_post_creation_hour(self):
        """Test that posts created in different hours produce separate MentionDataPoints
        with timestamps matching each post's creation hour, not the current time."""
        hour_12 = datetime(2025, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
        hour_13 = datetime(2025, 1, 1, 13, 45, 0, tzinfo=timezone.utc)

        posts = [
            Post(id='t10a', subreddit='pennystocks', type='post', text='AAPL to the moon',
                 link_flair_text=None, created_utc=hour_12.timestamp(), origin_id=None,
                 user_id=self.default_user_id, score=self.default_score, upvote_ratio=1.0,
                 num_comments=self.default_num_comments, author_quality=self.default_author_quality),
            Post(id='t10b', subreddit='pennystocks', type='post', text='Buying more AAPL',
                 link_flair_text=None, created_utc=hour_13.timestamp(), origin_id=None,
                 user_id=self.default_user_id, score=self.default_score, upvote_ratio=1.0,
                 num_comments=self.default_num_comments, author_quality=self.default_author_quality),
        ]

        with patch.object(self.scanner, '_batch_save_posts'):
            result = self.scanner.process_mentions(posts)

        self.assertEqual(len(result), 2)

        timestamps = {dp.timestamp for dp in result}
        expected_12 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        expected_13 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        self.assertIn(expected_12, timestamps)
        self.assertIn(expected_13, timestamps)

        for dp in result:
            self.assertEqual(dp.mention_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)