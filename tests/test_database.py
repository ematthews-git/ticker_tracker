import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from storage.database_manager import insert_mention_counts, fetch_ticker_mentions, fetch_popular_tickers
from models import MentionDataPoint


class TestDatabase(unittest.TestCase):
    """Test suite for Database module"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_db_url = "postgresql://test:test@localhost/test_db"
        self.test_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.test_timestamp2 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        
        # Sample MentionDataPoint for testing
        self.sample_data_point = MentionDataPoint(
            ticker='AAPL',
            subreddit='pennystocks',
            timestamp=self.test_timestamp,
            mention_count=10,
            unique_users=5,
            total_score=100,
            total_comments=20,
            avg_sentiment=0.5
        )


class TestInsertMentionCounts(TestDatabase):
    """Test suite for insert_mention_counts function"""

    @patch('storage.Database.execute_batch')
    def test_inserts_single_mention(self, mock_execute_batch):
        """Test inserting a single MentionDataPoint"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        insert_mention_counts(mock_pool, [self.sample_data_point])

        # Verify connection was retrieved from pool
        mock_pool.getconn.assert_called_once()
        mock_conn.cursor.assert_called_once()

        # Verify execute_batch was called with correct data
        mock_execute_batch.assert_called_once()
        call_args = mock_execute_batch.call_args
        
        # Check that cursor was passed as first argument
        self.assertEqual(call_args[0][0], mock_cursor)
        
        # Check SQL query
        self.assertIn('INSERT INTO mentions', call_args[0][1])
        self.assertIn('ON CONFLICT', call_args[0][1])
        
        # Check data format
        data = call_args[0][2]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0][0], 'AAPL')  # ticker (uppercase)
        self.assertEqual(data[0][1], 'pennystocks')  # subreddit
        self.assertEqual(data[0][2], self.test_timestamp)  # timestamp
        self.assertEqual(data[0][3], 10)  # mention_count
        self.assertEqual(data[0][4], 5)  # unique_users
        self.assertEqual(data[0][5], 100)  # total_score
        self.assertEqual(data[0][6], 20)  # total_comments
        self.assertEqual(data[0][7], 0.5)  # avg_sentiment

        # Verify commit was called
        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

    @patch('storage.Database.execute_batch')
    def test_inserts_multiple_mentions(self, mock_execute_batch):
        """Test inserting multiple MentionDataPoints"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        data_points = [
            self.sample_data_point,
            MentionDataPoint(
                ticker='TSLA',
                subreddit='wallstreetbets',
                timestamp=self.test_timestamp2,
                mention_count=20,
                unique_users=10,
                total_score=200,
                total_comments=30,
                avg_sentiment=0.7
            )
        ]

        insert_mention_counts(mock_pool, data_points)

        # Verify execute_batch was called with 2 data points
        call_args = mock_execute_batch.call_args
        data = call_args[0][2]
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0][0], 'AAPL')
        self.assertEqual(data[1][0], 'TSLA')

    def test_handles_empty_list(self):
        """Test that empty list returns early without database operations"""
        mock_pool = MagicMock()
        insert_mention_counts(mock_pool, [])
        
        # Should not get connection from pool
        mock_pool.getconn.assert_not_called()

    @patch('storage.Database.execute_batch')
    def test_uppercases_ticker(self, mock_execute_batch):
        """Test that ticker is converted to uppercase"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        data_point = MentionDataPoint(
            ticker='aapl',  # lowercase
            subreddit='pennystocks',
            timestamp=self.test_timestamp,
            mention_count=10,
            unique_users=5,
            total_score=100,
            total_comments=20,
            avg_sentiment=0.5
        )

        insert_mention_counts(mock_pool, [data_point])

        call_args = mock_execute_batch.call_args
        data = call_args[0][2]
        self.assertEqual(data[0][0], 'AAPL')  # Should be uppercase

    @patch('storage.Database.execute_batch')
    @patch('storage.Database.logger')
    def test_handles_database_error(self, mock_logger, mock_execute_batch):
        """Test error handling when database operation fails"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Simulate database error
        mock_execute_batch.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            insert_mention_counts(mock_pool, [self.sample_data_point])

        # Verify rollback was called
        mock_conn.rollback.assert_called_once()
        # Verify error was logged
        mock_logger.error.assert_called_once()
        # Verify cleanup still happens
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)


class TestFetchTickerMentions(TestDatabase):
    """Test suite for fetch_ticker_mentions function"""

    def test_fetches_mentions_for_ticker(self):
        """Test fetching mentions for a specific ticker"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock database response
        mock_cursor.fetchall.return_value = [
            ('AAPL', 'pennystocks', self.test_timestamp, 10, 5, 100, 20, 0.5),
            ('AAPL', 'wallstreetbets', self.test_timestamp2, 15, 8, 150, 25, 0.6)
        ]

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_ticker_mentions(mock_pool, 'AAPL', start_date, end_date)

        # Verify connection was retrieved from pool
        mock_pool.getconn.assert_called_once()
        # Verify query was executed with correct parameters
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        self.assertIn('SELECT', call_args[0][0])
        self.assertIn('WHERE ticker = %s', call_args[0][0])
        self.assertIn('BETWEEN', call_args[0][0])
        
        # Verify parameters
        params = call_args[0][1]
        self.assertEqual(params[0], 'AAPL')  # Uppercase ticker
        self.assertEqual(params[1], start_date)
        self.assertEqual(params[2], end_date)

        # Verify results
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].ticker, 'AAPL')
        self.assertEqual(result[0].subreddit, 'pennystocks')
        self.assertEqual(result[0].mention_count, 10)
        self.assertEqual(result[1].subreddit, 'wallstreetbets')
        self.assertEqual(result[1].mention_count, 15)
        # Verify connection was returned to pool
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_uppercases_ticker_in_query(self):
        """Test that ticker is uppercased in query"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        fetch_ticker_mentions(mock_pool, 'aapl', start_date, end_date)

        # Verify ticker was uppercased
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 'AAPL')

    def test_returns_empty_list_when_no_results(self):
        """Test that empty list is returned when no mentions found"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_ticker_mentions(mock_pool, 'AAPL', start_date, end_date)

        self.assertEqual(len(result), 0)
        self.assertIsInstance(result, list)

    def test_converts_data_types_correctly(self):
        """Test that database types are converted to Python types correctly"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock database returning string/int/float types (as they might come from DB)
        mock_cursor.fetchall.return_value = [
            ('AAPL', 'pennystocks', self.test_timestamp, '10', '5', '100', '20', '0.5')
        ]

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_ticker_mentions(mock_pool, 'AAPL', start_date, end_date)

        # Verify types are converted
        self.assertEqual(result[0].mention_count, 10)
        self.assertIsInstance(result[0].mention_count, int)
        self.assertEqual(result[0].unique_users, 5)
        self.assertIsInstance(result[0].unique_users, int)
        self.assertEqual(result[0].total_score, 100)
        self.assertIsInstance(result[0].total_score, int)
        self.assertEqual(result[0].avg_sentiment, 0.5)
        self.assertIsInstance(result[0].avg_sentiment, float)

    @patch('storage.Database.logger')
    def test_handles_database_error(self, mock_logger):
        """Test error handling when database query fails"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Database error")

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        with self.assertRaises(Exception):
            fetch_ticker_mentions(mock_pool, 'AAPL', start_date, end_date)

        # Verify error was logged
        mock_logger.error.assert_called_once()
        # Verify cleanup
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)


