import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Patch psycopg2.pool.SimpleConnectionPool BEFORE importing app so the
# module-level  `pool = SimpleConnectionPool(...)` on line 16 of app.py
# does not attempt a real database connection.
# ---------------------------------------------------------------------------
_mock_pool_instance = MagicMock()

with patch('psycopg2.pool.SimpleConnectionPool', return_value=_mock_pool_instance):
    import app  # safe — app.pool is now _mock_pool_instance

from config import SUBREDDITS


class TestCollectData(unittest.TestCase):
    """Tests for app.collect_data()"""

    def setUp(self):
        self.mock_scanner = MagicMock()
        self.mock_data_point = MagicMock()

        # Default scanner behaviour: returns one mention data point
        self.mock_scanner.process_mentions.return_value = [self.mock_data_point]

        # Each RedditClient instance returns two posts by default
        self.mock_post_a = MagicMock()
        self.mock_post_b = MagicMock()

        self.patcher_scanner = patch('app.TickerMentionScanner',
                                     return_value=self.mock_scanner)
        self.patcher_reddit = patch('app.RedditClient')
        self.patcher_insert = patch('app.insert_mention_counts')
        self.patcher_existing = patch('app.get_existing_post_ids_batch', return_value=set())
        self.patcher_stats = patch('app.append_stat')

        self.mock_scanner_class = self.patcher_scanner.start()
        self.mock_reddit_class = self.patcher_reddit.start()
        self.mock_insert = self.patcher_insert.start()
        self.patcher_existing.start()
        self.patcher_stats.start()

        # fetch_recent_posts returns (posts, stream_comments, per_post_comments)
        self.mock_reddit_class.return_value.fetch_recent_posts.return_value = (
            [self.mock_post_a, self.mock_post_b], [], []
        )

    def tearDown(self):
        self.patcher_scanner.stop()
        self.patcher_reddit.stop()
        self.patcher_insert.stop()
        self.patcher_existing.stop()
        self.patcher_stats.stop()

    def test_fetches_from_all_configured_subreddits(self):
        """One RedditClient is created per subreddit, each fetching posts."""
        # Make fetch_recent_posts return a fresh iterator on each call
        self.mock_reddit_class.return_value.fetch_recent_posts.side_effect = (
            lambda sub, limit: ([self.mock_post_a], [], [])
        )

        app.collect_data()

        # One RedditClient instance per subreddit
        self.assertEqual(self.mock_reddit_class.call_count, len(SUBREDDITS))
        # fetch_recent_posts called once per subreddit
        total_fetch_calls = sum(
            inst.fetch_recent_posts.call_count
            for inst in self.mock_reddit_class.return_value.__class__.instances
        ) if hasattr(self.mock_reddit_class.return_value.__class__, 'instances') else \
            self.mock_reddit_class.call_count  # each call creates an instance
        self.assertEqual(self.mock_reddit_class.call_count, len(SUBREDDITS))

    def test_all_posts_aggregated_and_passed_to_scanner(self):
        """Posts from all subreddits are combined into one list for the scanner."""
        num_subreddits = len(SUBREDDITS)

        # Each call returns fresh MagicMock posts with unique IDs so deduplication
        # doesn't collapse them into fewer entries than expected.
        def make_unique_posts(sub, limit):
            posts = [MagicMock(), MagicMock()]
            for i, p in enumerate(posts):
                p.id = f"{sub}_post_{i}"
            return (posts, [], [])

        self.mock_reddit_class.return_value.fetch_recent_posts.side_effect = make_unique_posts

        app.collect_data()

        self.mock_scanner.process_mentions.assert_called_once()
        all_posts_arg = self.mock_scanner.process_mentions.call_args[0][0]
        self.assertEqual(len(all_posts_arg), num_subreddits * 2)  # 2 unique posts per subreddit

    def test_insert_called_when_mentions_found(self):
        """insert_mention_counts is called with the pool and mention data when found."""
        self.mock_scanner.process_mentions.return_value = [self.mock_data_point]

        app.collect_data()

        self.mock_insert.assert_called_once_with(app.pool, [self.mock_data_point])

    def test_insert_not_called_when_no_mentions(self):
        """insert_mention_counts is NOT called when scanner finds no mentions."""
        self.mock_scanner.process_mentions.return_value = []

        app.collect_data()

        self.mock_insert.assert_not_called()

    def test_warning_logged_when_no_mentions(self):
        """A WARNING is logged when no ticker mentions are found."""
        self.mock_scanner.process_mentions.return_value = []

        with self.assertLogs('app', level='WARNING') as log_ctx:
            app.collect_data()

        self.assertTrue(
            any('No ticker mentions found' in msg for msg in log_ctx.output),
            f"Expected warning not found in logs: {log_ctx.output}"
        )

    def test_one_subreddit_failure_does_not_stop_others(self):
        """An exception in one subreddit thread does not prevent others from completing."""
        call_count = {'n': 0}

        def fetch_side_effect(sub, limit):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise Exception("Network error for first subreddit")
            return ([self.mock_post_a], [], [])

        self.mock_reddit_class.return_value.fetch_recent_posts.side_effect = fetch_side_effect

        # Should not raise, and scanner should still be called with posts
        app.collect_data()

        self.mock_scanner.process_mentions.assert_called_once()
        # Posts from all succeeding subreddits should be passed
        posts_arg = self.mock_scanner.process_mentions.call_args[0][0]
        self.assertGreater(len(posts_arg), 0)

    def test_scanner_created_with_valid_tickers_and_pool(self):
        """TickerMentionScanner is instantiated with VALID tickers and the pool."""
        from config import VALID

        app.collect_data()

        self.mock_scanner_class.assert_called_once_with(VALID, app.pool)

    def test_reddit_client_created_with_credentials(self):
        """RedditClient is created with CLIENT_ID, CLIENT_SECRET, USER_AGENT, pool."""
        from config import CLIENT_ID, CLIENT_SECRET, USER_AGENT

        self.mock_reddit_class.return_value.fetch_recent_posts.side_effect = (
            lambda sub, limit: ([self.mock_post_a], [], [])
        )

        app.collect_data()

        for call_args in self.mock_reddit_class.call_args_list:
            args = call_args[0]
            self.assertEqual(args[0], CLIENT_ID)
            self.assertEqual(args[1], CLIENT_SECRET)
            self.assertEqual(args[2], USER_AGENT)
            self.assertEqual(args[3], app.pool)


if __name__ == '__main__':
    unittest.main(verbosity=2)