class TestFetchPopularTickers(TestDatabase):
    """Test suite for fetch_popular_tickers function"""

    def test_fetches_popular_tickers(self):
        """Test fetching popular tickers"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock database response - ordered by total_mentions DESC
        mock_cursor.fetchall.return_value = [
            ('TSLA', 'pennystocks', self.test_timestamp, 50, 20, 500, 100, 0.8),
            ('TSLA', 'wallstreetbets', self.test_timestamp2, 30, 15, 300, 50, 0.7),
            ('AAPL', 'pennystocks', self.test_timestamp, 25, 10, 250, 40, 0.6),
        ]

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_popular_tickers(mock_pool, start_date, end_date, amount=2)

        # Verify connection was retrieved from pool
        mock_pool.getconn.assert_called_once()
        # Verify query was executed
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        self.assertIn('WITH top_tickers AS', call_args[0][0])
        self.assertIn('SUM(mention_count)', call_args[0][0])
        self.assertIn('LIMIT %s', call_args[0][0])

        # Verify parameters
        params = call_args[0][1]
        self.assertEqual(params[0], start_date)
        self.assertEqual(params[1], end_date)
        self.assertEqual(params[2], 2)  # amount
        self.assertEqual(params[3], start_date)
        self.assertEqual(params[4], end_date)

        # Verify results structure
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 2)  # TSLA and AAPL
        self.assertIn('TSLA', result)
        self.assertIn('AAPL', result)

        # Verify TSLA has 2 data points (most popular)
        self.assertEqual(len(result['TSLA']), 2)
        self.assertEqual(result['TSLA'][0].mention_count, 50)
        self.assertEqual(result['TSLA'][1].mention_count, 30)

        # Verify AAPL has 1 data point
        self.assertEqual(len(result['AAPL']), 1)
        self.assertEqual(result['AAPL'][0].mention_count, 25)
        # Verify connection was returned to pool
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_uses_default_amount(self):
        """Test that default amount of 10 is used when not specified"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        fetch_popular_tickers(mock_pool, start_date, end_date)

        # Verify default amount of 10 was used
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[2], 10)  # Default amount

    def test_returns_empty_dict_when_no_results(self):
        """Test that empty dict is returned when no tickers found"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_popular_tickers(mock_pool, start_date, end_date)

        self.assertEqual(len(result), 0)
        self.assertIsInstance(result, dict)

    def test_groups_mentions_by_ticker(self):
        """Test that mentions are properly grouped by ticker"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock multiple mentions for same ticker across different subreddits/times
        mock_cursor.fetchall.return_value = [
            ('AAPL', 'pennystocks', self.test_timestamp, 10, 5, 100, 20, 0.5),
            ('AAPL', 'wallstreetbets', self.test_timestamp, 15, 8, 150, 25, 0.6),
            ('AAPL', 'pennystocks', self.test_timestamp2, 20, 10, 200, 30, 0.7),
        ]

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_popular_tickers(mock_pool, start_date, end_date, amount=1)

        # Should have one ticker with 3 data points
        self.assertEqual(len(result), 1)
        self.assertIn('AAPL', result)
        self.assertEqual(len(result['AAPL']), 3)

    @patch('storage.Database.logger')
    def test_handles_database_error(self, mock_logger):
        """Test error handling when database query fails"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Database error")

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        with self.assertRaises(Exception):
            fetch_popular_tickers(mock_pool, start_date, end_date)

        # Verify error was logged
        mock_logger.error.assert_called_once()
        # Verify cleanup
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

    @patch('storage.Database.logger')
    def test_logs_debug_info(self, mock_logger):
        """Test that debug logging occurs"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        fetch_popular_tickers(mock_pool, start_date, end_date)

        # Verify debug log was called
        mock_logger.debug.assert_called_once()
        self.assertIn('rows', mock_logger.debug.call_args[0][0].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)


from models import Author

class TestAuthorData(TestDatabase):
    """Test suite for author data functions"""

    def test_get_author_data_hit(self):
        """Test getting existing author data"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock DB return
        now = datetime.now(timezone.utc)
        mock_cursor.fetchone.return_value = (
            "test_user", now, 100, 200, now
        )

        from storage.database_manager import get_author_data
        result = get_author_data(mock_pool, "test_user")

        self.assertIsNotNone(result)
        self.assertEqual(result.username, "test_user")
        self.assertEqual(result.comment_karma, 100)
        
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_get_author_data_miss(self):
        """Test getting non-existent author data"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None

        from storage.database_manager import get_author_data
        result = get_author_data(mock_pool, "test_user")

        self.assertIsNone(result)

    def test_upsert_author_data(self):
        """Test upserting author data"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        author = Author(
            username="test_user",
            created_utc=datetime.now(timezone.utc),
            comment_karma=100,
            link_karma=200,
            last_updated=datetime.now(timezone.utc)
        )

        from storage.database_manager import upsert_author_data
        upsert_author_data(mock_pool, author)

        mock_cursor.execute.assert_called_once()
        self.assertIn("INSERT INTO authors", mock_cursor.execute.call_args[0][0])
        mock_conn.commit.assert_called_once()

    def test_get_authors_batch(self):
        """Test batch fetching authors"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        now = datetime.now(timezone.utc)
        mock_cursor.fetchall.return_value = [
            ("user1", now, 10, 20, now),
            ("user2", now, 30, 40, now)
        ]

        from storage.database_manager import get_authors_batch
        results = get_authors_batch(mock_pool, ["user1", "user2"])

        self.assertEqual(len(results), 2)
        self.assertIn("user1", results)
        self.assertIn("user2", results)

    def test_get_existing_post_ids_batch(self):
        """Test batch checking existing posts"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [("post1",), ("post3",)]

        from storage.database_manager import get_existing_post_ids_batch
        results = get_existing_post_ids_batch(mock_pool, ["post1", "post2", "post3"])

        self.assertEqual(len(results), 2)
        self.assertIn("post1", results)
        self.assertIn("post3", results)
        self.assertNotIn("post2", results)
